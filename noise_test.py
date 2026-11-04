"""
NOISE TEST: saaf awaaz vs. traffic-horn wali awaaz par Prisma kitna sahi sunta hai.

Kaise chalana hai (README.md mein bhi likha hai):
1. test_clips/ folder mein apni recordings (.wav) daalo, jaise clip1.wav, clip2.wav ...
2. Pehli baar chalao:  python noise_test.py
   - Jin clips ka .txt nahi hoga, unka saaf-awaaz transcript clip1.txt mein likh diya jaayega.
3. Har .txt kholo, galti ho to sahi shabd (Devanagari mein) likh do. Yahi "sahi jawab" maana jaayega.
4. Dobara chalao:  python noise_test.py   -> results.csv aur noisy_clips/ folder banega.
5. Agent badalne ke baad (bina API key ke bhi):  python noise_test.py --rescore
   -> purane results.csv ke transcripts naye agent se score hote hain (results_rescored.csv).

Har clip ke 6 roop test hote hain:
  clean, 10dB, 0dB                 -> mic par shor (traffic + horn)
  phone, phone_10dB, phone_0dB     -> wahi, phir phone line jaisa (300-3400 Hz, 8 kHz)
Har roop par 3 cheezein naapi jaati hain:
  WER            -> kitne shabd galat sune (kam = behtar)
  intent sahi    -> agent ne wahi kaam samjha jo saaf transcript par samajhta (zyada = behtar)
  number sahi    -> charge % wahi nikla ya nahi (sirf un clips par jinmein % bola gaya)
"""
import os
import re
import sys
import io
import csv
import wave
import glob
import numpy as np

import agent
import gnani

CLIPS_DIR = "test_clips"
NOISY_DIR = "noisy_clips"
SNR_LEVELS_DB = [10, 0]      # 10 dB = halka shor, 0 dB = shor awaaz jitna tez
SEED = 7
PHONE_SR = 8000              # phone line ka sample rate
PHONE_BAND_HZ = (300, 3400)  # phone line sirf itni frequency aage bhejti hai


def read_wav(path):
    with wave.open(path, "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError(f"{path}: sirf 16-bit WAV chalta hai.")
        sr, ch = w.getframerate(), w.getnchannels()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    return data, sr


def to_wav_bytes(samples, sr):
    samples = np.clip(samples, -1, 1)
    pcm = (samples * 32767).astype(np.int16).tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)
    return buf.getvalue()


def traffic_noise(n, sr, rng):
    """Nakli traffic shor: engine ki gunj + hawa jaisa shor + beech-beech mein horn."""
    t = np.arange(n) / sr
    rumble = np.cumsum(rng.standard_normal(n))
    rumble -= np.convolve(rumble, np.ones(2000) / 2000, mode="same")
    rumble /= (np.std(rumble) + 1e-9)
    engine = np.sin(2 * np.pi * 80 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.7 * t))
    hiss = rng.standard_normal(n) * 0.35
    horns = np.zeros(n)
    pos = int(rng.uniform(0.2, 0.8) * sr)
    while pos < n:
        dur = int(rng.uniform(0.3, 0.8) * sr)
        f = rng.choice([420.0, 510.0, 650.0])
        seg_t = np.arange(min(dur, n - pos)) / sr
        tone = sum(np.sin(2 * np.pi * f * k * seg_t) / k for k in (1, 2, 3))
        horns[pos:pos + len(seg_t)] += tone * np.hanning(len(seg_t))
        pos += dur + int(rng.uniform(0.8, 2.0) * sr)
    noise = rumble * 0.8 + engine + hiss + horns * 1.2
    return noise / (np.std(noise) + 1e-9)


def add_noise(signal, sr, snr_db, rng):
    noise = traffic_noise(len(signal), sr, rng)
    sig_power = np.mean(signal ** 2) + 1e-12
    noise_power = sig_power / (10 ** (snr_db / 10))
    noise = noise * np.sqrt(noise_power)
    mixed = signal + noise
    peak = np.max(np.abs(mixed))
    return mixed / peak * 0.95 if peak > 0.95 else mixed


