"""
observability_manager.py
Central abstraction for logging, tracing, metrics, and event hooks.
Supports pluggable backends (logging, OpenTelemetry, Prometheus, etc.)
"""

import logging
from typing import Any, Callable, Dict, List, Optional

class ObservabilityManager:
    def __init__(self, backends: Optional[List[str]] = None):
        """
        backends: List of enabled backends (e.g., ["logging", "otel", "prometheus"])
        """
        self.backends = backends or ["logging"]
        self.logger = logging.getLogger("Observability")
        self.hooks: Dict[str, List[Callable]] = {}
        # Placeholders for future integrations
        self.otel = None  # OpenTelemetry
        self.prometheus = None  # Prometheus
        # ... add more as needed


    # --- Structured Logging ---
    def log_event(self, event_type: str, data: Dict[str, Any]):
        if "logging" in self.backends:
            self.logger.info(f"[{event_type}] {data}")
        # Future: send to other backends
        self._run_hooks(event_type, data)

    # --- Error Logging ---
    def log_error(self, error: Exception, context: Dict[str, Any] = None, notify: bool = False):
        msg = f"[ERROR] {str(error)} Context: {context}"
        if "logging" in self.backends:
            self.logger.error(msg)
        # Future: send to notification backends (email, Slack, etc.)
        self._run_hooks("error", {"error": str(error), "context": context})
        if notify:
            # Placeholder for notification logic
            pass

    # --- Tracing ---
    def trace_step(self, session_id: str, step_info: Dict[str, Any]):
        if "logging" in self.backends:
            self.logger.info(f"[TRACE][{session_id}] {step_info}")
        # Future: OpenTelemetry tracing
        self._run_hooks("trace_step", {"session_id": session_id, **step_info})

    # --- Metrics ---
    def record_metric(self, metric_name: str, value: Any, tags: Optional[Dict[str, Any]] = None):
        if "logging" in self.backends:
            self.logger.info(f"[METRIC] {metric_name}={value} tags={tags}")
        # Future: Prometheus, OpenTelemetry metrics
        self._run_hooks("metric", {"metric_name": metric_name, "value": value, "tags": tags})

    # --- Event Hooks ---

    def register_hook(self, event_type: str, callback: Callable):
        """
        Register a callback for a specific event type (e.g., 'pre_step', 'post_step', 'error', 'audit').
        """
        if event_type not in self.hooks:
            self.hooks[event_type] = []
        self.hooks[event_type].append(callback)

    def run_plugin_hooks(self, event_type: str, data: Dict[str, Any]):
        """
        Run all registered plugin hooks for the given event type.
        """
        for cb in self.hooks.get(event_type, []):
            try:
                cb(data)
            except Exception as e:
                self.logger.error(f"Error in plugin hook for {event_type}: {e}")

    def _run_hooks(self, event_type: str, data: Dict[str, Any]):
        for cb in self.hooks.get(event_type, []):
            try:
                cb(data)
            except Exception as e:
                self.logger.error(f"Error in hook for {event_type}: {e}")

# Example usage:
# obs = ObservabilityManager(["logging"])
# obs.log_event("agent_action", {"agent": "Researcher", "action": "search", "input": "stock prices"})
# obs.trace_step("sess1", {"step": 1, "node": "Researcher"})
# obs.record_metric("latency", 0.23, {"node": "Researcher"})
# obs.register_hook("agent_action", lambda d: print("Custom hook!", d))
