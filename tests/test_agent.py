"""
Unit tests for the e-rickshaw dialog agent. Run:  pytest -q
All inputs are synthetic.
"""
import json
import re

import pytest

import agent
import nlu
import tools
from agent import Session, step
from config import DEFAULT_CONFIG as CFG


def run(*utterances, session=None):
    s = session or Session()
    out = None
    for u in utterances:
        out = step(s, u, log=False)
    return out, s


def sentences(reply):
    return [x for x in re.split(r"[।?!]", reply) if x.strip()]


# ---------------------------------------------------------------- normalize
@pytest.mark.parametrize("raw,expected", [
    ("Bhaiya, 60% CHARGE hai!!", "bhaiya 60 percent charge hai"),
    ("हाँ जी।", "हां जी"),
    ("डीज़ल", "diesel"),
    ("battery ६० है", "battery 60 है"),
    ("40km   jana  hai", "40 km jana hai"),
    ("2.5 km", "2.5 km"),
    ("चार्जर नही", "charger नहीं"),
])
def test_normalize(raw, expected):
    assert nlu.normalize(raw) == expected


# ---------------------------------------------------------------- numbers
@pytest.mark.parametrize("word,value", [
    ("बासठ", 62), ("basath", 62), ("bassath", 62), ("सैंतालीस", 47), ("saintalis", 47),
    ("उनहत्तर", 69), ("निन्यानवे", 99), ("छियासठ", 66), ("अड़तीस", 38), ("सौ", 100), ("शून्य", 0),
    ("पाँच", 5), ("तिरेसठ", 63), ("chauvalis", 44),
])
def test_hindi_number_words_with_percent(word, value):
    assert nlu.extract_percent(f"{word} प्रतिशत") == value


def test_number_table_complete():
    assert set(nlu.NUMBER_WORDS.values()) == set(range(101))


@pytest.mark.parametrize("text,value", [
    ("battery ६० प्रतिशत", 60),
    ("चार्ज ७५ है", 75),
    ("60% charge hai", 60),
    ("charge 45 hai", 45),
    ("एक सौ percent", 100),
])
def test_percent_digits_and_devanagari_digits(text, value):
    assert nlu.extract_percent(text) == value


@pytest.mark.parametrize("text", [
    "mere saath chalo",            # saath = with
    "bhai ke sath jaana hai",
    "do minute ruko",              # do = give / two
    "ek baat batao",               # ek = a
    "chai 20 rupaye ki",           # no charge cue: not a percent
])
def test_no_percent_without_cue(text):
    assert nlu.extract_percent(text) is None


def test_saath_counts_when_next_to_percent():
    assert nlu.extract_percent("saath percent") == 60


def test_bare_number_accepted_only_when_pending():
    toks = nlu.tokens_of(nlu.normalize("साठ"))
    assert nlu.extract_slots(toks).percent is None
    s = nlu.extract_slots(toks, pending="percent")
    assert s.percent == 60 and s.percent_conf == "low"


def test_km_and_passengers_slots():
    s = nlu.extract_slots(nlu.tokens_of(nlu.normalize("चालीस किलोमीटर जाना है, 4 सवारी हैं, 60% है")))
    assert (s.km, s.passengers, s.percent) == (40, 4, 60)


def test_km_number_not_taken_as_percent():
    s = nlu.extract_slots(nlu.tokens_of(nlu.normalize("40 km jana hai battery hai")))
    assert s.km == 40 and s.percent is None


def test_range_before_after():
    s = nlu.extract_slots(nlu.tokens_of(nlu.normalize("पहले 90 चलती थी अब 65 चलती है")))
    assert (s.range_before, s.range_after) == (90, 65)


def test_correction_slot():
    s = nlu.extract_slots(nlu.tokens_of(nlu.normalize("नहीं, सत्तर")))
    assert s.percent == 70 and s.percent_override


