import sys, os as _os
sys.path.insert(0, _os.path.dirname(__file__))
from db import init_db, upsert_run, get_run, get_all_runs, record_to_dict, \
    seed_templates_from_files, get_all_templates, get_template_by_name, template_record_to_dict, \
    save_custom_template, get_template_versions, get_custom_templates
init_db()
seed_templates_from_files()

from fastapi import FastAPI, Body, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# ── Module-level helper: recursively make objects JSON-serializable ────────────
def _to_serializable(obj):
    try:
        if obj is None or isinstance(obj, (str, int, float, bool)):
            return obj
        if isinstance(obj, dict):
            return {k: _to_serializable(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_to_serializable(v) for v in obj]
        if hasattr(obj, "__dict__"):
            return {k: _to_serializable(v) for k, v in obj.__dict__.items()}
        return str(obj)
    except Exception:
        return str(obj)

# FastAPI app instance (must be defined before route decorators)
app = FastAPI()

# Allow requests from the React dev server and any localhost origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Enhanced Config-Driven Architecture Endpoints ---
@app.get("/config/summary")
def config_summary(request: Request):
    # SEC-5: require admin
    _require_admin(request)
    # Summarize config for UI/LLM
    cfg = config_mgr.config
    summary = {
        "memory": cfg.get("memory"),
        "observability": cfg.get("observability"),
        "tool_registry": cfg.get("tool_registry"),
        "api_keys": list(cfg.get("api_keys", {}).keys()),
        "num_templates": len(template_manager.list_templates()),
        "num_tools": len(tool_registry.list_tools()),
    }
    # SEC-4: recursively redact any nested secrets
    return {"summary": _redact_secrets(summary)}

@app.post("/config/generate_llm")
def generate_config_llm(request: dict = Body(...)):
    # Placeholder: Use LLM to generate config from natural language
    instructions = request.get("instructions")
    # In production, call LLM here
    return {"generated_config": {"instructions": instructions, "example": "...LLM output here..."}}

@app.post("/config/simulate")
def simulate_config(request: dict = Body(...)):
    # Simulate/dry-run config (validate, build, but do not execute)
    config_json = request.get("config_json")
    try:
        # Validate config
        config_mgr.schema.parse_obj(config_json)
        # Build graph (but do not run)
        factory = orchestrator.factory
        graph = factory.build_from_config(config_json)
        return {"status": "simulated", "nodes": list(graph.nodes.keys()), "edges": list(graph.edges.keys())}
    except Exception as e:
        return {"status": "error", "error": str(e)}
# --- Health & Readiness Endpoints ---
import time as _time

@app.get("/health")
def health_check():
    # Basic health check: service is up
    return {"status": "ok", "timestamp": _time.time()}

@app.get("/readiness")
def readiness_check():
    # Readiness: check core dependencies (DB, config, etc.)
    try:
        # Example: check config, memory, tool registry
        _ = config_mgr.config
        _ = memory_manager.ltm_backend
        _ = tool_registry.list_tools()
        return {"ready": True, "timestamp": _time.time()}
    except Exception as e:
        return {"ready": False, "error": str(e), "timestamp": _time.time()}
# --- Tool Versioning & Audit Endpoints ---
@app.get("/tools/{name}/versions")
def get_tool_versions(name: str, request: Request):
    # Auth as for /tools
    try:
        access_control.check_api_key(request)
    except HTTPException:
        access_control.check_jwt(request)
    return {"name": name, "versions": tool_registry.get_version_history(name)}

# --- Audit Log Example Endpoint (in-memory, for demo) ---
audit_log: list = []

@app.post("/audit")
def add_audit(action: str, details: dict):
    audit_log.append({"action": action, "details": details})
    observability.log_audit(action, details)
    return {"status": "logged"}

@app.get("/audit")
def get_audit(request: Request):
    # SEC-5: require admin
    _require_admin(request)
    return {"audit_log": audit_log}
# --- Config Management Endpoints ---
@app.get("/config")
def get_config():
    """Return the current effective config (after env overrides)."""
    return {"config": config_mgr.config, "env": config_mgr.env}

@app.post("/config/reload")
def reload_config(request: Request):
    """Hot-reload the config from disk."""
    # SEC-5: require admin
    _require_admin(request)
    # SEC-3: reject reload while active workflow runs are in progress
    with _active_run_lock:
        if _active_run_count > 0:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot reload config: {_active_run_count} active run(s) in progress. Try again when all runs have completed."
            )
    with _config_reload_lock:
        try:
            config_mgr.reload()
            # SEC-4: redact secrets from the reloaded config before returning
            return {"status": "reloaded", "config": _redact_secrets(config_mgr.config), "env": config_mgr.env}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Reload failed: {e}")

