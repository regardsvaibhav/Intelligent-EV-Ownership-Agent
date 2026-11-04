"""
EV Ownership Agent - dimaag (logic).
Driver ki baat (text) aati hai -> samajh ke jawab (Hindi text) banata hai.
Koi bhi API key yahan nahi chahiye.

Neeche ke NUMBERS aap apne e-rickshaw ke hisaab se badal sakte ho.
"""
import re
from stations import STATIONS, CITY_WORDS, CITY_HINDI

# ---------------- Settings (apne hisaab se badlo) ----------------
BATTERY_KWH = 7.2          # battery ka size (kWh)
FULL_RANGE_KM = 90         # 100% charge par kitna chalta hai (km)
CHARGER_KW = 1.2           # charger ki power (kW)
CHARGE_EFFICIENCY = 0.90   # charging mein ~10% loss
TARIFF_RS_PER_UNIT = 8.0   # bijli ka rate (Rs per unit)
# -----------------------------------------------------------------

HINDI_NUMBERS = {
    "दस": 10, "das": 10, "पंद्रह": 15, "pandrah": 15, "बीस": 20, "bees": 20,
    "पच्चीस": 25, "pachchis": 25, "pachis": 25, "तीस": 30, "tees": 30,
    "पैंतीस": 35, "paintis": 35, "चालीस": 40, "chalis": 40,
    "पैंतालीस": 45, "paintalis": 45, "पचास": 50, "pachas": 50,
    "पचपन": 55, "pachpan": 55, "साठ": 60, "saath": 60, "sath": 60,
    "पैंसठ": 65, "painsath": 65, "सत्तर": 70, "sattar": 70,
    "पचहत्तर": 75, "pachhattar": 75, "अस्सी": 80, "assi": 80,
    "पचासी": 85, "pachasi": 85, "नब्बे": 90, "nabbe": 90,
    "पंचानवे": 95, "panchanve": 95, "सौ": 100, "sau": 100,
}

PERCENT_WORDS = {"%", "percent", "प्रतिशत", "परसेंट", "पर्सेंट", "pratishat", "persent", "parsent"}
# Number ke aas-paas ye shabd hon tabhi use charge % maana jaata hai.
# Isse "saath" (= with), "das", "2 ghante" jaise shabd galti se % nahi bante.
PERCENT_CONTEXT_WORDS = PERCENT_WORDS | {"charge", "charging", "चार्ज", "चार्जिंग", "battery", "बैटरी"}


def _has(text, words):
    return any(w in text for w in words)


def _tokens(text):
    return [tok for tok in re.split(r"[\s,.?!।]+", text.lower()) if tok]


def _token_number(tok):
    """Ek shabd ko number banata hai (60 / साठ / saath). Nahi bana to None."""
    if tok.isdigit():
        v = int(tok)
        return v if 0 <= v <= 100 else None
    return HINDI_NUMBERS.get(tok)


def extract_percent(text, lenient=False):
    """
    Baat mein se charge % nikalta hai. Nahi mila to None.
    Number tabhi liya jaata hai jab uske paas % / charge / battery jaisa shabd ho,
    ya poori baat sirf number ho (jaise sawaal ke jawab mein "saath").
    lenient=True: bot ne abhi % poochha tha, to koi bhi akela number chalega.
    """
    t = text.lower()
    m = re.search(r"(\d{1,3})\s*(?:%|percent|per cent|प्रतिशत|परसेंट|पर्सेंट|pratishat|persent|parsent)", t)
    if m:
        v = int(m.group(1))
        if 0 <= v <= 100:
            return v

    toks = _tokens(t)
    numbers = [(i, _token_number(tok)) for i, tok in enumerate(toks)]
    numbers = [(i, v) for i, v in numbers if v is not None]
    if not numbers:
        return None

    for i, v in numbers:
        nearby = toks[max(0, i - 2): i] + toks[i + 1: i + 3]
        if any(w in PERCENT_CONTEXT_WORDS for w in nearby):
            return v

    # Sirf number bola (ya number + "hai"/"percent"), jaise "saath" ya "60 hai"
    fillers = {"hai", "h", "है", "bhaiya", "भैया", "ji", "जी", "abhi", "अभी"}
    if len(numbers) == 1 and all(tok in fillers for j, tok in enumerate(toks) if j != numbers[0][0]):
        return numbers[0][1]

    if lenient and len(numbers) == 1:
        return numbers[0][1]
    return None


def _fmt_time(hours):
    total_min = int(round(hours * 60))
    h, m = divmod(total_min, 60)
    if h and m:
        return f"{h} घंटे {m} मिनट"
    if h:
        return f"{h} घंटे"
    return f"{m} मिनट"


