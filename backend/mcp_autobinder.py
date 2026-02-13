import subprocess
import json
from typing import Dict, Any, List

# Simulated MCP client for demonstration
class MCPClient:
    def __init__(self, server_config: Dict[str, Any]):
        self.server_config = server_config
        self.tools = self._discover_tools()

    def _discover_tools(self) -> List[str]:
        # Simulate tool discovery (replace with actual MCP protocol calls)
        if self.server_config['type'] == 'stdio':
            # Example: run npx command and parse output
            cmd = [self.server_config['command']] + self.server_config.get('args', [])
            try:
                result = subprocess.run(cmd + ['--list-tools'], capture_output=True, text=True, timeout=10)
                return json.loads(result.stdout)
            except Exception:
                return ["simulated_tool_1", "simulated_tool_2"]
        elif self.server_config['type'] == 'sse':
            # Example: fetch from SSE endpoint (simulate)
            return ["simulated_sse_tool_1", "simulated_sse_tool_2"]
        return []

    def get_tools(self) -> List[str]:
        return self.tools

class MCPAutoBinder:
    def __init__(self, config_json: Dict[str, Any] = None):
        # Accept optional config; can bind later via bind_tools_to_agents(config_json)
        self.config_json = config_json or {}
        self.mcp_clients = self._init_mcp_clients()

    def _init_mcp_clients(self) -> Dict[str, MCPClient]:
        mcp_servers = (self.config_json or {}).get('mcp_servers', {})
        return {name: MCPClient(cfg) for name, cfg in mcp_servers.items()}

    def bind_tools_to_agents(self, config_json: Dict[str, Any] = None):
        cfg = config_json or self.config_json or {}
        # (re)initialize clients for provided config
        self.config_json = cfg
        self.mcp_clients = self._init_mcp_clients()
        for agent in cfg.get('agents', []):
            mcp_bindings = agent.get('mcp_bindings', [])
            bound_tools = []
            for mcp_name in mcp_bindings:
                client = self.mcp_clients.get(mcp_name)
                if client:
                    bound_tools.extend(client.get_tools())
            # Attach discovered tools to agent's tool list
            agent['tools'] = list(set(agent.get('tools', []) + bound_tools))
        return cfg

# Example usage:
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python mcp_autobinder.py <workflow_config.json>")
        exit(1)
    with open(sys.argv[1], "r") as f:
        config_json = json.load(f)
    autobinder = MCPAutoBinder(config_json)
    updated_config = autobinder.bind_tools_to_agents()
    print(json.dumps(updated_config, indent=2))
