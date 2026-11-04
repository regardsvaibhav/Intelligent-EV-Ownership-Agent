import pytest
import requests

import agent
import app as app_module
import gnani


# ---------- "kitni der lagegi" is a time question, not a slow-charging complaint ----------
@pytest.mark.parametrize("text", [
    "charge hone mein kitni der lagegi",
    "चार्ज होने में कितनी देर लगेगी",
    "full charge hone mein kitna time lagega",
])
def test_time_question_without_percent_asks_for_percent(text):
    r = agent.step(agent.Session(), text, log=False)
    assert r["intent"] == "charge_time_cost"
    assert "प्रतिशत" in r["reply"]


def test_time_question_with_percent_is_answered():
    r = agent.step(agent.Session(), "40% charge hai, charge hone mein kitni der lagegi", log=False)
    assert r["intent"] == "charge_time_cost"
    assert "घंटे" in r["reply"]


@pytest.mark.parametrize("text", [
    "charge hone mein bahut der lag rahi hai",
    "चार्ज होने में बहुत देर लग रही है",
    "charging slow hai, kitni der lagegi",
    "charging mein der lagti hai",
])
def test_slow_charging_complaints_still_troubleshoot(text):
    assert agent.step(agent.Session(), text, log=False)["intent"] == "trouble_slow_charging"


# ---------- gnani.py ----------
@pytest.mark.parametrize("key", ["", "replace_with_your_gnani_api_key", "PASTE_YOUR_API_KEY_HERE"])
def test_placeholder_keys_are_rejected(monkeypatch, key):
    monkeypatch.setenv("GNANI_API_KEY", key)
    with pytest.raises(gnani.GnaniError):
        gnani._api_key()


def _Resp(status):
    r = requests.Response()
    r.status_code = status
    return r


def test_retry_on_503_then_success(monkeypatch):
    calls = iter([_Resp(503), _Resp(200)])
    monkeypatch.setattr(gnani.requests, "post", lambda *a, **k: next(calls))
    monkeypatch.setattr(gnani.time, "sleep", lambda s: None)
    assert gnani._post_with_retry("u").status_code == 200


def test_no_retry_on_timeout(monkeypatch):
    n = {"calls": 0}

    def boom(*a, **k):
        n["calls"] += 1
        raise requests.Timeout()
    monkeypatch.setattr(gnani.requests, "post", boom)
    with pytest.raises(requests.Timeout):
        gnani._post_with_retry("u")
    assert n["calls"] == 1


def test_gives_up_after_retries_and_returns_last_response(monkeypatch):
    monkeypatch.setattr(gnani.requests, "post", lambda *a, **k: _Resp(429))
    monkeypatch.setattr(gnani.time, "sleep", lambda s: None)
    assert gnani._post_with_retry("u", retries=3).status_code == 429


# ---------- app.py ----------
@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("GNANI_API_KEY", raising=False)   # no real Gnani calls
    monkeypatch.setattr(app_module, "RATE_LIMIT_PER_MIN", 0)
    app_module.SESSIONS.clear()
    return app_module.app.test_client()


@pytest.mark.parametrize("body", [[1, 2], "hello", 5])
def test_non_object_json_does_not_crash(client, body):
    assert client.post("/api/text", json=body).status_code == 200
    assert client.post("/api/reset", json=body).status_code == 200


@pytest.mark.parametrize("body", [{"text": 5}, {"text": "hi", "session_id": ["x"]}])
def test_wrong_types_return_400(client, body):
    assert client.post("/api/text", json=body).status_code == 400


def test_upload_too_big_returns_413(client, monkeypatch):
    monkeypatch.setitem(app_module.app.config, "MAX_CONTENT_LENGTH", 1024)
    import io
    r = client.post("/api/voice", data={"audio": (io.BytesIO(b"0" * 4096), "a.wav")},
                    content_type="multipart/form-data")
    assert r.status_code == 413


def test_session_store_is_capped(client, monkeypatch):
    monkeypatch.setattr(app_module, "MAX_SESSIONS", 3)
    for i in range(10):
        client.post("/api/text", json={"text": "namaste", "session_id": f"session-{i:04d}"})
    assert len(app_module.SESSIONS) == 3
    assert "session-0009" in app_module.SESSIONS


def test_rate_limit(client, monkeypatch):
    monkeypatch.setattr(app_module, "RATE_LIMIT_PER_MIN", 2)
    app_module._hits.clear()
    codes = [client.post("/api/text", json={"text": "namaste"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
