from langgraph.graph import StateGraph, END
from typing import Any, Dict

class AgentState:
    def __init__(self, messages=None, sender=None, metadata=None):
        self.messages = messages or []
        self.sender = sender
        self.metadata = metadata or {}

class GraphFactory:
    def __init__(self, agent_state_cls=AgentState, mcp_tool_binder=None):
        self.agent_state_cls = agent_state_cls
        self.mcp_tool_binder = mcp_tool_binder

    def create_agent_node(self, agent: Dict[str, Any]):
        # This function returns a callable node for LangGraph
        def node(state: AgentState):
            # Example: Add system prompt and tool info to state metadata
            state.metadata[agent['name']] = {
                'system_prompt': agent.get('system_prompt', ''),
                'tools': agent.get('tools', []),
                'mcp_bindings': agent.get('mcp_bindings', []),
                'custom_metadata': agent.get('metadata', {})
            }
            state.sender = agent['name']
            # Add a message to the conversation history
            state.messages.append({
                'sender': agent['name'],
                'content': agent.get('system_prompt', '')
            })
            return state
        return node

    def build_from_config(self, config_json: Dict[str, Any]):
        # Allow an MCP tool binder to discover and attach tools before building nodes
        if self.mcp_tool_binder is not None:
            try:
                config_json = self.mcp_tool_binder.bind_tools_to_agents(config_json)
            except Exception:
                # Non-fatal: continue with original config if binding fails
                pass
        builder = StateGraph(self.agent_state_cls)
        agent_names = [agent['name'] for agent in config_json['agents']]
        # Add nodes
        for agent in config_json['agents']:
            node_func = self.create_agent_node(agent)
            builder.add_node(agent['name'], node_func)
        # Add edges
        for agent in config_json['agents']:
            if agent['next'] == "END":
                builder.add_edge(agent['name'], END)
            elif agent['next'] in agent_names:
                builder.add_edge(agent['name'], agent['next'])
            else:
                raise ValueError(f"Invalid next node: {agent['next']} for agent {agent['name']}")
        return builder.compile()

# Example usage:
if __name__ == "__main__":
    import json
    import sys
    if len(sys.argv) < 2:
        print("Usage: python graph_factory.py <workflow_config.json>")
        exit(1)
    with open(sys.argv[1], "r") as f:
        config_json = json.load(f)
    factory = GraphFactory()
    graph = factory.build_from_config(config_json)
    print("LangGraph StateGraph compiled successfully.")
