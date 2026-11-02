"""
Web server. Chalane ke liye:  python app.py   phir browser mein http://localhost:5000
Flow: awaaz -> Prisma -> agent -> Timbre -> awaaz
"""
import base64
import time
import os
from flask import Flask, jsonify, request, send_from_directory

import agent
import gnani

app = Flask(__name__)


@app.route("/")
def home():
    return send_from_directory(os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates"), "index.html")


def _run(text):
    result = agent.respond(text)
    out = {"transcript": text, "intent": result["intent"], "reply": result["reply"]}
    t0 = time.time()
    try:
        audio = gnani.synthesize(result["reply"])
        out["audio_b64"] = base64.b64encode(audio).decode()
        out["tts_seconds"] = round(time.time() - t0, 2)
    except gnani.GnaniError as e:
        out["tts_error"] = str(e)
    return out


@app.route("/api/voice", methods=["POST"])
def voice():
    f = request.files.get("audio")
    if not f:
        return jsonify({"error": "Audio nahi mila."}), 400
    t0 = time.time()
    try:
        text = gnani.transcribe(f.read())
    except gnani.GnaniError as e:
        return jsonify({"error": str(e)}), 502
    stt_seconds = round(time.time() - t0, 2)
    out = _run(text)
    out["stt_seconds"] = stt_seconds
    return jsonify(out)


@app.route("/api/text", methods=["POST"])
def text_chat():
    text = (request.get_json(silent=True) or {}).get("text", "")
    return jsonify(_run(text))


if __name__ == "__main__":
    print("Server chalu. Browser mein kholo: http://localhost:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)
