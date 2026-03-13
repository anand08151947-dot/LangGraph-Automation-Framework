# Phoenice Constellation

> ✦ The architect's workbench for the Agentic Era

**Phoenice Constellation** turns the "manual wiring" of AI into celestial orchestration. By defining agents, MCP tools, and RAG pipelines in a unified framework, developers can move from raw code to shippable Python bundles in minutes, not days.

---

## Vision

Phoenice Constellation is built for the Agentic Era. Developers become architects — defining agents, MCP tools, RAG pipelines, routing, memory, and guardrails in a unified JSON config. No graph wiring. No boilerplate. Just orchestration.

---

## How It Works

```
                 ┌─────────────────────────────────────────┐
  English text   │  Phoenice Agentic Workbench (UI)        │
  or JSON ──────▶│  Templates · Builder · Monitor · Export │
                 └────────────────┬────────────────────────┘
                                  │ REST API
                 ┌────────────────▼────────────────────────┐
                 │  FastAPI Backend                        │
                 │  ├─ LLM Translation (LM Studio / OAI)  │
                 │  ├─ Orchestrator  (LangGraph runner)    │
                 │  ├─ Graph Factory (dynamic StateGraph)  │
                 │  ├─ Memory Manager (STM / LTM)          │
                 │  ├─ Guardrail Engine (input + output)   │
                 │  └─ Code Generator  ──▶  agent.py 🍎    │
                 └─────────────────────────────────────────┘
```

The **generated bundle** ("the apple") is a standalone `agent.py` + supporting files that a developer can deploy anywhere — no workbench dependency required.

---

## Features

| Category | What's included |
|---|---|
| **Config-Driven Workflows** | Build agent graphs, routing, and tools entirely from JSON — no code wiring |
| **Visual Workflow Builder** | Drag-and-drop node editor with live graph preview and full-detail expand view |
| **LLM Translation** | Convert English instructions → workflow JSON via LM Studio, OpenAI, or Gemini |
| **Template Customize Flow** | Open any template in the Translation view; refine with LLM; apply back to Builder |
| **MCP Tool Binding** | Auto-discover and bind MCP tools (stdio / SSE / REST) to agents via config |
| **Pre-LLM Pipeline** | RAG (LTM / Chroma / Milvus / local files) + tool calls before every LLM call |
| **Post-LLM Checks** | Output validation (required fields, rules), output schema enforcement, output guardrails |
| **Input & Output Guardrails** | PII redaction, prompt-injection blocking, secrets detection, harmful content / hate speech filter |
| **Memory — STM** | In-process session state with LRU eviction (`max_entries`) |
| **Memory — LTM** | Persistent SQLite history with TTL pruning (`ttl_days`), queryable via RAG |
| **Observability Hooks** | Trace nodes, log state transitions, capture agent outputs — all config-driven |
| **Retry Policy** | Fixed or exponential backoff, configurable `retry_on` events |
| **Human-in-the-Loop** | Checkpoint nodes pause for approval; resumable via API |
| **Code Generation** | Produces a self-contained `agent.py` bundle from any workflow config |
| **Artifact Export** | Download ZIP with `agent.py`, `requirements.txt`, `docker-compose.yml`, `.env.template`, run logs, STM/LTM snapshots, validation report |
| **Versioned Templates** | Enterprise-grade templates with full memory/retry/observability config |

---

## Architecture

```
api_backend.py         FastAPI — all REST endpoints
  ├─ config_manager.py       Load & validate config.json
  ├─ template_manager.py     Load, version, and save prompt templates
  ├─ llm_translator.py       English → JSON via LLM
  ├─ orchestrator.py         End-to-end workflow runner
  │    ├─ graph_factory.py         Build LangGraph StateGraph dynamically
  │    ├─ mcp_autobinder.py        Auto-discover & bind MCP tools
  │    ├─ memory_manager.py        STM (in-memory) + LTM (SQLite)
  │    └─ observability_manager.py Logging, tracing, metrics
  └─ code_generator.py       Generate deployable agent.py bundle
```

---

## Directory Structure

