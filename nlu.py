"""
Rule-based NLU: text normalization, Hindi number parsing and slot extraction.

Everything here is offline and deterministic. Matching is done on TOKENS, not raw
substrings, so "near" does not match "nearly" and "chal" does not match "chalan".
(Python's regex \\b does not work reliably inside Devanagari words because vowel
signs are not \\w characters, so token matching is used instead.)
"""
import re
import unicodedata
from dataclasses import dataclass, field

from stations import PLACE_WORDS, STATIONS

# --------------------------------------------------------------------------
# Normalization
# --------------------------------------------------------------------------
_DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

# Spelling variants -> one canonical token. Loanwords are mapped to their
# romanized form so a pattern like ("charge", "nahi") also covers "चार्ज नहीं"
# written in mixed script. Hindi words stay in their own script.
VARIANTS = {
    # loanwords (Devanagari -> canonical roman)
    "चार्ज": "charge", "चार्जर": "charger", "चार्जिंग": "charging", "चारजिंग": "charging",
    "बैटरी": "battery", "बेटरी": "battery", "स्टेशन": "station", "रेंज": "range",
    "किलोमीटर": "km", "किमी": "km", "केएम": "km", "प्रतिशत": "percent", "परसेंट": "percent",
    "पर्सेंट": "percent", "परसेन्ट": "percent", "पॉइंट": "point", "प्वाइंट": "point", "पॉइन्ट": "point",
    "टाइम": "time", "माइलेज": "mileage", "डिटेक्ट": "detect", "करंट": "current", "शॉक": "shock",
    "सीएनजी": "cng", "पेट्रोल": "petrol", "डीजल": "diesel", "लाइट": "light", "प्लग": "plug",
    "सॉकेट": "socket", "वायर": "wire", "कनेक्ट": "connect", "फुल": "full", "बिल": "bill",
    "स्लो": "slow", "स्पार्क": "spark", "मोटर": "motor", "ट्रिप": "trip", "हेलो": "hello",
    "हैलो": "hello", "ओके": "ok", "नेक्स्ट": "next", "सेविंग": "saving", "मीटर": "meter",
    # romanized spelling variants
    "charj": "charge", "chaarj": "charge", "chargeing": "charging", "chargin": "charging",
    "batery": "battery", "battary": "battery", "battry": "battery", "betri": "battery", "baitri": "battery",
    "kms": "km", "kilometer": "km", "kilometre": "km", "kilomitar": "km", "kilometers": "km",
    "percentage": "percent", "pratishat": "percent", "persent": "percent", "parsent": "percent",
    "prcent": "percent", "pc": "percent", "%": "percent",
    "nahin": "nahi", "nhi": "nahi", "nahee": "nahi", "nai": "nahi",
    "kahaan": "kahan", "kaha": "kahan", "kahaa": "kahan",
    "nahi.": "nahi", "नही": "नहीं", "नई": "नहीं",
    "milage": "mileage", "millage": "mileage", "station.": "station",
}


def normalize(text):
    """
    Lowercase, unify Unicode forms, drop nukta/chandrabindu differences, convert
    Devanagari digits, strip punctuation (keeping decimals like 2.5), split
    "60km" -> "60 km", map spelling variants, collapse whitespace.
    """
    if not text:
        return ""
    s = unicodedata.normalize("NFC", str(text)).lower()
    s = s.translate(_DEV_DIGITS)
    s = s.replace("़", "")          # nukta: ज़ -> ज, ड़ -> ड, फ़ -> फ
    s = s.replace("ँ", "ं")    # chandrabindu -> anusvara: हाँ -> हां
    s = s.replace("।", " ").replace("॥", " ")   # । ॥
    s = s.replace("‌", "").replace("‍", "")     # zero-width joiners
    s = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", s)             # dots that are not decimals
    s = re.sub(r"[^\w\s%.ऀ-ॿ]", " ", s)          # other punctuation
    s = s.replace("%", " % ")
    s = re.sub(r"(\d)(?=[^\d\s.])", r"\1 ", s)             # 60km -> 60 km
    s = re.sub(r"([^\d\s.])(?=\d)", r"\1 ", s)             # km60 -> km 60
    toks = [VARIANTS.get(t, t) for t in s.split()]
    return " ".join(toks)


