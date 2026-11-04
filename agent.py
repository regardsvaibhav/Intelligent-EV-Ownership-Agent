"""
E-rickshaw voice assistant: a stateful, tool-using dialog agent with rule-based NLU.

Pipeline for every turn (step()):
    normalize -> safety check -> slot extraction -> intent scoring
    -> dialog manager (pending slots, confirmations, follow-ups) -> tool -> short Hindi reply

No LLM, no network calls: everything here is deterministic and unit-testable.
Speech-to-text and text-to-speech happen outside this module (gnani.py / app.py).

Public API
    Session                      per-conversation state
    step(session, text, source)  -> {"intent","reply","score","margin","slots","tool","needs_confirm", ...}
    respond(text, session=None, source="text")  backward-compatible wrapper
    reset()                      clears the module-level default session
"""
import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Callable

import config
import tools
from config import DEFAULT_CONFIG
from nlu import (Slots, compile_patterns, extract_slots, find_phrase, has_any, normalize, tokens_of)
from nlu import extract_percent as _nlu_extract_percent
from stations import CITY_HINDI, STATIONS


# --------------------------------------------------------------------------
# Session state
# --------------------------------------------------------------------------
@dataclass
class Session:
    percent: int | None = None
    city: str | None = None
    km: float | None = None              # distance of a planned trip
    passengers: int | None = None
    pending: str | None = None           # what the agent is waiting for (slot name or dialog act)
    last_intent: str | None = None
    trouble_flow: str | None = None
    trouble_step: int = 0
    history: list = field(default_factory=list)
    # extra state (beyond the minimal spec)
    km_driven: float | None = None       # km driven today (savings) - kept apart from trip km on purpose
    trip_origin: str | None = None
    trip_dest: str | None = None
    range_before: float | None = None
    range_after: float | None = None
    pending_percent: int | None = None   # low-confidence value waiting for "हां/नहीं"
    pending_intents: list = field(default_factory=list)   # what to run once the pending slot is filled
    clarify_options: list = field(default_factory=list)
    offer_flow: str | None = None
    failures: int = 0                    # consecutive empty / not-understood turns
    turn: int = 0


