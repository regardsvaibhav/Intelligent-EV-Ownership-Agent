"""
Deterministic "tools" the dialog agent calls. Each is a plain function
(session, cfg) -> (reply_text, data_dict), so it can be unit-tested on its own.

All models are simple and approximate (linear range, two-stage charging,
linear load derating). They are estimates for a driver, not measurements.
Replies are short Devanagari sentences with rounded numbers, meant for TTS.
"""
import math
import re

from config import DEFAULT_CONFIG, VehicleConfig
from stations import AREA_HINDI, DEMO_ROUTES, PLACE_HINDI, STATIONS


# --------------------------------------------------------------------------
# Voice-friendly rounding / formatting
# --------------------------------------------------------------------------
def round_km(km):
    return int(round(km / 5.0) * 5) if km >= 20 else int(round(km))


def round_rs(rs):
    if rs < 20:
        return int(round(rs))
    if rs < 200:
        return int(round(rs / 5.0) * 5)
    return int(round(rs / 10.0) * 10)


def fmt_rs(rs):
    """Indian digit grouping: 7257 -> '7,260' after rounding."""
    v = round_rs(rs)
    s = str(v)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups + [tail])


def fmt_duration(hours, oblique=False):
    """
    0.67 -> '40 मिनट', 1.5 -> 'डेढ़ घंटा', 2.5 -> 'ढाई घंटे', 3.5 -> 'साढ़े 3 घंटे'.
    oblique=True gives the form used before 'में' ('1 घंटे में', 'डेढ़ घंटे में').
    """
    if hours < 0.75:
        minutes = max(10, int(round(hours * 60 / 10.0) * 10))
        return f"{minutes} मिनट"
    half = round(hours * 2) / 2.0
    if half == 1:
        return "1 घंटे" if oblique else "1 घंटा"
    if half == 1.5:
        return "डेढ़ घंटे" if oblique else "डेढ़ घंटा"
    if half == 2.5:
        return "ढाई घंटे"
    if half != int(half):
        return f"साढ़े {int(half)} घंटे"
    return f"{int(half)} घंटे"


def fmt_hours_open(text):
    """'6 AM - 10 PM' -> 'सुबह 6 से रात 10 बजे तक', '24 hours' -> '24 घंटे खुला'."""
    if "24" in text and "hour" in text.lower():
        return "24 घंटे खुला"
    m = re.match(r"\s*(\d{1,2})\s*AM\s*-\s*(\d{1,2})\s*PM", text, re.I)
    if m:
        return f"सुबह {m.group(1)} से रात {m.group(2)} बजे तक"
    return text


# --------------------------------------------------------------------------
# Core models
# --------------------------------------------------------------------------
def load_factor(passengers, cfg: VehicleConfig = DEFAULT_CONFIG):
    """Linear derating above rated load (ASSUMPTION: -4% per extra passenger)."""
    if passengers is None:
        return 1.0
    p = max(0, min(cfg.max_passengers, passengers))
    extra = max(0, p - cfg.rated_passengers)
    return max(0.5, 1.0 - cfg.derate_per_extra_passenger * extra)


def estimate_range_km(percent, passengers=None, cfg: VehicleConfig = DEFAULT_CONFIG):
    percent = max(0, min(100, percent))
    return cfg.full_range_km * percent / 100.0 * cfg.battery_age_factor * load_factor(passengers, cfg)


def charge_hours(from_pct, to_pct, cfg: VehicleConfig = DEFAULT_CONFIG):
    """
    Two-stage estimate: full charger power up to taper_start_pct, then
    taper_power_factor x power above it (CC -> CV behaviour, approximate).
    """
    from_pct, to_pct = max(0, min(100, from_pct)), max(0, min(100, to_pct))
    if to_pct <= from_pct:
        return 0.0
    per_pct_kwh = cfg.battery_kwh / 100.0 / cfg.efficiency
    fast = max(0, min(to_pct, cfg.taper_start_pct) - from_pct)
    slow = max(0, to_pct - max(from_pct, cfg.taper_start_pct))
    return (fast * per_pct_kwh) / cfg.charger_kw + (slow * per_pct_kwh) / (cfg.charger_kw * cfg.taper_power_factor)


