from fastapi import FastAPI, Body, Request

# FastAPI app instance (must be defined before route decorators)
app = FastAPI()

# --- Enhanced Config-Driven Architecture Endpoints ---
@app.get("/config/summary")
def config_summary():
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
    return {"summary": summary}

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
def get_audit():
    return {"audit_log": audit_log}
# --- Config Management Endpoints ---
@app.get("/config")
def get_config():
    """Return the current effective config (after env overrides)."""
    return {"config": config_mgr.config, "env": config_mgr.env}

@app.post("/config/reload")
def reload_config():
    """Hot-reload the config from disk."""
    try:
        config_mgr.reload()
        return {"status": "reloaded", "config": config_mgr.config, "env": config_mgr.env}
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
import zipfile
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
    from orchestrator import Orchestrator
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

# --- Config Manager Instance ---
# Use path relative to this module so running from other cwd works
config_mgr = ConfigManager(os.path.join(os.path.dirname(__file__), "config.json"))
# --- Access Control Instance ---
access_control = AccessControl(
    api_keys=list(config_mgr.get("api_keys", {}).values()),
    jwt_secret=config_mgr.get("api_keys", {}).get("jwt_secret", "secret"),
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
llm_translator = LLMTranslator(mode=llm_mode)

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

@app.get("/templates", response_model=List[TemplateInfo])
def get_templates():
    templates = template_manager.list_templates()
    return [TemplateInfo(name=f"{t.name}", description=t.description, example=t.data) for t in templates]

@app.get("/template/{name}")
def get_template(name: str, version: Optional[str] = None):
    t = template_manager.get_template(name, version)
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    return TemplateInfo(name=t.name, description=t.description, example=t.data)

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

@app.post("/save_template")
def save_template(info: TemplateInfo, version: Optional[str] = None):
    try:
        fname = template_manager.save_template(info.name, info.example or {}, version=version, description=info.description)
        return {"status": "saved", "filename": fname}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))



def _run_workflow_async(run_id, config_json):
    # Preserve any existing metadata (e.g., stored config/template) and update runtime fields
    workflow_status.setdefault(run_id, {})
    workflow_status[run_id].update({"status": "running", "result": None})
    logger.info(f"Workflow {run_id} started.")
    # Guard against missing orchestrator (e.g., missing langgraph dependency)
    if orchestrator is None:
        err = globals().get("_orchestrator_import_error", "Orchestrator not available")
        workflow_status[run_id].update({"status": "error", "result": f"Orchestrator not available: {err}"})
        logger.error(f"Workflow {run_id} failed: Orchestrator not available: {err}")
        return
    try:
        # Pass run_id as session_id so STM/LTM are tracked for this run
        result = orchestrator.run_workflow(config_json, session_id=run_id)
        workflow_status[run_id].update({"status": "completed", "result": result})
        logger.info(f"Workflow {run_id} completed.")
    except Exception as e:
        workflow_status[run_id].update({"status": "error", "result": str(e)})
        logger.error(f"Workflow {run_id} failed: {e}")

@app.post("/orchestrate_async")
def orchestrate_async(req: OrchestrationRequest, template_name: Optional[str] = None):
    run_id = str(uuid.uuid4())
    logger.info(f"Received async orchestration request: run_id={run_id}, template={template_name}")
    # Persist initial run metadata including the submitted config (store a deep copy to avoid later mutation)
    import copy
    workflow_status[run_id] = {"status": "started", "result": None, "config": copy.deepcopy(req.config_json), "template": template_name}
    thread = threading.Thread(target=_run_workflow_async, args=(run_id, req.config_json))
    thread.start()

    # Conditional logging of the run config for traceability (controlled by env var)
    try:
        import os, json, copy as _copy
        if os.getenv("PRINT_RUN_CONFIG", "false").lower() == "true":
            # Create a safe copy and redact common secrets
            cfg_copy = _copy.deepcopy(req.config_json)
            if isinstance(cfg_copy, dict) and "api_keys" in cfg_copy:
                cfg_copy["api_keys"] = {k: "REDACTED" for k in cfg_copy.get("api_keys", {})}
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

def _to_serializable(obj):
    # Reusable converter for API responses (matches ws serializer)
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

    def _to_serializable(obj):
        # Recursively convert objects to JSON-serializable form
        try:
            # Primitives and simple containers
            if obj is None or isinstance(obj, (str, int, float, bool)):
                return obj
            if isinstance(obj, dict):
                return {k: _to_serializable(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [_to_serializable(v) for v in obj]
            # Fallback: if object has __dict__, convert it
            if hasattr(obj, "__dict__"):
                return {k: _to_serializable(v) for k, v in obj.__dict__.items()}
            # Last resort: string representation
            return str(obj)
        except Exception:
            return str(obj)

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

# --- Main ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
