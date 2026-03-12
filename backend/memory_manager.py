# MemoryManager: Modular STM & LTM Interface

from typing import Any, Dict, Optional, List
import threading
import sqlite3
import os
import json

class MemoryManager:
    """
    Modular Memory Manager supporting both Short Term Memory (STM) and Long Term Memory (LTM).
    STM: Fast in-memory (thread-safe dict) or Redis (future option)
    LTM: Durable storage (SQLite DB, file, or cloud - here: SQLite by default)
    """
    def __init__(self, stm_backend: str = 'memory', ltm_backend: str = 'sqlite', ltm_path: str = 'ltm.db'):
        # STM: session_id -> state (thread-safe)
        # Support common misconfigurations where 'sqlite' is used for memory.backend in config.json
        if stm_backend in ('memory', 'sqlite'):
            self._stm = {}
        else:
            # e.g., Redis (not implemented yet)
            self._stm = None
        self._stm_lock = threading.Lock()
        # LTM: SQLite DB for session history
        self.ltm_backend = ltm_backend
        self.ltm_path = ltm_path
        if ltm_backend == 'sqlite':
            self._init_sqlite()

    # --- STM Methods ---
    def save_stm(self, session_id: str, state: Dict[str, Any]):
        with self._stm_lock:
            self._stm[session_id] = state

    def load_stm(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._stm_lock:
            return self._stm.get(session_id)

    def reset_stm(self, session_id: str):
        with self._stm_lock:
            if session_id in self._stm:
                del self._stm[session_id]

    # --- LTM Methods ---
    def _init_sqlite(self):
        conn = sqlite3.connect(self.ltm_path)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS ltm (
            session_id TEXT,
            step_idx INTEGER,
            step_context TEXT
        )''')
        conn.commit()
        conn.close()

    def append_ltm(self, session_id: str, step_context: Dict[str, Any]):
        if self.ltm_backend == 'sqlite':
            conn = sqlite3.connect(self.ltm_path)
            c = conn.cursor()
            idx = self._get_next_step_idx(session_id, c)
            c.execute('INSERT INTO ltm (session_id, step_idx, step_context) VALUES (?, ?, ?)',
                      (session_id, idx, json.dumps(step_context)))
            conn.commit()
            conn.close()

    def _get_next_step_idx(self, session_id: str, c) -> int:
        c.execute('SELECT MAX(step_idx) FROM ltm WHERE session_id=?', (session_id,))
        row = c.fetchone()
        return (row[0] or 0) + 1

    def load_ltm(self, session_id: str) -> List[Dict[str, Any]]:
        if self.ltm_backend == 'sqlite':
            conn = sqlite3.connect(self.ltm_path)
            c = conn.cursor()
            c.execute('SELECT step_context FROM ltm WHERE session_id=? ORDER BY step_idx', (session_id,))
            rows = c.fetchall()
            conn.close()
            return [json.loads(r[0]) for r in rows]
        return []

    def query_ltm(self, session_id: str, keyword: str = "", limit: int = 10) -> List[str]:
        """Full-text keyword search over LTM entries. Returns matching step_context strings."""
        if self.ltm_backend == 'sqlite':
            conn = sqlite3.connect(self.ltm_path)
            c = conn.cursor()
            if keyword:
                c.execute(
                    'SELECT step_context FROM ltm WHERE session_id=? AND step_context LIKE ? ORDER BY step_idx DESC LIMIT ?',
                    (session_id, f"%{keyword}%", limit)
                )
            else:
                c.execute(
                    'SELECT step_context FROM ltm WHERE session_id=? ORDER BY step_idx DESC LIMIT ?',
                    (session_id, limit)
                )
            rows = c.fetchall()
            conn.close()
            return [r[0] for r in rows]
        return []

    def get_stats(self, session_id: str) -> Dict[str, Any]:
        """Return STM/LTM stats for a session (useful for Monitor view)."""
        stm_state = self.load_stm(session_id)
        stm_keys = list(stm_state.keys()) if stm_state else []
        ltm_count = 0
        if self.ltm_backend == 'sqlite':
            conn = sqlite3.connect(self.ltm_path)
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM ltm WHERE session_id=?', (session_id,))
            ltm_count = c.fetchone()[0]
            conn.close()
        return {"session_id": session_id, "stm_keys": stm_keys, "ltm_entry_count": ltm_count}

    def reset_ltm(self, session_id: str):
        if self.ltm_backend == 'sqlite':
            conn = sqlite3.connect(self.ltm_path)
            c = conn.cursor()
            c.execute('DELETE FROM ltm WHERE session_id=?', (session_id,))
            conn.commit()
            conn.close()

# Example usage:
# mm = MemoryManager()
# mm.save_stm('sess1', {'step': 1, 'state': 'foo'})
# mm.append_ltm('sess1', {'input': 'bar', 'output': 'baz'})
# print(mm.load_stm('sess1'))
# print(mm.load_ltm('sess1'))
