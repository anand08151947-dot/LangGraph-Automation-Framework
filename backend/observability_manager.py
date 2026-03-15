"""
observability_manager.py
Central abstraction for logging, tracing, metrics, and event hooks.
Supports pluggable backends (logging, OpenTelemetry, Prometheus, etc.)
"""

import json
import logging
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, List, Optional

# OBS-2: Optional OpenTelemetry import
try:
    from opentelemetry import trace as _otel_trace
    from opentelemetry.trace import NonRecordingSpan as _NonRecordingSpan
    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False

# OBS-3: Optional Prometheus import
try:
    from prometheus_client import Counter as _Counter, Histogram as _Histogram
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False


class _JsonFormatter(logging.Formatter):
    """OBS-1: Emit structured JSON log records for machine-parseable log aggregation.

    Each record includes: timestamp (ISO-8601), level, logger, session_id,
    run_id, node, event, duration_ms, and any extra fields passed via the
    log record's __dict__.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
        }
        # Carry structured fields attached by log_event / log_error / etc.
        for key in ("session_id", "run_id", "node", "event", "duration_ms"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        # The main message becomes the "message" field
        payload["message"] = record.getMessage()
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        try:
            return json.dumps(payload, default=str)
        except Exception:
            return record.getMessage()


def _make_json_handler() -> logging.StreamHandler:
    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())
    return handler


class ObservabilityManager:
    def __init__(self, backends: Optional[List[str]] = None):
        """
        backends: List of enabled backends (e.g., ["logging", "otel", "prometheus"])
        """
        self.backends = backends or ["logging"]
        # OBS-1: use a JSON-formatted logger so all output is structured
        self.logger = logging.getLogger("Observability")
        if "logging" in self.backends and not self.logger.handlers:
            self.logger.addHandler(_make_json_handler())
            self.logger.propagate = False
        self.hooks: Dict[str, List[Callable]] = {}

        # OBS-2: OpenTelemetry tracer initialization
        self._otel_tracer = None
        if _OTEL_AVAILABLE and "otel" in self.backends:
            self._otel_tracer = _otel_trace.get_tracer("phoenice.observability")
        self.otel = self._otel_tracer

        # OBS-3: Prometheus metrics initialization
        self._prometheus_enabled = False
        self._prom_node_executions = None
        self._prom_node_latency = None
        self._prom_errors_total = None
        self._prom_retries_total = None
        if _PROMETHEUS_AVAILABLE and "prometheus" in self.backends:
            self._prometheus_enabled = True
            self._prom_node_executions = _Counter(
                "phoenice_node_executions_total",
                "Total agent node executions",
                ["node", "session_id"],
            )
            self._prom_node_latency = _Histogram(
                "phoenice_node_latency_seconds",
                "Agent node latency in seconds",
                ["node"],
            )
            self._prom_errors_total = _Counter(
                "phoenice_errors_total",
                "Total agent node errors",
                ["node", "error_type"],
            )
            self._prom_retries_total = _Counter(
                "phoenice_retries_total",
                "Total agent node retries",
                ["node"],
            )
        self.prometheus = self._prom_node_executions  # legacy placeholder

        # OBS-5: SQLite event persistence
        self._event_db_path: Optional[str] = None
        self._event_db_conn: Optional[sqlite3.Connection] = None
        self._event_db_lock = threading.Lock()

    # --- Structured Logging ---
    def log_event(self, event_type: str, data: Dict[str, Any]):
        if "logging" in self.backends:
            extra = {
                "event": event_type,
                "session_id": data.get("session_id", ""),
                "run_id": data.get("run_id", ""),
                "node": data.get("node", data.get("sender", "")),
                "duration_ms": data.get("duration_ms", ""),
            }
            self.logger.info(json.dumps(data, default=str), extra=extra)
        # OBS-5: persist event to SQLite if enabled
        if self._event_db_conn is not None:
            self._persist_event(event_type, data)
        self._run_hooks(event_type, data)

    # --- Error Logging ---
    def log_error(self, error: Exception, context: Dict[str, Any] = None, notify: bool = False):
        if "logging" in self.backends:
            extra = {
                "event": "error",
                "session_id": (context or {}).get("session_id", ""),
                "node": (context or {}).get("sender", ""),
            }
            self.logger.error(
                json.dumps({"error": str(error), "context": context}, default=str),
                extra=extra,
                exc_info=error,
            )
        self._run_hooks("error", {"error": str(error), "context": context})
        if notify:
            pass  # Placeholder for notification logic

    # --- Tracing ---
    def trace_step(self, session_id: str, step_info: Dict[str, Any]):
        if "logging" in self.backends:
            extra = {
                "event": "trace_step",
                "session_id": session_id,
                "node": step_info.get("node", step_info.get("sender", "")),
            }
            self.logger.info(json.dumps({"session_id": session_id, **step_info}, default=str), extra=extra)
        self._run_hooks("trace_step", {"session_id": session_id, **step_info})

    # --- Metrics ---
    def record_metric(self, metric_name: str, value: Any, tags: Optional[Dict[str, Any]] = None):
        if "logging" in self.backends:
            extra = {"event": "metric", "node": (tags or {}).get("sender", "")}
            self.logger.info(
                json.dumps({"metric": metric_name, "value": value, "tags": tags}, default=str),
                extra=extra,
            )
        self._run_hooks("metric", {"metric_name": metric_name, "value": value, "tags": tags})

    # --- Audit ---
    def log_audit(self, action: str, details: Dict[str, Any]):
        if "logging" in self.backends:
            extra = {"event": "audit"}
            self.logger.info(json.dumps({"action": action, "details": details}, default=str), extra=extra)

    # --- Event Hooks ---
    def register_hook(self, event_type: str, callback: Callable):
        """Register a callback for a specific event type."""
        if event_type not in self.hooks:
            self.hooks[event_type] = []
        self.hooks[event_type].append(callback)

    def unregister_hook(self, event_type: str, callback: Callable) -> bool:
        """OBS-4: Remove a previously registered hook callback.

        Returns True if the callback was found and removed, False otherwise.
        """
        callbacks = self.hooks.get(event_type, [])
        if callback in callbacks:
            callbacks.remove(callback)
            return True
        return False

    def _run_hook_with_timeout(
        self,
        event_type: str,
        cb: Callable,
        data: Dict[str, Any],
        timeout_s: float = 2.0,
    ):
        """OBS-4: Run a single hook callback with a wall-clock timeout.

        Logs a warning if the callback exceeds the timeout but continues
        execution rather than blocking the orchestration step.
        """
        import threading as _threading
        result = {"done": False, "exc": None}

        def _target():
            try:
                cb(data)
            except Exception as e:
                result["exc"] = e
            finally:
                result["done"] = True

        t = _threading.Thread(target=_target, daemon=True)
        t.start()
        t.join(timeout=timeout_s)
        if not result["done"]:
            self.logger.warning(
                json.dumps({"event": "hook_timeout", "hook_event": event_type, "timeout_s": timeout_s}),
            )
        elif result["exc"]:
            self.logger.error(
                json.dumps({"error": str(result["exc"]), "hook_event": event_type}, default=str),
            )

    def run_plugin_hooks(self, event_type: str, data: Dict[str, Any]):
        """Run all registered plugin hooks for the given event type."""
        for cb in self.hooks.get(event_type, []):
            self._run_hook_with_timeout(event_type, cb, data)

    def _run_hooks(self, event_type: str, data: Dict[str, Any]):
        for cb in self.hooks.get(event_type, []):
            self._run_hook_with_timeout(event_type, cb, data)

    # OBS-2: OTEL span context manager
    @contextmanager
    def start_span(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        """Return a context manager that creates an OTEL span if configured, else a no-op."""
        if self._otel_tracer is not None:
            with self._otel_tracer.start_as_current_span(name) as span:
                if attributes:
                    for k, v in attributes.items():
                        try:
                            span.set_attribute(k, str(v))
                        except Exception:
                            pass
                yield span
        else:
            yield None

    # OBS-3: Prometheus node metric recorder
    def record_node_metric(self, node: str, duration_s: float, success: bool,
                           retries: int = 0, session_id: str = "", error_type: str = ""):
        """Increment Prometheus counters and histograms for a node execution."""
        if not self._prometheus_enabled:
            return
        try:
            self._prom_node_executions.labels(node=node, session_id=session_id).inc()
            self._prom_node_latency.labels(node=node).observe(duration_s)
            if not success:
                self._prom_errors_total.labels(node=node, error_type=error_type or "error").inc()
            if retries > 0:
                self._prom_retries_total.labels(node=node).inc(retries)
        except Exception:
            pass

    # OBS-5: SQLite event persistence methods
    def _enable_event_persistence(self, db_path: str):
        """Create SQLite DB and events table for persistent event logging."""
        self._event_db_path = db_path
        self._event_db_conn = sqlite3.connect(db_path, check_same_thread=False)
        with self._event_db_lock:
            self._event_db_conn.execute(
                "CREATE TABLE IF NOT EXISTS events("
                "id INTEGER PRIMARY KEY, session_id TEXT, event_type TEXT, "
                "data TEXT, ts REAL)"
            )
            self._event_db_conn.commit()

    def _persist_event(self, event_type: str, data: Dict[str, Any]):
        """Insert an event into the SQLite events table (thread-safe)."""
        try:
            session_id = data.get("session_id", "")
            data_str = json.dumps(data, default=str)
            with self._event_db_lock:
                self._event_db_conn.execute(
                    "INSERT INTO events(session_id, event_type, data, ts) VALUES (?,?,?,?)",
                    (session_id, event_type, data_str, time.time()),
                )
                self._event_db_conn.commit()
        except Exception:
            pass

    def query_events(self, session_id: str) -> List[Dict[str, Any]]:
        """Return all events for a given session_id from the SQLite store."""
        if self._event_db_conn is None:
            return []
        try:
            with self._event_db_lock:
                cur = self._event_db_conn.execute(
                    "SELECT id, session_id, event_type, data, ts FROM events WHERE session_id=?",
                    (session_id,),
                )
                rows = cur.fetchall()
            result = []
            for row in rows:
                try:
                    data = json.loads(row[3])
                except Exception:
                    data = row[3]
                result.append({
                    "id": row[0], "session_id": row[1], "event_type": row[2],
                    "data": data, "ts": row[4],
                })
            return result
        except Exception:
            return []
