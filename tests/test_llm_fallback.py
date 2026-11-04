import json
import pytest

import agent
import llm_fallback

UNKNOWN = "bhaiya baarish mein gaadi chala sakte hain kya"   # rules don't understand this


@pytest.fixture
def use_classifier():
    def _set(fn):
        agent.register_fallback_classifier(fn)
    yield _set
    agent.register_fallback_classifier(None)


def run(text, session=None):
    return agent.step(session or agent.Session(), text, log=False)


def test_without_classifier_unknown_text_is_fallback():
    assert run(UNKNOWN)["intent"] == "fallback"


def test_general_ev_answer_is_spoken(use_classifier):
    use_classifier(lambda t: {"intent": "general_ev", "answer": "हाँ, पर पानी में गाड़ी मत ले जाइए।"})
    r = run(UNKNOWN)
    assert r["intent"] == "llm_answer"
    assert r["reply"] == "हाँ, पर पानी में गाड़ी मत ले जाइए।"


def test_routed_intent_uses_agent_tools_for_numbers(use_classifier):
    use_classifier(lambda t: {"intent": "range", "percent": 60, "km": None, "city": None, "answer": None})
    r = run(UNKNOWN)
    assert r["intent"] == "range"
    # same reply the rule path gives for "60% charge hai, kitna chalega": numbers come from tools.py
    assert r["reply"] == run("60 प्रतिशत चार्ज है कितना चलेगा")["reply"]


def test_routed_intent_without_slot_asks_for_it(use_classifier):
    use_classifier(lambda t: {"intent": "range", "percent": None, "km": None, "city": None, "answer": None})
    s = agent.Session()
    r = agent.step(s, UNKNOWN, log=False)
    assert "प्रतिशत" in r["reply"]
    assert s.pending == "percent"


def test_routed_city_goes_to_stations(use_classifier):
    use_classifier(lambda t: {"intent": "stations", "percent": None, "km": None, "city": "indore", "answer": None})
    r = run(UNKNOWN)
    assert r["intent"] == "stations"
    assert "इंदौर" in r["reply"]


def test_llm_safety_gives_safety_reply(use_classifier):
    use_classifier(lambda t: {"intent": "safety"})
    assert run(UNKNOWN)["intent"] == "safety"


def test_other_or_none_keeps_normal_fallback(use_classifier):
    use_classifier(lambda t: None)
    assert run(UNKNOWN)["intent"] == "fallback"


def test_classifier_exception_keeps_normal_fallback(use_classifier):
    def boom(t):
        raise RuntimeError("down")
    use_classifier(boom)
    assert run(UNKNOWN)["intent"] == "fallback"


def test_legacy_tuple_classifier_still_works(use_classifier):
    use_classifier(lambda t: ("greeting", 0.9))
    assert run(UNKNOWN)["intent"] == "greeting"


def test_rules_win_before_classifier_is_called(use_classifier):
    calls = []
    use_classifier(lambda t: calls.append(t) or {"intent": "general_ev", "answer": "x"})
    run("60% charge hai, kitna chalega")
    run("jaipur mein charging point")
    assert run("namaste")["intent"] == "greeting"
    assert calls == []


def test_rule_safety_wins_before_classifier(use_classifier):
    calls = []
    use_classifier(lambda t: calls.append(t) or {"intent": "general_ev", "answer": "x"})
    assert run("charger se dhuan aa raha hai")["intent"] == "safety"
    assert calls == []


# ---------- llm_fallback.py with a fake HTTP API (no network) ----------
class _Resp:
    def __init__(self, status=200, content=None, finish="stop"):
        self.status_code = status
        self.text = "err"
        self._content, self._finish = content, finish

    def json(self):
        c = self._content if isinstance(self._content, str) else json.dumps(self._content, ensure_ascii=False)
        return {"choices": [{"message": {"content": c}, "finish_reason": self._finish}]}


