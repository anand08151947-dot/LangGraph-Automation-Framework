from fastapi.testclient import TestClient
import backend.api_backend as api_backend
import time
import json
import jsonschema
import os

client = TestClient(api_backend.app)


def _load_status_schema():
    schema_path = os.path.join(os.path.dirname(api_backend.__file__), "schemas", "status_message.schema.json")
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_ws_status_streaming_validates_schema():
    schema = _load_status_schema()

    cfg = {
        "graph_name": "ws_test",
        "agents": [
            {"name": "a1", "system_prompt": "s1", "next": "a2"},
            {"name": "a2", "system_prompt": "s2", "next": "END"}
        ]
    }
    r = client.post("/orchestrate_async", json={"config_json": cfg})
    assert r.status_code == 200
    run_id = r.json().get("run_id")
    assert run_id

    with client.websocket_connect(f"/ws/status/{run_id}") as websocket:
        final = None
        for _ in range(20):
            data = websocket.receive_json()
            # validate against schema
            jsonschema.validate(instance=data, schema=schema)
            assert data.get("run_id") == run_id
            status = data.get("status")
            if status in ("completed", "error"):
                final = data
                break
            time.sleep(0.1)
        assert final is not None, "Did not receive completed/error status over websocket"
        assert "status" in final
