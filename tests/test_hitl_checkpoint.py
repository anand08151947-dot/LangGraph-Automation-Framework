"""TEST-5: Human-in-loop checkpoint and resume tests."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# Set JWT_SECRET before import
import os
os.environ.setdefault("JWT_SECRET", "test-only-jwt-secret-do-not-use-in-production")

from backend.api_backend import app
from backend.orchestrator import Orchestrator, HumanApprovalRequired as HumanApprovalPause
from backend.memory_manager import MemoryManager

client = TestClient(app)


def _make_mock_graph():
    """Mock graph that streams one node result."""
    mock_graph = MagicMock()
    mock_graph.stream.return_value = iter([{"agent1": {"result": "done"}}])
    return mock_graph


class TestHumanApprovalResumeLogic:
    """TEST-5: resume_run logic tested against real orchestrator with mocked graph."""

    def test_resume_without_saved_state_raises(self, tmp_path):
        """resume_run should raise ValueError if no saved state exists."""
        mem = MemoryManager(stm_backend="memory", ltm_backend="sqlite",
                            ltm_path=str(tmp_path / "no_state.db"))
        orch = Orchestrator()
        orch.memory_manager = mem

        with pytest.raises(ValueError, match="No saved state found"):
            orch.resume_run("nonexistent-run", {}, {"graph_name": "test", "nodes": []})

    def test_resume_requires_awaiting_flag(self, tmp_path):
        """resume_run should raise ValueError if STM lacks __awaiting_approval__."""
        mem = MemoryManager(stm_backend="memory", ltm_backend="sqlite",
                            ltm_path=str(tmp_path / "no_approval.db"))
        orch = Orchestrator()
        orch.memory_manager = mem

        mem.save_stm("run-no-approval", {"task": "done"})
        with pytest.raises(ValueError, match="not awaiting approval"):
            orch.resume_run("run-no-approval", {}, {"graph_name": "test", "nodes": []})

    def test_resume_merges_approval_input(self, tmp_path):
        """On resume, approval_input must be merged and flags cleared before re-run."""
        mem = MemoryManager(stm_backend="memory", ltm_backend="sqlite",
                            ltm_path=str(tmp_path / "resume_merge.db"))
        orch = Orchestrator()
        orch.memory_manager = mem

        mem.save_stm("run-resume", {
            "__awaiting_approval__": True,
            "__checkpoint_node__": "review",
            "task": "pending",
        })

        called_with_state = {}
        original_run = orch.run_workflow

        def capture_run(cfg, session_id=None, initial_state=None, **kw):
            called_with_state.update(initial_state or {})
            return {"result": "resumed"}

        with patch.object(orch, "run_workflow", side_effect=capture_run):
            orch.resume_run("run-resume", {"approved": True}, {"graph_name": "test"})

        assert called_with_state.get("approved") is True
        assert called_with_state.get("task") == "pending"
        assert "__awaiting_approval__" not in called_with_state
        assert "__checkpoint_node__" not in called_with_state

    def test_resume_clears_awaiting_flag(self, tmp_path):
        """__awaiting_approval__ must not appear in the state passed to re-run."""
        mem = MemoryManager(stm_backend="memory", ltm_backend="sqlite",
                            ltm_path=str(tmp_path / "clear_flag.db"))
        orch = Orchestrator()
        orch.memory_manager = mem

        mem.save_stm("run-clear", {"__awaiting_approval__": True, "x": 1})

        seen_state = {}

        def capture_run(cfg, session_id=None, initial_state=None, **kw):
            seen_state.update(initial_state or {})
            return {}

        with patch.object(orch, "run_workflow", side_effect=capture_run):
            orch.resume_run("run-clear", {}, {"graph_name": "t"})

        assert "__awaiting_approval__" not in seen_state


class TestApprovalAPI:
    """TEST-5: Human-in-loop API endpoints."""

    def test_resume_endpoint_404_for_unknown_run(self):
        """POST /resume/{run_id} with unknown run_id should return 400 or 404."""
        resp = client.post("/resume/nonexistent-run-999", json={"approval_input": {}, "config_json": {}})
        assert resp.status_code in (400, 404)

    def test_approval_status_endpoint_404_for_unknown(self):
        """GET /approval/{run_id} should return 404 for unknown run."""
        resp = client.get("/approval/completely-unknown-run-xyz")
        assert resp.status_code == 404

    def test_resume_validates_required_fields(self):
        """ORCH-7: Approval input missing required fields should return 422."""
        from backend.api_backend import _workflow_status_set
        run_id = "test-schema-validation-123"
        _workflow_status_set(run_id, {
            "status": "awaiting_approval",
            "approval_schema": {"required": ["decision"]},
            "config": {"graph_name": "test"},
        })

        resp = client.post(f"/resume/{run_id}",
                           json={"approval_input": {}, "config_json": {"graph_name": "t"}})
        assert resp.status_code == 422
        assert "decision" in resp.json().get("detail", "")

    def test_resume_validates_unexpected_fields(self):
        """ORCH-7: Approval input with unknown keys should return 422."""
        from backend.api_backend import _workflow_status_set
        run_id = "test-unexpected-fields-456"
        _workflow_status_set(run_id, {
            "status": "awaiting_approval",
            "approval_schema": {"allowed_keys": ["approved", "reviewer"]},
            "config": {"graph_name": "test"},
        })

        resp = client.post(f"/resume/{run_id}", json={
            "approval_input": {"approved": True, "injected_key": "evil"},
            "config_json": {"graph_name": "t"}
        })
        assert resp.status_code == 422
        assert "injected_key" in resp.json().get("detail", "")
