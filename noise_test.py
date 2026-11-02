"""
NOISE TEST: saaf awaaz vs. traffic-horn wali awaaz par Prisma kitna sahi sunta hai.

Kaise chalana hai (README.txt mein bhi likha hai):
1. test_clips/ folder mein apni recordings (.wav) daalo, jaise clip1.wav, clip2.wav ...
2. Pehli baar chalao:  python noise_test.py
   - Jin clips ka .txt nahi hoga, unka saaf-awaaz transcript clip1.txt mein likh diya jaayega.
3. Har .txt kholo, galti ho to sahi shabd (Devanagari mein) likh do. Yahi "sahi jawab" maana jaayega.
4. Dobara chalao:  python noise_test.py   -> results.csv aur noisy_clips/ folder banega.
"""
import os
import re
import io
import csv
import wave
import glob
import numpy as np

import gnani

CLIPS_DIR = "test_clips"
NOISY_DIR = "noisy_clips"
SNR_LEVELS_DB = [10, 0]      # 10 dB = halka shor, 0 dB = shor awaaz jitna tez
SEED = 7


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

        variants = [("clean", samples)]
        for snr in SNR_LEVELS_DB:
            noisy = add_noise(samples, sr, snr, rng)
            with open(os.path.join(NOISY_DIR, f"{name}_snr{snr}dB.wav"), "wb") as f:
                f.write(to_wav_bytes(noisy, sr))
            variants.append((f"{snr}dB", noisy))

        for label, audio in variants:
            hyp = gnani.transcribe(to_wav_bytes(audio, sr))
            score = wer(reference, hyp)
            rows.append({"clip": name, "condition": label, "reference": reference,
                         "hypothesis": hyp, "wer_percent": round(score * 100, 1)})
            print(f"{name:12s} {label:6s} WER {score*100:5.1f}%   -> {hyp}")

    with open("results.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print("\n===== SUMMARY (average WER, kam = behtar) =====")
    for label in ["clean"] + [f"{s}dB" for s in SNR_LEVELS_DB]:
        vals = [r["wer_percent"] for r in rows if r["condition"] == label]
        print(f"{label:6s}: {sum(vals)/len(vals):5.1f}%   ({len(vals)} clips)")
    print("\nPoora result results.csv mein hai. Shor wali awaazein noisy_clips/ folder mein hain.")


if __name__ == "__main__":
    try:
        main()
    except gnani.GnaniError as e:
        print("ERROR:", e)
