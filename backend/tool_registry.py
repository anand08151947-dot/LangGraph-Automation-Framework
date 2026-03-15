"""
tool_registry.py
Dynamic tool registry and discovery for agentic workflows.
Supports registration, metadata, health, and REST API exposure.
"""

import json
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

class ToolRegistry:
    def __init__(self, db_path: str = None):
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._version_history: Dict[str, List[Dict[str, Any]]] = {}  # name -> list of versions

        # MCP-6: SQLite persistence
        self._db_path = db_path
        self._db_conn: Optional[sqlite3.Connection] = None
        if db_path:
            self._db_conn = sqlite3.connect(db_path, check_same_thread=False)
            self._db_conn.execute(
                "CREATE TABLE IF NOT EXISTS tools("
                "name TEXT PRIMARY KEY, metadata TEXT, version TEXT, "
                "status TEXT, registered_at REAL)"
            )
            self._db_conn.commit()
            self._load_from_db()

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
            # MCP-6: persist to DB
            if self._db_conn is not None:
                self._db_conn.execute(
                    "INSERT OR REPLACE INTO tools(name, metadata, version, status, registered_at) "
                    "VALUES (?,?,?,?,?)",
                    (name, json.dumps(metadata), version, "healthy", time.time()),
                )
                self._db_conn.commit()

    def unregister_tool(self, name: str):
        with self._lock:
            if name in self._tools:
                del self._tools[name]
            # MCP-6: remove from DB
            if self._db_conn is not None:
                self._db_conn.execute("DELETE FROM tools WHERE name=?", (name,))
                self._db_conn.commit()

    def update_tool_status(self, name: str, status: str):
        with self._lock:
            if name in self._tools:
                self._tools[name]["status"] = status
                # Track status change in version history
                self._version_history[name].append(self._tools[name].copy())
            # MCP-6: update DB
            if self._db_conn is not None:
                self._db_conn.execute(
                    "UPDATE tools SET status=? WHERE name=?", (status, name)
                )
                self._db_conn.commit()

    def _load_from_db(self):
        """MCP-6: Hydrate _tools from SQLite DB at startup."""
        if self._db_conn is None:
            return
        cur = self._db_conn.execute(
            "SELECT name, metadata, version, status FROM tools"
        )
        for row in cur.fetchall():
            name, metadata_str, version, status = row
            try:
                metadata = json.loads(metadata_str)
            except Exception:
                metadata = {}
            tool_data = {**metadata, "version": version, "status": status}
            self._tools[name] = tool_data
            if name not in self._version_history:
                self._version_history[name] = []
            self._version_history[name].append(tool_data.copy())
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
        """MCP-5: Real health check — probe each tool's health_url (if configured).

        For tools that declare a ``health_url`` key, an HTTP GET is issued with a
        3-second timeout.  A 2xx response marks the tool ``healthy``; any error
        (network, non-2xx, timeout) marks it ``unhealthy``.

        Tools without a ``health_url`` retain their current status unchanged.
        """
        import urllib.request
        import urllib.error

        with self._lock:
            tools_snapshot = list(self._tools.items())

        results = []
        for name, meta in tools_snapshot:
            health_url = meta.get("health_url")
            if health_url:
                try:
                    req = urllib.request.urlopen(health_url, timeout=3)
                    new_status = "healthy" if 200 <= req.status < 300 else "unhealthy"
                except Exception:
                    new_status = "unhealthy"
                with self._lock:
                    if name in self._tools:
                        self._tools[name]["status"] = new_status
            results.append({"name": name, **meta, "status": self._tools.get(name, meta).get("status", "unknown")})

        return results

# Example usage:
# registry = ToolRegistry()
# registry.register_tool("search", {"description": "Web search tool", "version": "1.0"})
# registry.update_tool_status("search", "unhealthy")
# print(registry.list_tools())
