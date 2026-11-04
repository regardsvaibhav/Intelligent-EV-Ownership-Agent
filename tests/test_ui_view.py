"""The web page's card data must match what the agent says."""
import agent
import ui_view
from agent import Session, step


def view_after(*utterances):
    s = Session()
    r = None
    for u in utterances:
        r = step(s, u, log=False)
    return ui_view.build_view(r, s), r, s


def test_gauge_matches_spoken_numbers():
    v, r, _ = view_after("60% charge hai, kitna chalega aur kitna kharcha")
    assert v["kind"] == "gauge" and v["range_km"] == 55 and v["cost"] == "25"
    assert "55 किलोमीटर" in r["reply"] and "25 रुपये" in r["reply"]


def test_ask_percent_offers_choices():
    v, _, _ = view_after("kitna chalega")
    assert v["kind"] == "ask" and v["slot"] == "percent" and len(v["choices"]) == 10


def test_choice_text_is_understood_by_agent():
    s = Session()
    step(s, "kitna chalega", log=False)
    say = ui_view.ask_choices("percent")["choices"][5]["say"]
    r = step(s, say, log=False)
    assert r["intent"] == "range" and s.percent == 60


def test_confirm_view():
    v, _, _ = view_after("kitna chalega", "साठ")
    assert v == {"kind": "confirm", "percent": 60}


def test_trip_view_has_target_and_station():
    v, _, _ = view_after("भोपाल से सीहोर जाना है, 30% है")
    assert v["kind"] == "trip" and v["verdict"] == "no_charge_first" and v["target"] == 50
    assert v["station"]["area"] == "आईएसबीटी" and v["charge_cost"] == "13"


def test_stations_view_sorted_and_flagged():
    v, _, _ = view_after("भोपाल में चार्जिंग स्टेशन")
    assert [i["price"] for i in v["items"]] == [8, 9, 10] and v["items"][0]["cheapest"]


def test_savings_view():
    v, _, _ = view_after("aaj 80 km chalaya kitna bacha")
    assert v["kind"] == "savings" and v["saved"] == "280" and v["bars"][2]["mine"]


def test_trouble_view_steps():
    v, _, _ = view_after("charger detect nahi kar raha")
    assert v["kind"] == "trouble" and v["step"] == 1 and v["total"] == 4
    v, _, _ = view_after("charger detect nahi kar raha", "अगला")
    assert v["step"] == 2


def test_clarify_option_labels_resolve():
    s = Session()
    r = step(s, "range", log=False)
    v = ui_view.build_view(r, s)
    assert v["kind"] == "clarify"
    r = step(s, v["options"][0]["say"], log=False)
    assert r["intent"] != "clarify"


def test_safety_view():
    v, _, _ = view_after("चार्जर से धुआं निकल रहा है")
    assert v["kind"] == "safety"


def test_memory_uses_hindi_city():
    _, _, s = view_after("bhopal mein station batao")
    assert ui_view.memory(s)["city"] == "भोपाल"
