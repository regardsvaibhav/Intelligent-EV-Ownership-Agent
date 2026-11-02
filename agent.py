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
    "पंचानवे": 95, "सौ": 100, "sau": 100,
}


def _has(text, words):
    return any(w in text for w in words)


def extract_percent(text):
    """Baat mein se charge % nikalta hai. Nahi mila to None."""
    t = text.lower()
    m = re.search(r"(\d{1,3})\s*(?:%|percent|per cent|प्रतिशत|परसेंट|पर्सेंट|pratishat|persent)", t)
    if m:
        v = int(m.group(1))
        if 0 <= v <= 100:
            return v
    for tok in re.split(r"[\s,.?!]+", t):
        if tok in HINDI_NUMBERS:
            return HINDI_NUMBERS[tok]
    m = re.search(r"\b(\d{1,3})\b", t)
    if m:
        v = int(m.group(1))
        if 1 <= v <= 100:
            return v
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


def _trouble_reply(kind, max_steps=3):
    flow = TROUBLE_FLOWS[kind]
    steps = flow["steps"][:max_steps]
    ordinals = ["पहला", "दूसरा", "तीसरा"]
    parts = [f"{flow['title']}, घबराइए मत। ये चीज़ें देखिए।"]
    for i, s in enumerate(steps):
        parts.append(f"{ordinals[i]}, {s}")
    if len(flow["steps"]) > max_steps:
        parts.append("और भी उपाय हैं, चाहें तो फिर से पूछिए।")
    return " ".join(parts)


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
SLOW_WORDS = ["slow", "dheere", "dhire", "dhima", "देर", "धीमा", "धीमी", "धीरे", "der lag", "bahut time", "time lag"]
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
              "कितना टाइम", "घंटे", "घंटा", "time lagega", "देर लगेगी"]
CALC_HINT_WORDS = ["charge hai", "charge h", "battery", "बैटरी", "चार्ज है", "percent", "%", "प्रतिशत", "परसेंट"]
GREETING_WORDS = ["namaste", "namaskar", "hello", "hi ", "नमस्ते", "नमस्कार", "हेलो", "राम राम", "ram ram"]


def respond(text):
    """
    Driver ki baat (text) -> {"intent": ..., "reply": ...}
    """
    t = (text or "").strip().lower()
    if not t:
        return {"intent": "empty",
                "reply": "मुझे आवाज़ साफ़ नहीं सुनाई दी। कृपया दोबारा बोलिए।"}

    # 1) Troubleshooting (sabse pehle, kyunki "charge nahi" jaise words calculator se milte hain)
    if _has(t, NOT_DETECT_WORDS) and not _has(t, STATION_WORDS):
        return {"intent": "trouble_not_detecting", "reply": _trouble_reply("not_detecting")}
    if _has(t, RANGE_DROP_WORDS):
        return {"intent": "trouble_range_drop", "reply": _trouble_reply("range_drop")}
    if _has(t, SLOW_WORDS) and ("charg" in t or "चार्ज" in t):
        return {"intent": "trouble_slow_charging", "reply": _trouble_reply("slow_charging")}

    # 2) Station dhundna
    city = find_city(t)
    if _has(t, STATION_WORDS) or (city and not extract_percent(t)):
        return {"intent": "stations", "reply": _station_reply(city), "city": city}

    # 3) Calculator
    pct = extract_percent(t)
    wants_range = _has(t, RANGE_WORDS)
    wants_cost = _has(t, COST_WORDS)
    wants_time = _has(t, TIME_WORDS)
    if pct is not None and (wants_range or wants_cost or wants_time or _has(t, CALC_HINT_WORDS)):
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
        return {"intent": "calculator", "reply": " ".join(parts), "calc": r}

    # 4) Charge % nahi bataya par poochha
    if wants_range or wants_cost or wants_time:
        return {"intent": "need_percent",
                "reply": "अभी बैटरी कितने प्रतिशत चार्ज है? प्रतिशत बताइए, जैसे साठ प्रतिशत।"}

    # 5) Namaste
    if _has(t, GREETING_WORDS):
        return {"intent": "greeting",
                "reply": "नमस्ते भैया! मैं आपका ई-रिक्शा सहायक हूँ। चार्ज के हिसाब से रेंज और खर्चा, चार्जिंग की दिक्कत, या पास का चार्जिंग पॉइंट, कुछ भी पूछिए।"}

    # 6) Samajh nahi aaya
    return {"intent": "fallback",
            "reply": "माफ़ कीजिए, मैं समझ नहीं पाया। आप पूछ सकते हैं: साठ प्रतिशत चार्ज है, कितना चलेगा और कितना खर्चा आएगा? या, चार्जिंग धीमी क्यों है? या, जयपुर में चार्जिंग पॉइंट कहाँ है?"}


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
    for q in tests:
        r = respond(q)
        print("Q:", q)
        print("  ->", r["intent"], "|", r["reply"], "\n")
