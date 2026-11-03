"""Live smoke test for Gnani Prisma (STT) and Timbre (TTS). Run: python smoke_test.py [your_voice.wav]"""
import sys, time, wave, requests
import gnani

TEXT = "नमस्ते भैया, साठ प्रतिशत चार्ज है, करीब चौवन किलोमीटर चलेगा।"

def wav_info(path):
    try:
        with wave.open(path) as w:
            return f"{w.getframerate()} Hz, {w.getnchannels()} ch, {w.getnframes()/w.getframerate():.1f}s"
    except Exception as e:
        return f"not a readable WAV ({e})"

def probe_tts_minimal():
    """If the full body fails, try the minimal body from the docs to isolate audio_config."""
    key = gnani._api_key()
    r = requests.post(
        gnani.TTS_URL,
        headers={"Content-Type": "application/json", "X-API-Key-ID": key},
        json={"text": TEXT, "voice": gnani.TTS_VOICE, "model": gnani.TTS_MODEL},
        timeout=60,
    )
    print("Minimal TTS body ->", r.status_code, r.headers.get("Content-Type"), len(r.content), "bytes")
    if r.status_code != 200:
        print(r.text[:400])

def main():
    # 1) TTS
    t = time.time()
    try:
        audio = gnani.synthesize(TEXT)
    except gnani.GnaniError as e:
        print("TTS FAILED:", e)
        probe_tts_minimal()
        return
    print(f"TTS ok in {time.time()-t:.2f}s, {len(audio)} bytes")
    with open("smoke_tts.wav", "wb") as f:
        f.write(audio)
    print("Output audio:", wav_info("smoke_tts.wav"))

    # 2) STT round trip (connectivity check only, not robustness evidence)
    t = time.time()
    try:
        text = gnani.transcribe(audio, "smoke_tts.wav")
        print(f"STT ok in {time.time()-t:.2f}s -> {text!r}")
    except gnani.GnaniError as e:
        print("STT FAILED:", e)

    # 3) STT on a real recording
    if len(sys.argv) > 1:
        path = sys.argv[1]
        print("Input audio:", wav_info(path))
        with open(path, "rb") as f:
            data = f.read()
        t = time.time()
        try:
            print(f"Real voice -> {gnani.transcribe(data, path)!r} ({time.time()-t:.2f}s)")
        except gnani.GnaniError as e:
            print("STT FAILED on real audio:", e)

if __name__ == "__main__":
    main()