# --------------------------------------------------------------------------
# Intent patterns (weighted). Tokens are normalized at load time; '*' = prefix.
# --------------------------------------------------------------------------
_RAW_PATTERNS = {
    "trouble_not_detecting": [
        ("detect", 1.5), ("pakad nahi", 1.5), ("nahi pakad*", 1.5), ("charger nahi", 1.2), ("charging nahi", 1.5),
        ("charge nahi ho*", 1.5), ("charge nahi", 1.0), ("charge hi nahi", 1.5), ("light nahi", 1.5),
        ("light hi nahi", 1.5), ("led nahi", 1.5), ("connect nahi", 1.5), ("start nahi", 1.2), ("chalu nahi", 1.2),
        ("connect नहीं", 1.5), ("charge नहीं", 1.2), ("charger नहीं", 1.2), ("नहीं पकड*", 1.5),
        ("light नहीं", 1.5), ("charging नहीं", 1.5), ("charging शुरू ही नहीं", 1.5), ("शुरू नहीं", 1.2),
        ("शुरू ही नहीं", 1.2), ("चालू नहीं", 1.2), ("charge नहीं हो*", 1.5), ("charge ही नहीं", 1.5),
    ],
    "trouble_slow_charging": [
        ("slow", 1.0), ("dheere", 1.0), ("dhire", 1.0), ("dhima", 1.0), ("dheema", 1.0), ("dhimi", 1.0),
        ("dheemi", 1.0), ("धीमा", 1.0), ("धीमी", 1.0), ("धीरे", 1.0), ("der lag*", 1.0), ("bahut der", 1.0),
        ("bahut time", 0.8), ("बहुत देर", 1.0), ("बहुत time", 0.8), ("देर लग*", 1.0),
    ],
    "trouble_range_drop": [
        ("range kam", 1.5), ("range ghat*", 1.5), ("kam chal*", 1.2), ("mileage", 1.2), ("average kam", 1.5),
        ("range कम", 1.5), ("range घट*", 1.5), ("कम चल*", 1.2), ("ज्यादा नहीं चल*", 1.5), ("ज़्यादा नहीं चल*", 1.5),
        ("jyada nahi chal*", 1.5), ("pehle jitna nahi", 1.5), ("पहले जितना नहीं", 1.5), ("range gir*", 1.5),
        ("range गिर*", 1.5), ("ghat gay*", 1.2), ("ghat gai", 1.2), ("घट ग*", 1.2), ("range bahut kam", 1.5),
        ("range बहुत कम", 1.5), ("kam de", 0.8), ("कम दे*", 0.8), ("pehle", 0.3), ("पहले", 0.3), ("ab", 0.2), ("अब", 0.2),
    ],
    "range": [
        ("kitna chal*", 1.2), ("kitni chal*", 1.2), ("kitni door", 1.2), ("kitna door", 1.2), ("kitne km", 1.2),
        ("कितना चल*", 1.2), ("कितनी चल*", 1.2), ("कितनी दूर", 1.2), ("कितना दूर", 1.2), ("कितने km", 1.2),
        ("range kitn*", 1.5), ("range कितन*", 1.5), ("range", 0.6), ("chalega", 0.6), ("chalegi", 0.6),
        ("चलेगा", 0.6), ("चलेगी", 0.6), ("kahan tak", 1.0), ("कहां तक", 1.0), ("km", 0.2),
        ("range mil*", 1.0), ("range मिल*", 1.0), ("जाएगी", 0.4), ("jayegi", 0.4),
    ],
    "charge_time_cost": [
        ("kharcha", 1.2), ("kharch*", 1.0), ("paisa", 1.0), ("paise", 1.0), ("rupaye", 1.0), ("rupay*", 1.0),
        ("rupee*", 1.0), ("cost", 1.0), ("खर्च*", 1.2), ("पैस*", 1.0), ("रुपय*", 1.0), ("रुपए", 1.0),
        ("kitne ka", 1.0), ("कितने का", 1.0), ("bill", 1.0), ("kitni der", 1.2), ("kitna time", 1.2),
        ("kitna samay", 1.2), ("ghante", 1.0), ("ghanta", 1.0), ("कितनी देर", 1.2), ("कितना समय", 1.2),
        ("कितना time", 1.2), ("कितने घंटे", 1.2), ("घंटे", 1.0), ("घंटा", 1.0), ("full charge", 0.8),
        ("full hone", 0.8), ("full होने", 0.8), ("पूरा charge", 0.8), ("pura charge", 0.8), ("time lag*", 0.8),
        ("kitne paise", 1.2), ("कितने पैसे", 1.2),
    ],
    "trip": [
        ("jana hai", 1.5), ("jaana hai", 1.5), ("जाना है", 1.5), ("pahunch*", 1.5), ("पहुंच*", 1.5),
        ("jaunga", 1.5), ("jaaunga", 1.5), ("जाऊंगा", 1.5), ("जाऊंगी", 1.5), ("trip", 1.2), ("safar", 1.5),
        ("सफर", 1.5), ("chal paunga", 1.5), ("चल पाऊंगा", 1.5), ("ja paunga", 1.5), ("जा पाऊंगा", 1.5),
        ("tak jana", 1.2), ("तक जाना", 1.2),
    ],
    "stations": [
        ("station", 1.5), ("charging point", 1.5), ("point", 0.6), ("kahan charge", 1.5), ("charge kahan", 1.5),
        ("charging kahan", 1.5), ("कहां charge", 1.5), ("charge कहां", 1.5), ("charging कहां", 1.5),
        ("paas mein", 1.2), ("पास में", 1.2), ("nearby", 1.5), ("near", 1.0), ("नजदीक", 1.2), ("nazdeek", 1.2),
        ("kahan lag*", 1.2), ("कहां लगा*", 1.2), ("charge karu", 0.8), ("charge करूं", 0.8),
    ],
    "savings": [
        ("bacha", 1.5), ("bachat", 1.5), ("bachaya", 1.5), ("bache", 1.5), ("बचा", 1.5), ("बचे", 1.5),
        ("बचत", 1.5), ("saving*", 1.5), ("save", 1.2), ("petrol", 1.2), ("cng", 1.2), ("diesel", 1.2),
        ("सस्ता", 1.0), ("sasta", 1.0), ("chalaya", 0.7), ("chalayi", 0.7), ("चलाया", 0.7), ("चलाई", 0.7),
        ("mukable", 0.5), ("मुकाबले", 0.5),
    ],
    "greeting": [
        ("namaste", 1.2), ("namaskar", 1.2), ("hello", 1.2), ("नमस्ते", 1.2),
        ("नमस्कार", 1.2), ("hello", 1.2), ("राम राम", 1.2), ("ram ram", 1.2), ("सत श्री अकाल", 1.2),
    ],
}
PATTERNS = {intent: compile_patterns(raw) for intent, raw in _RAW_PATTERNS.items()}