@pytest.fixture
def fake_api(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    def _make(*responses, error=None):
        calls = []
        queue = list(responses)

        def post(url, headers=None, json=None, timeout=None):
            calls.append({"url": url, "headers": headers, "body": json, "timeout": timeout})
            if error:
                raise error
            return queue.pop(0) if len(queue) > 1 else queue[0]
        monkeypatch.setattr(llm_fallback.requests, "post", post)
        return calls
    return _make


def test_classify_parses_and_sends_request(fake_api):
    calls = fake_api(_Resp(content={"intent": "trip", "percent": 30, "km": 40, "city": "Bhopal", "answer": None}))
    out = llm_fallback.classify(UNKNOWN)
    assert out == {"intent": "trip", "percent": 30, "km": 40.0, "city": "bhopal", "answer": None}
    req = calls[0]
    assert req["url"] == llm_fallback.BASE_URL + "chat/completions"
    assert req["headers"]["Authorization"] == "Bearer test-key"
    assert req["body"]["model"] == llm_fallback.MODEL
    assert req["body"]["response_format"] == {"type": "json_object"}
    assert req["body"]["messages"][1]["content"] == UNKNOWN
    assert req["timeout"] == llm_fallback.TIMEOUT_SEC


def test_json_in_code_fence_is_parsed(fake_api):
    fake_api(_Resp(content='```json\n{"intent": "greeting", "percent": null, "km": null, "city": null, "answer": null}\n```'))
    assert llm_fallback.classify(UNKNOWN)["intent"] == "greeting"


def test_400_retries_without_json_mode(fake_api):
    calls = fake_api(_Resp(status=400), _Resp(content={"intent": "range", "percent": 50}))
    assert llm_fallback.classify(UNKNOWN)["percent"] == 50
    assert "response_format" in calls[0]["body"]
    assert "response_format" not in calls[1]["body"] and "reasoning_effort" not in calls[1]["body"]


@pytest.mark.parametrize("payload,expected", [
    ({"intent": "range", "percent": 250, "km": -5, "city": "delhi", "answer": None},
     {"intent": "range", "percent": None, "km": None, "city": None, "answer": None}),
    ({"intent": "other", "percent": None, "km": None, "city": None, "answer": None}, None),
    ({"intent": "general_ev", "percent": None, "km": None, "city": None, "answer": "  "}, None),
    ({"intent": "made_up", "percent": None, "km": None, "city": None, "answer": None}, None),
    ("not json at all", None),
])
def test_classify_validates_output(fake_api, payload, expected):
    fake_api(_Resp(content=payload))
    assert llm_fallback.classify(UNKNOWN) == expected


def test_long_answer_is_trimmed(fake_api):
    fake_api(_Resp(content={"intent": "general_ev", "answer": "क" * 1000}))
    assert len(llm_fallback.classify(UNKNOWN)["answer"]) == llm_fallback.MAX_ANSWER_CHARS


def test_cut_off_answer_returns_none(fake_api):
    fake_api(_Resp(content={"intent": "general_ev", "answer": "अधूरा"}, finish="length"))
    assert llm_fallback.classify(UNKNOWN) is None


@pytest.mark.parametrize("status", [401, 429, 500])
def test_http_errors_return_none(fake_api, status):
    fake_api(_Resp(status=status))
    assert llm_fallback.classify(UNKNOWN) is None


def test_network_error_returns_none(fake_api):
    fake_api(error=llm_fallback.requests.Timeout("slow"))
    assert llm_fallback.classify(UNKNOWN) is None


def test_empty_text_makes_no_call(fake_api):
    calls = fake_api(_Resp(content={"intent": "range"}))
    assert llm_fallback.classify("   ") is None
    assert calls == []


def test_enabled_flags(monkeypatch):
    for k in ("LLM_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LLM_FALLBACK", "1")
    assert not llm_fallback.enabled()
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    assert llm_fallback.enabled()
    monkeypatch.setenv("LLM_FALLBACK", "0")
    assert not llm_fallback.enabled()
