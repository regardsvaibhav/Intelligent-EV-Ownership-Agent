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