# Context that must be present for an intent to keep its full score.
_CONTEXT = {
    "trouble_slow_charging": compile_patterns([("charg*", 1), ("battery", 1)]),
}
# "kitni der lagegi" asks HOW LONG; it is not a complaint. Without a complaint word
# ("bahut der", "slow", "धीमी"...) the bare "der lag*" match must not pull the turn
# into slow-charging troubleshooting (troubleshooting wins close calls via PRIORITY).
_TIME_QUESTION = compile_patterns([
    ("kitni der", 1), ("kitna time", 1), ("kitna samay", 1), ("kitne ghante", 1), ("kab tak", 1),
    ("कितनी देर", 1), ("कितना समय", 1), ("कितना time", 1), ("कितने घंटे", 1), ("कब तक", 1),
])
_SLOW_COMPLAINT = compile_patterns([
    ("slow", 1), ("dheere", 1), ("dhire", 1), ("dhima", 1), ("dheema", 1), ("dhimi", 1), ("dheemi", 1),
    ("धीमा", 1), ("धीमी", 1), ("धीरे", 1), ("bahut der", 1), ("bahut time", 1), ("बहुत देर", 1),
    ("बहुत time", 1), ("jyada time", 1), ("zyada time", 1), ("ज्यादा time", 1), ("ज़्यादा time", 1),
])
_CHARGING_CONTEXT = compile_patterns([("charg*", 1), ("battery", 1), ("plug", 1), ("socket", 1)])

# Explicit priority: when two intents are close, a higher tier wins without asking.
PRIORITY = {"trouble_not_detecting": 2, "trouble_slow_charging": 2, "trouble_range_drop": 2}
COMPATIBLE = {frozenset({"range", "charge_time_cost"})}

INTENT_LABEL = {
    "range": "रेंज", "charge_time_cost": "चार्जिंग का समय और खर्चा", "trip": "सफ़र पूरा होगा या नहीं",
    "stations": "चार्जिंग स्टेशन", "savings": "आज की बचत", "trouble_slow_charging": "धीमी चार्जिंग",
    "trouble_range_drop": "रेंज कम होने की दिक्कत", "trouble_not_detecting": "चार्जर न पकड़ने की दिक्कत",
    "greeting": "नमस्ते",
}

# --------------------------------------------------------------------------
# Safety (checked before everything else, overrides pending dialogs)
# --------------------------------------------------------------------------
_SAFETY_STRONG = compile_patterns([(p, 1) for p in [
    "धुआं", "धुंआ", "धुआ", "dhuan", "dhuaan", "dhua", "dhuan", "smoke", "चिंगारी", "chingari", "chingaari",
    "spark", "पिघल*", "pighal*", "current lag*", "current maar*", "current aa*", "current मार*", "current लग*",
    "current आ*", "shock",
    "बदबू", "badbu", "aag", "आग", "जल गया", "जल गई", "जल रहा", "जल रही", "jal gaya", "jal gayi", "jal raha",
    "jal rahi", "जलने की", "jalne ki", "जलना", "jalna", "जला", "jala", "burning",
]])
_SAFETY_WITH_DEVICE = compile_patterns([(p, 1) for p in [
    "garam", "गरम", "गर्म", "geela", "gila", "geeli", "गीला", "गीली", "bhig*", "भीग*", "jal", "जल", "heat",
]])
_DEVICE = compile_patterns([(p, 1) for p in [
    "charger", "charging", "charge", "battery", "plug", "socket", "wire", "तार", "taar", "motor", "switch",
    "स्विच", "board", "बोर्ड", "मीटर", "meter",
]])
# Only distinctive words get fuzzy matching. "jalna" is NOT here: fuzzy "jalna" matches "jana" (= to go).
_SAFETY_FUZZY_OK = {normalize(w) for w in [
    "धुआं", "धुंआ", "dhuan", "dhuaan", "smoke", "चिंगारी", "chingari", "chingaari", "spark", "shock", "बदबू",
    "badbu", "burning", "current",
]}
# "light nahi jal rahi" = the lamp does not glow, NOT fire.
_SAFETY_NEGATORS = compile_patterns([(p, 1) for p in [
    "nahi jal*", "नहीं जल*", "light", "led", "bulb", "बल्ब", "batti", "बत्ती", "लाइट",
]])


def detect_safety(tokens):
    """
    Safety keywords use fuzzy matching too (4+ letter words only): missing a real
    "धुआं" because STT dropped a letter is worse than an occasional false alarm.
    """
    hits = []
    for phrase, _ in _SAFETY_STRONG + _SAFETY_WITH_DEVICE:
        fuzzy_ok = phrase[0] in _SAFETY_FUZZY_OK
        pos = find_phrase(tokens, phrase, config.FUZZY_THRESHOLD if fuzzy_ok else 0)
        if pos is None:
            continue
        is_jal = phrase[0].startswith(("jal", "जल"))
        if is_jal and has_any(tokens, _SAFETY_NEGATORS):
            continue
        if (phrase, 1) in _SAFETY_WITH_DEVICE and not has_any(tokens, _DEVICE):
            continue
        hits.append(" ".join(phrase))
    return hits


