import subprocess
import json
import urllib.request
import urllib.parse
import urllib.error
import threading
from typing import Dict, Any, List, Optional, Tuple


# ---------------------------------------------------------------------------
# MCPClient — connects to an MCP server and discovers its tools via the
# official JSON-RPC tools/list protocol (MCP-1).  Supports stdio, SSE, and
# HTTP transport (MCP-2) with optional credential/auth headers (MCP-3).
# ---------------------------------------------------------------------------

_JSONRPC_TOOLS_LIST = json.dumps(
    {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
).encode()


def _build_auth_headers(auth_cfg: Dict[str, Any]) -> Dict[str, str]:
    """MCP-3: Build HTTP auth headers from the server's auth config block.

    Supported auth types:
      bearer   — Authorization: Bearer <token>
      api_key  — configurable header name (default: X-API-Key)
      basic    — Authorization: Basic base64(user:password)
    """
    headers: Dict[str, str] = {}
    if not auth_cfg:
        return headers
    auth_type = auth_cfg.get("type", "").lower()
    if auth_type == "bearer":
        token = auth_cfg.get("token", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
    elif auth_type == "api_key":
        key = auth_cfg.get("key", "")
        header = auth_cfg.get("header", "X-API-Key")
        if key:
            headers[header] = key
    elif auth_type == "basic":
        import base64
        user = auth_cfg.get("username", "")
        pwd  = auth_cfg.get("password", "")
        encoded = base64.b64encode(f"{user}:{pwd}".encode()).decode()
        headers["Authorization"] = f"Basic {encoded}"
    return headers


def _http_jsonrpc_tools_list(
    url: str,
    headers: Dict[str, str],
    timeout: int = 10,
) -> Tuple[List[str], Dict[str, Any]]:
    """MCP-2 / MCP-1: POST JSON-RPC tools/list to an HTTP MCP endpoint.

    Returns (tool_names, tool_schemas).
    """
    all_headers = {"Content-Type": "application/json"}
    all_headers.update(headers)
    req = urllib.request.Request(url, data=_JSONRPC_TOOLS_LIST, headers=all_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        data = json.loads(body)
        tools = data.get("result", {}).get("tools", [])
        names = [t["name"] for t in tools if "name" in t]
        schemas = {t["name"]: t.get("inputSchema", {}) for t in tools if "name" in t}
        return names, schemas
    except Exception:
        return [], {}


def _sse_jsonrpc_tools_list(
    base_url: str,
    headers: Dict[str, str],
    timeout: int = 10,
) -> Tuple[List[str], Dict[str, Any]]:
    """MCP-2 / MCP-1: Discover tools from an SSE-transport MCP server.

    MCP SSE servers expose two endpoints:
      GET  <base_url>/sse      — server-sent event stream (for server→client push)
      POST <base_url>/messages — client→server JSON-RPC messages

    We POST tools/list to /messages and read the one-shot JSON response.
    """
    messages_url = base_url.rstrip("/") + "/messages"
    return _http_jsonrpc_tools_list(messages_url, headers, timeout=timeout)


# Simulated MCP client for demonstration
class MCPClient:
    def __init__(self, server_name: str, server_config: Dict[str, Any]):
        self.server_name = server_name
        self.server_config = server_config
        self.tool_schemas: Dict[str, Any] = {}
        self.tools = self._discover_tools()

    def _discover_tools(self) -> List[str]:
        """MCP-1/2: Discover tools available on this MCP server using the
        official JSON-RPC tools/list protocol.

        MCP-4: Results are cached by server_name + config hash for up to
        _MCP_CACHE_TTL_SECONDS to avoid redundant subprocess/network calls.

        Supports server types: stdio, sse, http.
        Falls back to empty list (no simulated tools) when real discovery fails.
        """
        # MCP-4: check TTL cache before hitting the server
        ttl = float(self.server_config.get("cache_ttl_seconds", _MCP_CACHE_TTL_SECONDS))
        cached = _get_cached_tools(self.server_name, self.server_config, ttl=ttl)
        if cached is not None:
            names, schemas = cached
            self.tool_schemas = schemas
            return names

        stype = self.server_config.get("type", "")
        auth_headers = _build_auth_headers(self.server_config.get("auth") or {})

        if stype == "stdio":
            # MCP-1: send JSON-RPC tools/list via stdin/stdout of the server process
            cmd = [self.server_config["command"]] + self.server_config.get("args", [])
            env_overrides = self.server_config.get("env") or {}
            try:
                import os
                env = {**os.environ, **env_overrides}
                proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                )
                stdout_data, _ = proc.communicate(
                    input=_JSONRPC_TOOLS_LIST + b"\n", timeout=10
                )
                # The response may be the first complete JSON line
                for line in stdout_data.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        tools = data.get("result", {}).get("tools", [])
                        names = [t["name"] for t in tools if "name" in t]
                        self.tool_schemas = {
                            t["name"]: t.get("inputSchema", {})
                            for t in tools if "name" in t
                        }
                        _set_cached_tools(self.server_name, self.server_config, names, self.tool_schemas, ttl=ttl)
                        return names
                    except json.JSONDecodeError:
                        continue
            except Exception:
                pass
            return []

        elif stype == "sse":
            # MCP-2: SSE transport — POST tools/list to the /messages endpoint
            base_url = self.server_config.get("url", "")
            if not base_url:
                return []
            names, schemas = _sse_jsonrpc_tools_list(base_url, auth_headers)
            self.tool_schemas = schemas
            if names:
                _set_cached_tools(self.server_name, self.server_config, names, schemas, ttl=ttl)
            return names

        elif stype in ("http", "rest"):
            # MCP-2: HTTP transport — POST JSON-RPC tools/list directly
            endpoint = self.server_config.get("endpoint", "") or self.server_config.get("url", "")
            if not endpoint:
                return [f"{self.server_name}_http_tool"]
            names, schemas = _http_jsonrpc_tools_list(endpoint, auth_headers)
            self.tool_schemas = schemas
            if names:
                _set_cached_tools(self.server_name, self.server_config, names, schemas, ttl=ttl)
            return names

        return []

    def get_tools(self) -> List[str]:
        return self.tools

    def get_tool_schema(self, tool_name: str) -> Dict[str, Any]:
        """Return the inputSchema for a specific tool, or {} if not found."""
        return self.tool_schemas.get(tool_name, {})


# MCP-4: Module-level TTL cache for tool discovery results.
# Key: (server_name, frozenset of config items), Value: (tool_names, schemas, expiry_time)
import time as _time
_mcp_tool_cache: Dict[str, tuple] = {}
_MCP_CACHE_TTL_SECONDS = 300  # 5 minutes default; can be overridden via config

def _mcp_cache_key(server_name: str, server_config: Dict[str, Any]) -> str:
    """Stable string key from server name + config snapshot."""
    import hashlib
    cfg_repr = json.dumps(server_config, sort_keys=True, default=str)
    return hashlib.md5(f"{server_name}:{cfg_repr}".encode()).hexdigest()


def _get_cached_tools(
    server_name: str,
    server_config: Dict[str, Any],
    ttl: float = _MCP_CACHE_TTL_SECONDS,
) -> Optional[Tuple[List[str], Dict[str, Any]]]:
    """Return cached (names, schemas) if still within TTL, or None."""
    key = _mcp_cache_key(server_name, server_config)
    entry = _mcp_tool_cache.get(key)
    if entry is None:
        return None
    names, schemas, expiry = entry
    if _time.monotonic() > expiry:
        del _mcp_tool_cache[key]
        return None
    return names, schemas


def _set_cached_tools(
    server_name: str,
    server_config: Dict[str, Any],
    names: List[str],
    schemas: Dict[str, Any],
    ttl: float = _MCP_CACHE_TTL_SECONDS,
) -> None:
    key = _mcp_cache_key(server_name, server_config)
    _mcp_tool_cache[key] = (names, schemas, _time.monotonic() + ttl)


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
