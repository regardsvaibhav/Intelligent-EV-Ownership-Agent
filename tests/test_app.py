import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import app as app_module


@pytest.fixture
def client(monkeypatch):
    # No real Gnani calls in tests: TTS fails fast without a key.
    monkeypatch.delenv("GNANI_API_KEY", raising=False)
    return app_module.app.test_client()


def test_follow_up_is_remembered_across_requests(client):
    first = client.post("/api/text", json={"text": "kitna chalega"}).get_json()
    assert first["intent"] == "need_percent"
    second = client.post("/api/text", json={"text": "saath"}).get_json()
    assert second["intent"] == "calculator"


def test_separate_clients_do_not_share_state():
    a = app_module.app.test_client()
    b = app_module.app.test_client()
    a.post("/api/text", json={"text": "kitna chalega"})
    assert b.post("/api/text", json={"text": "saath"}).get_json()["intent"] == "fallback"


def test_non_object_json_is_treated_as_empty(client):
    r = client.post("/api/text", json=[1, 2])
    assert r.status_code == 200
    assert r.get_json()["intent"] == "empty"


def test_non_string_text_returns_400(client):
    assert client.post("/api/text", json={"text": 5}).status_code == 400