def test_word_boundary_near_vs_nearly():
    pats = nlu.compile_patterns([("near", 1)])
    assert nlu.has_any(["near"], pats)
    assert not nlu.has_any(["nearly"], pats)


def test_tag_particle_na_is_not_no():
    s = nlu.extract_slots(nlu.tokens_of(nlu.normalize("सही है ना")))
    assert s.yes and not s.no


# ---------------------------------------------------------------- intents (single turn)
@pytest.mark.parametrize("text,intent", [
    ("60 प्रतिशत है, कितनी दूर जाएगी", "range"),
    ("battery 50 percent, kitna chalegi", "range"),
    ("30% se poora charge kitne ghante mein", "charge_time_cost"),
    ("पूरा चार्ज करने में कितने पैसे लगेंगे, 20 प्रतिशत है", "charge_time_cost"),
    ("इंदौर से महू जाना है, 50% है", "trip"),
    ("25 km ka safar hai 30 percent battery", "trip"),
    ("उदयपुर में चार्जिंग स्टेशन", "stations"),
    ("bharatpur mein charging point kahan hai", "stations"),
    ("aaj 70 km chalaya kitna bacha", "savings"),
    ("आज 50 किलोमीटर, पेट्रोल से कितनी बचत", "savings"),
    ("charging bahut dheere ho rahi", "trouble_slow_charging"),
    ("चार्ज होने में बहुत देर लग रही है", "trouble_slow_charging"),
    ("mileage bahut kam ho gaya", "trouble_range_drop"),
    ("रेंज कम हो गई है", "trouble_range_drop"),
    ("charger connect nahi ho raha", "trouble_not_detecting"),
    ("चार्जर लगाने पर चार्ज नहीं हो रहा", "trouble_not_detecting"),
    ("namaskar bhaiya", "greeting"),
    ("आज क्रिकेट मैच कौन जीता", "fallback"),
])
def test_intents(text, intent):
    r, _ = run(text)
    assert r["intent"] == intent or intent in r["intents"], r


def test_combined_range_and_cost():
    r, _ = run("Bhaiya, 60% charge hai, kitna chalega aur kitna kharcha aayega?")
    assert set(r["intents"]) == {"range", "charge_time_cost"}
    assert "55 किलोमीटर" in r["reply"] and "रुपये" in r["reply"]


def test_bare_city_means_stations():
    r, s = run("भोपाल")
    assert r["intent"] == "stations" and s.city == "bhopal"


def test_trouble_beats_calculator_words():
    r, _ = run("charge nahi ho raha, kitna time lagega?")
    assert r["intent"] == "trouble_not_detecting"


def test_fuzzy_keyword_tolerates_stt_typo():
    r, _ = run("60 percent hai, kitna kharchaa aayega")     # 'kharchaa' is misspelt
    assert r["intent"] == "charge_time_cost"


# ---------------------------------------------------------------- safety
@pytest.mark.parametrize("text", [
    "चार्जर से धुआं निकल रहा है",
    "plug mein chingari aa rahi hai",
    "battery bahut garam ho gayi",
    "तार पिघल गया",
    "चार्ज करते समय करंट लगा",
    "socket geela hai",
    "wire jal gaya",
])
def test_safety_triggers(text):
    r, _ = run(text)
    assert r["intent"] == "safety"
    assert "बंद" in r["reply"] and "मैकेनिक" in r["reply"]


@pytest.mark.parametrize("text", [
    "charger ki light nahi jal rahi",        # lamp not glowing, not fire
    "आज बहुत गर्मी है",                      # weather
    "jaldi batao kitna chalega",             # jaldi != jal
    "kal 30 km jana hai, pahunch jaunga",    # fuzzy 'jalna' must not match 'jana'
])
def test_safety_no_false_positive(text):
    r, _ = run(text)
    assert r["intent"] != "safety"


