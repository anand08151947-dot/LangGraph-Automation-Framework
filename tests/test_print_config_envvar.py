import os
import json
import time
from fastapi.testclient import TestClient
import backend.api_backend as api_backend

client = TestClient(api_backend.app)


def test_print_config_envvar_logs_config(caplog, monkeypatch):
    # Enable printing via env var
    monkeypatch.setenv("PRINT_RUN_CONFIG", "true")
    caplog.set_level("INFO")

    cfg = {"graph_name": "env_print_test", "agents": [{"name": "a1", "system_prompt": "s1", "next": "END"}]}
    r = client.post("/orchestrate_async", json={"config_json": cfg})
    assert r.status_code == 200
    run_id = r.json().get("run_id")

    # The log entry should contain the run_id and the graph_name
    logged = "\n".join([rec.getMessage() for rec in caplog.records])
    assert f"Run {run_id} config" in logged
    assert json.dumps(cfg["graph_name"]) or cfg["graph_name"] in logged or cfg["graph_name"] in logged

    # Cleanup env var
    monkeypatch.delenv("PRINT_RUN_CONFIG", raising=False)