@app.post("/config/validate")
def validate_config():
    """Validate the current config against schema."""
    try:
        config_mgr.schema.parse_obj(config_mgr.config)
        return {"status": "valid"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Validation failed: {e}")
import zipfile, re
from fastapi.responses import FileResponse
# --- Bundle Download Endpoint ---
@app.get("/download_bundle")
def download_bundle(include_templates: bool = True, include_code: bool = True, config_name: str = None):
    bundle_path = "bundle.zip"
    with zipfile.ZipFile(bundle_path, "w") as bundle:
        # Add workflow configs
        config_dir = "."
        if config_name:
            bundle.write(config_name)
        else:
            for fname in os.listdir(config_dir):
                if fname.endswith(".json"):
                    bundle.write(fname)
        # Add code files
        if include_code:
            for code_file in ["graph_factory.py", "orchestrator.py", "mcp_autobinder.py", "llm_translator.py", "template_manager.py"]:
                if os.path.exists(code_file):
                    bundle.write(code_file)
        # Add templates
        if include_templates:
            template_dir = "prompt_templates"
            if os.path.exists(template_dir):
                for fname in os.listdir(template_dir):
                    path = os.path.join(template_dir, fname)
                    bundle.write(path)
    return FileResponse(bundle_path, media_type="application/zip", filename="agentic_ai_bundle.zip")
"""
FastAPI backend for LangGraph Automation Framework
Features:
- List available prompt templates
- Select/customize templates
- Orchestrate workflow (English-to-JSON, validation, graph assembly, MCP binding, execution)
- Return results/status to front end
"""


from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import os
import json
import asyncio

from template_manager import TemplateManager, TemplateVersion

from llm_translator import LLMTranslator
try:
    from orchestrator import Orchestrator, HumanApprovalRequired
except Exception as e:
    # Orchestrator (and its dependencies like langgraph) may not be installed in this environment.
    # We provide a lightweight fallback so the API can start for LLM/manual testing.
    import logging as _logging
    _logging.getLogger(__name__).warning(f"Orchestrator import failed: {e}")
    _orchestrator_import_error = str(e)
    class Orchestrator:  # simple fallback
        def __init__(self, *args, **kwargs):
            # Use the captured error message rather than the exception object which may be out of scope
            raise RuntimeError("Orchestrator not available in this environment: " + _orchestrator_import_error)
    class HumanApprovalRequired(Exception):  # fallback stub
        pass
from memory_manager import MemoryManager
from observability_manager import ObservabilityManager
from config_manager import ConfigManager
from tool_registry import ToolRegistry
from access_control import AccessControl
# --- Access Control Instance (initialized after ConfigManager is ready) ---
access_control = None
# --- Tool Registry Instance ---
tool_registry = ToolRegistry()

# --- Tool Registry Endpoints ---
from fastapi import Body

from fastapi import Depends, Request

@app.get("/tools")
def list_tools(request: Request):
    # Allow either API key or JWT
    try:
        access_control.check_api_key(request)
    except HTTPException:
        access_control.check_jwt(request)
    return {"tools": tool_registry.list_tools()}

@app.post("/tools/register")
def register_tool(tool: dict = Body(...), request: Request = None):
    # Require admin role
    try:
        access_control.check_api_key(request)
    except HTTPException:
        access_control.check_jwt(request)
        access_control.check_role(request, "admin")
    name = tool.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="Tool name required")
    tool_registry.register_tool(name, tool)
    return {"status": "registered", "tool": name}

@app.post("/tools/unregister")
def unregister_tool(tool: dict = Body(...), request: Request = None):
    # Require admin role
    try:
        access_control.check_api_key(request)
    except HTTPException:
        access_control.check_jwt(request)
        access_control.check_role(request, "admin")
    name = tool.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="Tool name required")
    tool_registry.unregister_tool(name)
    return {"status": "unregistered", "tool": name}

@app.post("/tools/status")
def update_tool_status(tool: dict = Body(...), request: Request = None):
    # Allow either API key or JWT
    try:
        access_control.check_api_key(request)
    except HTTPException:
        access_control.check_jwt(request)
    name = tool.get("name")
    status = tool.get("status")
    if not name or not status:
        raise HTTPException(status_code=400, detail="Tool name and status required")
    tool_registry.update_tool_status(name, status)
    return {"status": "updated", "tool": name, "new_status": status}

@app.get("/tools/health")
def tools_health(request: Request):
    # Allow either API key or JWT
    try:
        access_control.check_api_key(request)
    except HTTPException:
        access_control.check_jwt(request)
    return {"tools": tool_registry.health_check()}
import uuid
import threading
import time
import logging
from fastapi import WebSocket
# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("LangGraphAPI")

# SEC-3: Read-write lock for config reloads. Shared reads, exclusive write.
import threading as _threading
_config_reload_lock = _threading.RLock()
_active_run_count = 0
_active_run_lock = _threading.Lock()

def _increment_active_runs():
    global _active_run_count
    with _active_run_lock:
        _active_run_count += 1

def _decrement_active_runs():
    global _active_run_count
    with _active_run_lock:
        _active_run_count -= 1

# SEC-4: Recursive secret redaction helper
_SECRET_KEY_PATTERNS = re.compile(r"key|secret|token|password|credential|auth|passwd", re.IGNORECASE)

