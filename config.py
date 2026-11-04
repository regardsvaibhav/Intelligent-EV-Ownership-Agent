"""
All tunable numbers in one place.

Every vehicle value below is an ASSUMPTION for a typical Indian lithium e-rickshaw,
not a measurement. Change them for your vehicle; the agent reads nothing else.
"""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class VehicleConfig:
    # --- Battery and range ---
    battery_kwh: float = 7.2            # usable pack energy (assumption)
    full_range_km: float = 90.0         # km at 100% charge with `rated_passengers`, flat road (assumption)
    battery_age_factor: float = 1.0     # 1.0 = new pack; 0.8 = old pack holds ~80% (assumption, set per vehicle)

    # --- Load derating (simple linear assumption, NOT measured) ---
    rated_passengers: int = 2           # load at which full_range_km is quoted
    derate_per_extra_passenger: float = 0.04   # -4% range per passenger above rated_passengers
    max_passengers: int = 6

    # --- Charging ---
    charger_kw: float = 1.2             # charger output
    efficiency: float = 0.90            # wall-to-battery efficiency (~10% loss)
    taper_start_pct: int = 80           # above this, charger slows down (CC -> CV phase, assumption)
    taper_power_factor: float = 0.6     # average power above taper_start = 60% of charger_kw (assumption)
    tariff_rs_per_unit: float = 8.0     # electricity price, Rs per kWh (assumption)

    # --- Trip planning ---
    trip_buffer: float = 0.15           # keep 15% extra range for hills, load, detours

    # --- Fuel comparison for savings (assumptions, change to local prices) ---
    petrol_rs_per_km: float = 105.0 / 25.0    # Rs 105/litre, petrol auto 25 km/litre
    cng_rs_per_km: float = 85.0 / 30.0        # Rs 85/kg, CNG auto 30 km/kg
    work_days_per_month: int = 26


DEFAULT_CONFIG = VehicleConfig()

# --- NLU settings ---
INTENT_THRESHOLD = 1.0      # min score to act on an intent without asking
CLARIFY_MARGIN = 0.5        # if top-2 scores are closer than this, ask which one
WEAK_EVIDENCE = 0.5         # below this, treat as "not understood"
FUZZY_THRESHOLD = 85        # rapidfuzz ratio needed to count a misspelt keyword
FUZZY_WEIGHT = 0.7          # a fuzzy keyword hit counts for 70% of an exact hit
MAX_FAILURES_BEFORE_SIMPLE_PROMPT = 2

# Kept for compatibility. A fallback classifier is used whenever one is registered with
# agent.register_fallback_classifier(); app.py registers llm_fallback.classify when
# LLM_API_KEY (or GEMINI_API_KEY) is set (see README, "LLM fallback").
USE_EMBEDDINGS = False

# Per-turn JSONL log. Set EV_AGENT_LOG_PATH="" to disable (tests do this).
LOG_PATH = os.environ.get("EV_AGENT_LOG_PATH", os.path.join("logs", "turns.jsonl"))
