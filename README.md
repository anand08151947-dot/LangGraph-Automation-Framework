# LangGraph-Automation-Framework

## Vision
Transform Agentic AI development from manual coding into orchestration. Developers become architects, defining workflows and agent logic in config files, not code.

## Functional Flow
1. **Input Layer:** User provides a goal in plain English or JSON.
2. **Translation Layer:** LLM interprets intent and generates config/schema.
3. **Assembly Layer:** Utility reads config, spins up MCP clients, and builds LangGraph StateGraph dynamically.
4. **Execution Layer:** Agents run tasks, use tools, and return results.

## Overview
LangGraph-Automation-Framework is a configuration-driven, agentic AI orchestration platform. It enables rapid assembly and execution of complex workflows using LLMs, tools, and memory, all defined via JSON config—no manual code wiring required. The backend is Python (LangGraph, FastAPI, MCP), and the frontend is React+Vite+TypeScript.

## Features
- **Config-Driven Workflows:** Build agent graphs, tools, and routing via JSON config files.
- **LLM-Powered Translation:** Convert English instructions to workflow JSON using OpenAI/Gemini.
- **Dynamic Tool Binding:** Auto-discover and bind MCP tools to agents.
- **Memory Management:** STM (in-memory) and LTM (SQLite/file) for agent state/history.
- **Observability:** Centralized logging, tracing, and metrics with pluggable backends.
- **Versioned Prompt Templates:** Store and reference prompt templates for agents/workflows.
- **Artifact Bundling:** Export run artifacts (config, logs, memory, results) for analysis.
- **Zero/Low-Code:** Modify workflows by editing config, not code.

## Key Benefits
- **Zero/Low-Code:** Create and modify workflows by editing config or using English instructions.
- **Hot-Swapping:** Change agent prompts, tools, or flow instantly—no redeploys.
- **Version Control:** Workflows are versioned as JSON files in Git.

## MCP Integration
MCP (Model Context Protocol) enables plug-and-play tool binding. Agents connect to databases, APIs, or filesystems by updating config, not code. Tools are auto-discovered and exposed via REST/SSE/stdio. This allows decoupled infrastructure and language-agnostic tools.

## Memory & Observability
- **STM (Short Term Memory):** In-memory/session state for ongoing workflows.
- **LTM (Long Term Memory):** Persistent history (SQLite/file) for resumption, analytics, and debugging.
- **Observability:** Centralized logging, tracing, metrics, and event hooks. Pluggable backends (logging, OpenTelemetry, Prometheus).

## Frontend Plan
- React+Vite UI for workflow building, monitoring, and artifact export.
- Key screens: Dashboard, Templates Library, Workflow Builder, Customization/Translation, Orchestration Monitor, Artifact Export, Settings, Help/Docs.
- Real-time status, visual workflow graphs, and seamless backend integration.

## Architecture
```
User/Frontend/API
  |
  v
api_backend.py (FastAPI endpoints)
  |
  |---> config_manager.py (config loading/validation)
  |---> template_manager.py (template management)
  |---> llm_translator.py (LLM-driven config generation)
  |
  v
orchestrator.py (workflow runner)
  |
  |---> graph_factory.py (builds agent graph)
  |---> mcp_autobinder.py (tool discovery/binding)
  |---> memory_manager.py (STM/LTM)
  |---> observability_manager.py (logging/metrics)
  |
  v
LangGraph execution (dynamic agent graph)
  |
  v
Artifacts/results written to backend/artifacts/
```

## Directory Structure
```
backend/
  api_backend.py         # FastAPI endpoints
  orchestrator.py        # Workflow runner
  graph_factory.py       # Dynamic graph builder
  memory_manager.py      # STM/LTM state
  mcp_autobinder.py      # MCP tool binding
  tool_registry.py       # Tool registry
  observability_manager.py # Logging/tracing
  config_manager.py      # Config loader/validator
  template_manager.py    # Prompt template management
  prompt_templates/      # Versioned prompt templates
  artifacts/             # Run artifacts (config, logs, memory, results)
frontend/
  ...                    # React+Vite UI
tests/
  ...                    # Pytest-based tests
```

## Quickstart
### Backend
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Start FastAPI server:
   ```bash
   uvicorn backend.api_backend:app --reload
   ```

### Frontend
1. Install dependencies:
   ```bash
   cd frontend
   npm install
   ```
2. Start Vite dev server:
   ```bash
   npm run dev
   ```

### Run a Workflow
1. Edit or create a workflow config in `backend/` (e.g., example_langgraph_workflow.json).
2. Use the UI or API to build, run, and monitor workflows.
3. Artifacts are saved in `backend/artifacts/`.

## Configuration-Driven Development
- Define agents, tools, and routing in JSON config files.
- Use `/english_to_json` or `/customize_json_llm` API endpoints for LLM-driven config generation.
- Hot-swap agent logic by editing config, not code.

## Testing
- Run backend tests:
  ```bash
  pytest tests/
  ```

## Contribution
Pull requests and issues are welcome! Please see the [CONTRIBUTING guidelines](CONTRIBUTING.md) if available.

## License
This project is licensed under the MIT License.

## Contact
For questions or support, open an issue or contact the maintainer.

---
For detailed module breakdown and developer workflows, see ENHANCEMENT_PLAN.md and COMMANDS.md.


git ls-files --cached | Where-Object { $_ -match "__pycache__|\.pyc$|\.pyo$|/artifacts/|node_modules|/dist/|dist-ssr|\.db$|\.zip$|\.log$|\.env|\.coverage|htmlcov" } 2>&1

git ls-files --cached 2>&1

npx vite build 2>&1

curl -s http://localhost:1234/v1/models 2>&1

$body = '{"model":"llama-3.2-3b-instruct","prompt":"Say hello in one word.","temperature":0.2,"stream":false,"max_tokens":20}'; curl -s -X POST http://localhost:1234/v1/completions -H "Content-Type: application/json" -d $body 2>&1

Start-Process -NoNewWindow -FilePath "python" -ArgumentList "-m uvicorn backend.api_backend:app --host 0.0.0.0 --port 8000" -PassThru | Select-Object Id

python -m uvicorn backend.api_backend:app --host 0.0.0.0 --port 8000

# Test 1: Health check
Write-Host "=== Health ===" 
curl -s http://localhost:8000/health

# Test 2: English to JSON via LM Studio
Write-Host "`n=== English to JSON (LM Studio) ==="
$body = '{"instructions":"Create a two-agent workflow: a researcher agent that searches the web and a writer agent that summarizes the findings."}'
curl -s -X POST http://localhost:8000/english_to_json -H "Content-Type: application/json" -d $body 2>&1 | Select-Object -First 40


Get-Content "C:\Anand\AI-WorkSpace\LangGraph-Automation-Framework\backend\api_backend.py" | Select-String -Pattern "import sys|_run_workflow_async|orchestrate_async|workflow_status\[run_id\]|if __name__" | Select-Object LineNumber, Line | Format-Table -AutoSize