def _redact_secrets(obj):
    """Recursively redact dict values whose keys look like secrets."""
    if isinstance(obj, dict):
        return {
            k: "REDACTED" if _SECRET_KEY_PATTERNS.search(k) else _redact_secrets(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact_secrets(v) for v in obj]
    return obj

# SEC-5: Helper to require admin role (API key path skips role check; JWT path enforces it)
def _require_admin(request: Request):
    try:
        access_control.check_api_key(request)
    except HTTPException:
        access_control.check_jwt(request)
        access_control.check_role(request, "admin")

# --- Config Manager Instance ---
# Use path relative to this module so running from other cwd works
config_mgr = ConfigManager(os.path.join(os.path.dirname(__file__), "config.json"))
# --- Access Control Instance ---
access_control = AccessControl(
    api_keys=list(config_mgr.get("api_keys", {}).values()),
    jwt_secret=config_mgr.get("api_keys", {}).get("jwt_secret"),  # SEC-1: no fallback; env var required
    user_roles=config_mgr.get("user_roles", {})
)
# --- Observability Manager Instance ---
observability = ObservabilityManager(config_mgr.get("observability", {}).get("backends", ["logging"]))
# --- Orchestrator Instance & Status Store ---
try:
    orchestrator = Orchestrator()
    # If available, inject the shared memory manager and observability so STM/LTM
    # and telemetry are visible to API endpoints and tests.
    try:
        orchestrator.memory_manager = memory_manager
        orchestrator.observability = observability
    except Exception:
        pass
except Exception as e:
    import logging as _logging
    logger = _logging.getLogger(__name__)
    logger.warning(f"Orchestrator unavailable: {e}")
    orchestrator = None
workflow_status = {}  # run_id: {status, result}
# --- Memory Manager Instance ---
memory_manager = MemoryManager(
    stm_backend=config_mgr.get("memory", {}).get("backend", "memory"),
    ltm_backend=config_mgr.get("memory", {}).get("backend", "sqlite"),
    ltm_path=config_mgr.get("memory", {}).get("ltm_path", "ltm.db")
)
# Ensure Orchestrator uses the shared memory manager so STM/LTM API endpoints see run data
if 'orchestrator' in globals() and orchestrator is not None:
    try:
        orchestrator.memory_manager = memory_manager
        orchestrator.observability = observability
    except Exception:
        pass

# --- Initialize LLM Translator according to config/env ---
llm_mode = config_mgr.get("llm", {}).get("mode", os.getenv("LLM_MODE", "openai"))
lm_studio_cfg = config_mgr.get("lm_studio", {})
llm_translator = LLMTranslator(
    mode=llm_mode,
    lm_studio_url=lm_studio_cfg.get("url"),
    lm_studio_model=lm_studio_cfg.get("model"),
)

# --- Memory Management Endpoints ---
from fastapi import Body

@app.get("/memory/stm/{session_id}")
def get_stm(session_id: str):
    state = memory_manager.load_stm(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="STM not found for session")
    return {"session_id": session_id, "stm": state}

@app.post("/memory/stm/{session_id}")
def save_stm(session_id: str, state: dict = Body(...)):
    memory_manager.save_stm(session_id, state)
    return {"status": "saved", "session_id": session_id}

@app.delete("/memory/stm/{session_id}")
def reset_stm(session_id: str):
    memory_manager.reset_stm(session_id)
    return {"status": "reset", "session_id": session_id}

@app.get("/memory/ltm/{session_id}")
def get_ltm(session_id: str):
    history = memory_manager.load_ltm(session_id)
    return {"session_id": session_id, "ltm": history}

@app.delete("/memory/ltm/{session_id}")
def reset_ltm(session_id: str):
    memory_manager.reset_ltm(session_id)
    return {"status": "reset", "session_id": session_id}

# --- Models ---
class TemplateInfo(BaseModel):
    name: str
    description: Optional[str] = None
    example: Optional[Dict[str, Any]] = None

class CustomizationRequest(BaseModel):
    template_name: str
    custom_instructions: Optional[str] = None
    custom_json: Optional[Dict[str, Any]] = None

class OrchestrationRequest(BaseModel):
    config_json: Dict[str, Any]



# --- Template Manager Instance (LLM Translator will be initialized after config load) ---
template_manager = TemplateManager()

class EnglishToJsonRequest(BaseModel):
    instructions: str

class EnglishToJsonSubmitRequest(BaseModel):
    instructions: str
    llm_response: str

class CustomizationLLMRequest(BaseModel):
    base_json: Dict[str, Any]
    custom_instructions: str

class CustomizeSubmitRequest(BaseModel):
    base_json: Dict[str, Any]
    llm_response: str

# --- LLM Translation Endpoints ---
@app.post("/english_to_json")
def english_to_json(req: EnglishToJsonRequest):
    try:
        if llm_translator.mode == "manual":
            prompt = llm_translator.get_prompt(req.instructions)
            return {
                "prompt": prompt,
                "note": "Copy the prompt into your LLM, then POST the LLM output (JSON only) to /english_to_json/submit with fields {instructions, llm_response}."
            }
        config = llm_translator.english_to_json(req.instructions)
        return {"config_json": config}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/english_to_json/submit")
def english_to_json_submit(req: EnglishToJsonSubmitRequest):
    try:
        config = llm_translator.parse_llm_response(req.llm_response)
        return {"config_json": config}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/customize_json_llm")
def customize_json_llm(req: CustomizationLLMRequest):
    try:
        if llm_translator.mode == "manual":
            prompt = llm_translator.get_prompt(req.custom_instructions, base_json=req.base_json, customization=True)
            return {
                "prompt": prompt,
                "note": "Copy the prompt into your LLM, then POST the LLM output (JSON only) to /customize_json_llm/submit with fields {base_json, llm_response}."
            }
        config = llm_translator.customize_json(req.base_json, req.custom_instructions)
        return {"customized_json": config}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/customize_json_llm/submit")
def customize_json_llm_submit(req: CustomizeSubmitRequest):
    try:
        config = llm_translator.parse_llm_response(req.llm_response)
        return {"customized_json": config}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# --- Endpoints ---

@app.get("/templates")
def get_templates():
    """Return all templates from the DB (seeded from prompt_templates/ files)."""
    records = get_all_templates()
    return [template_record_to_dict(r) for r in records]

@app.get("/template/{name}")
def get_template(name: str, version: Optional[str] = None):
    record = get_template_by_name(name)
    if not record:
        raise HTTPException(status_code=404, detail="Template not found")
    return template_record_to_dict(record)

@app.post("/customize_template")
def customize_template(req: CustomizationRequest):
    # Option 1: Use LLM to translate custom_instructions to JSON (not implemented here)
    # Option 2: Accept custom_json directly
    if req.custom_json:
        return {"customized_template": req.custom_json}
    # Fallback: Return original template
    t = template_manager.get_template(req.template_name)
    if t:
        return {"customized_template": t.data}
    raise HTTPException(status_code=404, detail="Template not found")

class SaveCustomTemplateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    template_json: Dict[str, Any]
    parent_name: Optional[str] = None
    sample_prompt: Optional[str] = None

@app.post("/save_template")
def save_template_endpoint(req: SaveCustomTemplateRequest):
    """Save a user-customized template with versioning. Auto-increments version for same name."""
    try:
        result = save_custom_template(
            name=req.name,
            description=req.description or "",
            template_json_obj=req.template_json,
            parent_name=req.parent_name,
            sample_prompt=req.sample_prompt,
        )
        return {"status": "saved", "template": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/templates/custom")
def list_custom_templates():
    """Return all user-saved/customized templates."""
    return get_custom_templates()

@app.get("/templates/versions/{base_name}")
def list_template_versions(base_name: str):
    """Return all versions of a template family."""
    return get_template_versions(base_name)

def _save_run_artifacts(run_id: str, config_json: dict, result: dict, elapsed: str):
    """Generate and persist the full deployable artifact bundle for a completed run."""
    import datetime as _dt
    artifacts_dir = os.path.join(os.path.dirname(__file__), "artifacts", run_id)
    os.makedirs(artifacts_dir, exist_ok=True)

    graph_name = config_json.get("graph_name", "GeneratedWorkflow")

    # 1. workflow_config.json — exact config that produced this run
    with open(os.path.join(artifacts_dir, "workflow_config.json"), "w", encoding="utf-8") as f:
        json.dump(config_json, f, indent=2)

    # 2. run_result.json — final execution state
    with open(os.path.join(artifacts_dir, "run_result.json"), "w", encoding="utf-8") as f:
        json.dump({
            "run_id": run_id,
            "graph_name": graph_name,
            "status": "completed",
            "elapsed": elapsed,
            "completed_at": _dt.datetime.utcnow().isoformat() + "Z",
            "result": _to_serializable(result),
        }, f, indent=2)

    # 3. agent.py — standalone deployable Python script
    # 4. requirements.txt
    # 5. .env.example
    # 6. validation_report.json
    try:
        from code_generator import CodeGenerator
        gen = CodeGenerator()
        script = gen.generate_workflow_script(config_json)
        requirements = gen.generate_requirements(config_json)
        env_template = gen.generate_env_template(config_json)

        with open(os.path.join(artifacts_dir, "agent.py"), "w", encoding="utf-8") as f:
            f.write(script)
        with open(os.path.join(artifacts_dir, "requirements.txt"), "w", encoding="utf-8") as f:
            f.write(requirements)
        with open(os.path.join(artifacts_dir, ".env.example"), "w", encoding="utf-8") as f:
            f.write(env_template)

        # docker-compose.yml + Dockerfile
        docker_compose = gen.generate_docker_compose(config_json)
        dockerfile = gen.generate_dockerfile(config_json)
        with open(os.path.join(artifacts_dir, "docker-compose.yml"), "w", encoding="utf-8") as f:
            f.write(docker_compose)
        with open(os.path.join(artifacts_dir, "Dockerfile"), "w", encoding="utf-8") as f:
            f.write(dockerfile)

        # Validate the generated artifact against the workflow config
        try:
            validation_report = gen.validate_artifact(script, config_json)
        except Exception as val_err:
            logger.warning(f"Artifact validation error for run {run_id}: {val_err}")
            validation_report = {"passed": None, "score": None, "error": str(val_err), "checks": [], "summary": {}}

        with open(os.path.join(artifacts_dir, "validation_report.json"), "w", encoding="utf-8") as f:
            json.dump(validation_report, f, indent=2)

        v_score = validation_report.get("score")
        v_passed = validation_report.get("passed")
        logger.info(f"Artifact validation: passed={v_passed}, score={v_score} for run {run_id}")
    except Exception as cg_err:
        logger.warning(f"CodeGenerator failed for run {run_id}: {cg_err}")

    # 6. README.md — deployment instructions
    node_count = len(config_json.get("nodes", []))
    mcp_count = len(config_json.get("mcp_servers") or {})
    readme = f"""# {graph_name} — Agentic Workflow

Generated by LangGraph Automation Workbench  
Run ID: `{run_id}` | Completed: `{_dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC` | Duration: `{elapsed}`

## Quick Start

### Option A — Run directly (Python)
```bash
pip install -r requirements.txt
cp .env.example .env   # fill in LLM URL and any API keys
python agent.py
```

### Option B — Docker Compose (recommended for production)
```bash
cp .env.example .env   # fill in values
docker-compose up --build
```

## Workflow Overview
- **Nodes**: {node_count}
- **State Schema Fields**: {len(config_json.get("state_schema", {}))}
- **MCP Servers**: {mcp_count}

## Files
| File | Description |
|------|-------------|
| `agent.py` | Standalone runnable agentic workflow script |
| `requirements.txt` | Python package dependencies |
| `.env.example` | Environment variable template (copy to `.env`) |
| `docker-compose.yml` | Docker Compose for one-command deployment |
| `Dockerfile` | Container build recipe for agent.py |
| `workflow_config.json` | The workflow definition (re-import into Workbench) |
| `run_result.json` | Output from the validation run |
| `validation_report.json` | Artifact completeness & correctness report |

## Deployment
Deploy anywhere Python runs — local machine, Docker, AWS Lambda, Cloud Run, Kubernetes, etc.  
No dependency on this workbench. The bundle is fully self-contained.

- No dependency on this workbench — fully self-contained.
"""
    with open(os.path.join(artifacts_dir, "README.md"), "w", encoding="utf-8") as f:
        f.write(readme)

    logger.info(f"Artifacts saved to {artifacts_dir}")
    return artifacts_dir


def _run_workflow_async(run_id, config_json):
    import time as _t
    start = _t.time()
    _increment_active_runs()  # SEC-3: track active runs for reload guard
    workflow_status.setdefault(run_id, {})
    workflow_status[run_id].update({"status": "running", "result": None})
    upsert_run(run_id, status="running", logs=json.dumps([f"Workflow {run_id} started."]))
    logger.info(f"Workflow {run_id} started.")
    if orchestrator is None:
        err = globals().get("_orchestrator_import_error", "Orchestrator not available")
        workflow_status[run_id].update({"status": "error", "result": f"Orchestrator not available: {err}"})
        upsert_run(run_id, status="error", result=f"Orchestrator not available: {err}")
        logger.error(f"Workflow {run_id} failed: Orchestrator not available: {err}")
        _decrement_active_runs()
        return
    try:
        result = orchestrator.run_workflow(config_json, session_id=run_id)
        elapsed = f"{_t.time() - start:.2f}s"
        workflow_status[run_id].update({"status": "completed", "result": result})
        upsert_run(run_id, status="completed", result=result, duration=elapsed,
                   end_time=__import__("datetime").datetime.utcnow(),
                   logs=json.dumps([f"Workflow {run_id} completed in {elapsed}."]))
        logger.info(f"Workflow {run_id} completed.")
        # ── Generate and persist the deployable artifact bundle ────────
        _save_run_artifacts(run_id, config_json, result, elapsed)
    except HumanApprovalRequired as hap:
        workflow_status[run_id].update({
            "status": "awaiting_approval",
            "result": None,
            "checkpoint_node": hap.checkpoint_node,
            "state_snapshot": hap.state,
        })
        upsert_run(run_id, status="awaiting_approval",
                   result=f"Paused at {hap.checkpoint_node}")
        logger.info(f"Workflow {run_id} paused for human approval at {hap.checkpoint_node}")
    except Exception as e:
        elapsed = f"{_t.time() - start:.2f}s"
        workflow_status[run_id].update({"status": "error", "result": str(e)})
        upsert_run(run_id, status="error", result=str(e), duration=elapsed,
                   end_time=__import__("datetime").datetime.utcnow(),
                   logs=json.dumps([f"Workflow {run_id} failed: {str(e)}"]))
        logger.error(f"Workflow {run_id} failed: {e}")
    finally:
        _decrement_active_runs()  # SEC-3: always release the counter

@app.post("/orchestrate_async")
def orchestrate_async(req: OrchestrationRequest, template_name: Optional[str] = None):
    run_id = str(uuid.uuid4())
    logger.info(f"Received async orchestration request: run_id={run_id}, template={template_name}")
    # Persist initial run metadata including the submitted config (store a deep copy to avoid later mutation)
    import copy
    workflow_status[run_id] = {"status": "started", "result": None, "config": copy.deepcopy(req.config_json), "template": template_name}
    # Derive a human-readable name from config
    _wf_name = req.config_json.get("graph_name") or req.config_json.get("name") or (template_name if template_name else f"Run {run_id[:8]}")
    upsert_run(run_id, name=_wf_name, status="started", config=req.config_json, template=template_name)
    thread = threading.Thread(target=_run_workflow_async, args=(run_id, req.config_json))
    thread.start()

    # Conditional logging of the run config for traceability (controlled by env var)
    try:
        import os, json, copy as _copy
        if os.getenv("PRINT_RUN_CONFIG", "false").lower() == "true":
            # SEC-4: recursively redact secrets before logging
            cfg_copy = _redact_secrets(_copy.deepcopy(req.config_json))
            logger.info(f"Run {run_id} config:\n{json.dumps(cfg_copy, indent=2)}")
            try:
                observability.log_event("run_config", {"run_id": run_id, "template": template_name})
            except Exception:
                # Non-fatal if observability backend fails
                logger.debug("observability.log_event failed for run_config")
    except Exception:
        # Best-effort logging only
        logger.exception("Failed to log run config")

    return {"run_id": run_id, "status": "started"}

class ResumeRequest(BaseModel):
    config_json: Dict[str, Any]
    approval_input: Dict[str, Any] = {}

@app.post("/resume/{run_id}")
def resume_run(run_id: str, req: ResumeRequest):
    """Resume a workflow paused at a human_node checkpoint."""
    status = workflow_status.get(run_id)
    if not status or status.get("status") != "awaiting_approval":
        raise HTTPException(status_code=400, detail="Run is not awaiting approval")
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator not available")

    def _resume():
        try:
            result = orchestrator.resume_run(run_id, req.approval_input, req.config_json)
            workflow_status[run_id].update({"status": "completed", "result": result})
            upsert_run(run_id, status="completed", result=result)
            logger.info(f"Workflow {run_id} resumed and completed.")
        except HumanApprovalRequired as hap:
            workflow_status[run_id].update({
                "status": "awaiting_approval",
                "checkpoint_node": hap.checkpoint_node,
                "state_snapshot": hap.state,
            })
            upsert_run(run_id, status="awaiting_approval", result=f"Paused at {hap.checkpoint_node}")
        except Exception as e:
            workflow_status[run_id].update({"status": "error", "result": str(e)})
            upsert_run(run_id, status="error", result=str(e))
            logger.error(f"Resume of {run_id} failed: {e}")

    workflow_status[run_id]["status"] = "resuming"
    t = threading.Thread(target=_resume)
    t.start()
    return {"run_id": run_id, "status": "resuming"}

@app.get("/approval/{run_id}")
def get_approval_status(run_id: str):
    """Get checkpoint info for a run awaiting human approval."""
    status = workflow_status.get(run_id)
    if not status:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "run_id": run_id,
        "status": status.get("status"),
        "checkpoint_node": status.get("checkpoint_node"),
        "state_snapshot": _to_serializable(status.get("state_snapshot", {})),
    }


@app.get("/status/{run_id}")
def get_status(run_id: str):
    status = workflow_status.get(run_id)
    logger.info(f"Status check for run_id={run_id}: {status}")
    if not status:
        logger.warning(f"Status check failed: run_id={run_id} not found.")
        raise HTTPException(status_code=404, detail="Run ID not found")
    serializable = _to_serializable(status)
    return {"run_id": run_id, **serializable}

@app.get("/runs/{run_id}/config")
def get_run_config(run_id: str):
    """Return the stored config (and optional template) for a given run id."""
    status = workflow_status.get(run_id)
    if not status:
        raise HTTPException(status_code=404, detail="Run ID not found")
    cfg = status.get("config")
    if cfg is None:
        raise HTTPException(status_code=404, detail="No config stored for this run")
    return {"run_id": run_id, "config": cfg, "template": status.get("template")}


# --- WebSocket for result streaming ---
@app.websocket("/ws/status/{run_id}")
async def ws_status(websocket: WebSocket, run_id: str):
    await websocket.accept()
    logger.info(f"WebSocket status stream opened for run_id={run_id}")

    while True:
        status = workflow_status.get(run_id)
        s = status or {"status": "unknown"}
        serializable_status = _to_serializable(s)
        await websocket.send_json({"run_id": run_id, **serializable_status})
        if status and status["status"] in ["completed", "error"]:
            logger.info(f"WebSocket status stream closed for run_id={run_id}")
            break
        await asyncio.sleep(1)
    await websocket.close()



# --- Streaming/Async Execution (optional) ---
# You can add WebSocket or StreamingResponse endpoints for real-time updates

# --- Run History Endpoints (SQLite-backed) ---
@app.get("/runs")
def list_runs():
    """List all workflow runs from DB."""
    records = get_all_runs()
    return [record_to_dict(r) for r in records]

@app.get("/run/{run_id}")
def get_run_detail(run_id: str):
    """Get detailed info for a single run from DB (falls back to in-memory)."""
    record = get_run(run_id)
    if record:
        return record_to_dict(record)
    # Fallback: in-memory status
    status = workflow_status.get(run_id)
    if not status:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "id": run_id,
        "name": status.get("template") or f"Run {run_id[:8]}",
        "status": status.get("status", "unknown").upper(),
        "startTime": None,
        "duration": None,
        "result": _to_serializable(status.get("result")),
        "logs": [],
        "config": status.get("config"),
        "template": status.get("template"),
    }

