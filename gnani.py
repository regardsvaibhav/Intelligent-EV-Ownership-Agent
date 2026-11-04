"""
Gnani ke Prisma (awaaz -> text) aur Timbre (text -> awaaz) ko bulane wala code.
API key .env file se padhi jaati hai (GNANI_API_KEY).

Agar Gnani ke docs mein koi naam alag ho (jaise voice ya model), to neeche
SETTINGS wale hisse mein badal do.
"""
import os
import io
import wave
import base64
import time
import struct
import requests
from dotenv import load_dotenv

load_dotenv()

# ---------------- SETTINGS ----------------
STT_URL = "https://api.vachana.ai/stt/v3"
TTS_URL = "https://api.vachana.ai/api/v1/tts/inference"
STT_LANGUAGE = "hi-IN"        # Hinglish ke liye Hindi sahi chalta hai
TTS_VOICE = "Nalini"
TTS_MODEL = "timbre-v2.5"
TTS_SAMPLE_RATE = 48000
TIMEOUT_SEC = 60
# ------------------------------------------


class GnaniError(Exception):
    pass


# .env.example / purane README ke placeholder: inhe asli key mat samjho
_PLACEHOLDER_KEYS = {"PASTE_YOUR_API_KEY_HERE", "replace_with_your_gnani_api_key"}


def _api_key():
    key = os.getenv("GNANI_API_KEY", "").strip()
    if not key or key in _PLACEHOLDER_KEYS:
        raise GnaniError(
            "API key nahi mili. .env file kholo aur GNANI_API_KEY mein apni asli Gnani API key daalo."
        )
    return key


def _find_text(obj):
    """Prisma ke jawab (JSON) mein se transcript dhundta hai."""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        for k in ("transcript", "transcription", "text", "result", "output"):
            if k in obj:
                found = _find_text(obj[k])
                if found:
                    return found
        for v in obj.values():
            found = _find_text(v)
            if found:
                return found
    if isinstance(obj, list):
        parts = [_find_text(x) for x in obj]
        parts = [p for p in parts if p]
        if parts:
            return " ".join(parts)
    return ""


def transcribe(wav_bytes, filename="audio.wav"):
    """Prisma: WAV audio bytes -> text."""
    key = _api_key()
    try:
        resp = _post_with_retry(
            STT_URL,
            headers={"X-API-Key-ID": key},
            files={"audio_file": (filename, wav_bytes, "audio/wav")},
            data={"language_code": STT_LANGUAGE},
            timeout=TIMEOUT_SEC,
        )
    except requests.RequestException as e:
        raise GnaniError(f"Prisma se connect nahi ho paya: {e}")
    if resp.status_code != 200:
        raise GnaniError(f"Prisma error {resp.status_code}: {resp.text[:300]}")
    try:
        data = resp.json()
    except ValueError:
        return resp.text.strip()
    return _find_text(data).strip()


def _pcm_to_wav(pcm_bytes, sample_rate):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm_bytes)
    return buf.getvalue()

def _normalize_wav(audio):
    """Timbre sends a WAV with a placeholder length. Rebuild it with the real one."""
    if not audio.startswith(b"RIFF"):
        return _pcm_to_wav(audio, TTS_SAMPLE_RATE)
    fmt_i = audio.find(b"fmt ")
    data_i = audio.find(b"data")
    if fmt_i < 0 or data_i < 0:
        return audio
    channels, rate = struct.unpack("<HI", audio[fmt_i + 10: fmt_i + 16])
    bits = struct.unpack("<H", audio[fmt_i + 22: fmt_i + 24])[0]
    width = max(1, bits // 8)
    pcm = audio[data_i + 8:]
    pcm = pcm[: len(pcm) - (len(pcm) % (width * channels))]
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def _extract_audio(resp):
    """Timbre ke jawab se audio bytes nikalta hai (seedha audio ya JSON mein base64)."""
    ctype = resp.headers.get("Content-Type", "")
    if "json" in ctype:
        try:
            data = resp.json()
        except ValueError:
            raise GnaniError(f"Timbre ka jawab JSON nahi hai: {resp.text[:300]}")
        b64 = None
        if isinstance(data, dict):
            for k in ("audio", "audio_content", "audio_base64", "data"):
                if isinstance(data.get(k), str):
                    b64 = data[k]
                    break
        if not b64:
            raise GnaniError(f"Timbre ke jawab mein audio nahi mila: {str(data)[:300]}")
        return base64.b64decode(b64)
    return resp.content


RETRY_STATUS = {429, 502, 503, 504}


def _post_with_retry(*args, retries=3, **kwargs):
    """
    requests.post, lekin 429/502/503/504 ya connection toot-ne par 3 baar tak koshish.
    Timeout par dobara nahi bhejte: driver pehle hi TIMEOUT_SEC intezaar kar chuka hai.
    """
    last = None
    for i in range(retries):
        try:
            resp = requests.post(*args, **kwargs)
        except requests.Timeout:
            raise
        except requests.ConnectionError as e:
            last = e
        else:
            if resp.status_code not in RETRY_STATUS:
                return resp
            last = resp
        if i < retries - 1:
            time.sleep(1.5 * (i + 1))
    if isinstance(last, requests.Response):
        return last
    raise last


def synthesize(text):
    """Timbre: text -> WAV audio bytes."""
    key = _api_key()
    headers = {"Content-Type": "application/json", "X-API-Key-ID": key}
    body = {
        "text": text,
        "voice": TTS_VOICE,
        "model": TTS_MODEL,
        "language": "hi-IN",
        "audio_config": {
            "sample_rate": TTS_SAMPLE_RATE,
            "num_channels": 1,
            "sample_width": 2,
            "encoding": "linear_pcm",
            "container": "wav",
        },
    }
    try:
        resp = _post_with_retry(TTS_URL, headers=headers, json=body, timeout=TIMEOUT_SEC)
    except requests.RequestException as e:
        raise GnaniError(f"Timbre se connect nahi ho paya: {e}")
    if resp.status_code != 200:
        raise GnaniError(f"Timbre error {resp.status_code}: {resp.text[:300]}")


    return _normalize_wav(_extract_audio(resp))