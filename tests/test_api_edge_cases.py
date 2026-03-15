"""
TEST-2: Error handling and edge case tests for the API layer.
Covers: malformed payloads (400/422), missing required fields, unknown session IDs (404),
and boundary conditions.
"""
import pytest
from fastapi.testclient import TestClient
import backend.api_backend as api_backend

client = TestClient(api_backend.app)


# ---------------------------------------------------------------------------
# /orchestrate_async — validation errors
# ---------------------------------------------------------------------------

def test_orchestrate_async_missing_config_json_returns_422():
    r = client.post("/orchestrate_async", json={})
    assert r.status_code == 422


def test_orchestrate_async_malformed_body_returns_422():
    r = client.post("/orchestrate_async", content=b"not valid json", headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_orchestrate_async_empty_config_still_starts():
    # An empty config_json dict is technically valid (no required inner fields at API layer)
    r = client.post("/orchestrate_async", json={"config_json": {}})
    assert r.status_code == 200
    assert "run_id" in r.json()


# ---------------------------------------------------------------------------
# /status/{run_id} — unknown run IDs
# ---------------------------------------------------------------------------

def test_status_unknown_run_id_returns_404():
    r = client.get("/status/00000000-dead-beef-0000-000000000000")
    assert r.status_code == 404


def test_status_valid_run_id_returns_200():
    # Start a run, then immediately poll status
    r = client.post("/orchestrate_async", json={"config_json": {"graph_name": "status_test", "agents": []}})
    assert r.status_code == 200
    run_id = r.json()["run_id"]
    s = client.get(f"/status/{run_id}")
    assert s.status_code == 200
    assert s.json()["run_id"] == run_id


# ---------------------------------------------------------------------------
# /runs/{run_id}/config — unknown run IDs
# ---------------------------------------------------------------------------

def test_run_config_unknown_run_id_returns_404():
    r = client.get("/runs/00000000-dead-beef-0000-000000000001/config")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# /memory/stm/{session_id} and /memory/ltm/{session_id} — unknown sessions
# ---------------------------------------------------------------------------

def test_stm_unknown_session_returns_404_or_empty():
    r = client.get("/memory/stm/nonexistent-session-xyz")
    # Either 404 or returns empty/null stm — both are acceptable
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        assert r.json().get("stm") is None or r.json().get("stm") == {}


def test_ltm_unknown_session_returns_404_or_empty():
    r = client.get("/memory/ltm/nonexistent-session-xyz")
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        data = r.json().get("ltm")
        assert data is None or data == []


# ---------------------------------------------------------------------------
# /english_to_json — missing required fields
# ---------------------------------------------------------------------------

def test_english_to_json_missing_instructions_returns_422():
    r = client.post("/english_to_json", json={})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# /runs/{run_id}/cancel — unknown run ID
# ---------------------------------------------------------------------------

def test_cancel_unknown_run_returns_404():
    r = client.post("/runs/00000000-dead-beef-0000-000000000002/cancel")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# /templates — listing
# ---------------------------------------------------------------------------

def test_templates_endpoint_returns_list():
    r = client.get("/templates")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_template_unknown_name_returns_404():
    r = client.get("/template/nonexistent-template-xyz-12345")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

def test_health_endpoint_returns_ok():
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert "status" in data
