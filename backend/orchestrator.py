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

import math
import json
import threading
import time
import concurrent.futures
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


def _build_memory_manager(memory_cfg: dict) -> MemoryManager:
    """Translate workflow template memory config keys → MemoryManager kwargs."""
    if not memory_cfg:
        return MemoryManager()
    stm = memory_cfg.get("short_term", {})
    ltm = memory_cfg.get("long_term", {})
    stm_backend = stm.get("type", stm.get("backend", "memory")) if isinstance(stm, dict) else "memory"
    ltm_backend = ltm.get("type", ltm.get("backend", "sqlite")) if isinstance(ltm, dict) else "sqlite"
    ltm_path = ltm.get("path", "ltm.db") if isinstance(ltm, dict) else "ltm.db"
    max_stm_entries = int(stm.get("max_entries", 0)) if isinstance(stm, dict) else 0
    ltm_ttl_days = float(ltm.get("ttl_days", 0)) if isinstance(ltm, dict) else 0
    return MemoryManager(
        stm_backend=stm_backend,
        ltm_backend=ltm_backend,
        ltm_path=ltm_path,
        max_stm_entries=max_stm_entries,
        ltm_ttl_days=ltm_ttl_days,
    )


class Orchestrator:
    def __init__(self, max_retries: int = 2):
        # MCP binder may be optionally configured at runtime
        self.mcp_binder = MCPAutoBinder()
        self.factory = GraphFactory(mcp_tool_binder=self.mcp_binder)
        self.memory_manager = MemoryManager()
        self.observability = ObservabilityManager(["logging"])
        self.max_retries = max_retries
        # ORCH-4: per-session locks to prevent concurrent STM corruption
        self._session_locks: Dict[str, threading.Lock] = {}
        self._session_locks_mutex = threading.Lock()

    def _get_session_lock(self, session_id: str) -> threading.Lock:
        """Return (creating if needed) the per-session lock."""
        with self._session_locks_mutex:
            if session_id not in self._session_locks:
                self._session_locks[session_id] = threading.Lock()
            return self._session_locks[session_id]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_workflow(
        self,
        config_json: Dict[str, Any],
        session_id: Optional[str] = None,
        initial_state: Optional[Dict[str, Any]] = None,
        cancel_check_fn: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Run the workflow step-by-step, persisting memory at every step.

        Uses graph.stream() (the correct LangGraph API) which yields
        {node_name: state_updates} dicts for each executed node.

        Args:
            config_json:     Workflow config (old agents[] or new nodes[]).
            session_id:      Unique run identifier used for STM/LTM storage.
            initial_state:   Optional override for the starting state dict.
            cancel_check_fn: Optional zero-argument callable; if it returns
                             True the orchestrator raises CancelledError after
                             the current step (API-3).

        Returns:
            The final merged state dict (JSON-serializable).
        """
        # ── ORC-1: Config-driven managers ─────────────────────────────
        memory_cfg = config_json.get("memory", {})
        runtime_cfg = config_json.get("runtime", {})
        retry_policy = config_json.get("retry_policy", {})

        # ORC-5: Parse observability_hooks — supports both dict and legacy list form
        obs_hooks_raw = config_json.get("observability_hooks", {})
        if isinstance(obs_hooks_raw, dict):
            obs_cfg = obs_hooks_raw
            obs_backends = ["logging"]
        else:
            obs_cfg = {}
            obs_backends = obs_hooks_raw if isinstance(obs_hooks_raw, list) and obs_hooks_raw else ["logging"]
        _obs_trace_nodes = obs_cfg.get("trace_nodes", True)
        _obs_log_transitions = obs_cfg.get("log_state_transitions", True)
        _obs_capture_outputs = obs_cfg.get("capture_agent_outputs", True)

        # ORC-4: Retry / backoff configuration from retry_policy
        max_retries_cfg = int(retry_policy.get("max_retries", self.max_retries))
        backoff_strategy = retry_policy.get("backoff_strategy", "fixed")
        backoff_base = float(retry_policy.get("backoff_base_seconds", 1.0))

        # ORCH-1: Per-node timeout (None = no limit)
        node_timeout_seconds = runtime_cfg.get("node_timeout_seconds")

        # ORCH-2: Circuit-breaker — track consecutive per-node failures
        cb_threshold = int(retry_policy.get("circuit_breaker_threshold", max_retries_cfg + 1))
        _node_failure_counts: Dict[str, int] = {}
        _open_circuits: Dict[str, str] = {}  # node_name -> reason

        # Build per-run MemoryManager from config (fall back to instance default)
        memory_manager = _build_memory_manager(memory_cfg) if memory_cfg else self.memory_manager
        observability = ObservabilityManager(obs_backends)

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

        # ORCH-3: Validate initial_state against state_schema before the run starts.
        # Unknown keys in initial_state silently corrupt downstream state; reject early.
        if initial_state and isinstance(initial_state, dict) and state_schema:
            declared_keys = set(state_schema.keys())
            unknown_keys = set(initial_state.keys()) - declared_keys
            if unknown_keys:
                raise ValueError(
                    f"initial_state contains keys not declared in state_schema: {sorted(unknown_keys)}. "
                    f"Declared keys: {sorted(declared_keys)}"
                )

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

        # ORCH-4: acquire session lock to prevent concurrent STM corruption
        _session_lock = self._get_session_lock(session_id) if session_id else None

        def _advance(stream_iter):
            """Advance the graph stream by one step; returns (step_output, done)."""
            try:
                return next(stream_iter), False
            except StopIteration:
                return None, True

        try:
            if _session_lock:
                _session_lock.acquire()
            stream_iter = iter(graph.stream(current_state))
            # ORCH-1: use a thread pool so we can apply a per-node wall-clock timeout.
            # We manage shutdown manually (cancel_futures=True) to avoid blocking on
            # interpreter teardown (e.g., during tests).
            _exec = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            try:
                while True:
                    # ORC-6: Check workflow-level timeout at every step boundary
                    if _timed_out.is_set():
                        raise TimeoutError(
                            f"Workflow exceeded timeout of {timeout_seconds}s "
                            f"after {step_idx} steps."
                        )

                    # API-3: Check cancellation flag between steps
                    if cancel_check_fn is not None and cancel_check_fn():
                        raise InterruptedError(
                            f"Workflow {session_id} cancelled after {step_idx} steps."
                        )

                    # ORCH-1: advance the stream with a per-node deadline
                    _future = _exec.submit(_advance, stream_iter)
                    try:
                        step_output, _done = _future.result(timeout=node_timeout_seconds)
                    except concurrent.futures.TimeoutError:
                        raise TimeoutError(
                            f"Node timed out after {node_timeout_seconds}s at step {step_idx}. "
                            "Increase runtime.node_timeout_seconds or fix the blocking node."
                        )
                    if _done:
                        break

                    # Identify the node name from this step's output
                    _current_node = next(iter(step_output), "") if step_output else ""

                    # ORCH-2: skip nodes whose circuit is open
                    if _current_node and _current_node in _open_circuits:
                        reason = _open_circuits[_current_node]
                        observability.log_event("circuit_open_skip", {
                            "node": _current_node,
                            "reason": reason,
                            "step_idx": step_idx,
                        })
                        step_idx += 1
                        continue

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

                            # ORC-5: Log state transition (conditional)
                            if _obs_log_transitions:
                                observability.log_event("agent_action", {
                                    "step_idx": step_idx,
                                    "sender": sender,
                                    "messages": last_state.get("messages", []),
                                    "metadata": last_state.get("metadata", {}),
                                })

                            # ORC-5: Trace the step (conditional on trace_nodes)
                            if _obs_trace_nodes and session_id:
                                observability.trace_step(session_id, {
                                    "step_idx": step_idx,
                                    "sender": sender,
                                    "node": sender,
                                    "metadata": last_state.get("metadata", {}),
                                })

                            # ORC-5: Capture agent outputs (conditional)
                            if _obs_capture_outputs:
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

                            # ORCH-2: on success, reset the node's consecutive failure count
                            if _current_node:
                                _node_failure_counts.pop(_current_node, None)

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

                            # ORCH-2: track consecutive failures per node and open circuit
                            if _current_node:
                                _node_failure_counts[_current_node] = (
                                    _node_failure_counts.get(_current_node, 0) + 1
                                )
                                if _node_failure_counts[_current_node] >= cb_threshold:
                                    reason = (
                                        f"Circuit opened after {cb_threshold} consecutive "
                                        f"failures: {exc}"
                                    )
                                    _open_circuits[_current_node] = reason
                                    observability.log_event("circuit_breaker_open", {
                                        "node": _current_node,
                                        "failures": _node_failure_counts[_current_node],
                                        "reason": reason,
                                    })
                                    last_state.setdefault("__circuit_breaker_events__", []).append({
                                        "node": _current_node, "reason": reason,
                                        "step_idx": step_idx,
                                    })
                                    break  # skip this node; move to next step

                            if retry_count > max_retries_cfg:
                                raise  # abort after max retries
                            # ORC-4: Backoff sleep before retry (fixed or exponential) with ±20% jitter
                            if backoff_strategy == "exponential":
                                sleep_s = backoff_base * math.pow(2, retry_count - 1)
                            else:
                                sleep_s = backoff_base
                            import random
                            jitter = sleep_s * 0.2 * (random.random() * 2 - 1)  # ORCH-5: ±20%
                            time.sleep(min(max(0, sleep_s + jitter), 30.0))  # cap at 30s

                    step_idx += 1

                    # Honour max_iterations guard (defensive; graph also enforces it)
                    if step_idx >= max_iterations:
                        break
            finally:
                # ORCH-1: shut down without waiting so interpreter teardown
                # (e.g., during tests) doesn't block on in-flight futures.
                _exec.shutdown(wait=False, cancel_futures=True)

        finally:
            # ORC-6: always cancel the timer to avoid resource leaks
            if _timer:
                _timer.cancel()
            # ORCH-4: release session lock
            if _session_lock and _session_lock.locked():
                _session_lock.release()

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
        memory_manager = _build_memory_manager(memory_cfg) if memory_cfg else self.memory_manager

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
