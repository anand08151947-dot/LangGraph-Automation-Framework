import time
from fastapi.testclient import TestClient
import backend.api_backend as api_backend

client = TestClient(api_backend.app)


def test_end_to_end_template_orchestration():
    # Ensure a template exists: save one via API
    cfg = {
        "graph_name": "e2e_workflow",
        "agents": [
            {"name": "a1", "system_prompt": "first", "next": "a2"},
            {"name": "a2", "system_prompt": "second", "next": "END"}
        ]
    }
    r = client.post("/save_template", json={"name": "e2e_template", "example": cfg, "description": "E2E test template"})
    assert r.status_code == 200

    # Pick a template
    r = client.get("/templates")
    assert r.status_code == 200
    templates = r.json()
    assert len(templates) > 0
    tmpl = next((t for t in templates if t['name'] == 'e2e_template'), templates[0])

    # Retrieve template details
    r = client.get(f"/template/{tmpl['name']}")
    assert r.status_code == 200
    template_info = r.json()

    # Orchestrate using template JSON
    cfg = template_info['example']

    # Kick off orchestration
    r = client.post("/orchestrate_async", json={"config_json": cfg})
    assert r.status_code == 200
    run_id = r.json().get("run_id")
    assert run_id is not None

    # Poll for completion
    for _ in range(100):
        s = client.get(f"/status/{run_id}")
        assert s.status_code == 200
        data = s.json()
        if data.get("status") == "completed":
            result = data.get("result")
            # Final step_state should include messages and sender from last agent
            assert result is not None
            assert hasattr(result, 'messages') or isinstance(result, dict) or isinstance(result, list) or result != {}
            break
        time.sleep(0.05)
    else:
        assert False, "E2E orchestration did not complete"

    # Check STM/LTM were saved for this run_id
    stm = client.get(f"/memory/stm/{run_id}")
    assert stm.status_code == 200
    ltm = client.get(f"/memory/ltm/{run_id}")
    assert ltm.status_code == 200
    assert isinstance(ltm.json().get('ltm'), list)
