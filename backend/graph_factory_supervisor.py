from langgraph.graph import StateGraph, END
from typing import Any, Dict, Callable

class AgentState:
    def __init__(self, messages=None, sender=None, metadata=None):
        self.messages = messages or []
        self.sender = sender
        self.metadata = metadata or {}
        self.status = {}  # Track agent status/results

class SupervisorRouter:
    def __init__(self, config_json: Dict[str, Any]):
        self.config_json = config_json
        self.agent_names = [agent['name'] for agent in config_json['agents']]
        self.supervisor_logic = config_json.get('supervisor_logic', {})

    def get_next(self, agent_name: str, state: AgentState) -> str:
        # Default: use agent['next']
        agent = next(a for a in self.config_json['agents'] if a['name'] == agent_name)
        # If supervisor logic exists for this agent, use it
        logic = self.supervisor_logic.get(agent_name)
        if logic:
            # Example: logic = {"if": "state.status['reviewer'] == 'fail'", "then": "Researcher", "else": "Writer"}
            try:
                if eval(logic['if']):
                    return logic['then']
                else:
                    return logic['else']
            except Exception:
                return agent['next']
        return agent['next']

class GraphFactory:
    def __init__(self, agent_state_cls=AgentState):
        self.agent_state_cls = agent_state_cls

    def create_agent_node(self, agent: Dict[str, Any]) -> Callable:
        def node(state: AgentState):
            state.metadata[agent['name']] = {
                'system_prompt': agent.get('system_prompt', ''),
                'tools': agent.get('tools', []),
                'mcp_bindings': agent.get('mcp_bindings', []),
                'custom_metadata': agent.get('metadata', {})
            }
            state.sender = agent['name']
            state.messages.append({
                'sender': agent['name'],
                'content': agent.get('system_prompt', '')
            })
            # Simulate agent result for routing (customize as needed)
            if 'review' in agent['name'].lower():
                state.status[agent['name']] = 'fail' if len(state.messages) % 2 == 0 else 'pass'
            return state
        return node

    def build_from_config(self, config_json: Dict[str, Any]):
        builder = StateGraph(self.agent_state_cls)
        agent_names = [agent['name'] for agent in config_json['agents']]
        router = SupervisorRouter(config_json)
        # Add nodes
        for agent in config_json['agents']:
            node_func = self.create_agent_node(agent)
            builder.add_node(agent['name'], node_func)
        # Add edges with supervisor logic
        for agent in config_json['agents']:
            def edge_func(agent_name=agent['name']):
                def next_node(state: AgentState):
                    next_name = router.get_next(agent_name, state)
                    return END if next_name == "END" else next_name
                return next_node
            builder.add_edge(agent['name'], edge_func())
        return builder.compile()

# Integration example:
if __name__ == "__main__":
    import json
    import sys
    from mcp_autobinder import MCPAutoBinder
    if len(sys.argv) < 2:
        print("Usage: python graph_factory_supervisor.py <workflow_config.json>")
        exit(1)
    with open(sys.argv[1], "r") as f:
        config_json = json.load(f)
    # Step 1: Auto-bind MCP tools
    config_json = MCPAutoBinder(config_json).bind_tools_to_agents()
    # Step 2: Build graph with supervisor routing
    factory = GraphFactory()
    graph = factory.build_from_config(config_json)
    print("LangGraph StateGraph with supervisor routing compiled successfully.")
