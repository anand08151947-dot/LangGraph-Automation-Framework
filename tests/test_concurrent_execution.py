"""TEST-3: Concurrent workflow execution tests — race conditions and STM integrity.

All tests use real MemoryManager with mocked graph/LLM layers to avoid network calls.
"""

import threading
import time
import pytest
from unittest.mock import patch, MagicMock
from backend.orchestrator import Orchestrator
from backend.memory_manager import MemoryManager


def _simple_config(name: str = "concurrent_test"):
    return {
        "graph_name": name,
        "agents": [
            {"name": "step1", "system_prompt": "process", "next": "END"},
        ],
    }


def _make_mock_graph(state_per_node=None):
    """Return a mock LangGraph that yields one fake node update."""
    state_per_node = state_per_node or [{"result": "done"}]
    mock_graph = MagicMock()
    mock_graph.stream.return_value = iter([{"step1": s} for s in state_per_node])
    return mock_graph


def _run_session_mocked(orch, session_id, results, errors):
    """Run orchestrator with mocked graph factory for speed."""
    try:
        cfg = _simple_config()
        mock_graph = _make_mock_graph()
        with patch.object(orch.factory, "build_from_config", return_value=mock_graph):
            r = orch.run_workflow(cfg, session_id=session_id)
        results[session_id] = r
    except Exception as e:
        errors[session_id] = str(e)


class TestConcurrentExecution:
    """TEST-3: Concurrent session isolation and STM integrity."""

    def test_separate_sessions_have_isolated_stm(self, tmp_path):
        """Different session IDs must not cross-contaminate STM."""
        ltm_db = str(tmp_path / "concurrent.db")
        mem = MemoryManager(stm_backend="memory", ltm_backend="sqlite", ltm_path=ltm_db)
        orch = Orchestrator()
        orch.memory_manager = mem

        for i in range(3):
            sid = f"sess-{i}"
            cfg = _simple_config()
            mock_graph = _make_mock_graph([{"payload": f"data-{i}"}])
            with patch.object(orch.factory, "build_from_config", return_value=mock_graph):
                orch.run_workflow(cfg, session_id=sid)

        for i in range(3):
            stm = mem.load_stm(f"sess-{i}")
            assert stm is not None, f"STM missing for sess-{i}"

    def test_concurrent_distinct_sessions_do_not_corrupt(self, tmp_path):
        """Concurrent runs on distinct sessions must each complete without STM corruption."""
        ltm_db = str(tmp_path / "concurrent2.db")
        mem = MemoryManager(stm_backend="memory", ltm_backend="sqlite", ltm_path=ltm_db)
        orch = Orchestrator()
        orch.memory_manager = mem

        results: dict = {}
        errors: dict = {}
        threads = []

        for i in range(4):
            t = threading.Thread(
                target=_run_session_mocked,
                args=(orch, f"concurrent-sess-{i}", results, errors),
            )
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"Threads raised errors: {errors}"
        for i in range(4):
            sid = f"concurrent-sess-{i}"
            stm = mem.load_stm(sid)
            assert stm is not None, f"STM missing for {sid}"

    def test_session_lock_acquired_per_session(self, tmp_path):
        """_get_session_lock must return distinct locks for distinct session IDs."""
        orch = Orchestrator()
        lock_a = orch._get_session_lock("lock-sess-A")
        lock_b = orch._get_session_lock("lock-sess-B")
        lock_a2 = orch._get_session_lock("lock-sess-A")
        assert lock_a is lock_a2, "Same session must return same lock"
        assert lock_a is not lock_b, "Different sessions must have different locks"

    def test_concurrent_ltm_writes_do_not_corrupt(self, tmp_path):
        """Concurrent LTM append operations must all persist without data loss."""
        ltm_db = str(tmp_path / "ltm_concurrent.db")
        mem = MemoryManager(stm_backend="memory", ltm_backend="sqlite", ltm_path=ltm_db)

        write_errors: list = []

        def write_entries(session_id: str):
            for i in range(5):
                try:
                    mem.append_ltm(session_id, {"thread": session_id, "step": i, "data": f"x{i}"})
                except Exception as e:
                    write_errors.append(str(e))

        threads = [threading.Thread(target=write_entries, args=(f"ltm-sess-{j}",)) for j in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert not write_errors, f"LTM write errors: {write_errors}"

        for j in range(4):
            entries = mem.load_ltm(f"ltm-sess-{j}")
            assert isinstance(entries, list)
            assert len(entries) == 5

    def test_concurrent_stm_writes_are_isolated(self, tmp_path):
        """Concurrent save_stm calls for distinct sessions must not interfere."""
        mem = MemoryManager(stm_backend="memory", ltm_backend="sqlite", ltm_path=str(tmp_path / "stm.db"))
        write_errors: list = []

        def do_writes(sid: str):
            for i in range(10):
                try:
                    mem.save_stm(sid, {"count": i, "session": sid})
                except Exception as e:
                    write_errors.append(str(e))

        threads = [threading.Thread(target=do_writes, args=(f"stm-sess-{j}",)) for j in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert not write_errors, f"STM write errors: {write_errors}"
        for j in range(6):
            stm = mem.load_stm(f"stm-sess-{j}")
            assert stm is not None
