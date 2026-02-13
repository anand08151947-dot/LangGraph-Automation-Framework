import json
import pytest
from backend.mcp_autobinder import MCPAutoBinder, MCPClient
from backend.observability_manager import ObservabilityManager


def test_mcp_autobinder_binds_discovered_tools(monkeypatch):
    # Prepare a config with one mcp server and one agent bound to it
    cfg = {
        "mcp_servers": {
            "test_mcp": {"type": "stdio", "command": "echo", "args": ["-n"]}
        },
        "agents": [
            {"name": "agent1", "mcp_bindings": ["test_mcp"], "tools": []}
        ]
    }

    # Monkeypatch MCPClient._discover_tools to return a fixed list
    def fake_discover(self):
        return ["toolA", "toolB"]

    monkeypatch.setattr(MCPClient, "_discover_tools", fake_discover)

    binder = MCPAutoBinder(cfg)
    updated = binder.bind_tools_to_agents(cfg)

    tools = updated["agents"][0].get("tools", [])
    assert "toolA" in tools and "toolB" in tools


def test_observability_hooks_are_called_and_exceptions_handled():
    obs = ObservabilityManager(["logging"])
    events = []

    def hook_pre(data):
        events.append(("pre", data))

    def hook_raise(data):
        raise RuntimeError("boom")

    def hook_post(data):
        events.append(("post", data))

    obs.register_hook("pre_step", hook_pre)
    obs.register_hook("pre_step", hook_raise)
    obs.register_hook("pre_step", hook_post)

    # Should not raise despite one hook raising; other hooks should run
    obs.run_plugin_hooks("pre_step", {"step_idx": 1})
    assert ("pre", {"step_idx": 1}) in events
    assert ("post", {"step_idx": 1}) in events
