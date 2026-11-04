# SYNTHETIC (nakli) charging station data - sirf demo ke liye.
# Koi real jagah, number ya address nahi hai.

STATIONS = {
    "jaipur": [
        {"name": "Demo Charge Point - Station Road", "area": "Station Road", "price": 9, "slots": 4, "open": "6 AM - 10 PM"},
        {"name": "Demo EV Hub - Bus Stand", "area": "Bus Stand", "price": 8, "slots": 6, "open": "24 hours"},
        {"name": "Demo Quick Charge - Mandi", "area": "Sabzi Mandi", "price": 10, "slots": 2, "open": "7 AM - 9 PM"},
    ],
    "bhopal": [
        {"name": "Demo Charge Point - Railway Station", "area": "Railway Station", "price": 9, "slots": 5, "open": "24 hours"},
        {"name": "Demo EV Hub - New Market", "area": "New Market", "price": 10, "slots": 3, "open": "6 AM - 11 PM"},
        {"name": "Demo Quick Charge - Bus Stand", "area": "ISBT", "price": 8, "slots": 4, "open": "6 AM - 10 PM"},
    ],
    "udaipur": [
        {"name": "Demo Charge Point - Surajpole", "area": "Surajpole", "price": 9, "slots": 3, "open": "6 AM - 10 PM"},
        {"name": "Demo EV Hub - Chetak Circle", "area": "Chetak Circle", "price": 10, "slots": 4, "open": "24 hours"},
        {"name": "Demo Quick Charge - Bus Stand", "area": "Roadways Bus Stand", "price": 8, "slots": 2, "open": "7 AM - 9 PM"},
    ],
    "bharatpur": [
        {"name": "Demo Charge Point - Bus Stand", "area": "Bus Stand", "price": 8, "slots": 3, "open": "6 AM - 10 PM"},
        {"name": "Demo EV Hub - Mathura Gate", "area": "Mathura Gate", "price": 9, "slots": 4, "open": "24 hours"},
        {"name": "Demo Quick Charge - Ganga Mandir", "area": "Ganga Mandir Road", "price": 10, "slots": 2, "open": "7 AM - 9 PM"},
    ],
    "indore": [
        {"name": "Demo Charge Point - Rajwada", "area": "Rajwada", "price": 10, "slots": 4, "open": "6 AM - 11 PM"},
        {"name": "Demo EV Hub - Sarafa", "area": "Sarafa", "price": 9, "slots": 3, "open": "24 hours"},
        {"name": "Demo Quick Charge - Bus Stand", "area": "Sarwate", "price": 8, "slots": 5, "open": "6 AM - 10 PM"},
    ],
}

# Bolne mein shehar ke naam Roman aur Devanagari dono mein aa sakte hain
CITY_WORDS = {
    "jaipur": ["jaipur", "जयपुर"],
    "bhopal": ["bhopal", "भोपाल"],
    "udaipur": ["udaipur", "उदयपुर"],
    "bharatpur": ["bharatpur", "भरतपुर"],
    "indore": ["indore", "इंदौर", "इन्दौर"],
}

CITY_HINDI = {
    "jaipur": "जयपुर",
    "bhopal": "भोपाल",
    "udaipur": "उदयपुर",
    "bharatpur": "भरतपुर",
    "indore": "इंदौर",
}

# ---------------- Trip feasibility ke liye DEMO routes ----------------
# Doori lagbhag (approximate) road km hai, sirf demo ke liye. Asli trip se pehle map par check karein.
DEMO_ROUTES = {
    ("jaipur", "chomu"): 33,
    ("bhopal", "sehore"): 38,
    ("udaipur", "nathdwara"): 48,
    ("bharatpur", "deeg"): 35,
    ("indore", "dewas"): 38,
    ("indore", "mhow"): 23,
}

# Shehar + aas-paas ke kasbe, Roman aur Devanagari dono
PLACE_WORDS = dict(CITY_WORDS)
PLACE_WORDS.update({
    "chomu": ["chomu", "चौमूं", "चौमू"],
    "sehore": ["sehore", "सीहोर"],
    "nathdwara": ["nathdwara", "नाथद्वारा"],
    "deeg": ["deeg", "डीग"],
    "dewas": ["dewas", "देवास"],
    "mhow": ["mhow", "महू"],
})

PLACE_HINDI = dict(CITY_HINDI)
PLACE_HINDI.update({
    "chomu": "चौमूं",
    "sehore": "सीहोर",
    "nathdwara": "नाथद्वारा",
    "deeg": "डीग",
    "dewas": "देवास",
    "mhow": "महू",
})

# Bolne ke liye area ke Hindi naam (replies Devanagari mein rehte hain). Demo data.
AREA_HINDI = {
    "Station Road": "स्टेशन रोड", "Bus Stand": "बस स्टैंड", "Sabzi Mandi": "सब्ज़ी मंडी",
    "Railway Station": "रेलवे स्टेशन", "New Market": "न्यू मार्केट", "ISBT": "आईएसबीटी",
    "Surajpole": "सूरजपोल", "Chetak Circle": "चेतक सर्कल", "Roadways Bus Stand": "रोडवेज़ बस स्टैंड",
    "Mathura Gate": "मथुरा गेट", "Ganga Mandir Road": "गंगा मंदिर रोड",
    "Rajwada": "राजवाड़ा", "Sarafa": "सराफा", "Sarwate": "सरवटे",
}