def test_safety_overrides_pending_question():
    _, s = run("kitna chalega")
    assert s.pending == "percent"
    r, s = run("ruko, charger se dhuan aa raha hai", session=s)
    assert r["intent"] == "safety" and s.pending is None


def test_safety_overrides_trouble_flow():
    _, s = run("charging bahut slow hai")
    r, s = run("arre chingari nikli", session=s)
    assert r["intent"] == "safety" and s.trouble_flow is None


# ---------------------------------------------------------------- multi-turn
def test_pending_percent_resume_with_digit():
    r, s = run("kitna chalega", "60")
    assert r["intent"] == "range" and "55 किलोमीटर" in r["reply"]
    assert s.percent == 60 and s.pending is None


def test_pending_percent_word_needs_confirmation_then_yes():
    r, s = run("kitna chalega", "साठ")
    assert r["needs_confirm"] and "60 प्रतिशत, सही" in r["reply"]
    r, s = run("हां", session=s)
    assert r["intent"] == "range" and s.percent == 60


def test_confirmation_no_then_new_value():
    r, s = run("kitna chalega", "सत्तर", "नहीं")
    assert s.pending == "percent"
    r, s = run("50 percent", session=s)
    assert s.percent == 50 and "45 किलोमीटर" in r["reply"]


def test_confirmation_correction_in_one_go():
    r, s = run("kitna chalega", "सत्तर", "नहीं, साठ")
    assert s.percent == 60 and r["intent"] == "range"


def test_followup_cost_reuses_percent():
    r, _ = run("60% hai kitna chalega", "और खर्चा?")
    assert r["intent"] == "charge_time_cost" and "रुपये" in r["reply"]


def test_followup_what_if_other_percent():
    r, s = run("60% hai kitna chalega", "और अगर 40% हो?")
    assert r["intent"] == "range" and s.percent == 40 and "35 किलोमीटर" in r["reply"]


def test_followup_time_after_range():
    r, _ = run("80 percent hai kitna chalega", "फिर चार्ज में कितना टाइम?")
    assert r["intent"] == "charge_time_cost" and "घंटे" in r["reply"]


def test_slot_overwrite_correction_without_pending():
    r, s = run("60% hai kitna chalega", "नहीं, सत्तर")
    assert s.percent == 70 and "65 किलोमीटर" in r["reply"]


def test_trip_asks_percent_then_answers():
    r, s = run("भोपाल से सीहोर जाना है, पहुंच जाऊंगा?")
    assert r["intent"] == "trip" and s.pending == "percent" and s.km == 38
    r, s = run("40 प्रतिशत", session=s)
    assert r["data"]["trip_feasibility"]["verdict"] == "no_charge_first"


def test_trip_uses_city_from_earlier_turn():
    r, s = run("indore mein station batao", "देवास जाना है, 60% है")
    assert s.trip_origin == "indore" and s.trip_dest == "dewas"
    assert r["data"]["trip_feasibility"]["verdict"] == "yes"


def test_trip_unknown_route_asks_km():
    r, s = run("लखनऊ जाना है, 60% है")
    assert s.pending == "km"
    r, s = run("50 km", session=s)
    assert r["intent"] == "trip"


def test_savings_asks_km_then_answers():
    r, s = run("aaj kitna bacha?")
    assert s.pending == "km_driven"
    r, s = run("80", session=s)
    assert r["intent"] == "savings" and s.km_driven == 80


def test_savings_km_does_not_become_trip_km():
    _, s = run("aaj 80 km chalaya kitna bacha")
    assert s.km_driven == 80 and s.km is None


def test_stations_asks_city():
    r, s = run("charging station kahan hai")
    assert s.pending == "city"
    r, s = run("जयपुर", session=s)
    assert r["intent"] == "stations" and "बस स्टैंड" in r["reply"]


def test_new_question_abandons_pending_slot():
    _, s = run("kitna chalega")
    r, s = run("उदयपुर में चार्जिंग स्टेशन कहां है", session=s)
    assert r["intent"] == "stations" and s.pending is None


