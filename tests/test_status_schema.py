import json
import os
import time
import jsonschema
from fastapi.testclient import TestClient
import backend.api_backend as api_backend

client = TestClient(api_backend.app)


def _load_status_schema():
    schema_path = os.path.join(os.path.dirname(api_backend.__file__), "schemas", "status_message.schema.json")
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_status_endpoint_validates_schema():
    schema = _load_status_schema()

    cfg = {
        "graph_name": "status_test",
        "agents": [
            {"name": "a1", "system_prompt": "s1", "next": "a2"},
            {"name": "a2", "system_prompt": "s2", "next": "END"}
        ]
    }
    r = client.post("/orchestrate_async", json={"config_json": cfg})
    assert r.status_code == 200
    run_id = r.json().get("run_id")

    # Poll until terminal state
    final = None
    for _ in range(50):
        s = client.get(f"/status/{run_id}")
        assert s.status_code == 200
        data = s.json()
        # Validate shape
        jsonschema.validate(instance=data, schema=schema)
        if data.get("status") in ("completed", "error"):
            final = data
            break
        time.sleep(0.05)

    assert final is not None, "Status endpoint did not reach terminal state"
    assert "status" in final