def tokens_of(text_norm):
    return text_norm.split() if text_norm else []


# --------------------------------------------------------------------------
# Hindi numbers 0-100 (Devanagari + common romanized spellings)
# --------------------------------------------------------------------------
_NUMBER_WORDS = {
    0: ["शून्य", "zero", "shunya", "sunya"],
    1: ["एक", "ek"], 2: ["दो", "do"], 3: ["तीन", "teen", "tin"], 4: ["चार", "char", "chaar"],
    5: ["पांच", "पाँच", "panch", "paanch", "paach"], 6: ["छह", "छः", "छे", "छै", "chhah", "chhe", "che", "chah"],
    7: ["सात", "saat", "sat"], 8: ["आठ", "aath", "ath"], 9: ["नौ", "nau"], 10: ["दस", "das"],
    11: ["ग्यारह", "gyarah", "gyara"], 12: ["बारह", "barah", "bara"], 13: ["तेरह", "terah", "tera"],
    14: ["चौदह", "chaudah", "chauda"], 15: ["पंद्रह", "पन्द्रह", "pandrah", "pandra"],
    16: ["सोलह", "solah", "sola"], 17: ["सत्रह", "satrah", "satra"], 18: ["अठारह", "atharah", "athara"],
    19: ["उन्नीस", "unnis", "unees", "unnees"], 20: ["बीस", "bees", "bis"],
    21: ["इक्कीस", "ikkis", "ikkees"], 22: ["बाईस", "bais", "baees", "baais"], 23: ["तेईस", "teis", "teees"],
    24: ["चौबीस", "chaubis", "chaubees"], 25: ["पच्चीस", "pachchis", "pachis", "pachees", "pachchees"],
    26: ["छब्बीस", "chhabbis", "chabbis"], 27: ["सत्ताईस", "sattais", "sattaees"],
    28: ["अट्ठाईस", "अठ्ठाईस", "अट्ठाइस", "atthais", "athais", "athaees"], 29: ["उनतीस", "untis", "unatis"],
    30: ["तीस", "tees", "tis"], 31: ["इकतीस", "iktis", "ikattis"], 32: ["बत्तीस", "battis"],
    33: ["तैंतीस", "taintis", "tentis"], 34: ["चौंतीस", "chauntis", "chautis"],
    35: ["पैंतीस", "paintis", "pentis"], 36: ["छत्तीस", "chhattis", "chattis"],
    37: ["सैंतीस", "saintis", "sentis"], 38: ["अड़तीस", "अडतीस", "adtis", "artis", "adatis"],
    39: ["उनतालीस", "untalis", "unchalis"], 40: ["चालीस", "chalis", "chaalis"],
    41: ["इकतालीस", "iktalis"], 42: ["बयालीस", "bayalis", "byalis"],
    43: ["तैंतालीस", "taintalis", "tentalis"], 44: ["चवालीस", "चौवालीस", "chavalis", "chawalis", "chauvalis"],
    45: ["पैंतालीस", "paintalis", "pentalis"], 46: ["छियालीस", "chhiyalis", "chiyalis"],
    47: ["सैंतालीस", "saintalis", "sentalis"], 48: ["अड़तालीस", "adtalis", "artalis"],
    49: ["उनचास", "unchas"], 50: ["पचास", "pachas", "pachaas"],
    51: ["इक्यावन", "ikyavan", "ikyawan"], 52: ["बावन", "bavan", "bawan"],
    53: ["तिरेपन", "तिरपन", "tirepan", "tirpan"], 54: ["चौवन", "चौव्वन", "chauvan", "chauwan"],
    55: ["पचपन", "pachpan"], 56: ["छप्पन", "chhappan", "chappan"],
    57: ["सत्तावन", "sattavan", "sattawan"], 58: ["अट्ठावन", "atthavan", "athawan", "athavan"],
    59: ["उनसठ", "unsath"], 60: ["साठ", "saath", "sath"],
    61: ["इकसठ", "iksath"], 62: ["बासठ", "basath", "bassath"], 63: ["तिरेसठ", "तिरसठ", "tiresath", "tirsath"],
    64: ["चौंसठ", "chaunsath", "chausath"], 65: ["पैंसठ", "painsath", "pensath"],
    66: ["छियासठ", "chhiyasath", "chiyasath"], 67: ["सड़सठ", "sadsath", "sarsath"],
    68: ["अड़सठ", "adsath", "arsath"], 69: ["उनहत्तर", "unhattar"], 70: ["सत्तर", "sattar"],
    71: ["इकहत्तर", "ikhattar"], 72: ["बहत्तर", "bahattar"], 73: ["तिहत्तर", "tihattar"],
    74: ["चौहत्तर", "chauhattar"], 75: ["पचहत्तर", "pachhattar", "pachattar"],
    76: ["छिहत्तर", "chhihattar", "chihattar"], 77: ["सतहत्तर", "sathattar", "satattar"],
    78: ["अठहत्तर", "athhattar", "athattar"], 79: ["उन्यासी", "उनासी", "unyasi", "unasi"],
    80: ["अस्सी", "assi", "asi"], 81: ["इक्यासी", "ikyasi"], 82: ["बयासी", "bayasi"],
    83: ["तिरासी", "tirasi"], 84: ["चौरासी", "chaurasi"], 85: ["पचासी", "pachasi"],
    86: ["छियासी", "chhiyasi"], 87: ["सत्तासी", "sattasi"], 88: ["अट्ठासी", "atthasi", "athasi"],
    89: ["नवासी", "navasi", "nawasi"], 90: ["नब्बे", "nabbe"],
    91: ["इक्यानबे", "इक्यानवे", "ikyanbe", "ikyanve"], 92: ["बानबे", "बानवे", "banbe", "banve"],
    93: ["तिरानबे", "तिरानवे", "tiranbe", "tiranve"], 94: ["चौरानबे", "चौरानवे", "chauranbe", "chauranve"],
    95: ["पंचानबे", "पंचानवे", "panchanbe", "panchanve"], 96: ["छियानबे", "छियानवे", "chhiyanbe", "chhiyanve"],
    97: ["सत्तानबे", "सत्तानवे", "sattanbe", "sattanve"], 98: ["अट्ठानबे", "अट्ठानवे", "atthanbe", "atthanve"],
    99: ["निन्यानबे", "निन्यानवे", "ninyanbe", "ninyanve"], 100: ["सौ", "sau"],
}