# ---------------------------------------------------------------- troubleshooting step by step
def test_troubleshoot_one_step_at_a_time_and_escalate():
    r, s = run("charger detect nahi kar raha")
    assert "पहला उपाय" in r["reply"] and "दूसरा" not in r["reply"]
    n = len(tools.TROUBLE_FLOWS["not_detecting"]["steps"])
    for i in range(1, n):
        r, s = run("हो गया", session=s)
        assert tools.ORDINALS[i] in r["reply"]
        assert s.trouble_step == i
    r, s = run("नहीं हुआ", session=s)
    assert r["intent"] == "trouble_escalate" and "मैकेनिक" in r["reply"] and s.trouble_flow is None


def test_troubleshoot_fixed_ends_flow():
    r, s = run("charging slow hai", "अगला", "ठीक हो गया")
    assert r["intent"] == "trouble_fixed" and s.trouble_flow is None


def test_troubleshoot_exit_on_new_question():
    r, s = run("charging slow hai", "जयपुर में चार्जिंग स्टेशन कहां है")
    assert r["intent"] == "stations" and s.trouble_flow is None


def test_switch_from_one_trouble_flow_to_another():
    r, s = run("charger detect nahi kar raha", "पहले 90 चलती थी अब 60 चलती है")
    assert r["tool"] == "range_drop_diagnosis" and s.trouble_flow is None


def test_range_drop_diagnosis_tiers_and_offer():
    r, s = run("पहले 90 चलती थी अब 60 चलती है")
    assert r["tool"] == "range_drop_diagnosis"
    assert r["data"]["tier"] == "battery_check" and s.pending == "offer_trouble"
    r, s = run("हां", session=s)
    assert "पहला उपाय" in r["reply"] and s.trouble_flow == "range_drop"


# ---------------------------------------------------------------- clarification / failures
def test_low_confidence_targeted_clarification():
    r, s = run("range")          # weak evidence only
    assert r["intent"] == "clarify" and "?" in r["reply"]
    assert "रेंज" in r["reply"]


def test_clarification_answer_resolves():
    r, s = run("range")
    opts = s.clarify_options
    assert "range" in opts
    r, s = run("कितना चलेगा, 60 प्रतिशत", session=s)
    assert r["intent"] == "range"


def test_empty_then_simpler_prompt():
    r, s = run("")
    assert r["intent"] == "empty" and "दोबारा" in r["reply"]
    r, s = run("...", session=s)
    assert "बस इतना बोलिए" in r["reply"]


def test_success_resets_failure_counter():
    _, s = run("", "pizza")
    assert s.failures == 2
    run("namaste", session=s)
    assert s.failures == 0


# ---------------------------------------------------------------- tools (numbers)
def test_range_tool_linear_and_derated():
    assert tools.estimate_range_km(60) == pytest.approx(54.0)
    assert tools.estimate_range_km(60, passengers=5) == pytest.approx(54.0 * (1 - 0.04 * 3))
    assert tools.estimate_range_km(100, passengers=1) == pytest.approx(90.0)


def test_charge_time_two_stage():
    per = CFG.battery_kwh / 100 / CFG.efficiency
    assert tools.charge_hours(60, 80) == pytest.approx(20 * per / CFG.charger_kw)
    assert tools.charge_hours(80, 100) == pytest.approx(20 * per / (CFG.charger_kw * CFG.taper_power_factor))
    assert tools.charge_hours(60, 100) > tools.charge_hours(60, 80) * 2


def test_charge_cost():
    assert tools.charge_cost_rs(60, 100) == pytest.approx(7.2 * 0.4 / 0.9 * 8)


