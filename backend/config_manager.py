"""
config_manager.py
Centralized configuration management for all backend modules.
Supports environment overrides, dynamic reload, and schema validation.
"""

import os
import json
import re
import threading
from typing import Any, Dict, Optional
from pydantic import BaseModel, ValidationError

_ENV_VAR_RE = re.compile(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}')


def _substitute_env_vars(obj: Any) -> Any:
    """Recursively replace ${ENV_VAR_NAME} tokens in string values.

    Raises ValueError at load time if a referenced variable is not set,
    keeping secrets out of config files (CFG-1).
    """
    if isinstance(obj, str):
        def _replace(match: re.Match) -> str:
            var_name = match.group(1)
            value = os.environ.get(var_name)
            if value is None:
                raise ValueError(
                    f"Config references undefined environment variable: ${{{var_name}}}. "
                    f"Set the variable before starting the API."
                )
            return value
        return _ENV_VAR_RE.sub(_replace, obj)
    if isinstance(obj, dict):
        return {k: _substitute_env_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_substitute_env_vars(v) for v in obj]
    return obj

class ConfigSchema(BaseModel):
    memory: Optional[dict] = None
    observability: Optional[dict] = None
    tool_registry: Optional[dict] = None
    api_keys: Optional[dict] = None
    # Add more config sections as needed

class ConfigManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, config_path: str = "config.json", env: Optional[str] = None, schema: Any = ConfigSchema):
        self.config_path = config_path
        self.env = env or os.getenv("APP_ENV", "dev")
        self.schema = schema
        self._config = None
        self._load_config()

    def _load_config(self):
        # Load base config
        if not os.path.exists(self.config_path):
            self._config = {}
            return
        with open(self.config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        # Apply environment overrides if present
        env_overrides = config.get("environments", {}).get(self.env, {})
        merged = {**config, **env_overrides}
        # Remove environments key from merged config
        merged.pop("environments", None)
        # CFG-1: substitute ${ENV_VAR_NAME} tokens in all string values
        merged = _substitute_env_vars(merged)
        # Validate config
        try:
            self.schema.parse_obj(merged)
        except ValidationError as e:
            raise ValueError(f"Config validation failed: {e}")
        self._config = merged

    def get(self, key: str, default: Any = None) -> Any:
        """CFG-2: Support dot-notation path for nested config access.

        e.g., config_mgr.get("memory.backend", "sqlite") is equivalent to
        config_mgr.get("memory", {}).get("backend", "sqlite").
        Falls back to top-level key lookup if no dot is present.
        """
        if "." not in key:
            return self._config.get(key, default)
        parts = key.split(".")
        node: Any = self._config
        for part in parts:
            if not isinstance(node, dict):
                return default
            node = node.get(part)
            if node is None:
                return default
        return node if node is not None else default

    def reload(self):
        self._load_config()

    def watch(self, interval: float = 5.0) -> None:
        """CFG-6: Start a background thread that polls the config file for changes
        and calls reload() automatically when the file's mtime changes.

        The watcher runs as a daemon thread so it does not prevent process exit.
        Calling watch() multiple times is safe — subsequent calls are no-ops.
        """
        if getattr(self, "_watcher_active", False):
            return
        self._watcher_active = True
        import os as _os

        def _poll():
            last_mtime = None
            while getattr(self, "_watcher_active", True):
                try:
                    mtime = _os.path.getmtime(self.config_path)
                    if last_mtime is not None and mtime != last_mtime:
                        import logging as _log
                        _log.getLogger(__name__).info(
                            "CFG-6: config file changed, reloading %s", self.config_path
                        )
                        with self._lock:
                            self._load_config()
                    last_mtime = mtime
                except Exception:
                    pass
                import time as _time
                _time.sleep(interval)

        t = threading.Thread(target=_poll, daemon=True, name="config-watcher")
        t.start()

    def stop_watch(self) -> None:
        """Stop the config file watcher thread."""
        self._watcher_active = False

    @property
    def config(self) -> Dict[str, Any]:
        return self._config

# Example config.json:
# {
#   "memory": {"backend": "sqlite"},
#   "observability": {"backends": ["logging"]},
#   "api_keys": {"openai": "sk-..."},
#   "environments": {
#     "prod": {"memory": {"backend": "redis"}},
#     "dev": {"observability": {"backends": ["logging"]}}
#   }
# }

# Usage example:
# config_mgr = ConfigManager("config.json")
# memory_cfg = config_mgr.get("memory")
# config_mgr.reload()  # Hot-reload config