# --------------------------------------------------------------------------
# Intent scoring
# --------------------------------------------------------------------------
def score_intents(tokens, slots: Slots, fuzzy_threshold=config.FUZZY_THRESHOLD):
    """
    Returns [(intent, score, details)] sorted by score, highest first.
    Each pattern counts once; fuzzy hits count FUZZY_WEIGHT of an exact hit.
    Slot evidence (a city, two places, a km value) adds small bonuses.
    """
    scores = {}
    for intent, pats in PATTERNS.items():
        total, hits, fuzzy = 0.0, [], False
        for phrase, w in pats:
            m = find_phrase(tokens, phrase, fuzzy_threshold)
            if m is None:
                continue
            _, used_fuzzy = m
            total += w * (config.FUZZY_WEIGHT if used_fuzzy else 1.0)
            fuzzy = fuzzy or used_fuzzy
            hits.append(" ".join(phrase) + ("~" if used_fuzzy else ""))
        if intent in _CONTEXT and total and not has_any(tokens, _CONTEXT[intent]):
            total *= 0.5
        scores[intent] = [total, {"hits": hits, "fuzzy": fuzzy}]

    # "hi"/"hey" greet only as the first word: in Hindi "hi" also means "even/only" ("light hi nahi")
    if tokens and tokens[0] in ("hi", "hey", "हाय"):
        scores["greeting"][0] += 1.0

    # Slot evidence
    if slots.city:
        scores["stations"][0] += 1.0           # a bare city name means "stations there" (old behaviour)
    if len(slots.places) >= 2:
        scores["trip"][0] += 1.0
    if slots.km is not None:
        if scores["trip"][0] > 0:
            scores["trip"][0] += 0.5
        if scores["savings"][0] > 0:
            scores["savings"][0] += 0.5
    if slots.range_before is not None and slots.range_after is not None:
        scores["trouble_range_drop"][0] += 1.0
    if slots.percent is not None:
        # a percent in the sentence makes "how far / how long" readings more likely than trouble
        for k in ("range", "charge_time_cost"):
            if scores[k][0] > 0:
                scores[k][0] += 0.3
    if (scores["trouble_slow_charging"][0] > 0 and has_any(tokens, _TIME_QUESTION)
            and not has_any(tokens, _SLOW_COMPLAINT)):
        scores["trouble_slow_charging"][0] = 0.0
    # "charge nahi ho raha" style trouble sentences beat calculator words like "kitna time"
    if scores["trouble_not_detecting"][0] >= 1.0:
        scores["charge_time_cost"][0] *= 0.5

    ranked = sorted(((k, round(v[0], 3), v[1]) for k, v in scores.items()), key=lambda x: -x[1])
    return ranked


# Optional plug-in for a learned fallback classifier (e.g. sentence embeddings).
# Not implemented in this build; the rule engine never depends on it.
_fallback_classifier: Callable[[str], tuple] | None = None


def register_fallback_classifier(fn):
    """fn(text_norm) -> (intent, confidence 0..1). Used only when rules find nothing."""
    global _fallback_classifier
    _fallback_classifier = fn


# --------------------------------------------------------------------------
# Tool registry
# --------------------------------------------------------------------------
@dataclass
class Tool:
    name: str
    required: tuple
    run: Callable
    ask: dict


ASK = {
    "percent": "अभी बैटरी कितने प्रतिशत चार्ज है? जैसे, साठ प्रतिशत।",
    "km": "कितने किलोमीटर जाना है? जैसे, चालीस किलोमीटर।",
    "km_driven": "आज कितने किलोमीटर चलाया?",
    "city": "आप किस शहर में हैं? " + ", ".join(CITY_HINDI.values()) + " में से बताइए।",
}

TOOLS = {
    "range": Tool("range_calc", ("percent",), tools.range_calc, ASK),
    "charge_time_cost": Tool("charge_time_cost", ("percent",), tools.charge_time_cost, ASK),
    "trip": Tool("trip_feasibility", ("km", "percent"), tools.trip_feasibility, ASK),
    "stations": Tool("find_stations", ("city",), tools.find_stations, ASK),
    "savings": Tool("savings", ("km_driven",), tools.savings, ASK),
    "range_drop_diagnosis": Tool("range_drop_diagnosis", ("range_before", "range_after"),
                                 tools.range_drop_diagnosis, ASK),
}
TROUBLE_INTENT_FLOW = {"trouble_slow_charging": "slow_charging", "trouble_range_drop": "range_drop",
                       "trouble_not_detecting": "not_detecting"}
