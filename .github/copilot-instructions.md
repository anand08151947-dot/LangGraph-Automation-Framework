---
## Fine-Grained Module & Workflow Breakdown

### api_backend.py (API Layer)
- Exposes REST endpoints for config, template, translation, orchestration, status, and artifact download.
- Delegates to config_manager, template_manager, llm_translator, and orchestrator for business logic.
- Handles request validation, error formatting, and response shaping.

### config_manager.py
- Loads and validates config.json (and environment overrides).
- Provides config access to all backend modules.
- Enforces schema via Pydantic.

### template_manager.py / template_selector.py
- Loads, validates, and versions prompt templates from prompt_templates/.
- Lists, retrieves, and saves templates for use in workflows.
- Enables search/filter by use case, domain, or keyword.

### llm_translator.py / english_to_json.py
- Converts English instructions to workflow JSON using LLMs (OpenAI/Gemini/manual).
- Validates generated JSON against schema.
- Handles error reporting and manual/automated LLM modes.

### orchestrator.py
- Central workflow runner: accepts config JSON and session info.
- Initializes MCP tool binding, graph factory, memory, and observability.
- Runs workflow, saving STM/LTM after each step, logging events, and handling retries/errors.
- Returns results, logs, and status for API or artifact export.

### graph_factory.py / graph_factory_supervisor.py
- Dynamically builds LangGraph StateGraph from config JSON.
- Creates agent nodes, sets up routing/edges, and supervisor/conditional logic.
- Integrates MCP tool bindings as needed.

### mcp_autobinder.py
- Discovers MCP servers/tools from config.
- Binds discovered tools to agents in the workflow graph.
- Supports stdio/SSE/REST MCP server types.

### tool_registry.py
- Maintains registry of available tools, with metadata, health, and versioning.
- Supports dynamic registration/unregistration and status updates.

### memory_manager.py
- Implements STM (in-memory) and LTM (SQLite/file) for agent state/history.
- Saves STM after each step, appends to LTM for full history.
- Supports resumption, querying, and debugging via API.

### observability_manager.py
- Centralized logging, tracing, metrics, and event hooks.
- Pluggable backends: logging, OpenTelemetry, Prometheus, etc.
- Used throughout for step/event logging and monitoring.

### produce_run_bundle.py / produce_run_bundle_v2.py
- Bundles all run artifacts (config, STM, LTM, logs, results) for export.
- Used by API for artifact download endpoints.

### prompt_templates/ and schemas/
- Store versioned prompt templates and JSON schemas for config/template validation.

### artifacts/
- Stores per-run artifacts: config, STM, LTM, logs, results, and bundles.

### Example Workflows & Scripts
- example_langgraph_workflow.json, complex_langgraph_workflows.json, customer_onboarding.json: Example workflow configs.
- post_run.py, run_orchestrator.py, run_data_pipeline_test.py, smoke.py: Scripts for running, testing, or demoing workflows.

---
### Example Data Flow for a Workflow Run

1. User sends English instructions or config JSON to API.
2. API uses llm_translator.py/english_to_json.py if translation is needed.
3. API loads config/templates via config_manager/template_manager.
4. orchestrator.py initializes MCP tool binding, graph factory, memory, and observability.
5. graph_factory.py builds the agent graph from config, binding tools as needed.
6. Workflow executes step-by-step:
  - Each agent node updates state, may invoke tools (via MCP or local).
  - memory_manager.py saves STM/LTM after each step.
  - observability_manager.py logs/traces each step.
  - Errors/retries/conditional routing handled as per config.
7. Results, logs, STM/LTM, and config are saved to artifacts/.
8. produce_run_bundle.py can bundle all run artifacts for export.
9. API endpoints allow querying status, downloading bundles, or inspecting memory.
# Copilot Instructions for LangGraph-Automation-Framework

## Project Overview
This repository implements a configuration-driven, LLM-powered agentic AI framework. The core idea is to treat workflow orchestration as a config/JSON-driven process, abstracting away manual code wiring. The backend is Python (LangGraph, FastAPI, MCP), and the frontend is React+Vite+TypeScript.

