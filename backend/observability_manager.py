"""
observability_manager.py
Central abstraction for logging, tracing, metrics, and event hooks.
Supports pluggable backends (logging, OpenTelemetry, Prometheus, etc.)
"""

import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional


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
        # Placeholders for future integrations
        self.otel = None  # OpenTelemetry
        self.prometheus = None  # Prometheus

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

    def run_plugin_hooks(self, event_type: str, data: Dict[str, Any]):
        """Run all registered plugin hooks for the given event type."""
        for cb in self.hooks.get(event_type, []):
            try:
                cb(data)
            except Exception as e:
                self.logger.error(json.dumps({"error": str(e), "hook_event": event_type}, default=str))

    def _run_hooks(self, event_type: str, data: Dict[str, Any]):
        for cb in self.hooks.get(event_type, []):
            try:
                cb(data)
            except Exception as e:
                self.logger.error(json.dumps({"error": str(e), "hook_event": event_type}, default=str))