def calculate(percent):
    """Range, charging time aur cost nikalta hai."""
    percent = max(0, min(100, percent))
    range_km = round(FULL_RANGE_KM * percent / 100)
    kwh_needed = BATTERY_KWH * (100 - percent) / 100 / CHARGE_EFFICIENCY
    hours = kwh_needed / CHARGER_KW
    cost = kwh_needed * TARIFF_RS_PER_UNIT
    return {
        "percent": percent,
        "range_km": range_km,
        "kwh_needed": round(kwh_needed, 2),
        "hours": hours,
        "time_text": _fmt_time(hours),
        "cost_rs": round(cost),
    }


# ---------------- Troubleshooting ----------------
TROUBLE_FLOWS = {
    "slow_charging": {
        "title": "चार्जिंग धीमी है",
        "steps": [
            "सबसे पहले चार्जर का प्लग और सॉकेट देखिए, ढीला या गंदा तो नहीं है। सूखे कपड़े से साफ करिए।",
            "एक्सटेंशन बोर्ड हटाकर सीधे दीवार के सॉकेट में चार्जर लगाइए।",
            "देखिए कि वोल्टेज कम तो नहीं है। शाम के समय अक्सर वोल्टेज गिर जाता है, तो रात में चार्ज करके देखिए।",
            "अगर फिर भी धीमा रहे तो बैटरी पुरानी हो सकती है। मैकेनिक से बैटरी चेक करवाइए।",
        ],
    },
    "range_drop": {
        "title": "रेंज कम हो गई है",
        "steps": [
            "टायर की हवा चेक करिए। कम हवा से रेंज काफी घट जाती है।",
            "ज्यादा सवारी या सामान से भी रेंज कम होती है, इसलिए लोड देखिए।",
            "बैटरी के तार और कनेक्शन ढीले या जंग लगे तो नहीं, यह देखिए।",
            "महीने में एक बार बैटरी को पूरा 100 प्रतिशत चार्ज करिए। इससे बैटरी संतुलित रहती है।",
            "फिर भी रेंज कम रहे तो बैटरी पुरानी हो चुकी हो सकती है, मैकेनिक को दिखाइए।",
        ],
    },
    "not_detecting": {
        "title": "चार्जर डिटेक्ट नहीं कर रहा",
        "steps": [
            "चार्जर की लाइट जल रही है या नहीं देखिए। नहीं जल रही तो सॉकेट में बिजली चेक करिए।",
            "चार्जर का कनेक्टर पूरा अंदर तक दबाकर लगाइए और पिन साफ करिए।",
            "दूसरे सॉकेट में लगाकर देखिए, और MCB या फ्यूज भी देख लीजिए।",
            "तार कटा या पिघला तो नहीं है, यह देखिए। टूटा तार हो तो चार्जर इस्तेमाल मत करिए।",
            "गीले हाथों से या पानी के पास चार्जर को हाथ मत लगाइए।",
        ],
    },
}


ORDINALS = ["पहला", "दूसरा", "तीसरा", "चौथा", "पाँचवाँ", "छठा", "सातवाँ"]


def _trouble_reply(kind, start=0, max_steps=3):
    """Troubleshooting ke steps, `start` number wale step se. Returns (reply, next_start)."""
    flow = TROUBLE_FLOWS[kind]
    steps = flow["steps"][start:start + max_steps]
    if start == 0:
        parts = [f"{flow['title']}, घबराइए मत। ये चीज़ें देखिए।"]
    else:
        parts = ["और उपाय ये हैं।"]
    for i, s in enumerate(steps, start=start):
        parts.append(f"{ORDINALS[i]}, {s}")
    next_start = start + len(steps)
    if next_start < len(flow["steps"]):
        parts.append("और भी उपाय हैं, चाहें तो बोलिए: और बताओ।")
    return " ".join(parts), next_start


# ---------------- Stations ----------------
def find_city(text):
    t = text.lower()
    for city, words in CITY_WORDS.items():
        if _has(t, words):
            return city
    return None


def _station_reply(city):
    if city is None:
        names = "، ".join(CITY_HINDI.values()).replace("،", ",")
        return f"आप किस शहर में हैं? मैं इन शहरों के डेमो चार्जिंग पॉइंट बता सकता हूँ: {names}।"
    items = STATIONS[city]
    parts = [f"{CITY_HINDI[city]} में ये चार्जिंग पॉइंट हैं।"]
    for s in items:
        opening_hours = s["open"]
        parts.append(f"{s['area']} पर, {s['price']} रुपये प्रति यूनिट, {s['slots']} स्लॉट, समय {opening_hours}।")
    return " ".join(parts)