```
backend/
  api_backend.py           FastAPI app + all REST endpoints
  orchestrator.py          Workflow runner
  graph_factory.py         Dynamic LangGraph StateGraph builder
  graph_factory_supervisor.py  Supervisor-style graph builder
  code_generator.py        Deployable agent.py bundle generator
  memory_manager.py        STM / LTM state management
  mcp_autobinder.py        MCP tool auto-discovery & binding
  tool_registry.py         Tool registry (metadata, health, versioning)
  observability_manager.py Logging, tracing, metrics, event hooks
  config_manager.py        Config loader / validator (Pydantic)
  template_manager.py      Prompt template management
  template_selector.py     Template search / filter
  llm_translator.py        LLM-powered config translation
  english_to_json.py       CLI: English → JSON (OpenAI / Gemini)
  config.json              Central backend config
  artifacts/               Per-run artifacts (auto-generated)
  prompt_templates/        Versioned enterprise prompt templates

frontend/                  React + Vite + TypeScript UI
  src/views/               Builder, Monitor, Export, Templates, Docs, Settings
  src/components/          Shared UI components

tests/                     Pytest test suite
COMMANDS.md                Developer command cheatsheet
ToDo.md                    Roadmap and task tracker
```

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | ≥ 3.11 | Tested on 3.11 / 3.12 |
| Node.js | ≥ 18 | For frontend Vite dev server |
| LM Studio | latest | Load a model, enable server on port 1234 |

---

## Quickstart

### 1 · Backend

```powershell
# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Start the backend
python -m uvicorn backend.api_backend:app --reload
# API available at http://localhost:8000
```

### 2 · Frontend

```powershell
cd frontend
npm install
npm run dev
# UI available at http://localhost:3000
```

### 3 · LM Studio

1. Download and open [LM Studio](https://lmstudio.ai).
2. Load a model (e.g. `llama-3.2-3b-instruct`).
3. Start the local server (default port **1234**).
4. In Phoenice → **Settings**, click **Test Connection** to verify.

### 4 · Build and export your first workflow

1. Go to **Templates**, pick a template, click **Use Template**.
2. Adjust nodes in the **Builder** and click **Run**.
3. After the run completes, open **Export** to download the deployable ZIP bundle.

---

## Workflow Config — Quick Reference

```json
{
  "graph_name": "MyWorkflow",
  "version": "1.0",
  "state_schema": {
    "task":   { "type": "string" },
    "result": { "type": "string" }
  },
  "nodes": [
    {
      "id": "Planner",
      "type": "agent",
      "system_prompt": "Break the task into steps.",
      "next": "Executor"
    },
    {
      "id": "Executor",
      "type": "agent",
      "system_prompt": "Execute the plan.",
      "guardrails": { "pii": { "action": "redact" }, "harmful_content": { "action": "block" } },
      "output_schema": { "format": "json", "state_key": "result" },
      "next": "END"
    }
  ],
  "edges": [{ "from": "Planner", "to": "Executor" }],
  "memory": {
    "short_term": { "type": "graph_state", "max_entries": 100 },
    "long_term":  { "type": "sqlite", "ttl_days": 30 }
  },
  "retry_policy": { "max_retries": 3, "backoff_strategy": "exponential" },
  "observability_hooks": { "trace_nodes": true, "capture_agent_outputs": true }
}
```

See [COMMANDS.md](COMMANDS.md) for all CLI commands and API smoke tests.  
See the in-app **Help & Docs** tab for the full JSON Schema reference.

---

## Generated Artifact Bundle

Every successful run produces a self-contained deployable bundle:

```
agent.py              Complete runnable agent (LangGraph + STM/LTM + guardrails)
requirements.txt      Pinned Python dependencies
docker-compose.yml    Ready-to-run Docker Compose config
.env.template         Environment variable template
run_config.json       Exact workflow config used for this run
run_status.json       Final run status and metadata
validation_report.json Code generation trust score and checks
```

Deploy with:
```bash
pip install -r requirements.txt
python agent.py
```

---

## Testing

```powershell
pytest tests/
```

---

## License

MIT License — see [LICENSE](LICENSE).

---

For the developer command cheatsheet, see [COMMANDS.md](COMMANDS.md).  
For the roadmap and outstanding tasks, see [ToDo.md](ToDo.md).
