"""
orchestrator.py
End-to-end workflow execution and result collection
Features:
- Accept config JSON (from LLM or template)
- Assemble graph (GraphFactory + MCPAutoBinder)
- Execute workflow
- Collect and return results
"""

from graph_factory import GraphFactory, AgentState
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

    def run_workflow(self, config_json, session_id=None, initial_state=None):
        """
        Run the workflow, saving STM and LTM after each step.
        session_id: Unique identifier for the workflow run (for memory tracking)
        """
        graph = self.factory.build_from_config(config_json)
        state = None
        if session_id:
            # Try to load STM for resumption
            loaded = self.memory_manager.load_stm(session_id)
            if loaded:
                state = AgentState(**loaded)
        if not state:
            state = initial_state or AgentState()

        # Custom step-by-step execution to hook memory
        step_idx = 0
        for step_state in graph.iter_run(state):
            retry_count = 0
            while True:
                try:
                    # --- Pre-step plugin hooks ---
                    self.observability.run_plugin_hooks("pre_step", {
                        "step_idx": step_idx,
                        "state": step_state
                    })

                    # Observability: log agent action
                    self.observability.log_event(
                        "agent_action",
                        {
                            "step_idx": step_idx,
                            "sender": step_state.sender,
                            "messages": step_state.messages,
                            "metadata": step_state.metadata
                        }
                    )
                    # Observability: trace step
                    if session_id:
                        self.observability.trace_step(session_id, {
                            "step_idx": step_idx,
                            "sender": step_state.sender,
                            "node": step_state.sender,
                            "metadata": step_state.metadata
                        })
                    # Observability: record metrics (example: step count)
                    self.observability.record_metric("step_executed", 1, {"step_idx": step_idx, "sender": step_state.sender})

                    # Save STM (current state)
                    if session_id:
                        self.memory_manager.save_stm(session_id, step_state.__dict__)
                        # Save LTM (step context)
                        self.memory_manager.append_ltm(session_id, {
                            'step_idx': step_idx,
                            'messages': step_state.messages,
                            'sender': step_state.sender,
                            'metadata': step_state.metadata
                        })

                    # --- Post-step plugin hooks ---
                    self.observability.run_plugin_hooks("post_step", {
                        "step_idx": step_idx,
                        "state": step_state
                    })

                    break  # Success, exit retry loop
                except Exception as e:
                    self.observability.log_error(e, context={
                        "step_idx": step_idx,
                        "sender": getattr(step_state, 'sender', None),
                        "messages": getattr(step_state, 'messages', None),
                        "metadata": getattr(step_state, 'metadata', None),
                        "retry": retry_count
                    })
                    retry_count += 1
                    if retry_count > self.max_retries:
                        # Fallback: skip or abort (here: abort)
                        raise
            step_idx += 1
        # Final state/result
        return step_state

# Usage example:
# orchestrator = Orchestrator()
# result = orchestrator.run_workflow(config_json)