NUMBER_WORDS = {}
for _value, _words in _NUMBER_WORDS.items():
    for _w in _words:
        NUMBER_WORDS[normalize(_w)] = _value

# Romanized words that are ALSO common Hindi words ("saath" = with, "do" = give,
# "ek" = a, "sau"/"das" in prices...). These count as numbers only when they sit
# right next to a unit ("saath percent") or when the agent asked for a number.
AMBIGUOUS_NUMBER_WORDS = {"saath", "sath", "sat", "do", "ek", "nau", "tin", "char", "chaar", "che", "chhe",
                          "das", "sau", "bis", "tis", "asi", "ath", "bara", "tera", "sola"}

PERCENT_UNITS = {"percent"}
KM_UNITS = {"km"}
PASSENGER_UNITS_PREFIX = ("सवारी", "savari", "sawari", "sawaari", "savaari", "passenger", "aadmi", "आदमी",
                          "लोग", "log", "बंदे", "bande", "सवारियां", "sawariyan", "savariyan")
CHARGE_CUES = {"charge", "battery", "charging"}
NO_WORDS = {"nahi", "no", "galat", "नहीं", "गलत", "nope"}
SHORT_NO_WORDS = {"na", "ना"}        # "ना" is also a tag particle ("सही है ना"), so only in short replies
YES_WORDS = {"haan", "han", "haa", "ha", "ji", "jee", "sahi", "ok", "okay", "theek", "thik", "bilkul", "yes",
             "हां", "हा", "जी", "सही", "ठीक", "बिल्कुल", "हांजी", "haanji", "hanji"}

