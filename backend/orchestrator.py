"""
orchestrator.py
End-to-end workflow execution and result collection.

Features:
- Accept config JSON (old agents[] or new enterprise nodes[] format)
- Assemble graph via GraphFactory + MCPAutoBinder
- Execute workflow using graph.stream() (correct LangGraph API)
- Save STM/LTM via MemoryManager after each step
- Log and trace each step via ObservabilityManager
- Return final state as a JSON-serializable dict
"""

import threading
import time
from typing import Any, Dict, Optional

from graph_factory import GraphFactory, _make_default_state
from mcp_autobinder import MCPAutoBinder
from memory_manager import MemoryManager
from observability_manager import ObservabilityManager


class Orchestrator:
    def __init__(self, max_retries: int = 2):
        # MCP binder may be optionally configured at runtime
        self.mcp_binder = MCPAutoBinder()
        self.factory = GraphFactory(mcp_tool_binder=self.mcp_binder)
        self.memory_manager = MemoryManager()
        self.observability = ObservabilityManager(["logging"])
        self.max_retries = max_retries

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_workflow(
        self,
        config_json: Dict[str, Any],
        session_id: Optional[str] = None,
        initial_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Run the workflow step-by-step, persisting memory at every step.

        Uses graph.stream() (the correct LangGraph API) which yields
        {node_name: state_updates} dicts for each executed node.

        Args:
            config_json:   Workflow config (old agents[] or new nodes[]).
            session_id:    Unique run identifier used for STM/LTM storage.
            initial_state: Optional override for the starting state dict.

        Returns:
            The final merged state dict (JSON-serializable).
        """
        # ── ORC-1: Config-driven managers ─────────────────────────────
        memory_cfg = config_json.get("memory", {})
        obs_hooks = config_json.get("observability_hooks", ["logging"])
        runtime_cfg = config_json.get("runtime", {})

        # Build per-run MemoryManager from config (fall back to instance default)
        memory_manager = (
            MemoryManager(**memory_cfg) if memory_cfg else self.memory_manager
        )
        observability = ObservabilityManager(obs_hooks)

        # ── ORC-2: Build graph (pass session_id through) ───────────────
        graph = self.factory.build_from_config(config_json, session_id=session_id)

        # ── ORC-6: Timeout setup ───────────────────────────────────────
        timeout_seconds = runtime_cfg.get("timeout_seconds")
        _timed_out = threading.Event()
        _timer = (
            threading.Timer(timeout_seconds, _timed_out.set)
            if timeout_seconds
            else None
        )
        if _timer:
            _timer.start()

        # ── Build initial state dict ───────────────────────────────────
        state_schema: Dict[str, str] = config_json.get("state_schema", {})
        max_iterations: int = runtime_cfg.get("max_iterations", 20)

        # Try to resume from saved STM when a session_id is provided
        current_state: Dict[str, Any] = {}
        if session_id:
            loaded = memory_manager.load_stm(session_id)
            if loaded and isinstance(loaded, dict):
                current_state = loaded

        if not current_state:
            if initial_state and isinstance(initial_state, dict):
                current_state = initial_state
            else:
                current_state = _make_default_state(state_schema)

        # ── Step-by-step execution via graph.stream() ──────────────────
        # graph.stream() yields {node_name: {field: value, ...}} per step.
        step_idx = 0
        last_state = dict(current_state)

        try:
            for step_output in graph.stream(current_state):
                # ORC-6: Check timeout at every step boundary
                if _timed_out.is_set():
                    raise TimeoutError(
                        f"Workflow exceeded timeout of {timeout_seconds}s "
                        f"after {step_idx} steps."
                    )

                retry_count = 0
                while True:
                    try:
                        step_start = time.time()  # ORC-3: per-step start time

                        # Merge node updates into running state
                        for node_name, node_updates in step_output.items():
                            if isinstance(node_updates, dict):
                                last_state.update(node_updates)

                        sender = last_state.get("sender", "")

                        # Pre-step hooks
                        observability.run_plugin_hooks("pre_step", {
                            "step_idx": step_idx,
                            "state": last_state,
                        })

                        # Log the agent action
                        observability.log_event("agent_action", {
                            "step_idx": step_idx,
                            "sender": sender,
                            "messages": last_state.get("messages", []),
                            "metadata": last_state.get("metadata", {}),
                        })

                        # Trace the step (if session tracking is enabled)
                        if session_id:
                            observability.trace_step(session_id, {
                                "step_idx": step_idx,
                                "sender": sender,
                                "node": sender,
                                "metadata": last_state.get("metadata", {}),
                            })

                        # Record step metric
                        observability.record_metric(
                            "step_executed", 1,
                            {"step_idx": step_idx, "sender": sender},
                        )

                        # ORC-3: capture end time and compute duration
                        step_end = time.time()
                        duration_ms = round((step_end - step_start) * 1000, 3)

                        # Persist STM (latest state) and append LTM entry
                        if session_id:
                            memory_manager.save_stm(session_id, last_state)
                            memory_manager.append_ltm(session_id, {
                                "step_idx": step_idx,
                                "messages": last_state.get("messages", []),
                                "sender": sender,
                                "metadata": last_state.get("metadata", {}),
                                "start_time": step_start,   # ORC-3
                                "end_time": step_end,        # ORC-3
                                "duration_ms": duration_ms,  # ORC-3
                            })

                        # Post-step hooks
                        observability.run_plugin_hooks("post_step", {
                            "step_idx": step_idx,
                            "state": last_state,
                        })

                        break  # success – exit retry loop

                    except Exception as exc:
                        observability.log_error(exc, context={
                            "step_idx": step_idx,
                            "sender": last_state.get("sender"),
                            "retry": retry_count,
                        })
                        retry_count += 1
                        if retry_count > self.max_retries:
                            raise  # abort after max retries

                step_idx += 1

                # Honour max_iterations guard (defensive; graph also enforces it)
                if step_idx >= max_iterations:
                    break

        finally:
            # ORC-6: always cancel the timer to avoid resource leaks
            if _timer:
                _timer.cancel()

        return last_state


# Usage example:
# orchestrator = Orchestrator()
# result = orchestrator.run_workflow(config_json, session_id="run-001")
