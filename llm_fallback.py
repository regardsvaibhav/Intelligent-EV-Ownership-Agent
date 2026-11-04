"""
LLM fallback using a FREE LLM API. Used ONLY when the rule engine understands nothing
(the "माफ़ कीजिए, समझ नहीं पाया" path). Common questions never reach it, so they stay
fast, free and deterministic.

Works with any OpenAI-compatible chat API. Default: Google Gemini (free tier from
https://aistudio.google.com/apikey). Groq or OpenRouter also work: set LLM_BASE_URL
and LLM_MODEL (see README, "LLM fallback").

The LLM does one of three things with the driver's sentence:
  1. Maps it to an intent the agent already has (range, trip, stations, ...), plus any
     percent / km / city it heard. The agent's own tools then compute the answer, so
     every number the driver hears still comes from tools.py, never from the LLM.
  2. For other EV-ownership questions (battery care, rain, servicing, ...), writes a
     short spoken Hindi answer with no invented numbers or prices.
  3. Says "other" for anything off-topic; the agent then gives its normal fallback.

Turned on only when LLM_API_KEY (or GEMINI_API_KEY) is set and LLM_FALLBACK is not "0".
Any error or timeout returns None, so the driver just gets the normal fallback.
"""
import json
import logging
import os
import re

import requests

log = logging.getLogger(__name__)

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
BASE_URL = os.environ.get("LLM_BASE_URL", GEMINI_BASE_URL).rstrip("/") + "/"
MODEL = os.environ.get("LLM_MODEL", "gemini-3.8-flash")
# Gemini thinks by default; "low" keeps it quick. Other providers: only sent if you set it.
REASONING_EFFORT = os.environ.get("LLM_REASONING_EFFORT", "low" if BASE_URL == GEMINI_BASE_URL else "")
TIMEOUT_SEC = float(os.environ.get("LLM_TIMEOUT_SEC", "8"))   # a driver is waiting on a voice reply
MAX_ANSWER_CHARS = 300

# Intents the agent can run itself. Keep in sync with agent.TOOLS / TROUBLE_INTENT_FLOW.
ROUTABLE_INTENTS = [
    "range", "charge_time_cost", "trip", "stations", "savings",
    "trouble_slow_charging", "trouble_range_drop", "trouble_not_detecting",
    "greeting", "safety",
]
CITIES = ["jaipur", "bhopal", "udaipur", "bharatpur", "indore"]

SYSTEM_PROMPT = f"""You are the understanding step of a Hindi voice assistant for Indian e-rickshaw drivers.
The driver's sentence comes from speech-to-text, so it may be Hinglish, Devanagari, or misspelt.
A rule-based parser could not understand it. Decide what the driver wants.

Reply with ONLY a JSON object, no other text:
{{"intent": "...", "percent": null, "km": null, "city": null, "answer": null}}

"intent" is exactly one of:
- range: how far the vehicle will go on the current charge.
- charge_time_cost: how long a charge takes or what it costs.
- trip: whether the battery is enough to reach a place or travel some km.
- stations: where to charge / charging points in a city.
- savings: money saved versus petrol / CNG for km driven.
- trouble_slow_charging: complaint that charging is slow.
- trouble_range_drop: complaint that the vehicle now goes less distance than before.
- trouble_not_detecting: the charger does not start, connect or show a light.
- greeting: hello / namaste with no question.
- safety: smoke, sparks, burning smell, heat, swelling battery, electric shock, fire, water inside the battery.
- general_ev: any other question about owning, driving, charging or maintaining an electric rickshaw.
- other: anything unrelated to the vehicle.

"percent" (battery charge 0-100, integer), "km" (distance, number) and "city" (one of {", ".join(CITIES)}):
fill them only when the driver clearly said them, otherwise null.

"answer" is used only for general_ev, otherwise null. Write it in simple spoken Hindi (Devanagari),
at most two short sentences, the way a helpful mechanic would say it to a driver.
Do not state prices, battery specifications, distances or other numbers. Do not name brands.
If the problem could be dangerous or needs a repair, tell them to show it to a mechanic.
If you are not sure of the answer, say so briefly and suggest asking a mechanic."""


def _api_key():
    return (os.environ.get("LLM_API_KEY") or os.environ.get("GEMINI_API_KEY") or "").strip()


def enabled():
    return bool(_api_key()) and os.environ.get("LLM_FALLBACK", "1") != "0"


def _post(body):
    return requests.post(
        BASE_URL + "chat/completions",
        headers={"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"},
        json=body,
        timeout=TIMEOUT_SEC,
    )


def _call_llm(text):
    body = {
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": text}],
        "response_format": {"type": "json_object"},
        "max_tokens": 1024,
    }
    if REASONING_EFFORT:
        body["reasoning_effort"] = REASONING_EFFORT
    resp = _post(body)
    if resp.status_code == 400:
        # Some free models don't support JSON mode / reasoning_effort: retry once without them.
        plain = {k: v for k, v in body.items() if k not in ("response_format", "reasoning_effort")}
        resp = _post(plain)
    if resp.status_code != 200:
        raise RuntimeError(f"LLM HTTP {resp.status_code}: {resp.text[:200]}")
    choice = resp.json()["choices"][0]
    if choice.get("finish_reason") == "length":
        return None
    return _parse_json(choice["message"].get("content") or "")


def _parse_json(content):
    """JSON object from the model's text, also when wrapped in ```json fences or extra words."""
    content = content.strip()
    try:
        return json.loads(content)
    except ValueError:
        m = re.search(r"\{.*\}", content, re.S)
        return json.loads(m.group(0)) if m else None


def _clean(data):
    """Validate the LLM's JSON before the agent acts on it."""
    if not isinstance(data, dict):
        return None
    intent = data.get("intent")
    if intent not in ROUTABLE_INTENTS + ["general_ev"]:
        return None
    out = {"intent": intent, "percent": None, "km": None, "city": None, "answer": None}
    p = data.get("percent")
    if isinstance(p, int) and not isinstance(p, bool) and 0 <= p <= 100:
        out["percent"] = p
    km = data.get("km")
    if isinstance(km, (int, float)) and not isinstance(km, bool) and 0 < km <= 500:
        out["km"] = float(km)
    city = data.get("city")
    if isinstance(city, str) and city.lower() in CITIES:
        out["city"] = city.lower()
    if intent == "general_ev":
        answer = data.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            return None
        out["answer"] = answer.strip()[:MAX_ANSWER_CHARS]
    return out


def classify(text):
    """
    text -> {"intent", "percent", "km", "city", "answer"} or None.
    Never raises: the voice reply must not fail because the LLM did.
    """
    if not text or not text.strip():
        return None
    try:
        return _clean(_call_llm(text.strip()[:500]))
    except Exception as e:          # network, auth, rate limit, bad JSON...
        log.warning("LLM fallback failed: %s", e)
        return None