# ---------------- Intent samajhna ----------------
# Dhyaan: "kitni der lagegi" / "kitna time lagega" sawaal hain, shikayat nahi. Isliye
# yahan sirf shikayat wale shabd hain; time ke sawaal TIME_WORDS mein hain.
SLOW_WORDS = ["slow", "dheere", "dhire", "dhima", "dheema", "धीमा", "धीमी", "धीरे", "bahut der", "बहुत देर",
              "bahut time", "बहुत टाइम", "bahut samay", "बहुत समय", "jyada time", "ज्यादा समय", "ज़्यादा समय"]
RANGE_DROP_WORDS = ["range kam", "range ghat", "kam chal", "kam chalti", "kam chalta", "mileage", "average kam",
                    "रेंज कम", "रेंज घट", "कम चल", "माइलेज", "ज्यादा नहीं चल", "jyada nahi chal"]
NOT_DETECT_WORDS = ["detect", "nahi pakad", "pakad nahi", "charger nahi", "charging nahi", "charge nahi ho",
                    "charge nahin", "light nahi", "led nahi", "कनेक्ट नहीं", "चार्ज नहीं", "चार्जर नहीं",
                    "डिटेक्ट", "नहीं पकड़", "लाइट नहीं", "चार्जिंग नहीं", "start nahi", "शुरू नहीं"]
STATION_WORDS = ["station", "charging point", "charging pt", "kahan charge", "kaha charge", "paas mein", "nearby",
                 "near", "स्टेशन", "चार्जिंग पॉइंट", "चार्जिंग प्वाइंट", "कहाँ चार्ज", "कहां चार्ज", "पास में",
                 "नज़दीक", "नजदीक", "kahan lagau", "कहाँ लगाऊं"]
RANGE_WORDS = ["kitna chal", "kitni door", "kitna door", "range", "km", "kilometer", "किलोमीटर", "कितना चल",
               "कितनी दूर", "रेंज", "कितना दूर", "चलेगा", "chalega", "chalegi"]
COST_WORDS = ["kharcha", "kharch", "paisa", "paise", "rupay", "rupee", "cost", "खर्चा", "खर्च", "पैसा", "पैसे",
              "रुपये", "रुपए", "kitne ka", "कितने का"]
TIME_WORDS = ["kitni der", "kitna time", "kitna samay", "ghante", "ghanta", "कितनी देर", "कितना समय",
              "कितना टाइम", "घंटे", "घंटा", "time lagega", "time lagta", "der lagegi", "der lagti",
              "देर लगेगी", "देर लगती", "टाइम लगेगा", "समय लगेगा"]
CALC_HINT_WORDS = ["charge hai", "charge h", "battery", "बैटरी", "चार्ज है", "percent", "%", "प्रतिशत", "परसेंट"]
GREETING_TOKENS = {"namaste", "namaskar", "hello", "hi", "hey", "helo", "नमस्ते", "नमस्कार", "हेलो", "हाय"}
GREETING_PHRASES = ["राम राम", "ram ram"]
MORE_WORDS = ["aur batao", "aur bataiye", "aur upay", "aur kuch", "aage", "more", "और बताओ", "और बताइए",
              "और उपाय", "और कुछ", "आगे"]
MORE_TOKENS = {"aur", "और"}


def _is_greeting(t):
    return bool(GREETING_TOKENS & set(_tokens(t))) or _has(t, GREETING_PHRASES)


def _asks_more(t):
    toks = _tokens(t)
    return _has(t, MORE_WORDS) or (bool(toks) and all(tok in MORE_TOKENS for tok in toks))


def _calc_reply(pct, wants_range, wants_cost, wants_time):
    r = calculate(pct)
    if not (wants_range or wants_cost or wants_time):
        wants_range = wants_cost = wants_time = True
    parts = [f"अभी {r['percent']} प्रतिशत चार्ज है।"]
    if wants_range:
        parts.append(f"इस पर करीब {r['range_km']} किलोमीटर चलेगा।")
    if r["percent"] >= 100:
        parts.append("बैटरी पूरी भरी हुई है।")
    else:
        if wants_time:
            parts.append(f"पूरा चार्ज होने में लगभग {r['time_text']} लगेंगे।")
        if wants_cost:
            parts.append(f"खर्चा करीब {r['cost_rs']} रुपये आएगा।")
    parts.append("रास्ते और सवारी के हिसाब से थोड़ा कम या ज़्यादा हो सकता है।")
    return {"intent": "calculator", "reply": " ".join(parts), "calc": r, "state": None}