SLOT_INTENTS = {"range", "charge_time_cost", "trip", "savings"}   # can be re-run as follow-ups


# --------------------------------------------------------------------------
# Dialog manager
# --------------------------------------------------------------------------
def _result(intent, reply, *, score=0.0, margin=0.0, tool=None, needs_confirm=False, data=None, intents=None):
    return {"intent": intent, "reply": reply, "score": round(score, 3), "margin": round(margin, 3),
            "tool": tool, "needs_confirm": needs_confirm, "data": data or {}, "intents": intents or [intent]}


def _snapshot(session):
    return {"percent": session.percent, "city": session.city, "km": session.km, "km_driven": session.km_driven,
            "passengers": session.passengers, "trip_origin": session.trip_origin, "trip_dest": session.trip_dest}


def _failure(session, reply_first, kind):
    session.failures += 1
    if session.failures >= config.MAX_FAILURES_BEFORE_SIMPLE_PROMPT:
        return _result(kind, "बस इतना बोलिए: 'कितना चलेगा', या 'चार्जिंग पॉइंट कहां है'।")
    return _result(kind, reply_first)


def _clear_dialog(session):
    session.pending = None
    session.pending_percent = None
    session.pending_intents = []
    session.clarify_options = []
    session.offer_flow = None


def _start_trouble(session, flow):
    _clear_dialog(session)
    session.trouble_flow, session.trouble_step = flow, 0
    session.pending = "trouble"
    return tools.trouble_step_reply(flow, 0, first=True)


def _advance_trouble(session):
    flow = session.trouble_flow
    session.trouble_step += 1
    if session.trouble_step >= len(tools.TROUBLE_FLOWS[flow]["steps"]):
        session.trouble_flow, session.pending = None, None
        return tools.ESCALATE, True
    return tools.trouble_step_reply(flow, session.trouble_step), False


def _apply_slots(session, slots: Slots, intents):
    """Writes this turn's slot values into the session. km goes to trip or savings depending on intent."""
    if slots.percent is not None and slots.percent_conf == "high":
        session.percent = slots.percent
    if slots.passengers is not None:
        session.passengers = slots.passengers
    if slots.city:
        session.city = slots.city
    if slots.range_before is not None:
        session.range_before, session.range_after = slots.range_before, slots.range_after
    if "trip" in intents:
        places = slots.places
        if len(places) >= 2:
            session.trip_origin, session.trip_dest = places[0], places[1]
        elif len(places) == 1 and session.city and places[0] != session.city:
            session.trip_origin, session.trip_dest = session.city, places[0]
        elif len(places) == 1 and places[0] not in STATIONS:
            session.trip_origin, session.trip_dest = None, places[0]
        if slots.km is not None:
            session.km = slots.km
            if len(places) < 2:
                session.trip_origin = session.trip_origin if session.trip_dest else None
        elif session.trip_origin and session.trip_dest:
            km = tools.route_km(session.trip_origin, session.trip_dest)
            if km is not None:
                session.km = km
        if session.trip_origin in STATIONS:
            session.city = session.trip_origin
    elif "savings" in intents and slots.km is not None:
        session.km_driven = slots.km
    elif slots.km is not None and session.last_intent == "trip":
        session.km = slots.km