# --- Artifacts Listing Endpoint ---
@app.get("/artifacts")
def list_artifacts():
    """List artifact bundles grouped by run_id."""
    artifacts_dir = os.path.join(os.path.dirname(__file__), "artifacts")
    if not os.path.exists(artifacts_dir):
        return []
    runs = []
    for entry in sorted(os.scandir(artifacts_dir), key=lambda e: e.stat().st_mtime, reverse=True):
        if not entry.is_dir():
            continue
        run_id = entry.name
        files = []
        has_code = False
        graph_name = run_id[:8]
        completed_at = None
        elapsed = None
        try:
            result_path = os.path.join(entry.path, "run_result.json")
            if os.path.exists(result_path):
                with open(result_path, encoding="utf-8") as f:
                    meta = json.load(f)
                graph_name = meta.get("graph_name", graph_name)
                completed_at = meta.get("completed_at")
                elapsed = meta.get("elapsed")
        except Exception:
            pass
        # Load validation summary if present
        validation_summary = None
        try:
            val_path = os.path.join(entry.path, "validation_report.json")
            if os.path.exists(val_path):
                with open(val_path, encoding="utf-8") as f:
                    vr = json.load(f)
                validation_summary = {
                    "passed": vr.get("passed"),
                    "score": vr.get("score"),
                    "summary": vr.get("summary", {}),
                }
        except Exception:
            pass
        for f in sorted(os.scandir(entry.path), key=lambda e: e.name):
            if not f.is_file():
                continue
            size_bytes = f.stat().st_size
            size_str = f"{size_bytes // 1024} KB" if size_bytes >= 1024 else f"{size_bytes} B"
            ext = os.path.splitext(f.name)[1].lower()
            ftype = "code" if ext == ".py" else "json" if ext == ".json" else "text" if ext in (".txt", ".md", ".example") else "config"
            if f.name == "agent.py":
                has_code = True
            files.append({
                "name": f.name,
                "type": ftype,
                "size": size_str,
                "size_bytes": size_bytes,
            })
        if files:
            runs.append({
                "run_id": run_id,
                "graph_name": graph_name,
                "completed_at": completed_at,
                "elapsed": elapsed,
                "has_code": has_code,
                "files": files,
                "total_files": len(files),
                "validation": validation_summary,
            })
    return runs