def telephony(signal, sr):
    """Awaaz ko phone line jaisa banata hai: 300-3400 Hz band, phir 8 kHz par resample."""
    spec = np.fft.rfft(signal)
    freqs = np.fft.rfftfreq(len(signal), 1 / sr)
    spec[(freqs < PHONE_BAND_HZ[0]) | (freqs > PHONE_BAND_HZ[1])] = 0
    band = np.fft.irfft(spec, n=len(signal))
    n_out = int(len(band) * PHONE_SR / sr)
    t_in = np.arange(len(band)) / sr
    t_out = np.arange(n_out) / PHONE_SR
    return np.interp(t_out, t_in, band).astype(np.float32), PHONE_SR


def understand(text):
    """
    Agent is text se kya samjha: (intent, charge %).
    Har clip ko NAYA Session milta hai, taaki ek clip ki yaad doosri par asar na kare.
    """
    r = agent.step(agent.Session(), text, log=False)
    return r["intent"], agent.extract_percent(text)


def has_api_key():
    try:
        gnani._api_key()
        return True
    except gnani.GnaniError:
        return False


def print_summary(rows):
    print("\n===== SUMMARY =====")
    print(f"{'condition':11s} {'avg WER':>8s} {'intent sahi':>12s} {'number sahi':>12s}")
    labels = list(dict.fromkeys(r["condition"] for r in rows))
    for label in labels:
        sub = [r for r in rows if r["condition"] == label]
        avg_wer = sum(float(r["wer_percent"]) for r in sub) / len(sub)
        intent_acc = 100 * sum(r["intent_ok"] in (True, "True") for r in sub) / len(sub)
        nums = [r["number_ok"] in (True, "True") for r in sub if r["number_ok"] not in ("", None)]
        num_txt = f"{100 * sum(nums) / len(nums):5.1f}%" if nums else "  -  "
        print(f"{label:11s} {avg_wer:7.1f}% {intent_acc:11.1f}% {num_txt:>12s}   ({len(sub)} clips)")


def rescore_transcripts(csv_path="results.csv", out_path="results_rescored.csv"):
    """
    Audio/API ke bina chalne wala mode: pichhle audio run ke transcripts (results.csv)
    ko naye agent se dobara score karta hai. Agent badalne ke baad yahi chalao.
    """
    if not os.path.exists(csv_path):
        print(f"'{csv_path}' nahi mili. Pehle API key ke saath ek audio run karo.")
        return []
    with open(csv_path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        ref_intent, ref_num = understand(r["reference"])
        hyp_intent, hyp_num = understand(r["hypothesis"])
        r.update(ref_intent=ref_intent, hyp_intent=hyp_intent, intent_ok=hyp_intent == ref_intent,
                 ref_percent="" if ref_num is None else ref_num, hyp_percent="" if hyp_num is None else hyp_num,
                 number_ok="" if ref_num is None else hyp_num == ref_num)
    if rows:
        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"{len(rows)} transcripts naye agent se dobara score kiye -> {out_path}")
        print_summary(rows)
    return rows


def normalize_text(s):
    s = s.lower()
    s = re.sub(r"[।\.,\?\!\-\"'’‘:;()]", " ", s)
    return s.split()


def wer(reference, hypothesis):
    r, h = normalize_text(reference), normalize_text(hypothesis)
    if not r:
        return 0.0 if not h else 1.0
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = d[j]
            d[j] = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev = cur
    return d[len(h)] / len(r)


