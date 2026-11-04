"""
Web server. Chalane ke liye:  python app.py   phir browser mein http://localhost:5000
Flow: awaaz -> Prisma -> agent -> Timbre -> awaaz
"""
import base64
import time
import os
from flask import Flask, jsonify, request, send_from_directory, session

import agent
import gnani

app = Flask(__name__)
# Baatcheet ka state (follow-up sawaal) signed cookie mein rehta hai.
# Production mein FLASK_SECRET_KEY set karo, warna har restart par purani baat bhool jaayega
# aur kai gunicorn workers aapas mein state share nahi karenge.
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.urandom(32)


@app.route("/")
def home():
    return send_from_directory(os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates"), "index.html")


def _run(text):
    result = agent.respond(text, session.get("agent_state"))
    session["agent_state"] = result.get("state")
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
    body = request.get_json(silent=True)
    text = body.get("text", "") if isinstance(body, dict) else ""
    if not isinstance(text, str):
        return jsonify({"error": "text string hona chahiye."}), 400
    return jsonify(_run(text))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    print(f"Server chalu. Port: {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