def charge_cost_rs(from_pct, to_pct, cfg: VehicleConfig = DEFAULT_CONFIG):
    kwh = cfg.battery_kwh * max(0, min(100, to_pct) - max(0, from_pct)) / 100.0 / cfg.efficiency
    return kwh * cfg.tariff_rs_per_unit


def ev_rs_per_km(cfg: VehicleConfig = DEFAULT_CONFIG):
    return cfg.battery_kwh / cfg.efficiency * cfg.tariff_rs_per_unit / cfg.full_range_km


def route_km(a, b):
    return DEMO_ROUTES.get((a, b)) or DEMO_ROUTES.get((b, a))


def cheapest_station(city):
    if city not in STATIONS:
        return None
    return min(STATIONS[city], key=lambda s: (s["price"], -s["slots"]))


def area_hi(station):
    return AREA_HINDI.get(station["area"], station["area"])


# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------
def range_calc(session, cfg=DEFAULT_CONFIG, brief=False):
    km = estimate_range_km(session.percent, session.passengers, cfg)
    pax = ""
    if session.passengers is not None and session.passengers > cfg.rated_passengers:
        pax = f" {session.passengers} सवारी के साथ"
    reply = f"{session.percent} प्रतिशत पर{pax} करीब {round_km(km)} किलोमीटर चलेगा।"
    if not brief:
        reply += " रास्ते और लोड के हिसाब से थोड़ा कम-ज़्यादा हो सकता है।"
    return reply, {"percent": session.percent, "range_km": round(km, 1), "passengers": session.passengers}


def charge_time_cost(session, cfg=DEFAULT_CONFIG, brief=False):
    p = session.percent
    if p >= 100:
        return "बैटरी पूरी भरी हुई है, अभी चार्ज की ज़रूरत नहीं।", {"percent": p, "hours_full": 0, "cost_rs": 0}
    full_h = charge_hours(p, 100, cfg)
    cost = charge_cost_rs(p, 100, cfg)
    data = {"percent": p, "hours_full": round(full_h, 2), "cost_rs": round(cost, 1)}
    if p < cfg.taper_start_pct:
        h80 = charge_hours(p, cfg.taper_start_pct, cfg)
        data["hours_to_80"] = round(h80, 2)
        reply = (f"{cfg.taper_start_pct} प्रतिशत तक करीब {fmt_duration(h80, True)} में, "
                 f"और पूरी बैटरी करीब {fmt_duration(full_h, True)} में भरेगी। खर्चा करीब {fmt_rs(cost)} रुपये आएगा।")
    else:
        reply = (f"पूरी बैटरी करीब {fmt_duration(full_h, True)} में भरेगी, "
                 f"और करीब {fmt_rs(cost)} रुपये खर्च होंगे।")
    return reply, data


