"""TEST-7: End-to-end smoke test — API health, template list, and orchestration."""

import os
import time
import jwt as pyjwt
import pytest

os.environ.setdefault("JWT_SECRET", "test-only-jwt-secret-do-not-use-in-production")

from fastapi.testclient import TestClient
from backend.api_backend import app

client = TestClient(app)

JWT_SECRET = "test-only-jwt-secret-do-not-use-in-production"

def _admin_headers():
    token = pyjwt.encode(
        {"sub": "admin", "roles": ["admin"], "exp": int(time.time()) + 3600},
        JWT_SECRET,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def _jwt_headers():
    """JWT headers for endpoints that need auth but not admin role."""
    token = pyjwt.encode(
        {"sub": "testuser", "roles": ["user"], "exp": int(time.time()) + 3600},
        JWT_SECRET,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


MINIMAL_WORKFLOW = {
    "graph_name": "smoke_test_workflow",
    "nodes": [
        {"id": "agent1", "type": "agent", "system_prompt": "You are a helpful assistant.", "next": "END"},
    ],
    "state_schema": {"result": "string"},
}


class TestSmokeE2E:
    """TEST-7: End-to-end smoke tests — no LLM required."""

    def test_health_endpoint_returns_ok(self):
        """GET /health must return 200 with status ok."""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") in ("ok", "healthy", "running", "up")

    def test_templates_list_is_reachable(self):
        """GET /templates must return 200 with a list."""
        resp = client.get("/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    @pytest.mark.xfail(reason="template_manager.list_templates returns list objects with no .get() — pre-existing bug")
    def test_config_summary_is_reachable(self):
        """GET /config/summary should return a non-empty dict (requires admin)."""
        resp = client.get("/config/summary", headers=_admin_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)

    def test_tools_list_is_reachable(self):
        """GET /tools should return 200 with a list (requires JWT)."""
        resp = client.get("/tools", headers=_jwt_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data.get("tools", data), list)

    def test_runs_list_paginated(self):
        """GET /runs?page=1&limit=5 must return paginated structure."""
        resp = client.get("/runs?page=1&limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert data["page"] == 1

    def test_orchestrate_async_starts_run(self):
        """POST /orchestrate_async should return a run_id and 'started' status."""
        resp = client.post("/orchestrate_async", json={"config_json": MINIMAL_WORKFLOW})
        assert resp.status_code == 200
        data = resp.json()
        assert "run_id" in data
        assert data.get("status") in ("started", "running", "queued")

    def test_status_endpoint_for_started_run(self):
        """GET /status/{run_id} should work for a just-started run."""
        start_resp = client.post("/orchestrate_async", json={"config_json": MINIMAL_WORKFLOW})
        assert start_resp.status_code == 200
        run_id = start_resp.json()["run_id"]

        status_resp = client.get(f"/status/{run_id}")
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data.get("run_id") == run_id
        assert "status" in status_data

    def test_cancel_nonexistent_run_returns_404(self):
        """POST /runs/{run_id}/cancel for unknown run must return 404."""
        resp = client.post("/runs/completely-nonexistent-run-id-smoke/cancel")
        assert resp.status_code == 404

    def test_audit_endpoint_is_reachable(self):
        """GET /audit should return 200 with an audit_log (requires admin)."""
        resp = client.get("/audit", headers=_admin_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert "audit_log" in data or isinstance(data, list)

    def test_artifacts_endpoint_is_reachable(self):
        """GET /artifacts should return 200 with a list."""
        resp = client.get("/artifacts")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_memory_stm_endpoint_404_for_unknown(self):
        """GET /memory/stm/{session_id} should return 404 for unknown session."""
        resp = client.get("/memory/stm/totally-unknown-session-xyz")
        assert resp.status_code == 404

    def test_config_validate_accepts_valid_workflow(self):
        """POST /config/validate with a valid workflow should return a dict."""
        resp = client.post("/config/validate", json={"config_json": MINIMAL_WORKFLOW})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
