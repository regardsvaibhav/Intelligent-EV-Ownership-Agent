import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import agent


def intent(text, state=None):
    return agent.respond(text, state)["intent"]


# ---------- Original sample queries keep working ----------
@pytest.mark.parametrize("text,expected", [
    ("Bhaiya, 60% charge hai, kitna chalega aur charge mein kitna kharcha aayega?", "calculator"),
    ("भैया साठ प्रतिशत चार्ज है कितना चलेगा और कितना खर्चा आएगा", "calculator"),
    ("meri charging bahut slow ho rahi hai", "trouble_slow_charging"),
    ("range kam ho gayi hai", "trouble_range_drop"),
    ("charger detect nahi kar raha", "trouble_not_detecting"),
    ("जयपुर में चार्जिंग पॉइंट कहाँ है", "stations"),
    ("charging station kahan hai", "stations"),
    ("kitna chalega", "need_percent"),
    ("namaste", "greeting"),
    ("pizza chahiye", "fallback"),
])
def test_sample_queries(text, expected):
    assert intent(text) == expected


# ---------- Charge-time questions go to the calculator, not troubleshooting ----------
@pytest.mark.parametrize("text", [
    "60% charge hai, kitna time lagega?",
    "40 percent charge hai full charge hone mein kitni der lagegi",
    "चालीस प्रतिशत चार्ज है, चार्ज होने में कितनी देर लगेगी",
    "battery 50 hai, charge hone mein time lagega kitna",
])
def test_time_questions_are_calculated(text):
    r = agent.respond(text)
    assert r["intent"] == "calculator"
    assert "लगभग" in r["reply"]


@pytest.mark.parametrize("text", [
    "charging bahut dheere ho rahi hai",
    "चार्जिंग बहुत धीमी है",
    "charge hone mein bahut der lagti hai",
])
def test_slow_charging_complaints(text):
    assert intent(text) == "trouble_slow_charging"


# ---------- Number parsing ----------
@pytest.mark.parametrize("text,expected", [
    ("60% charge hai", 60),
    ("60 percent", 60),
    ("साठ प्रतिशत चार्ज है", 60),
    ("battery 45 hai", 45),
    ("charge 80 hai", 80),
    ("saath", 60),
    ("60", 60),
    ("60 hai", 60),
])
def test_extract_percent_finds_charge(text, expected):
    assert agent.extract_percent(text) == expected


@pytest.mark.parametrize("text", [
    "mere saath chalo",          # saath = with
    "2 ghante se ruka hua hoon",
    "das minute mein aata hoon",
    "sau baat ki ek baat",
    "ward 12 mein rehta hoon",
])
def test_extract_percent_ignores_everyday_words(text):
    assert agent.extract_percent(text) is None


def test_saath_meaning_with_is_not_a_charge_level():
    assert intent("bhaiya mere saath kitna kharcha aayega") == "need_percent"


# ---------- Greeting ----------
def test_bare_hi_is_greeting():
    assert intent("hi") == "greeting"


def test_nahi_is_not_greeting():
    assert intent("kuch nahi pata") == "fallback"


# ---------- Conversation memory ----------
def test_percent_follow_up_completes_calculation():
    first = agent.respond("kitna kharcha aayega")
    assert first["intent"] == "need_percent"
    second = agent.respond("saath", first["state"])
    assert second["intent"] == "calculator"
    assert "खर्चा" in second["reply"]
    # only cost was asked, so range is not added
    assert "किलोमीटर" not in second["reply"]
    assert second["state"] is None


@pytest.mark.parametrize("answer", ["60", "saath", "साठ", "60 percent", "abhi 70 hai"])
def test_percent_follow_up_variants(answer):
    state = agent.respond("kitna chalega")["state"]
    assert intent(answer, state) == "calculator"


def test_follow_up_still_open_after_unclear_answer():
    state = agent.respond("kitna chalega")["state"]
    r = agent.respond("pata nahi", state)
    assert r["intent"] == "fallback"
    assert intent("saath", r["state"]) == "calculator"


def test_new_question_overrides_pending_percent():
    state = agent.respond("kitna chalega")["state"]
    assert intent("jaipur mein station kahan hai", state) == "stations"


def test_without_state_bare_number_word_in_sentence_is_not_calculated():
    assert intent("saath chalo") == "fallback"


def test_trouble_more_steps():
    first = agent.respond("range kam ho gayi hai")
    assert first["state"] == {"pending": "trouble_more", "kind": "range_drop", "next": 3}
    second = agent.respond("aur batao", first["state"])
    assert second["intent"] == "trouble_range_drop"
    assert "चौथा" in second["reply"]
    assert "पहला" not in second["reply"]
    # range_drop has 5 steps, so nothing more is left
    assert second["state"] is None


def test_aur_without_pending_trouble_is_fallback():
    assert intent("aur batao") == "fallback"


def test_garbage_state_is_ignored():
    assert intent("namaste", "not-a-dict") == "greeting"
    assert intent("60% charge hai", {"pending": "trouble_more", "kind": "nope"}) == "calculator"


# ---------- Calculator numbers ----------
def test_calculate_values():
    r = agent.calculate(60)
    assert r["range_km"] == 54
    assert r["kwh_needed"] == 3.2
    assert r["cost_rs"] == 26
    assert r["time_text"] == "2 घंटे 40 मिनट"
