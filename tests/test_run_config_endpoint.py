import time
import json
import os
from fastapi.testclient import TestClient
import backend.api_backend as api_backend

client = TestClient(api_backend.app)


def test_run_config_endpoint_persists_and_returns_config():
    cfg = {
        "graph_name": "config_test",
        "agents": [
            {"name": "a1", "system_prompt": "s1", "next": "END"}
        ]
    }
    # Start orchestration and include template_name query param
    r = client.post("/orchestrate_async?template_name=test_template", json={"config_json": cfg})
    assert r.status_code == 200
    run_id = r.json().get("run_id")
    assert run_id

    # Immediately query the stored config
    r2 = client.get(f"/runs/{run_id}/config")
    assert r2.status_code == 200
    body = r2.json()
    assert body["run_id"] == run_id
    assert body["config"] == cfg
    assert body["template"] == "test_template"

    # Also ensure status endpoint still works and contains config
    s = client.get(f"/status/{run_id}")
    assert s.status_code == 200
    sbody = s.json()
    assert sbody.get("config") == cfg
