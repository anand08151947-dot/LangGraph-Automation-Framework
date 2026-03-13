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


class HumanApprovalRequired(Exception):
    def __init__(self, run_id: str, checkpoint_node: str, state: dict):
        super().__init__(f"Workflow paused at human checkpoint: {checkpoint_node}")
        self.run_id = run_id
        self.checkpoint_node = checkpoint_node
        self.state = state


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
                        _human_pause_node = None
                        for node_name, node_updates in step_output.items():
                            if isinstance(node_updates, dict):
                                last_state.update(node_updates)
                            # Check if this node is a human_node checkpoint
                            nodes_cfg = config_json.get("nodes", [])
                            for n in nodes_cfg:
                                if n.get("id") == node_name and n.get("type") == "human_node":
                                    _human_pause_node = node_name
                                    break

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

                        # HITL: pause at human_node checkpoint
                        if _human_pause_node:
                            last_state["__awaiting_approval__"] = True
                            last_state["__checkpoint_node__"] = _human_pause_node
                            if session_id:
                                memory_manager.save_stm(session_id, last_state)
                            raise HumanApprovalRequired(
                                run_id=session_id or "",
                                checkpoint_node=_human_pause_node,
                                state=dict(last_state),
                            )

                        # Post-step hooks
                        observability.run_plugin_hooks("post_step", {
                            "step_idx": step_idx,
                            "state": last_state,
                        })

                        break  # success – exit retry loop

                    except HumanApprovalRequired:
                        raise  # propagate without retry
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

    def resume_run(
        self,
        run_id: str,
        approval_input: Dict[str, Any],
        config_json: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Resume a workflow paused at a human_node checkpoint.

        Loads the persisted STM state, merges approval_input into it,
        clears the __awaiting_approval__ flag, then re-runs from there.
        """
        memory_cfg = config_json.get("memory", {})
        memory_manager = (
            MemoryManager(**memory_cfg) if memory_cfg else self.memory_manager
        )

        loaded = memory_manager.load_stm(run_id)
        if not loaded or not isinstance(loaded, dict):
            raise ValueError(f"No saved state found for run_id={run_id}")
        if not loaded.get("__awaiting_approval__"):
            raise ValueError(f"Run {run_id} is not awaiting approval")

        merged_state = dict(loaded)
        merged_state.update(approval_input)
        merged_state.pop("__awaiting_approval__", None)
        merged_state.pop("__checkpoint_node__", None)

        return self.run_workflow(config_json, session_id=run_id, initial_state=merged_state)


# Usage example:
# orchestrator = Orchestrator()
# result = orchestrator.run_workflow(config_json, session_id="run-001")
