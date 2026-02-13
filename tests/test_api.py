import time
import pytest
from fastapi.testclient import TestClient

import backend.api_backend as api_backend

client = TestClient(api_backend.app)


def test_health_readiness_config_templates():
    r = client.get("/health")
    assert r.status_code == 200 and r.json().get("status") == "ok"

    r = client.get("/readiness")
    assert r.status_code == 200 and isinstance(r.json().get("timestamp"), float)

    r = client.get("/config")
    assert r.status_code == 200 and "config" in r.json()

    r = client.get("/templates")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_memory_stm_and_ltm():
    session = "pytestsession"

    # ensure we can create and read STM
    r = client.post(f"/memory/stm/{session}", json={"foo": "bar"})
    assert r.status_code == 200 and r.json()["status"] == "saved"

    r = client.get(f"/memory/stm/{session}")
    assert r.status_code == 200 and r.json()["stm"]["foo"] == "bar"

    # LTM (sqlite backend) should return a list
    r = client.get(f"/memory/ltm/{session}")
    assert r.status_code == 200 and "ltm" in r.json()


def test_tools_auth():
    # without key -> 401
    r = client.get("/tools")
    assert r.status_code == 401

    # with api key from config -> should be allowed (even if empty list)
    api_key = api_backend.config_mgr.get("api_keys", {}).get("openai")
    assert api_key is not None
    r = client.get("/tools", headers={"x-api-key": api_key})
    assert r.status_code == 200


def test_english_to_json_manual_mode():
    # Config is set to manual by default in tests; endpoint should return a prompt
    assert api_backend.llm_translator.mode == "manual"
    r = client.post("/english_to_json", json={"instructions": "Create a simple workflow"})
    assert r.status_code == 200
    j = r.json()
    assert "prompt" in j and "note" in j


def test_orchestrate_async_with_mock(monkeypatch):
    class FakeOrch:
        def run_workflow(self, cfg):
            return {"ok": True, "cfg": cfg}

    monkeypatch.setattr(api_backend, "orchestrator", FakeOrch())

    r = client.post("/orchestrate_async", json={"config_json": {"x": 1}})
    assert r.status_code == 200
    run_id = r.json().get("run_id")
    assert run_id is not None

    # Poll for status until completed
    for _ in range(30):
        s = client.get(f"/status/{run_id}")
        assert s.status_code == 200
        data = s.json()
        if data.get("status") == "completed":
            assert data.get("result") == {"ok": True, "cfg": {"x": 1}}
            break
        time.sleep(0.1)
    else:
        pytest.fail("orchestration did not complete")