def _run_intents(session, intents, slots, score, margin):
    """Runs the tool(s) for the chosen intent(s), asking for missing slots / confirmation first."""
    intent = intents[0]

    # Troubleshooting flows (range drop with numbers -> diagnosis tool instead)
    if intent in TROUBLE_INTENT_FLOW:
        if intent == "trouble_range_drop" and session.range_before is not None and slots.range_before is not None:
            reply, data = tools.range_drop_diagnosis(session, DEFAULT_CONFIG)
            _clear_dialog(session)
            session.last_intent = intent
            if data["offer_flow"]:
                session.pending, session.offer_flow = "offer_trouble", "range_drop"
            return _result(intent, reply, score=score, margin=margin, tool="range_drop_diagnosis", data=data)
        session.last_intent = intent
        reply = _start_trouble(session, TROUBLE_INTENT_FLOW[intent])
        return _result(intent, reply, score=score, margin=margin, tool="troubleshoot",
                       data={"flow": session.trouble_flow, "step": 0})

    if intent == "greeting":
        _clear_dialog(session)
        session.last_intent = intent
        return _result(intent, "नमस्ते भैया! मैं ई-रिक्शा सहायक हूं। रेंज, चार्जिंग का खर्चा, सफ़र, बचत या "
                               "चार्जिंग की दिक्कत, कुछ भी पूछिए।", score=score, margin=margin)

    session.last_intent = intent
    session.pending_intents = list(intents)

    # Missing required slots -> ask for the first one
    for it in intents:
        tool = TOOLS[it]
        for slot in tool.required:
            if slot == "percent" and getattr(session, "percent") is None and slots.percent is not None \
                    and slots.percent_conf == "low":
                session.pending, session.pending_percent = "confirm_percent", slots.percent
                return _result(intent, f"{slots.percent} प्रतिशत, सही?", score=score, margin=margin,
                               tool=tool.name, needs_confirm=True, intents=intents)
            if getattr(session, slot) is None:
                session.pending = slot
                return _result(intent, tool.ask[slot], score=score, margin=margin, tool=tool.name, intents=intents)

    # Everything present -> run
    _clear_dialog(session)
    replies, data, names = [], {}, []
    brief = len(intents) > 1
    for it in intents:
        tool = TOOLS[it]
        r, d = tool.run(session, DEFAULT_CONFIG, brief=brief)
        replies.append(r)
        data[tool.name] = d
        names.append(tool.name)
    return _result(intent, " ".join(replies), score=score, margin=margin, tool="+".join(names), data=data,
                   intents=intents)


def _choose_intents(ranked):
    """Decide from scores: act, run two compatible intents together, or ask to clarify."""
    top, top_s = ranked[0][0], ranked[0][1]
    second, second_s = ranked[1][0], ranked[1][1]
    margin = top_s - second_s
    if top_s < config.INTENT_THRESHOLD:
        return None, margin
    if second_s >= config.INTENT_THRESHOLD and frozenset({top, second}) in COMPATIBLE:
        return ["range", "charge_time_cost"], margin
    if second_s >= config.WEAK_EVIDENCE and margin < config.CLARIFY_MARGIN:
        pt, ps = PRIORITY.get(top, 1), PRIORITY.get(second, 1)
        if pt != ps:
            return [top if pt > ps else second], margin
        if frozenset({top, second}) in COMPATIBLE:
            return ["range", "charge_time_cost"], margin
        return ("clarify", [top, second]), margin
    return [top], margin


def _decide(session, text_norm, tokens, slots, ranked, source):
    """Main (non-pending) routing for one turn."""
    top_s = ranked[0][1]
    margin = top_s - ranked[1][1]
    choice, margin = _choose_intents(ranked)

    if choice and choice[0] == "clarify":
        a, b = choice[1]
        session.pending, session.clarify_options = "clarify", [a, b]
        _apply_slots(session, slots, [])
        return _result("clarify", f"{INTENT_LABEL[a]} पूछ रहे हैं या {INTENT_LABEL[b]}?", score=top_s, margin=margin,
                       data={"options": [a, b]})

    if choice:
        _apply_slots(session, slots, choice)
        session.failures = 0
        return _run_intents(session, choice, slots, top_s, margin)

    # No intent above threshold. Slot-only utterance? -> follow-up on the last intent.
    has_slot = slots.percent is not None or slots.km is not None or slots.passengers is not None
    if has_slot:
        if session.last_intent in SLOT_INTENTS:
            intents = session.pending_intents if set(session.pending_intents) <= SLOT_INTENTS and \
                session.pending_intents else [session.last_intent]
            if slots.km is not None and session.last_intent == "savings":
                intents = ["savings"]
        elif slots.percent is not None:
            intents = ["range", "charge_time_cost"]      # "60% charge hai" alone -> full calculator answer
        else:
            intents = None
        if intents:
            _apply_slots(session, slots, intents)
            if slots.percent_override and session.percent is None:
                session.percent = slots.percent
            session.failures = 0
            return _run_intents(session, intents, slots, top_s, margin)

    # Weak evidence -> targeted clarification
    if top_s >= config.WEAK_EVIDENCE:
        options = [ranked[0][0]] + ([ranked[1][0]] if ranked[1][1] >= config.WEAK_EVIDENCE * 0.6 else [])
        session.pending, session.clarify_options = "clarify", options
        if len(options) == 2:
            q = f"{INTENT_LABEL[options[0]]} पूछ रहे हैं या {INTENT_LABEL[options[1]]}?"
        else:
            q = f"क्या आप {INTENT_LABEL[options[0]]} के बारे में पूछ रहे हैं?"
        return _result("clarify", q, score=top_s, margin=margin, data={"options": options})

    # Optional learned fallback (not shipped)
    if _fallback_classifier is not None and config.USE_EMBEDDINGS:
        label, conf = _fallback_classifier(text_norm)
        if label in TOOLS or label in TROUBLE_INTENT_FLOW or label == "greeting":
            _apply_slots(session, slots, [label])
            return _run_intents(session, [label], slots, conf, 0.0)

    return _failure(session, "माफ़ कीजिए, समझ नहीं पाया। रेंज, चार्जिंग का खर्चा, सफ़र या चार्जिंग पॉइंट के बारे में "
                             "पूछिए।", "fallback")