@app.get("/artifacts/{run_id}/code")
def get_artifact_code(run_id: str):
    """Return the generated agent.py code for a run."""
    artifacts_dir = os.path.join(os.path.dirname(__file__), "artifacts", run_id)
    code_path = os.path.join(artifacts_dir, "agent.py")
    if not os.path.exists(code_path):
        raise HTTPException(status_code=404, detail="agent.py not found for this run")
    with open(code_path, encoding="utf-8", errors="replace") as f:
        code = f.read()

    def _read(path: str) -> str:
        try:
            return open(path, encoding="utf-8", errors="replace").read()
        except Exception:
            return ""

    # Also return requirements and env
    req_path = os.path.join(artifacts_dir, "requirements.txt")
    env_path = os.path.join(artifacts_dir, ".env.example")
    readme_path = os.path.join(artifacts_dir, "README.md")
    docker_path = os.path.join(artifacts_dir, "docker-compose.yml")
    dockerfile_path = os.path.join(artifacts_dir, "Dockerfile")
    val_path = os.path.join(artifacts_dir, "validation_report.json")
    val_report = None
    if os.path.exists(val_path):
        try:
            with open(val_path, encoding="utf-8") as vf:
                val_report = json.load(vf)
        except Exception:
            val_report = None
    return {
        "run_id": run_id,
        "agent_py": code,
        "requirements_txt": _read(req_path) if os.path.exists(req_path) else "",
        "env_example": _read(env_path) if os.path.exists(env_path) else "",
        "readme": _read(readme_path) if os.path.exists(readme_path) else "",
        "docker_compose": _read(docker_path) if os.path.exists(docker_path) else "",
        "dockerfile": _read(dockerfile_path) if os.path.exists(dockerfile_path) else "",
        "validation_report": val_report,
    }


