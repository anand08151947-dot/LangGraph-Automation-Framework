# MemoryManager: Modular STM & LTM Interface

from typing import Any, Dict, Optional, List
import threading
import sqlite3
import os
import json
import time

class MemoryManager:
    """
    Modular Memory Manager supporting both Short Term Memory (STM) and Long Term Memory (LTM).
    STM: Fast in-memory (thread-safe dict) or Redis (future option)
    LTM: Durable storage (SQLite DB, file, or cloud - here: SQLite by default)
    """
    def __init__(
        self,
        stm_backend: str = 'memory',
        ltm_backend: str = 'sqlite',
        ltm_path: str = 'ltm.db',
        max_stm_entries: int = 0,   # 0 = unlimited; >0 evicts oldest sessions (MM-2)
        ltm_ttl_days: float = 0,    # 0 = no pruning; >0 deletes rows older than N days (MM-3)
    ):
        # STM: session_id -> state (thread-safe, insertion-ordered dict for LRU eviction)
        if stm_backend in ('memory', 'sqlite', 'graph_state'):
            self._stm: Dict[str, Any] = {}
        else:
            self._stm = {}
        self._stm_lock = threading.Lock()
        self.max_stm_entries = max_stm_entries  # MM-2: eviction limit
        # LTM: SQLite DB for session history
        self.ltm_backend = ltm_backend
        self.ltm_path = ltm_path
        self.ltm_ttl_days = ltm_ttl_days  # MM-3: TTL pruning
        if ltm_backend == 'sqlite':
            self._init_sqlite()

    # --- STM Methods ---
    def save_stm(self, session_id: str, state: Dict[str, Any]):
        with self._stm_lock:
            # Move session to end (most-recently-used) by re-inserting
            self._stm.pop(session_id, None)
            self._stm[session_id] = state
            # MM-2: evict oldest sessions when over limit
            if self.max_stm_entries > 0:
                while len(self._stm) > self.max_stm_entries:
                    # Dict is insertion-ordered; first key = oldest
                    oldest = next(iter(self._stm))
                    del self._stm[oldest]

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
            step_context TEXT,
            timestamp REAL DEFAULT 0
        )''')
        # MM-3: migration — add timestamp column to existing tables
        try:
            c.execute('ALTER TABLE ltm ADD COLUMN timestamp REAL DEFAULT 0')
        except sqlite3.OperationalError:
            pass  # column already exists
        conn.commit()
        conn.close()

    def append_ltm(self, session_id: str, step_context: Dict[str, Any]):
        if self.ltm_backend == 'sqlite':
            conn = sqlite3.connect(self.ltm_path)
            c = conn.cursor()
            idx = self._get_next_step_idx(session_id, c)
            now = time.time()
            c.execute(
                'INSERT INTO ltm (session_id, step_idx, step_context, timestamp) VALUES (?, ?, ?, ?)',
                (session_id, idx, json.dumps(step_context), now)
            )
            # MM-3: prune rows older than ltm_ttl_days
            if self.ltm_ttl_days > 0:
                cutoff = now - (self.ltm_ttl_days * 86400)
                c.execute(
                    'DELETE FROM ltm WHERE session_id=? AND timestamp > 0 AND timestamp < ?',
                    (session_id, cutoff)
                )
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
