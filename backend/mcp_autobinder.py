import subprocess
import json
from typing import Dict, Any, List


# Simulated MCP client for demonstration
class MCPClient:
    def __init__(self, server_name: str, server_config: Dict[str, Any]):
        self.server_name = server_name
        self.server_config = server_config
        self.tools = self._discover_tools()

    def _discover_tools(self) -> List[str]:
        """Discover tools available on this MCP server.

        Supports server types: stdio, sse, http.
        Falls back to simulated tools when real discovery fails.
        """
        stype = self.server_config.get("type", "")

        if stype == "stdio":
            # Run the MCP server process and ask it to list tools
            cmd = [self.server_config["command"]] + self.server_config.get("args", [])
            try:
                result = subprocess.run(
                    cmd + ["--list-tools"],
                    capture_output=True, text=True, timeout=10,
                )
                return json.loads(result.stdout)
            except Exception:
                return ["simulated_tool_1", "simulated_tool_2"]

        elif stype == "sse":
            # SSE endpoint — tool discovery would use SSE protocol
            return ["simulated_sse_tool_1", "simulated_sse_tool_2"]

        elif stype == "http":
            # HTTP endpoint — register the endpoint URL itself as the tool name
            endpoint = self.server_config.get("endpoint", "")
            return [endpoint] if endpoint else [f"{self.server_name}_http_tool"]

        return []

    def get_tools(self) -> List[str]:
        return self.tools


class MCPAutoBinder:
    def __init__(self, config_json: Dict[str, Any] = None):
        # Accept optional config; tools can also be bound later via bind_tools_to_agents()
        self.config_json = config_json or {}
        self.mcp_clients = self._init_mcp_clients()

    def _init_mcp_clients(self) -> Dict[str, MCPClient]:
        mcp_servers = (self.config_json or {}).get("mcp_servers", {})
        return {
            name: MCPClient(name, cfg)
            for name, cfg in mcp_servers.items()
        }

    def bind_tools_to_agents(self, config_json: Dict[str, Any] = None):
        """Bind MCP-discovered tools to agents/nodes in the config.

        Supports both:
        - Old format: config_json["agents"] with mcp_bindings[] listing server keys
        - New enterprise format: config_json["nodes"] with tools[] that may contain
          MCP server key names (keys present in mcp_servers{})

        For each agent/node, discovered tools are merged into its tools[] list.
        """
        cfg = config_json or self.config_json or {}
        # Re-initialise clients for the provided config
        self.config_json = cfg
        self.mcp_clients = self._init_mcp_clients()

        # Handle both old agents[] and new nodes[] formats
        items: List[Dict[str, Any]] = cfg.get("agents") or cfg.get("nodes") or []

        for item in items:
            # Explicit MCP bindings (old format field)
            mcp_bindings: List[str] = item.get("mcp_bindings", [])

            # In enterprise format, tools[] entries that match an mcp_servers key
            # are treated as MCP server references, not literal tool names
            tool_refs: List[str] = item.get("tools", [])
            mcp_server_refs = [t for t in tool_refs if t in self.mcp_clients]

            # Union of all MCP server keys to resolve
            all_mcp_refs = set(mcp_bindings) | set(mcp_server_refs)

            bound_tools: List[str] = []
            for mcp_name in all_mcp_refs:
                client = self.mcp_clients.get(mcp_name)
                if client:
                    bound_tools.extend(client.get_tools())

            # Merge discovered tools; preserve non-MCP literal tool names
            literal_tools = [t for t in tool_refs if t not in self.mcp_clients]
            item["tools"] = list(set(literal_tools + bound_tools))

        return cfg


# Example usage:
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python mcp_autobinder.py <workflow_config.json>")
        exit(1)
    with open(sys.argv[1]) as f:
        config_json = json.load(f)
    autobinder = MCPAutoBinder(config_json)
    updated_config = autobinder.bind_tools_to_agents()
    print(json.dumps(updated_config, indent=2))
