import json
import os
import zipfile
import time
from pathlib import Path

from orchestrator import Orchestrator
from memory_manager import MemoryManager
from observability_manager import ObservabilityManager

ROOT = Path(__file__).resolve().parent
TEMPLATES_FILE = ROOT / "prompt_templates_advanced.json"
ARTIFACTS_DIR = ROOT / "artifacts"
ARTIFACTS_DIR.mkdir(exist_ok=True)

USE_CASE = "Multi-Agent Chatbot Escalation"


def find_template(use_case: str):
    with open(TEMPLATES_FILE, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    for item in data:
        if item.get("use_case") == use_case:
            return item
    return None


def save_json(obj, path: Path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)


def run():
    tpl = find_template(USE_CASE)
    if not tpl:
        print(f"Template use_case='{USE_CASE}' not found in {TEMPLATES_FILE}")
        return 2

    cfg = tpl.get("template_json") or tpl
    run_id = f"e2e_{int(time.time())}"
    print("Running E2E for:", USE_CASE, "run_id=", run_id)

    # Prepare orchestrator with isolated memory and observability pointing to artifacts
    ltm_path = ARTIFACTS_DIR / f"{run_id}_ltm.db"
    orch = Orchestrator()
    orch.memory_manager = MemoryManager(stm_backend="memory", ltm_backend="sqlite", ltm_path=str(ltm_path))

    events = []
    obs = ObservabilityManager(["logging"])

    def _to_serializable(o):
        try:
            if o is None or isinstance(o, (str, int, float, bool)):
                return o
            if isinstance(o, dict):
                return {k: _to_serializable(v) for k, v in o.items()}
            if isinstance(o, (list, tuple)):
                return [_to_serializable(v) for v in o]
            if hasattr(o, "__dict__"):
                return {k: _to_serializable(v) for k, v in o.__dict__.items()}
            return str(o)
        except Exception:
            return str(o)

    def _append_event(evt_type, data):
        events.append({"type": evt_type, "data": _to_serializable(data)})

    obs.register_hook("pre_step", lambda d: _append_event("pre_step", d))
    obs.register_hook("post_step", lambda d: _append_event("post_step", d))
    obs.register_hook("error", lambda d: _append_event("error", d))
    orch.observability = obs

    # Persist the run config for traceability
    run_meta_path = ARTIFACTS_DIR / f"{run_id}_config.json"
    save_json({"run_id": run_id, "template_use_case": USE_CASE, "config": cfg}, run_meta_path)

    # Run synchronously
    try:
        result = orch.run_workflow(cfg, session_id=run_id)
        status = "completed"
    except Exception as e:
        result = str(e)
        status = "error"

    # Collect STM and LTM
    stm = orch.memory_manager.load_stm(run_id)
    ltm = orch.memory_manager.load_ltm(run_id)

    # Save artifacts
    save_json({"stm": stm}, ARTIFACTS_DIR / f"{run_id}_stm.json")
    save_json({"ltm": ltm}, ARTIFACTS_DIR / f"{run_id}_ltm.json")
    save_json({"result": str(result), "status": status}, ARTIFACTS_DIR / f"{run_id}_result.json")
    save_json(events, ARTIFACTS_DIR / f"{run_id}_events.json")

    # Create a bundle: include config, template file snippet, ltm.db if exists, and other code files for reproducibility
    bundle_path = ARTIFACTS_DIR / f"{run_id}_bundle.zip"
    with zipfile.ZipFile(bundle_path, "w") as z:
        z.write(run_meta_path, arcname=run_meta_path.name)
        z.write(ARTIFACTS_DIR / f"{run_id}_stm.json", arcname=f"{run_id}_stm.json")
        z.write(ARTIFACTS_DIR / f"{run_id}_ltm.json", arcname=f"{run_id}_ltm.json")
        z.write(ARTIFACTS_DIR / f"{run_id}_events.json", arcname=f"{run_id}_events.json")
        z.write(ARTIFACTS_DIR / f"{run_id}_result.json", arcname=f"{run_id}_result.json")
        # include the template file and a copy of the code used to run
        z.write(TEMPLATES_FILE, arcname=TEMPLATES_FILE.name)
        for fname in ["graph_factory.py", "orchestrator.py", "mcp_autobinder.py", "memory_manager.py", "observability_manager.py"]:
            p = ROOT / fname
            if p.exists():
                z.write(p, arcname=fname)
        # include sqlite DB if present
        if ltm_path.exists():
            z.write(ltm_path, arcname=ltm_path.name)

    print("E2E run finished. Status:", status)
    print("Artifacts written to:", ARTIFACTS_DIR)
    print("Bundle:", bundle_path)
    return 0


if __name__ == '__main__':
    rc = run()
    exit(rc)
