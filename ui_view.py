"""
Turns an agent turn into a small "view" dict the web page can draw as a card.

The agent (agent.py) decides WHAT to say; this module only prepares numbers and
Hindi labels for the screen, using the same rounding as the spoken reply so the
card and the voice never disagree. No logic or decisions live here.
"""
import tools
from config import DEFAULT_CONFIG as CFG
from stations import CITY_HINDI, PLACE_HINDI, STATIONS

PERCENT_CHOICES = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
KM_CHOICES = [10, 20, 30, 40, 50, 60, 80, 100]


def _gauge(data, session):
    rc = data.get("range_calc")
    ct = data.get("charge_time_cost")
    pct = (rc or ct or {}).get("percent", session.percent)
    view = {"kind": "gauge", "percent": pct,
            "range_km": tools.round_km(tools.estimate_range_km(pct, session.passengers)),
            "passengers": session.passengers if (session.passengers or 0) > CFG.rated_passengers else None}
    if ct:
        view["full"] = tools.fmt_duration(ct["hours_full"]) if ct["hours_full"] else None
        view["to80"] = tools.fmt_duration(ct["hours_to_80"]) if ct.get("hours_to_80") else None
        view["cost"] = tools.fmt_rs(ct["cost_rs"])
    return view


def _trip(d):
    view = {"kind": "trip", "verdict": d["verdict"], "percent": d["percent"],
            "km": tools.round_km(d["km"]), "range_km": tools.round_km(d["range_km"]),
            "need_km": tools.round_km(d["km"] * (1 + CFG.trip_buffer)),
            "origin": PLACE_HINDI.get(d["origin"]) if d.get("origin") else None,
            "dest": PLACE_HINDI.get(d["dest"]) if d.get("dest") else None}
    view["range_share"] = max(4, min(100, round(d["range_km"] / (d["km"] * (1 + CFG.trip_buffer)) * 100)))
    if d.get("target_percent"):
        view["target"] = d["target_percent"]
        view["charge_time"] = tools.fmt_duration(tools.charge_hours(d["percent"], d["target_percent"]))
        view["charge_cost"] = tools.fmt_rs(tools.charge_cost_rs(d["percent"], d["target_percent"]))
    stop = d.get("charging_stop")
    if stop:
        st = next(s for s in STATIONS[stop["city"]] if s["area"] == stop["area"])
        view["station"] = {"city": CITY_HINDI[stop["city"]], "area": tools.area_hi(st), "price": st["price"],
                           "open": tools.fmt_hours_open(st["open"])}
    return view


def _stations(d):
    city = d["city"]
    cheap = tools.cheapest_station(city)
    items = []
    for s in sorted(STATIONS[city], key=lambda s: s["price"]):
        items.append({"area": tools.area_hi(s), "price": s["price"], "slots": s["slots"],
                      "open": tools.fmt_hours_open(s["open"]), "cheapest": s is cheap,
                      "always_open": "24" in s["open"]})
    return {"kind": "stations", "city": CITY_HINDI[city], "items": items, "demo": True}


def _savings(d):
    top = max(d["petrol_rs"], 1)
    return {"kind": "savings", "km": tools.round_km(d["km"]),
            "saved": tools.fmt_rs(d["saved_vs_petrol"]), "saved_cng": tools.fmt_rs(d["saved_vs_cng"]),
            "monthly": tools.fmt_rs(d["monthly_vs_petrol"]),
            "bars": [{"label": "पेट्रोल ऑटो", "rs": tools.fmt_rs(d["petrol_rs"]), "share": 100},
                     {"label": "सीएनजी ऑटो", "rs": tools.fmt_rs(d["cng_rs"]), "share": round(d["cng_rs"] / top * 100)},
                     {"label": "आपकी ई-रिक्शा", "rs": tools.fmt_rs(d["ev_rs"]),
                      "share": max(4, round(d["ev_rs"] / top * 100)), "mine": True}],
            "assumption": f"पेट्रोल ₹{CFG.petrol_rs_per_km * 25:.0f}/लीटर, बिजली ₹{CFG.tariff_rs_per_unit:.0f}/यूनिट (अनुमान)"}


def _trouble(result, session):
    flow = session.trouble_flow or (result["data"] or {}).get("flow")
    if result["intent"] == "trouble_escalate" or not flow:
        return {"kind": "trouble_end"}
    steps = tools.TROUBLE_FLOWS[flow]["steps"]
    i = session.trouble_step
    return {"kind": "trouble", "title": tools.TROUBLE_FLOWS[flow]["title"], "step": i + 1, "total": len(steps),
            "text": steps[i]}


def ask_choices(slot):
    if slot == "percent":
        return {"kind": "ask", "slot": "percent", "question": "बैटरी कितने प्रतिशत चार्ज है?",
                "choices": [{"label": f"{p}%", "say": f"{p} प्रतिशत"} for p in PERCENT_CHOICES]}
    if slot in ("km", "km_driven"):
        q = "कितने किलोमीटर जाना है?" if slot == "km" else "आज कितने किलोमीटर चलाया?"
        return {"kind": "ask", "slot": slot, "question": q,
                "choices": [{"label": f"{k} किमी", "say": f"{k} km"} for k in KM_CHOICES]}
    if slot == "city":
        return {"kind": "ask", "slot": "city", "question": "आप किस शहर में हैं?",
                "choices": [{"label": h, "say": h} for h in CITY_HINDI.values()]}
    return None


def build_view(result, session):
    """result = agent.step(...) output, session = the agent.Session after the turn."""
    import agent   # local import: agent imports nothing from here
    intent, tool, data = result["intent"], result.get("tool"), result.get("data") or {}

    if intent == "safety":
        return {"kind": "safety"}
    if result.get("needs_confirm") or (session.pending == "confirm_percent" and session.pending_percent is not None):
        return {"kind": "confirm", "percent": session.pending_percent}
    if intent == "clarify":
        return {"kind": "clarify", "options": [{"label": agent.INTENT_LABEL[o], "say": agent.INTENT_LABEL[o]}
                                               for o in data.get("options", [])]}
    if session.pending in ("percent", "km", "km_driven", "city"):
        return ask_choices(session.pending)
    if intent in ("trouble_fixed",):
        return {"kind": "fixed"}
    if tool == "troubleshoot" or intent in ("trouble_next", "trouble_escalate", "trouble_wait"):
        return _trouble(result, session)
    if tool == "range_drop_diagnosis":
        return {"kind": "diagnosis", "before": int(data["before"]), "after": int(data["after"]),
                "drop": int(round(data["drop_pct"])), "tier": data["tier"], "offer": data["offer_flow"]}
    if "trip_feasibility" in data:
        return _trip(data["trip_feasibility"])
    if "find_stations" in data:
        return _stations(data["find_stations"])
    if "savings" in data:
        return _savings(data["savings"])
    if "range_calc" in data or "charge_time_cost" in data:
        return _gauge(data, session)
    return {"kind": "home"}


def memory(session):
    return {"percent": session.percent, "city": CITY_HINDI.get(session.city) if session.city else None,
            "passengers": session.passengers}