def _handle_pending(session, tokens, slots, ranked):
    """Returns a result if this turn answered what the agent was waiting for, else None."""
    pending = session.pending
    top, top_s = ranked[0][0], ranked[0][1]
    strong_new = top_s >= config.INTENT_THRESHOLD + 0.5

    if pending == "confirm_percent":
        if slots.percent_override or (slots.percent is not None and slots.percent_conf == "high"):
            session.percent = slots.percent           # "नहीं, सत्तर" or a clear new number
        elif slots.yes:
            session.percent = session.pending_percent
        elif slots.no:
            session.pending, session.pending_percent = "percent", None
            return _result("confirm_percent", "ठीक है। सही प्रतिशत फिर से बताइए।", tool=None)
        elif slots.percent is not None:
            session.pending_percent = slots.percent
            return _result("confirm_percent", f"{slots.percent} प्रतिशत, सही?", needs_confirm=True)
        else:
            _clear_dialog(session)
            return None
        intents = session.pending_intents or [session.last_intent]
        session.pending = None
        _apply_slots(session, slots, intents)
        return _run_intents(session, intents, slots, top_s, 0.0)

    if pending == "trouble":
        if slots.fixed:
            session.trouble_flow, session.pending = None, None
            return _result("trouble_fixed", tools.FIXED)
        other_trouble = (top in TROUBLE_INTENT_FLOW and TROUBLE_INTENT_FLOW[top] != session.trouble_flow
                         and top_s >= config.INTENT_THRESHOLD)
        if other_trouble or (strong_new and not (slots.next_step or slots.yes or slots.no)
                             and top not in TROUBLE_INTENT_FLOW):
            session.trouble_flow, session.pending = None, None
            return None                                   # driver moved on to another question / problem
        if slots.next_step or slots.yes or slots.no:
            reply, done = _advance_trouble(session)
            return _result("trouble_escalate" if done else "trouble_next", reply, tool="troubleshoot",
                           data={"flow": session.trouble_flow, "step": session.trouble_step})
        return _result("trouble_wait", tools.STEP_HINT, tool="troubleshoot")

    if pending == "offer_trouble":
        flow = session.offer_flow
        if slots.yes:
            return _result("trouble_range_drop", _start_trouble(session, flow), tool="troubleshoot",
                           data={"flow": flow, "step": 0})
        _clear_dialog(session)
        if slots.no:
            return _result("ack", "ठीक है। और कुछ पूछना हो तो बोलिए।")
        return None

    if pending == "clarify":
        options = session.clarify_options
        chosen = None
        if slots.yes and len(options) == 1:
            chosen = options[0]
        else:
            for it, sc, _ in ranked:
                if it in options and sc > 0:
                    chosen = it
                    break
            if chosen is None:
                for it in options:
                    if has_any(tokens, compile_patterns([(INTENT_LABEL[it], 1)]), config.FUZZY_THRESHOLD):
                        chosen = it
                        break
        _clear_dialog(session)
        if chosen is None:
            return None
        _apply_slots(session, slots, [chosen])
        return _run_intents(session, [chosen], slots, top_s, 0.0)

    if pending in ("percent", "km", "km_driven", "city"):
        filled = {
            "percent": slots.percent is not None,
            "km": slots.km is not None or len(slots.places) >= 1,
            "km_driven": slots.km is not None,
            "city": slots.city is not None,
        }[pending]
        if strong_new and top not in session.pending_intents and not filled:
            _clear_dialog(session)
            return None
        if not filled:
            if top_s >= config.INTENT_THRESHOLD:
                _clear_dialog(session)
                return None
            session.failures += 1
            return _result("reask", ASK[pending], tool=None)
        intents = session.pending_intents or [session.last_intent]
        if pending == "percent" and slots.percent_conf == "low":
            session.pending, session.pending_percent = "confirm_percent", slots.percent
            return _result(intents[0], f"{slots.percent} प्रतिशत, सही?", tool=TOOLS[intents[0]].name,
                           needs_confirm=True, intents=intents)
        if pending == "km_driven":
            session.km_driven = slots.km
        session.pending = None
        _apply_slots(session, slots, intents)
        if pending == "km" and slots.km is None and not session.km:
            session.pending = "km"
            return _result(intents[0], ASK["km"], tool=TOOLS[intents[0]].name, intents=intents)
        session.failures = 0
        return _run_intents(session, intents, slots, top_s, 0.0)
    return None


