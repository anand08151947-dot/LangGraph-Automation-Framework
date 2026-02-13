import os
import tempfile
import time
import pytest
from backend.orchestrator import Orchestrator
from backend.memory_manager import MemoryManager
from backend.observability_manager import ObservabilityManager


def make_config():
    return {
        "graph_name": "itest",
        "agents": [
            {"name": "n1", "system_prompt": "s1", "next": "n2"},
            {"name": "n2", "system_prompt": "s2", "next": "END"}
        ]
    }


def test_orchestrator_persists_stm_and_ltm(tmp_path):
    ltm_db = str(tmp_path / "ltm.db")
    orch = Orchestrator()
    # Replace memory manager with temp-backed one for isolation
    orch.memory_manager = MemoryManager(stm_backend="memory", ltm_backend="sqlite", ltm_path=ltm_db)
    # Attach an observability manager that records hooks
    events = []
    obs = ObservabilityManager(["logging"])
    obs.register_hook("pre_step", lambda d: events.append(("pre", d)))
    obs.register_hook("post_step", lambda d: events.append(("post", d)))
    obs.register_hook("error", lambda d: events.append(("error", d)))
    orch.observability = obs

    cfg = make_config()
    result = orch.run_workflow(cfg, session_id="testsess1")

    # After run, STM should exist
    stm = orch.memory_manager.load_stm("testsess1")
    assert stm is not None
    # LTM should contain at least one step entry
    ltm = orch.memory_manager.load_ltm("testsess1")
    assert isinstance(ltm, list)
    assert len(ltm) >= 1
    # Observability hooks should have been triggered
    assert any(ev[0] == "pre" for ev in events)
    assert any(ev[0] == "post" for ev in events)


def test_orchestrator_retries_on_save_failure(tmp_path):
    ltm_db = str(tmp_path / "ltm_retry.db")
    orch = Orchestrator(max_retries=2)
    orch.memory_manager = MemoryManager(stm_backend="memory", ltm_backend="sqlite", ltm_path=ltm_db)
    obs = ObservabilityManager(["logging"])
    errors = []
    obs.register_hook("error", lambda d: errors.append(d))
    orch.observability = obs

    # Make save_stm fail on first call, succeed thereafter
    call_count = {"n": 0}
    real_save = orch.memory_manager.save_stm

    def flaky_save(session_id, state):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated save failure")
        return real_save(session_id, state)

    orch.memory_manager.save_stm = flaky_save

    cfg = make_config()
    # Should succeed despite initial failure due to retry
    result = orch.run_workflow(cfg, session_id="testsess_retry")

    # Ensure at least one error was logged (hook captured it)
    assert len(errors) >= 1
    # STM/LTM should still be present after recovery
    assert orch.memory_manager.load_stm("testsess_retry") is not None
    assert isinstance(orch.memory_manager.load_ltm("testsess_retry"), list)
