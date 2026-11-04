"""
Web server. Chalane ke liye:  python app.py   phir browser mein http://localhost:5000
Flow: awaaz -> Prisma -> agent -> Timbre -> awaaz
"""
import base64
import collections
import re
import threading
import time
import os
from flask import Flask, jsonify, request, send_from_directory

import agent
import gnani
import llm_fallback
import ui_view

# Free LLM (Gemini) sirf tab bulaya jaata hai jab rules kuch nahi samajh paate. LLM_API_KEY na ho to band.
if llm_fallback.enabled():
    agent.register_fallback_classifier(llm_fallback.classify)

app = Flask(__name__)
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)
# 15 second ki 16 kHz WAV ~0.5 MB hoti hai. Isse badi upload memory mein padhne se pehle hi 413.
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_UPLOAD_MB", "5")) * 1024 * 1024

# Har request Gnani ki paid API bulati hai. Ek IP se ek minute mein itni hi requests (0 = band).
# Note: proxy (nginx, Render, etc.) ke peeche sab ka IP ek dikh sakta hai; tab ProxyFix lagao.
RATE_LIMIT_PER_MIN = int(os.environ.get("RATE_LIMIT_PER_MIN", "30"))
_hits = collections.defaultdict(collections.deque)

# ---- Multi-turn memory: har browser tab (session_id) ki alag baatcheet ----
# Note: ye memory server process ke andar hai. gunicorn mein ek hi worker chalao
# (gunicorn -w 1 app:app), warna alag worker alag yaad rakhenge.
SESSIONS = {}                 # session_id -> (agent.Session, last_seen)
SESSION_TTL_SEC = 30 * 60     # 30 minute chup = baatcheet khatam
MAX_SESSIONS = int(os.environ.get("MAX_SESSIONS", "2000"))   # naye random session_id se memory na bhare
_lock = threading.Lock()
_SID_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def _get_state(session_id):
    now = time.time()
    with _lock:
        for sid in [k for k, (_, ts) in SESSIONS.items() if now - ts > SESSION_TTL_SEC]:
            del SESSIONS[sid]
        if not session_id or not _SID_RE.match(session_id):
            return agent.Session()            # bina session_id ke: koi yaad nahi (purana behaviour)
        if session_id not in SESSIONS and len(SESSIONS) >= MAX_SESSIONS:
            oldest = min(SESSIONS, key=lambda k: SESSIONS[k][1])
            del SESSIONS[oldest]
        state = SESSIONS.get(session_id, (agent.Session(), now))[0]
        SESSIONS[session_id] = (state, now)
        return state


def _rate_limited():
    if RATE_LIMIT_PER_MIN <= 0:
        return False
    now = time.time()
    with _lock:
        for ip in [k for k, q in _hits.items() if not q or now - q[-1] > 60]:
            del _hits[ip]
        q = _hits[request.remote_addr or "?"]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= RATE_LIMIT_PER_MIN:
            return True
        q.append(now)
        return False


@app.before_request
def _limit():
    if request.path.startswith("/api/") and request.path != "/api/reset" and _rate_limited():
        return jsonify({"error": "Bahut zyada sawaal. Ek minute baad phir poochhiye."}), 429


@app.errorhandler(413)
def _too_big(_e):
    return jsonify({"error": "Audio file bahut badi hai."}), 413


def _json_body():
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


@app.route("/")
def home():
    return send_from_directory(os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates"), "index.html")


def _run(text, session_id=None, source="text"):
    session = _get_state(session_id)
    result = agent.step(session, text, source)
    out = {"transcript": text, "intent": result["intent"], "reply": result["reply"],
           "score": result["score"], "needs_confirm": result["needs_confirm"],
           "memory": ui_view.memory(session),            # chips on the page
           "view": ui_view.build_view(result, session)}  # card on the page
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
    out = _run(text, request.form.get("session_id"), source="voice")
    out["stt_seconds"] = stt_seconds
    return jsonify(out)


@app.route("/api/text", methods=["POST"])
def text_chat():
    body = _json_body()
    text, sid = body.get("text", ""), body.get("session_id")
    if not isinstance(text, str) or not (sid is None or isinstance(sid, str)):
        return jsonify({"error": "text aur session_id string hone chahiye."}), 400
    return jsonify(_run(text, sid, source="text"))


@app.route("/api/reset", methods=["POST"])
def reset():
    sid = _json_body().get("session_id")
    if not isinstance(sid, str):
        return jsonify({"ok": True})
    with _lock:
        SESSIONS.pop(sid, None)
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    print(f"Server chalu. Port: {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
