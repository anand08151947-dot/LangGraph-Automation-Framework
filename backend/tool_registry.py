"""
tool_registry.py
Dynamic tool registry and discovery for agentic workflows.
Supports registration, metadata, health, and REST API exposure.
"""

import threading
from typing import Any, Dict, List, Optional

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._version_history: Dict[str, List[Dict[str, Any]]] = {}  # name -> list of versions

    def register_tool(self, name: str, metadata: Dict[str, Any]):
        with self._lock:
            version = metadata.get("version", "1.0")
            tool_data = {
                **metadata,
                "status": "healthy",
                "version": version,
            }
            self._tools[name] = tool_data
            # Track version history
            if name not in self._version_history:
                self._version_history[name] = []
            self._version_history[name].append(tool_data.copy())

    def unregister_tool(self, name: str):
        with self._lock:
            if name in self._tools:
                del self._tools[name]

    def update_tool_status(self, name: str, status: str):
        with self._lock:
            if name in self._tools:
                self._tools[name]["status"] = status
                # Track status change in version history
                self._version_history[name].append(self._tools[name].copy())
    def get_version_history(self, name: str) -> List[Dict[str, Any]]:
        with self._lock:
            return self._version_history.get(name, [])

    def list_tools(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [dict(name=name, **meta) for name, meta in self._tools.items()]

    def get_tool(self, name: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._tools.get(name)

    def health_check(self) -> List[Dict[str, Any]]:
        # Placeholder: In real use, ping/check each tool
        with self._lock:
            for tool in self._tools.values():
                tool["status"] = "healthy"  # Simulate all healthy
            return self.list_tools()

# Example usage:
# registry = ToolRegistry()
# registry.register_tool("search", {"description": "Web search tool", "version": "1.0"})
# registry.update_tool_status("search", "unhealthy")
# print(registry.list_tools())