@app.get("/download_bundle/{run_id}")
def download_run_bundle(run_id: str):
    """Download a ZIP bundle of all artifacts for a run."""
    artifacts_dir = os.path.join(os.path.dirname(__file__), "artifacts", run_id)
    if not os.path.exists(artifacts_dir):
        raise HTTPException(status_code=404, detail="No artifacts for this run")
    bundle_path = os.path.join(os.path.dirname(__file__), "artifacts", f"{run_id}_bundle.zip")
    with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in os.scandir(artifacts_dir):
            if f.is_file():
                zf.write(f.path, arcname=f.name)
    graph_name = run_id[:8]
    try:
        rp = os.path.join(artifacts_dir, "run_result.json")
        if os.path.exists(rp):
            with open(rp, encoding="utf-8") as fp:
                graph_name = json.load(fp).get("graph_name", graph_name)
    except Exception:
        pass
    safe_name = re.sub(r'[^\w\-]', '_', graph_name)
    return FileResponse(bundle_path, media_type="application/zip", filename=f"{safe_name}_{run_id[:8]}.zip")

# --- LM Studio Config Update Endpoint ---
@app.put("/config/lm_studio")
def update_lm_studio_config(update: dict = Body(...)):
    """Persist LM Studio URL and model name to config.json and reload."""
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if "lm_studio" not in cfg:
            cfg["lm_studio"] = {}
        if "url" in update:
            cfg["lm_studio"]["url"] = update["url"]
        if "model" in update:
            cfg["lm_studio"]["model"] = update["model"]
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        # Update live translator instance
        if "url" in update:
            llm_translator.lm_studio_url = update["url"]
        if "model" in update:
            llm_translator.lm_studio_model = update["model"]
        return {"status": "updated", "lm_studio": cfg["lm_studio"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update config: {e}")
# --- LLM Connection Test Endpoint ---
@app.post("/llm/test")
def test_llm_connection(req: dict = Body(...)):
    """Test connectivity to an LLM provider. Returns {ok, latency_ms, error?}."""
    import time as _t
    provider = req.get("provider", "lm_studio")
    start = _t.time()
    try:
        if provider == "lm_studio":
            base_url = req.get("base_url", "http://localhost:1234")
            model = req.get("model", "local-model")
            import requests as _req
            resp = _req.post(f"{base_url}/v1/chat/completions", json={
                "model": model, "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 5, "stream": False
            }, timeout=10)
            resp.raise_for_status()
        elif provider == "openai":
            import openai as _openai
            client = _openai.OpenAI(api_key=req.get("api_key"))
            client.models.list()
        elif provider == "gemini":
            import requests as _req
            api_key = req.get("api_key")
            resp = _req.get(f"https://generativelanguage.googleapis.com/v1/models?key={api_key}", timeout=10)
            resp.raise_for_status()
        elif provider == "anthropic":
            import requests as _req
            resp = _req.get("https://api.anthropic.com/v1/models",
                headers={"x-api-key": req.get("api_key"), "anthropic-version": "2023-06-01"}, timeout=10)
            resp.raise_for_status()
        elif provider == "ollama":
            import requests as _req
            url = req.get("url", "http://localhost:11434")
            resp = _req.get(f"{url}/api/tags", timeout=10)
            resp.raise_for_status()
        latency_ms = round((_t.time() - start) * 1000)
        return {"ok": True, "latency_ms": latency_ms}
    except Exception as e:
        return {"ok": False, "latency_ms": round((_t.time() - start) * 1000), "error": str(e)}

# --- LLM Config Update Endpoint ---
@app.put("/config/llm")
def update_llm_config(update: dict = Body(...)):
    """Save LLM provider config to config.json."""
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        provider = update.get("provider", "lm_studio")
        cfg["llm"] = {"mode": provider}
        if provider == "lm_studio":
            base = update.get("base_url", "http://localhost:1234").rstrip("/")
            cfg["lm_studio"] = {"url": f"{base}/v1/completions", "base_url": base, "model": update.get("model", "local-model")}
        elif provider == "openai":
            cfg.setdefault("api_keys", {})["openai"] = update.get("api_key", "")
            cfg["openai"] = {"model": update.get("model", "gpt-4o")}
        elif provider == "gemini":
            cfg.setdefault("api_keys", {})["gemini"] = update.get("api_key", "")
            cfg["gemini"] = {"model": update.get("model", "gemini-2.0-flash")}
        elif provider == "anthropic":
            cfg.setdefault("api_keys", {})["anthropic"] = update.get("api_key", "")
            cfg["anthropic"] = {"model": update.get("model", "claude-3-5-sonnet-20241022")}
        elif provider == "ollama":
            cfg["ollama"] = {"url": update.get("url", "http://localhost:11434"), "model": update.get("model", "llama3")}
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        try:
            config_mgr.reload()
        except Exception:
            pass
        return {"status": "updated", "provider": provider}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update config: {e}")


# --- SET-8: RAG Config Endpoints ---
@app.put("/config/rag")
def update_rag_config(update: dict = Body(...)):
    """Save RAG/vector-store global defaults to config.json."""
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        cfg["rag"] = {
            "provider": update.get("provider", "ltm"),
            "collection": update.get("collection", "memory"),
            "persist_dir": update.get("persist_dir", "./chroma_db"),
            "top_k": int(update.get("top_k", 5)),
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        return {"status": "updated", "rag": cfg["rag"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update RAG config: {e}")

@app.post("/config/rag/test")
def test_rag_connection(body: dict = Body(...)):
    """Test RAG provider connectivity."""
    provider = body.get("provider", "ltm")
    if provider == "ltm":
        import sqlite3 as _sq
        try:
            conn = _sq.connect("ltm.db")
            conn.execute("SELECT 1")
            conn.close()
            return {"status": "ok", "message": "LTM (SQLite) accessible"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    elif provider == "chroma":
        try:
            import chromadb  # type: ignore
            persist_dir = body.get("persist_dir", "./chroma_db")
            client = chromadb.PersistentClient(path=persist_dir)
            _ = client.list_collections()
            return {"status": "ok", "message": f"ChromaDB accessible at {persist_dir}"}
        except ImportError:
            raise HTTPException(status_code=400, detail="chromadb not installed — run: pip install chromadb")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    elif provider == "local":
        import os as _os
        persist_dir = body.get("persist_dir", "./docs")
        if _os.path.isdir(persist_dir):
            count = len([f for f in _os.listdir(persist_dir) if f.endswith(('.txt', '.md'))])
            return {"status": "ok", "message": f"Found {count} .txt/.md files in {persist_dir}"}
        return {"status": "ok", "message": f"Directory {persist_dir} will be created on first use"}
    else:
        return {"status": "ok", "message": f"Provider '{provider}' — connection check not implemented yet"}

# --- SET-9: Observability Config Endpoint ---
@app.put("/config/observability")
def update_observability_config(update: dict = Body(...)):
    """Save global observability settings to config.json."""
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        obs = {
            "trace_nodes": bool(update.get("trace_nodes", True)),
            "log_state_transitions": bool(update.get("log_state_transitions", True)),
            "capture_agent_outputs": bool(update.get("capture_agent_outputs", True)),
        }
        if update.get("langsmith_api_key"):
            obs["langsmith_api_key"] = update["langsmith_api_key"]
            obs["langsmith_project"] = update.get("langsmith_project", "default")
        if update.get("otel_endpoint"):
            obs["otel_endpoint"] = update["otel_endpoint"]
        cfg["observability"] = obs
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        return {"status": "updated", "observability": obs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update observability config: {e}")

# --- Code Generation ---
@app.post('/generate_code')
def generate_code_endpoint(req: dict = Body(...)):
    from code_generator import CodeGenerator
    gen = CodeGenerator()
    config = req.get('config_json', {})
    try:
        script = gen.generate_workflow_script(config)
        requirements = gen.generate_requirements(config)
        env_template = gen.generate_env_template(config)
        return {'script': script, 'requirements': requirements, 'env_template': env_template}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# --- Main ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