def step(session: Session, text, source="text", log=True):
    """
    One dialog turn. `source` is "voice" or "text" (kept for logging; confirmation
    is driven by parse confidence, not by source).
    """
    session.turn += 1
    text_norm = normalize(text)
    tokens = tokens_of(text_norm)

    result = _step(session, text_norm, tokens, source)
    result["slots"] = _snapshot(session)
    session.history.append({"user": text, "intent": result["intent"], "reply": result["reply"]})
    del session.history[:-20]
    if log:
        _log_turn(text, text_norm, result)
    return result


def _step(session, text_norm, tokens, source):
    # 0) Empty / garbled
    if not tokens or not re.search(r"[a-z0-9ऀ-ॿ]", text_norm):
        return _failure(session, "आवाज़ साफ़ नहीं आई, दोबारा बोलिए।", "empty")

    # 1) Safety first - overrides any pending question or troubleshooting flow
    hits = detect_safety(tokens)
    if hits:
        _clear_dialog(session)
        session.trouble_flow = None
        session.last_intent = "safety"
        session.failures = 0
        return _result("safety", tools.SAFETY_REPLY, score=10.0, margin=10.0, tool="safety_advice",
                       data={"triggers": hits})

    # 2) Slots and intent scores
    slots = extract_slots(tokens, pending=session.pending, fuzzy_threshold=config.FUZZY_THRESHOLD)
    ranked = score_intents(tokens, slots)

    # 3) Answer to a pending question?
    if session.pending:
        r = _handle_pending(session, tokens, slots, ranked)
        if r is not None:
            if r["intent"] not in ("reask",):
                session.failures = 0
            return r

    # 4) Normal routing
    return _decide(session, text_norm, tokens, slots, ranked, source)


# --------------------------------------------------------------------------
# Logging (one JSON line per turn, no personal data)
# --------------------------------------------------------------------------
_LONG_NUMBER = re.compile(r"\d{7,}")


def _mask(s):
    """Drops anything that looks like a phone/account number before logging."""
    return _LONG_NUMBER.sub("<num>", s or "")


def _log_turn(text_raw, text_norm, result):
    path = os.environ.get("EV_AGENT_LOG_PATH", config.LOG_PATH)
    if not path:
        return
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        rec = {"ts": round(time.time(), 3), "text_raw": _mask(text_raw), "text_norm": _mask(text_norm),
               "intent": result["intent"], "score": result["score"], "margin": result["margin"],
               "slots": result["slots"], "tool": result["tool"], "reply": result["reply"],
               "needs_confirm": result["needs_confirm"]}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass          # logging must never break a conversation


# --------------------------------------------------------------------------
# Backward-compatible API
# --------------------------------------------------------------------------
_default_session = Session()


def reset():
    """Forget the module-level default conversation."""
    global _default_session
    _default_session = Session()


def new_state():
    """Old name kept for callers that still use it; returns a fresh Session."""
    return Session()


def respond(text, session=None, source="text"):
    """Old API: respond(text) -> {"intent", "reply", ...}. Uses a shared default session if none given."""
    return step(session if session is not None else _default_session, text, source)


def extract_percent(text):
    """Old API kept for scripts: charge % in the text, or None (needs a %/charge cue)."""
    return _nlu_extract_percent(text)


if __name__ == "__main__":
    os.environ.setdefault("EV_AGENT_LOG_PATH", "")
    tests = [
        "Bhaiya, 60% charge hai, kitna chalega aur charge mein kitna kharcha aayega?",
        "भैया साठ प्रतिशत चार्ज है कितना चलेगा और कितना खर्चा आएगा",
        "meri charging bahut slow ho rahi hai",
        "range kam ho gayi hai",
        "charger detect nahi kar raha",
        "जयपुर में चार्जिंग पॉइंट कहाँ है",
        "charging station kahan hai",
        "kitna chalega",
        "namaste",
        "pizza chahiye",
    ]
    for q in tests:
        r = step(Session(), q)
        print("Q:", q)
        print("  ->", r["intent"], f"({r['score']})", "|", r["reply"], "\n")

    print("===== Multi-turn =====")
    s = Session()
    for q in ["kitna chalega", "साठ", "हां", "और खर्चा?", "भोपाल से सीहोर जाना है, पहुंच जाऊंगा?"]:
        r = step(s, q)
        print("Q:", q)
        print("  ->", r["intent"], "|", r["reply"], "\n")