NUMBER_FUZZY_THRESHOLD = 75

# Optional fuzzy matching (rapidfuzz). The agent works without it.
try:
    from rapidfuzz import fuzz as _fuzz
except ImportError:      # pragma: no cover
    _fuzz = None


def fuzzy_ratio(a, b):
    if _fuzz is None:
        return 0.0
    return _fuzz.ratio(a, b)


def _fuzzy_number(tok, threshold):
    """Closest number word if the token looks like a misheard one (e.g. 'बासट')."""
    if _fuzz is None or len(tok) < 3:
        return None
    scores = {}
    for w, v in NUMBER_WORDS.items():
        if len(w) >= 3:
            scores[v] = max(scores.get(v, 0), _fuzz.ratio(tok, w))
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    if not ranked or ranked[0][1] < threshold:
        return None
    if len(ranked) > 1 and ranked[1][1] == ranked[0][1]:
        return None        # e.g. "बासट" is equally close to बासठ (62) and बाईस (22): don't guess
    return ranked[0][0]


# --------------------------------------------------------------------------
# Pattern matching on tokens
# --------------------------------------------------------------------------
def _tok_match(tok, pat, fuzzy_threshold):
    """Returns 'exact', 'fuzzy' or None. A pattern token ending in '*' is a prefix."""
    if pat.endswith("*"):
        return "exact" if tok.startswith(pat[:-1]) else None
    if tok == pat:
        return "exact"
    if fuzzy_threshold and len(pat) >= 4 and len(tok) >= 4 and not tok.isdigit():
        if fuzzy_ratio(tok, pat) >= fuzzy_threshold:
            return "fuzzy"
    return None


def find_phrase(tokens, phrase, fuzzy_threshold=0):
    """
    Finds a contiguous token phrase. Returns (start_index, used_fuzzy) or None.
    phrase is a tuple of normalized pattern tokens.
    """
    n = len(phrase)
    for i in range(len(tokens) - n + 1):
        used_fuzzy = False
        for j in range(n):
            m = _tok_match(tokens[i + j], phrase[j], fuzzy_threshold)
            if m is None:
                break
            if m == "fuzzy":
                used_fuzzy = True
        else:
            return i, used_fuzzy
    return None


def compile_patterns(raw):
    """[('kitna chal*', 1.0), ...] -> [(('kitna','chal*'), 1.0), ...], normalizing each token."""
    out = []
    for phrase, weight in raw:
        toks = []
        for t in phrase.split():
            star = t.endswith("*")
            nt = normalize(t[:-1] if star else t)
            toks.append(nt + ("*" if star else ""))
        out.append((tuple(toks), weight))
    return out


def has_any(tokens, phrases, fuzzy_threshold=0):
    return any(find_phrase(tokens, p, fuzzy_threshold) for p, _ in phrases)


# --------------------------------------------------------------------------
# Places
# --------------------------------------------------------------------------
_PLACE_TOKENS = {}
for _place, _words in PLACE_WORDS.items():
    for _w in _words:
        _PLACE_TOKENS[normalize(_w)] = _place


def find_places(tokens):
    """Known cities/towns in the order they were spoken (exact token match)."""
    seen = []
    for t in tokens:
        p = _PLACE_TOKENS.get(t)
        if p and p not in seen:
            seen.append(p)
    return seen