## Architecture & Key Components
- **backend/**: Core logic for config-driven agent workflows, memory, observability, and tool registry.
  - `graph_factory.py`, `graph_factory_supervisor.py`: Build LangGraph StateGraphs dynamically from JSON config.
  - `memory_manager.py`: Implements STM/LTM for agent state/history.
  - `observability_manager.py`: Pluggable logging, tracing, metrics.
  - `mcp_autobinder.py`, `tool_registry.py`: Auto-discovers and binds MCP tools to agents.
  - `api_backend.py`: FastAPI endpoints for orchestration, template management, translation, and monitoring.
  - `config.json`, `*.json`: Define agents, tools, routing, and MCP servers.
- **frontend/**: React+Vite app for workflow building, monitoring, and artifact export. Uses `api.ts` for backend integration.
- **prompt_templates/**: Versioned prompt templates for agents and workflows.
- **tests/**: Pytest-based tests for backend modules and API.

## Developer Workflows
- **Backend**: Run with FastAPI (see `api_backend.py`).
  - Typical: `uvicorn backend.api_backend:app --reload`
  - Tests: `pytest tests/`
- **Frontend**: Run with Vite.
  - `cd frontend && npm install && npm run dev`
- **Config-Driven Development**:
  - Define/modify workflows in JSON (see `backend/*.json`).
  - Use `/english_to_json` or `/customize_json_llm` endpoints for LLM-driven config generation.
  - Hot-swap agent logic by editing config, not code.
- **Memory & Observability**:
  - STM/LTM logic in `memory_manager.py` (in-memory, SQLite, or file-based).
  - Observability via `observability_manager.py` (logging, OpenTelemetry, Prometheus).
- **MCP Integration**:
  - Define MCP servers in config; tools are auto-discovered and bound to agents.
  - No manual tool wiring—update config to add/remove tools.

## Project-Specific Patterns & Conventions
- **Zero/Low-Code**: All agent, tool, and workflow logic is config/JSON-driven. Python code is only for custom tools or framework logic.
- **Dynamic Graph Assembly**: Use `GraphFactory` to build graphs from config at runtime.
- **LLM-Driven Translation**: Use LLMs to convert English instructions to JSON config (see `english_to_json.py`).
- **Versioned Templates**: Store prompt templates in `prompt_templates/` and reference by name in config.
- **Memory/Observability**: Always use the provided managers for state and logging—do not implement ad-hoc solutions.
- **Testing**: Use pytest; see `tests/` for examples.

## Integration Points
- **API**: All frontend/backend integration via REST endpoints in `api_backend.py`.
- **MCP**: Tools are exposed via MCP servers (stdio/SSE/REST); config specifies bindings.
- **Artifacts**: Workflow runs produce artifacts in `backend/artifacts/`.

## Examples
- See `backend/example_langgraph_workflow.json` for a sample workflow config.
- See `frontend/api.ts` for API usage patterns.
- See `backend/memory_manager.py` and `backend/observability_manager.py` for memory/logging patterns.

## Quickstart
1. Edit or create a workflow config in `backend/`.
2. Start backend (`uvicorn backend.api_backend:app --reload`).
3. Start frontend (`cd frontend && npm run dev`).
4. Use the UI or API to build, run, and monitor workflows.

---
If any section is unclear or missing, please specify what needs improvement or what additional context is required.


---
## Backend Inventory & Mental Model

The `backend/` directory is organized for modular, config-driven agentic AI orchestration. Here’s how the main components are structured and interdependent:

### 1. Core Orchestration & Workflow
- **graph_factory.py / graph_factory_supervisor.py**: Build LangGraph StateGraphs dynamically from JSON config. Central to runtime graph assembly.
- **orchestrator.py**: End-to-end workflow runner. Ties together config, graph factory, memory, observability, and MCP tool binding.
- **api_backend.py**: FastAPI app exposing endpoints for orchestration, config, template, and monitoring.

### 2. Configuration & Templates
- **config.json**: Central config for memory, observability, tool registry, API keys, etc.
- **config_manager.py**: Loads, validates, and manages config (with environment overrides).
- **prompt_templates/**: Directory for versioned prompt templates (referenced by config).
- **template_manager.py**: Loads, validates, and manages templates.
- **template_selector.py**: Finds and lists templates by use case or keyword.

### 3. Agent State, Memory, and Observability
- **memory_manager.py**: Implements STM (in-memory) and LTM (SQLite/file) for agent state/history. Used by orchestrator and graph nodes.
- **observability_manager.py**: Pluggable logging, tracing, metrics, and event hooks. Used throughout for logging and monitoring.

### 4. Tooling & Integration
- **mcp_autobinder.py**: Discovers MCP servers/tools and auto-binds them to agents as defined in config.
- **tool_registry.py**: Dynamic registry for tools, with metadata, health, and versioning.

### 5. LLM-Driven Config & Translation
- **english_to_json.py / english_to_json_gemini.py**: CLI/utility for converting English instructions to JSON config using LLMs.
- **llm_translator.py**: Core logic for LLM-powered translation and customization (OpenAI/Gemini/manual).

### 6. Artifacts & Results
- **artifacts/**: Stores run artifacts (config, status, STM/LTM, results, bundles).
- **produce_run_bundle.py / produce_run_bundle_v2.py**: Bundle run artifacts for export.

### 7. Testing & Examples
- **tests/**: Pytest-based tests for all major modules and API.
- **example_langgraph_workflow.json, complex_langgraph_workflows.json, customer_onboarding.json**: Example workflow configs.

### 8. Utilities & Misc
- **post_run.py, run_orchestrator.py, run_data_pipeline_test.py, smoke.py**: Scripts for running, testing, or demoing workflows.

### 9. Schemas & Validation
- **langgraph_workflow.schema.json, schemas/**: JSON schemas for config and status validation.

**Interdependencies:**


---
## Backend Component Flow Chart (Textual)

```text
User/Frontend/API
  |
  v
api_backend.py (FastAPI endpoints)
  |
  |---> config_manager.py (loads/validates config)
  |---> template_manager.py / template_selector.py (load/select templates)
  |---> llm_translator.py / english_to_json.py (LLM-driven config generation)
  |
  v
orchestrator.py (main workflow runner)
  |
  |---> graph_factory.py / graph_factory_supervisor.py (builds LangGraph StateGraph from config)
  |---> mcp_autobinder.py (auto-discovers and binds MCP tools)
  |---> tool_registry.py (tracks tool metadata/health)
  |---> memory_manager.py (STM/LTM for agent state/history)
  |---> observability_manager.py (logging, tracing, metrics)
  |
  v
LangGraph execution (dynamic agent graph runs)
  |
  v
Artifacts/results written to backend/artifacts/
```

---
### Detailed Backend Flow (Expanded)

```text
1. User/Frontend/API
  - Sends English instructions or JSON config to FastAPI endpoints.

2. api_backend.py (API Layer)
  - Receives requests, routes to appropriate logic:
    - Loads config via config_manager.py
    - Loads/validates templates via template_manager.py/template_selector.py
    - If English, uses llm_translator.py or english_to_json.py to generate config JSON
    - Returns summaries, runs, or status as needed

3. orchestrator.py (Orchestration Layer)
  - Accepts config JSON and session info
  - Initializes:
    - mcp_autobinder.py (for MCP tool discovery/binding)
    - graph_factory.py (to build LangGraph StateGraph from config)
    - memory_manager.py (for STM/LTM state)
    - observability_manager.py (for logging/tracing/metrics)
  - Assembles workflow graph:
    - Each agent node is created dynamically from config
    - MCP tools are auto-bound to agents as specified
    - Routing/edges are set up per config (including supervisor/conditional logic)

4. Workflow Execution (LangGraph)
  - Runs agent graph step-by-step:
    - Each node/agent updates state, may invoke tools (via MCP or local)
    - memory_manager.py saves STM after each step, appends to LTM for history
    - observability_manager.py logs events, traces, and metrics for each step
    - Errors, retries, and conditional routing handled as per config

5. Artifacts & Results
  - After run, results, logs, STM/LTM, and config are saved to backend/artifacts/
  - produce_run_bundle.py/v2 can bundle all run artifacts for export
  - API endpoints allow querying status, downloading bundles, or inspecting memory

6. Tooling & Extensibility
  - mcp_autobinder.py discovers available MCP servers/tools from config
  - tool_registry.py tracks tool metadata, health, and versioning
  - New tools or agents can be added by updating config JSON, not code

7. Templates & Schema
  - template_manager.py loads, validates, and versions prompt templates
  - template_selector.py enables search/filter by use case/domain
  - langgraph_workflow.schema.json and schemas/ enforce config/template structure

8. Testing & Utilities
  - tests/ contains pytest-based tests for all modules and API
  - Utility scripts (run_orchestrator.py, post_run.py, etc.) support manual or automated runs
```

**Flow Summary:**
- User or frontend sends a request (English or JSON) to the API.
- API loads config/templates, may invoke LLM for config generation.
- Orchestrator assembles the workflow graph, binds tools, sets up memory/observability.
- Workflow executes as a dynamic agent graph (LangGraph), using tools and memory as needed.
- Results, logs, and artifacts are saved for monitoring and export.
