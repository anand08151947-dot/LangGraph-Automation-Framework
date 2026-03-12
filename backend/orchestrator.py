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
        # ── Build graph ────────────────────────────────────────────────
        graph = self.factory.build_from_config(config_json)

        # ── Build initial state dict ───────────────────────────────────
        state_schema: Dict[str, str] = config_json.get("state_schema", {})
        max_iterations: int = config_json.get("runtime", {}).get("max_iterations", 20)

        # Try to resume from saved STM when a session_id is provided
        current_state: Dict[str, Any] = {}
        if session_id:
            loaded = self.memory_manager.load_stm(session_id)
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

        for step_output in graph.stream(current_state):
            retry_count = 0
            while True:
                try:
                    # Merge node updates into running state
                    for node_name, node_updates in step_output.items():
                        if isinstance(node_updates, dict):
                            last_state.update(node_updates)

                    sender = last_state.get("sender", "")

                    # Pre-step hooks
                    self.observability.run_plugin_hooks("pre_step", {
                        "step_idx": step_idx,
                        "state": last_state,
                    })

                    # Log the agent action
                    self.observability.log_event("agent_action", {
                        "step_idx": step_idx,
                        "sender": sender,
                        "messages": last_state.get("messages", []),
                        "metadata": last_state.get("metadata", {}),
                    })

                    # Trace the step (if session tracking is enabled)
                    if session_id:
                        self.observability.trace_step(session_id, {
                            "step_idx": step_idx,
                            "sender": sender,
                            "node": sender,
                            "metadata": last_state.get("metadata", {}),
                        })

                    # Record step metric
                    self.observability.record_metric(
                        "step_executed", 1,
                        {"step_idx": step_idx, "sender": sender},
                    )

                    # Persist STM (latest state) and append LTM entry
                    if session_id:
                        self.memory_manager.save_stm(session_id, last_state)
                        self.memory_manager.append_ltm(session_id, {
                            "step_idx": step_idx,
                            "messages": last_state.get("messages", []),
                            "sender": sender,
                            "metadata": last_state.get("metadata", {}),
                        })

                    # Post-step hooks
                    self.observability.run_plugin_hooks("post_step", {
                        "step_idx": step_idx,
                        "state": last_state,
                    })

                    break  # success – exit retry loop

                except Exception as exc:
                    self.observability.log_error(exc, context={
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

        return last_state


# Usage example:
# orchestrator = Orchestrator()
# result = orchestrator.run_workflow(config_json, session_id="run-001")