def _trouble(kind, start=0):
    reply, next_start = _trouble_reply(kind, start)
    state = None
    if next_start < len(TROUBLE_FLOWS[kind]["steps"]):
        state = {"pending": "trouble_more", "kind": kind, "next": next_start}
    return {"intent": f"trouble_{kind}", "reply": reply, "state": state}


def respond(text, state=None):
    """
    Driver ki baat (text) + pichhli baat ka state -> {"intent", "reply", "state", ...}

    `state` ek chhota dict hai jo pichhle jawab ne lautaya tha (ya None). Isse bot
    follow-up samajhta hai, jaise:
      bot: "कितने प्रतिशत चार्ज है?"   driver: "saath"   -> calculation poori
      bot: "और भी उपाय हैं..."          driver: "aur batao" -> agle steps
    Jawab ka "state" agli baar wapas bhejiye.
    """
    state = state if isinstance(state, dict) else {}
    pending = state.get("pending")
    t = (text or "").strip().lower()
    if not t:
        return {"intent": "empty",
                "reply": "मुझे आवाज़ साफ़ नहीं सुनाई दी। कृपया दोबारा बोलिए।",
                "state": state or None}

    # 0) Follow-up: pichhle sawaal ka jawab
    if pending == "need_percent" and not find_city(t) and not _has(t, STATION_WORDS):
        pct = extract_percent(t, lenient=True)
        if pct is not None:
            wants = state.get("wants") or {}
            return _calc_reply(pct,
                               wants.get("range") or _has(t, RANGE_WORDS),
                               wants.get("cost") or _has(t, COST_WORDS),
                               wants.get("time") or _has(t, TIME_WORDS))
    if pending == "trouble_more" and _asks_more(t) and state.get("kind") in TROUBLE_FLOWS:
        return _trouble(state["kind"], int(state.get("next", 0)))

    pct = extract_percent(t)
    wants_range = _has(t, RANGE_WORDS)
    wants_cost = _has(t, COST_WORDS)
    wants_time = _has(t, TIME_WORDS)

    # 1) Troubleshooting (sabse pehle, kyunki "charge nahi" jaise words calculator se milte hain)
    if _has(t, NOT_DETECT_WORDS) and not _has(t, STATION_WORDS):
        return _trouble("not_detecting")
    if _has(t, RANGE_DROP_WORDS):
        return _trouble("range_drop")
    if _has(t, SLOW_WORDS) and ("charg" in t or "चार्ज" in t) and not (pct is not None and wants_time):
        return _trouble("slow_charging")

    # 2) Station dhundna
    city = find_city(t)
    if _has(t, STATION_WORDS) or (city and pct is None):
        return {"intent": "stations", "reply": _station_reply(city), "city": city,
                "state": {"pending": "city"} if city is None else None}

    # 3) Calculator
    if pct is not None and (wants_range or wants_cost or wants_time or _has(t, CALC_HINT_WORDS)):
        return _calc_reply(pct, wants_range, wants_cost, wants_time)

    # 4) Charge % nahi bataya par poochha
    if wants_range or wants_cost or wants_time:
        return {"intent": "need_percent",
                "reply": "अभी बैटरी कितने प्रतिशत चार्ज है? प्रतिशत बताइए, जैसे साठ प्रतिशत।",
                "state": {"pending": "need_percent",
                          "wants": {"range": wants_range, "cost": wants_cost, "time": wants_time}}}

    # 5) Namaste
    if _is_greeting(t):
        return {"intent": "greeting",
                "reply": "नमस्ते भैया! मैं आपका ई-रिक्शा सहायक हूँ। चार्ज के हिसाब से रेंज और खर्चा, चार्जिंग की दिक्कत, या पास का चार्जिंग पॉइंट, कुछ भी पूछिए।",
                "state": None}

    # 6) Samajh nahi aaya. Pichhla sawaal abhi bhi khula hai to state rakhte hain.
    return {"intent": "fallback",
            "reply": "माफ़ कीजिए, मैं समझ नहीं पाया। आप पूछ सकते हैं: साठ प्रतिशत चार्ज है, कितना चलेगा और कितना खर्चा आएगा? या, चार्जिंग धीमी क्यों है? या, जयपुर में चार्जिंग पॉइंट कहाँ है?",
            "state": state or None}


if __name__ == "__main__":
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
    tests += ["kitna kharcha aayega", "saath", "charging bahut slow hai", "aur batao"]
    state = None
    for q in tests:
        r = respond(q, state)
        state = r.get("state")
        print("Q:", q)
        print("  ->", r["intent"], "|", r["reply"], "\n")