def test_trip_verdicts():
    s = Session(percent=60, km=30)
    assert tools.trip_feasibility(s)[1]["verdict"] == "yes"
    s = Session(percent=40, km=34)          # range 36, need 39.1
    assert tools.trip_feasibility(s)[1]["verdict"] == "borderline"
    s = Session(percent=30, km=38, trip_origin="bhopal", trip_dest="sehore")
    _, d = tools.trip_feasibility(s)
    assert d["verdict"] == "no_charge_first" and d["target_percent"] == 50
    assert d["charging_stop"]["city"] == "bhopal"
    s = Session(percent=100, km=120)
    assert tools.trip_feasibility(s)[1]["verdict"] == "no_midway_charge"


def test_savings_numbers():
    _, d = tools.savings(Session(km_driven=80))
    assert d["ev_rs"] == pytest.approx(80 * 7.2 / 0.9 * 8 / 90, abs=0.1)
    assert d["petrol_rs"] == pytest.approx(80 * 105 / 25, abs=0.1)
    assert d["saved_vs_petrol"] > d["saved_vs_cng"] > 0


def test_range_drop_tiers():
    assert tools.range_drop_diagnosis(Session(range_before=90, range_after=85))[1]["tier"] == "normal"
    assert tools.range_drop_diagnosis(Session(range_before=90, range_after=75))[1]["tier"] == "check_basics"
    assert tools.range_drop_diagnosis(Session(range_before=90, range_after=60))[1]["tier"] == "battery_check"


@pytest.mark.parametrize("hours,text", [
    (0.33, "20 मिनट"), (1.0, "1 घंटा"), (1.5, "डेढ़ घंटा"), (2.5, "ढाई घंटे"), (3.4, "साढ़े 3 घंटे"), (4.1, "4 घंटे"),
])
def test_duration_wording(hours, text):
    assert tools.fmt_duration(hours) == text


def test_rupee_rounding():
    assert tools.fmt_rs(26) == "25" and tools.fmt_rs(7257) == "7,260" and tools.fmt_rs(12.4) == "12"


# ---------------------------------------------------------------- reply style
@pytest.mark.parametrize("text", [
    "Bhaiya, 60% charge hai, kitna chalega aur kitna kharcha aayega?",
    "भोपाल से सीहोर जाना है, 30% है",
    "aaj 80 km chalaya kitna bacha",
    "जयपुर में चार्जिंग पॉइंट",
    "charger detect nahi kar raha",
    "चार्जर से धुआं निकल रहा है",
])
def test_replies_are_short_devanagari(text):
    r, _ = run(text)
    reply = r["reply"]
    assert len(sentences(reply)) <= 3, reply
    assert reply.count("?") <= 1
    assert re.search(r"[ऀ-ॿ]", reply)
    assert not re.search(r"\d+\.\d", reply), "numbers should be rounded"


# ---------------------------------------------------------------- compatibility and logging
def test_respond_backward_compatible_with_default_session():
    agent.reset()
    r = agent.respond("kitna chalega")
    assert r["intent"] == "range" and "प्रतिशत" in r["reply"]
    r = agent.respond("60")
    assert "55 किलोमीटर" in r["reply"]
    agent.reset()
    assert agent.respond("60")["intent"] != "range"


def test_step_return_shape():
    r, _ = run("60% hai kitna chalega")
    for key in ("intent", "reply", "score", "slots", "tool", "needs_confirm", "margin"):
        assert key in r


def test_log_line_written_without_long_numbers(tmp_path, monkeypatch):
    path = tmp_path / "turns.jsonl"
    monkeypatch.setenv("EV_AGENT_LOG_PATH", str(path))
    step(Session(), "mera number 9876543210 hai, 60% charge kitna chalega")
    rec = json.loads(path.read_text(encoding="utf-8").strip())
    assert "9876543210" not in json.dumps(rec, ensure_ascii=False)
    for key in ("ts", "text_raw", "text_norm", "intent", "score", "margin", "slots", "tool", "reply", "needs_confirm"):
        assert key in rec