def main():
    if "--rescore" in sys.argv:
        rescore_transcripts()
        return
    if not has_api_key():
        print("GNANI_API_KEY nahi mili (.env dekho) - audio test skip kar rahe hain.")
        print("Purane results.csv ke transcripts naye agent se score karne ke liye: python noise_test.py --rescore")
        if os.path.exists("results.csv"):
            rescore_transcripts()
        return
    os.makedirs(CLIPS_DIR, exist_ok=True)
    os.makedirs(NOISY_DIR, exist_ok=True)
    clips = sorted(glob.glob(os.path.join(CLIPS_DIR, "*.wav")))
    if not clips:
        print(f"'{CLIPS_DIR}' folder mein koi .wav nahi mili. Pehle apni recordings wahan daalo.")
        return
    rng = np.random.default_rng(SEED)

    # Step A: jin clips ka reference text nahi hai, unka bana do
    missing = []
    for path in clips:
        ref_path = os.path.splitext(path)[0] + ".txt"
        if not os.path.exists(ref_path):
            samples, sr = read_wav(path)
            text = gnani.transcribe(to_wav_bytes(samples, sr))
            with open(ref_path, "w", encoding="utf-8") as f:
                f.write(text)
            missing.append(ref_path)
    if missing:
        print("Ye .txt files abhi bani hain (saaf awaaz ka transcript):")
        for m in missing:
            print("  ", m)
        print("\nIN FILES KO KHOLO, GALTI HO TO THEEK KARO, SAVE KARO, phir ye command dobara chalao.")
        return

    # Step B: clean aur noisy dono ka WER
    rows = []
    for path in clips:
        name = os.path.splitext(os.path.basename(path))[0]
        with open(os.path.splitext(path)[0] + ".txt", encoding="utf-8") as f:
            reference = f.read().strip()
        samples, sr = read_wav(path)

        ref_intent, ref_num = understand(reference)

        variants = [("clean", samples, sr)]
        for snr in SNR_LEVELS_DB:
            noisy = add_noise(samples, sr, snr, rng)
            with open(os.path.join(NOISY_DIR, f"{name}_snr{snr}dB.wav"), "wb") as f:
                f.write(to_wav_bytes(noisy, sr))
            variants.append((f"{snr}dB", noisy, sr))
        # Phone line: pehle mic par shor, phir phone ki patli line (asli call jaisa kram)
        phone, psr = telephony(samples, sr)
        with open(os.path.join(NOISY_DIR, f"{name}_phone.wav"), "wb") as f:
            f.write(to_wav_bytes(phone, psr))
        variants.append(("phone", phone, psr))
        for snr in SNR_LEVELS_DB:
            noisy_phone, psr = telephony(add_noise(samples, sr, snr, rng), sr)
            with open(os.path.join(NOISY_DIR, f"{name}_phone_snr{snr}dB.wav"), "wb") as f:
                f.write(to_wav_bytes(noisy_phone, psr))
            variants.append((f"phone_{snr}dB", noisy_phone, psr))

        for label, audio, rate in variants:
            try:
                hyp = gnani.transcribe(to_wav_bytes(audio, rate))
                err = ""
            except gnani.GnaniError as e:
                hyp, err = "", str(e)[:200]
            score = wer(reference, hyp)
            hyp_intent, hyp_num = understand(hyp)
            intent_ok = hyp_intent == ref_intent
            number_ok = "" if ref_num is None else (hyp_num == ref_num)
            rows.append({"clip": name, "condition": label, "sample_rate": rate,
                         "reference": reference, "hypothesis": hyp,
                         "wer_percent": round(score * 100, 1),
                         "ref_intent": ref_intent, "hyp_intent": hyp_intent, "intent_ok": intent_ok,
                         "ref_percent": "" if ref_num is None else ref_num,
                         "hyp_percent": "" if hyp_num is None else hyp_num, "number_ok": number_ok,
                         "error": err})
            flag = "OK " if intent_ok else "BAD"
            print(f"{name:12s} {label:11s} WER {score*100:5.1f}%  intent {flag}  -> {hyp or '[ERROR] ' + err}")

    with open("results.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print_summary(rows)
    errors = sum(1 for r in rows if r["error"])
    if errors:
        print(f"\nDhyan do: {errors} transcription fail hui (error column dekho). "
              "Agar sirf phone wale fail hue, to shayad Prisma 8 kHz WAV nahi le raha.")
    print("\nPoora result results.csv mein hai. Shor wali awaazein noisy_clips/ folder mein hain.")


if __name__ == "__main__":
    try:
        main()
    except gnani.GnaniError as e:
        print("ERROR:", e)
