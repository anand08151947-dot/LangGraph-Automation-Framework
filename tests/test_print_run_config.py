import json
import time
from fastapi.testclient import TestClient
import backend.api_backend as api_backend

client = TestClient(api_backend.app)


def test_print_run_config_and_template():
    cfg = {
        "graph_name": "print_config_test",
        "agents": [
            {"name": "a1", "system_prompt": "s1", "next": "END"}
        ]
    }
    # Start run with template_name
    r = client.post("/orchestrate_async?template_name=printed_template", json={"config_json": cfg})
    assert r.status_code == 200
    run_id = r.json().get("run_id")
    assert run_id

    # Fetch stored config
    r2 = client.get(f"/runs/{run_id}/config")
    assert r2.status_code == 200
    body = r2.json()

    # Print the stored config and template so test output shows traceability
    print("Stored run config for run_id:", run_id)
    print(json.dumps(body.get("config"), indent=2))
    print("Stored template name:", body.get("template"))

    # Assertions to ensure correctness
    assert body["config"] == cfg
    assert body["template"] == "printed_template"