def trip_feasibility(session, cfg=DEFAULT_CONFIG, brief=False):
    km = session.km
    p = session.percent
    origin, dest = session.trip_origin, session.trip_dest
    rng = estimate_range_km(p, session.passengers, cfg)
    need = km * (1 + cfg.trip_buffer)
    if origin and dest:
        head = f"{PLACE_HINDI[origin]} से {PLACE_HINDI[dest]} करीब {round_km(km)} किलोमीटर है"
    else:
        head = f"{round_km(km)} किलोमीटर का सफ़र है"
    data = {"km": km, "percent": p, "range_km": round(rng, 1), "origin": origin, "dest": dest}

    if rng >= need:
        data["verdict"] = "yes"
        return f"{head}, और {p} प्रतिशत पर करीब {round_km(rng)} किलोमीटर चलेगा। आराम से पहुंच जाएंगे।", data
    if rng >= km:
        data["verdict"] = "borderline"
        return (f"{head}, और {p} प्रतिशत पर करीब {round_km(rng)} किलोमीटर चलेगा। "
                "पहुंच तो जाएंगे पर रेंज बहुत कम बचेगी, निकलने से पहले थोड़ा चार्ज कर लीजिए।"), data

    target = int(math.ceil(need / (cfg.full_range_km * cfg.battery_age_factor * load_factor(session.passengers, cfg))
                           * 100 / 5.0) * 5)
    stop_city = origin or session.city
    station = cheapest_station(stop_city)
    station_txt = ""
    if station:
        station_txt = f" {PLACE_HINDI[stop_city]} में {area_hi(station)} पर चार्जिंग पॉइंट है।"
        data["charging_stop"] = {"city": stop_city, "area": station["area"], "price": station["price"]}
    if target <= 100:
        data["verdict"] = "no_charge_first"
        data["target_percent"] = target
        h = charge_hours(p, target, cfg)
        return (f"{head}, पर {p} प्रतिशत पर करीब {round_km(rng)} किलोमीटर ही चलेगा। "
                f"निकलने से पहले कम से कम {target} प्रतिशत चार्ज कीजिए, ये करीब {fmt_duration(h, True)} में होगा।"
                f"{station_txt}"), data
    data["verdict"] = "no_midway_charge"
    return (f"{head}, ये एक पूरे चार्ज में भी नहीं होगा। "
            f"पूरा चार्ज करके निकलिए और बीच रास्ते में एक बार चार्ज कीजिए।{station_txt}"), data


def find_stations(session, cfg=DEFAULT_CONFIG, brief=False):
    city = session.city
    items = STATIONS[city]
    cheap = cheapest_station(city)
    always = next((s for s in items if "24" in s["open"] and s is not cheap), None)
    reply = (f"{PLACE_HINDI[city]} में {len(items)} डेमो चार्जिंग पॉइंट हैं। "
             f"सबसे सस्ता {area_hi(cheap)} पर, {cheap['price']} रुपये यूनिट, {fmt_hours_open(cheap['open'])}।")
    if always:
        reply += f" 24 घंटे वाला {area_hi(always)} पर है।"
    return reply, {"city": city, "stations": [s["name"] for s in items]}


def savings(session, cfg=DEFAULT_CONFIG, brief=False):
    km = session.km_driven
    ev = km * ev_rs_per_km(cfg)
    petrol = km * cfg.petrol_rs_per_km
    cng = km * cfg.cng_rs_per_km
    monthly = (petrol - ev) * cfg.work_days_per_month
    reply = (f"आज {round_km(km)} किलोमीटर पर बिजली करीब {fmt_rs(ev)} रुपये की लगी। "
             f"पेट्रोल ऑटो से करीब {fmt_rs(petrol - ev)} और सीएनजी से करीब {fmt_rs(cng - ev)} रुपये बचे। "
             f"ऐसे चलाएं तो महीने में करीब {fmt_rs(monthly)} रुपये बचेंगे।")
    return reply, {"km": km, "ev_rs": round(ev, 1), "petrol_rs": round(petrol, 1), "cng_rs": round(cng, 1),
                   "saved_vs_petrol": round(petrol - ev, 1), "saved_vs_cng": round(cng - ev, 1),
                   "monthly_vs_petrol": round(monthly, 1)}