# --------------------------------------------------------------------------
# Slot extraction
# --------------------------------------------------------------------------
@dataclass
class Slots:
    percent: int | None = None
    percent_conf: str | None = None      # "high" or "low" (low -> read back before use)
    percent_override: bool = False       # "नहीं, सत्तर" style correction
    km: float | None = None
    passengers: int | None = None
    places: list = field(default_factory=list)
    city: str | None = None              # first spoken place that has demo stations
    range_before: float | None = None
    range_after: float | None = None
    yes: bool = False
    no: bool = False
    next_step: bool = False
    fixed: bool = False
    numbers: list = field(default_factory=list)   # [(value, kind, index, is_word)]


_FIXED = compile_patterns([(p, 1) for p in [
    "theek ho gaya", "thik ho gaya", "ठीक हो गया", "ठीक हो गई", "chal gaya", "चल गया", "chal gayi", "चल गई",
    "chalu ho gaya", "चालू हो गया", "sahi ho gaya", "सही हो गया", "ban gaya", "बन गया", "solve", "fix ho gaya",
    "ho gayi charge", "charge hone laga", "charge होने लगा", "chalne lagi", "चलने लगी", "theek hai ab", "ठीक है अब"]])
_NEXT = compile_patterns([(p, 1) for p in [
    "agla", "agle", "अगला", "अगले", "next", "aage", "आगे", "ho gaya", "हो गया", "ho gayi", "हो गई", "kar liya",
    "कर लिया", "kar diya", "कर दिया", "dekh liya", "देख लिया", "nahi hua", "नहीं हुआ", "abhi bhi", "अभी भी",
    "phir bhi", "फिर भी", "aur batao", "और बताओ", "और बताइए", "aur upay", "और उपाय"]])
_RANGE_PAIR_WORDS = {"se", "से", "pehle", "पहले", "ab", "अब", "थी", "thi", "tha", "था"}


def _number_at(tokens, i, allow_ambiguous, fuzzy_threshold=0):
    """(value, is_word, consumed, fuzzy) for a number starting at tokens[i], else None."""
    t = tokens[i]
    if re.fullmatch(r"\d{1,4}(\.\d+)?", t):
        return float(t), False, 1, False
    nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
    if t in ("एक", "ek") and nxt in ("सौ", "sau"):
        return 100.0, True, 2, False
    if t in NUMBER_WORDS:
        unit_next = nxt in PERCENT_UNITS or nxt in KM_UNITS or nxt.startswith(PASSENGER_UNITS_PREFIX)
        if t in AMBIGUOUS_NUMBER_WORDS and not (allow_ambiguous or unit_next):
            return None
        return float(NUMBER_WORDS[t]), True, 1, False
    if fuzzy_threshold and not re.search(r"\d", t):
        v = _fuzzy_number(t, fuzzy_threshold)
        if v is not None:
            return float(v), True, 1, True
    return None


