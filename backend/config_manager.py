"""
config_manager.py
Centralized configuration management for all backend modules.
Supports environment overrides, dynamic reload, and schema validation.
"""

import os
import json
import threading
from typing import Any, Dict, Optional
from pydantic import BaseModel, ValidationError

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
        # Validate config
        try:
            self.schema.parse_obj(merged)
        except ValidationError as e:
            raise ValueError(f"Config validation failed: {e}")
        self._config = merged

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def reload(self):
        self._load_config()

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