def range_drop_diagnosis(session, cfg=DEFAULT_CONFIG, brief=False):
    before, after = session.range_before, session.range_after
    if after >= before:
        return "इन नंबरों से रेंज कम नहीं हुई लगती। अगर फिर भी दिक्कत है तो टायर की हवा और लोड देखिए।", \
            {"before": before, "after": after, "drop_pct": 0, "tier": "none", "offer_flow": False}
    drop = (before - after) / before * 100
    d = int(round(drop))
    if drop < 10:
        return (f"रेंज करीब {d} प्रतिशत गिरी है, इतना मौसम, सवारी या रास्ते से हो जाता है। "
                "एक बार टायर की हवा चेक कर लीजिए।"), \
            {"before": before, "after": after, "drop_pct": round(drop, 1), "tier": "normal", "offer_flow": False}
    if drop <= 25:
        return (f"रेंज करीब {d} प्रतिशत गिरी है। पहले टायर की हवा, ज़्यादा लोड और ब्रेक जाम तो नहीं, ये देखिए। "
                "एक-एक करके उपाय बताऊं?"), \
            {"before": before, "after": after, "drop_pct": round(drop, 1), "tier": "check_basics", "offer_flow": True}
    return (f"रेंज करीब {d} प्रतिशत गिरी है, ये ज़्यादा है। टायर और लोड ठीक हों तो मैकेनिक से बैटरी की जांच करवाइए। "
            "एक-एक करके उपाय बताऊं?"), \
        {"before": before, "after": after, "drop_pct": round(drop, 1), "tier": "battery_check", "offer_flow": True}


# --------------------------------------------------------------------------
# Step-by-step troubleshooting flows (one short sentence per step)
# --------------------------------------------------------------------------
TROUBLE_FLOWS = {
    "slow_charging": {
        "title": "चार्जिंग धीमी है",
        "steps": [
            "चार्जर का प्लग और सॉकेट देखिए, ढीला या गंदा हो तो सूखे कपड़े से साफ कीजिए।",
            "एक्सटेंशन बोर्ड हटाकर चार्जर सीधे दीवार के सॉकेट में लगाइए।",
            "शाम को वोल्टेज गिरता है, इसलिए एक बार रात में चार्ज करके देखिए।",
        ],
    },
    "range_drop": {
        "title": "रेंज कम हो गई है",
        "steps": [
            "टायर की हवा चेक कीजिए, कम हवा से रेंज काफी घटती है।",
            "देखिए कि ब्रेक जाम तो नहीं और गाड़ी पर ज़्यादा लोड तो नहीं।",
            "बैटरी के तार और कनेक्शन ढीले या जंग लगे तो नहीं, ये देखिए।",
            "एक बार बैटरी को पूरा 100 प्रतिशत चार्ज कीजिए, इससे बैटरी संतुलित होती है।",
        ],
    },
    "not_detecting": {
        "title": "चार्जर डिटेक्ट नहीं कर रहा",
        "steps": [
            "चार्जर की लाइट जल रही है या नहीं देखिए, नहीं तो सॉकेट में बिजली चेक कीजिए।",
            "चार्जर का कनेक्टर पूरा अंदर तक दबाकर लगाइए और पिन साफ कीजिए।",
            "दूसरे सॉकेट में लगाकर देखिए, और MCB या फ्यूज भी देख लीजिए।",
            "तार कटा या पिघला तो नहीं, ये देखिए, टूटा तार हो तो चार्जर इस्तेमाल मत कीजिए।",
        ],
    },
}
ORDINALS = ["पहला", "दूसरा", "तीसरा", "चौथा", "पांचवां", "छठा"]
STEP_HINT = "हो जाए तो 'अगला' बोलिए, या बताइए अगर ठीक हो गया।"
ESCALATE = "ये सब करके भी ठीक नहीं हुआ, तो मैकेनिक को दिखाइए। चार्जर या बैटरी को खुद मत खोलिए।"
FIXED = "बढ़िया, दिक्कत ठीक हो गई! और कुछ पूछना हो तो बोलिए।"


def trouble_step_reply(flow, step, first=False):
    steps = TROUBLE_FLOWS[flow]["steps"]
    intro = f"{TROUBLE_FLOWS[flow]['title']}, घबराइए मत। " if first else ""
    return f"{intro}{ORDINALS[step]} उपाय: {steps[step]} {STEP_HINT}"


SAFETY_REPLY = ("खतरा हो सकता है! तुरंत मेन स्विच से चार्जर बंद कीजिए और उसे हाथ मत लगाइए। "
                "पानी से दूर रहिए और मैकेनिक को बुलाइए।")