def extract_slots(tokens, pending=None, fuzzy_threshold=85):
    """
    Pulls percent, km, passengers, places, range before/after and yes/no/next out of tokens.
    `pending` is the slot the agent just asked for: only then is a bare number
    (or an ambiguous word like "saath") accepted as that slot.
    """
    s = Slots()
    numbers = []          # (value, kind, index, is_word, fuzzy)
    i = 0
    allow_amb = pending in ("percent", "km", "km_driven", "confirm_percent", "range_before", "passengers")
    while i < len(tokens):
        # Fuzzy number words only when a number was asked for; short Devanagari words differ by
        # one letter at ratio ~75, and anything fuzzy is read back to the driver anyway.
        fz_thr = NUMBER_FUZZY_THRESHOLD if (fuzzy_threshold and pending in ("percent", "confirm_percent")) else 0
        got = _number_at(tokens, i, allow_amb, fz_thr)
        if not got:
            i += 1
            continue
        value, is_word, used, fz = got
        nxt = tokens[i + used] if i + used < len(tokens) else ""
        nxt2 = tokens[i + used + 1] if i + used + 1 < len(tokens) else ""
        kind = None
        if nxt in PERCENT_UNITS:
            kind = "percent"
        elif nxt in KM_UNITS or (nxt in ("kilo", "किलो") and nxt2 in ("meter", "मीटर")):
            kind = "km"
        elif nxt.startswith(PASSENGER_UNITS_PREFIX):
            kind = "passengers"
        numbers.append((value, kind, i, is_word, fz))
        i += used
    s.numbers = [(v, k, idx, w) for v, k, idx, w, _ in numbers]

    has_cue = any(t in CHARGE_CUES or t in PERCENT_UNITS for t in tokens)

    # percent: 1) number with a % unit  2) with a charge cue  3) pending question
    for v, k, idx, w, fz in numbers:
        if k == "percent" and 0 <= v <= 100:
            s.percent, s.percent_conf = int(v), "high"
            break
    if s.percent is None:
        free = [(v, idx, w, fz) for v, k, idx, w, fz in numbers if k is None and 0 <= v <= 100]
        if free and (has_cue or pending in ("percent", "confirm_percent")):
            v, idx, w, fz = free[0]
            tok = tokens[idx]
            low = fz or (w and not has_cue) or tok in AMBIGUOUS_NUMBER_WORDS
            s.percent, s.percent_conf = int(v), ("low" if low else "high")

    # "नहीं, सत्तर" -> correction. The number right after the "no" is taken as the new percent,
    # even without a cue, because the driver is explicitly correcting the agent.
    if len(tokens) >= 2 and (tokens[0] in NO_WORDS or tokens[0] in SHORT_NO_WORDS):
        got = _number_at(tokens, 1, True)
        if got and 0 <= got[0] <= 100 and (s.percent is None or s.percent == int(got[0])):
            nxt = tokens[1 + got[2]] if 1 + got[2] < len(tokens) else ""
            if nxt not in KM_UNITS and not nxt.startswith(PASSENGER_UNITS_PREFIX):
                s.percent = int(got[0])
        if s.percent is not None:
            s.percent_override = True
            s.percent_conf = "high"      # an explicit correction is taken as confirmed

    for v, k, idx, w, fz in numbers:
        if k == "km" and s.km is None:
            s.km = v
        elif k == "passengers" and s.passengers is None and 0 <= v <= 20:
            s.passengers = int(v)
    if s.km is None and pending in ("km", "km_driven"):
        free = [v for v, k, idx, w, fz in numbers if k is None]
        if free:
            s.km = free[0]

    # range before/after: "90 से 65", "पहले 90 चलती थी अब 60"
    plain = [(v, idx) for v, k, idx, w, fz in numbers if k in (None, "km") and v > 0]
    if len(plain) >= 2 and s.percent is None:
        (a, ia), (b, ib) = plain[0], plain[1]
        between = set(tokens[ia + 1:ib]) | set(tokens[max(0, ia - 2):ia])
        if between & _RANGE_PAIR_WORDS and a > b and a <= 300:
            s.range_before, s.range_after = a, b

    s.places = find_places(tokens)
    s.city = next((p for p in s.places if p in STATIONS), None)

    tokset = set(tokens)
    s.fixed = has_any(tokens, _FIXED)
    s.next_step = (not s.fixed) and has_any(tokens, _NEXT)
    s.no = bool(tokset & NO_WORDS) or (len(tokens) <= 2 and bool(tokset & SHORT_NO_WORDS))
    s.yes = (not s.no) and bool(tokset & YES_WORDS)
    return s


def extract_percent(text, pending=None):
    """Convenience: charge % from raw text, or None (cue-aware, see extract_slots)."""
    return extract_slots(tokens_of(normalize(text)), pending=pending).percent
