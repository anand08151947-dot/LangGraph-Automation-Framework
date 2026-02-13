from backend.graph_factory import GraphFactory, AgentState


def test_build_and_run_simple_graph():
    cfg = {
        "graph_name": "g",
        "agents": [
            {"name": "a1", "system_prompt": "s1", "next": "a2"},
            {"name": "a2", "system_prompt": "s2", "next": "END"}
        ]
    }
    factory = GraphFactory()
    graph = factory.build_from_config(cfg)

    states = list(graph.iter_run())
    # The graph runner mutates a single state object in-place; we expect two yielded steps
    assert len(states) == 2
    final_state = states[-1]
    assert final_state.sender == "a2"
    # Both agent messages should be present in the final state's messages
    senders = [m['sender'] for m in final_state.messages]
    assert 'a1' in senders and 'a2' in senders


def test_mcp_binder_attaches_tools():
    # Fake binder that adds discovered tools
    class FakeBinder:
        def bind_tools_to_agents(self, cfg):
            for a in cfg.get('agents', []):
                a['tools'] = a.get('tools', []) + ['discovered_tool']
            return cfg

    cfg = {
        "graph_name": "g",
        "agents": [
            {"name": "a1", "system_prompt": "s1", "next": "END", "tools": []}
        ]
    }
    factory = GraphFactory(mcp_tool_binder=FakeBinder())
    graph = factory.build_from_config(cfg)
    states = list(graph.iter_run())
    # The node should have added tool metadata in state
    assert 'discovered_tool' in states[0].metadata['a1']['tools']
