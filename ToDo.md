# Agentic Workbench — Full Enhancement Roadmap

> **Tracking file** — check off items as they are completed.  
> Session plan mirror: `~/.copilot/session-state/.../plan.md`

---

## Problem Statement
The Graph Factory can define and run workflows through the Builder UI, but several layers need
to be upgraded so the generated artifact is a **fully deployable, self-contained agentic bundle**
that a developer can trust, ship, and run without manual wiring. This plan covers eight
interconnected areas in priority order.

---

## Priority Execution Order

| Priority | ID | Area | Status |
|----------|----|------|--------|
| ✅ P0 | MM-1 | `query_ltm()` missing from MemoryManager | **DONE** |
| ✅ P0 | TRANS-1 | Schema out of date | **DONE** |
| ✅ P0 | TRANS-3 | LM Studio chat completions format | **DONE** |
| ✅ P1 | ORC-1,2,3 | Orchestrator config-driven init + session_id + timeout | **DONE** |
| ✅ P1 | BNDL-1,2,3 | Code generator + requirements + .env | **DONE** |
| ✅ P1 | SET-1,2,3 | Multi-provider selector + model fetch + connection test | **DONE** |
| ✅ P2 | RAG-1..6 | RAG provider integrations (LTM, Chroma, LocalFile, Registry) | **DONE** |
| ✅ P2 | ORC-7,8 | Human-in-loop checkpoint + resume | **DONE** |
| ✅ P2 | HELP-1..6 | Help view tabbed rewrite | **DONE** |
| ✅ P3 | BNDL-4 | docker-compose.yml + Dockerfile generator | **DONE** |
| ✅ NEW | BNDL-6,7 | `/generate_code` endpoint + Export view rewrite | **DONE** |
| ✅ NEW | INF-4,5,6,7 | `/runs`, `/artifacts` endpoints + Monitor + Export views | **DONE** |
| ✅ NEW | Validation | 13-check artifact validator + validation_report.json | **DONE** |
| ✅ NEW | MM-8 | `get_stats()` + `reset_ltm()` on MemoryManager | **DONE** |
| ✅ NEW | TRANS-2 | `_build_prompt()` rewritten with enterprise few-shot | **DONE** |
| 🟢 P3 | TRANS-5,6,7 | Multi-turn refine (backend method + frontend Refine tab) | pending |
| 🟢 P3 | INF-8 | End-to-end smoke test `tests/test_e2e_minimal.py` | pending |
| 🟢 P3 | INF-10 | `Makefile` — `make dev`, `make test`, `make bundle` | pending |
| ✅ P3 | MM-2,3 | STM max-entries eviction + LTM TTL pruning | **DONE** |
| ✅ P3 | SET-8,9 | RAG/Vector Store config card + Observability card in Settings | **DONE** |
| ✅ P3 | ORC-4,5 | Backoff retry strategy + observability_hooks wiring | **DONE** |

---

## AREA 1 — Memory Manager (STM / LTM / RAG)

### Current state
- STM: in-memory dict only (redis stub logs a warning)
- LTM: SQLite append-only; no TTL, no index, no vector search
- RAG: `_execute_rag_search()` in graph_factory stubs external providers
- No `query_ltm()` method — RAG in graph_factory calls it but it doesn't exist
- No STM max-entries enforcement

### TODOs
- [x] **MM-1** 🔴 Add `query_ltm(session_id, keyword, limit)` method to `MemoryManager` ✅
- [x] **MM-2** Enforce `max_stm_entries` — evict oldest entries when STM dict exceeds limit ✅
- [x] **MM-3** Add LTM TTL pruning — delete rows older than `ltm_ttl_days` on `append_ltm()` ✅
- [ ] **MM-4** Add `query_ltm` full-text keyword search using SQLite `LIKE`
- [ ] **MM-5** Add `reset_ltm(session_id)` method for clean reruns
- [ ] **MM-6** Add `ltm_index_fields` support — store structured JSON fields and allow
  query by field key (e.g. `query_ltm(session_id, field="task", value="research")`)
- [ ] **MM-7** Redis STM: implement basic Redis adapter using `redis-py` behind a feature
  flag — only instantiated when `stm_backend='redis'` and `redis` is importable
- [x] **MM-8** Expose STM/LTM stats via `get_stats(session_id)` + `reset_ltm()` ✅
- [ ] **MM-9** Wire `memory_manager` into `Orchestrator` with config-driven init

---

## AREA 2 — RAG Provider Integration

### Current state
- `_execute_rag_search()` has stub hooks for Chroma/Milvus/Pinecone/Weaviate
- Only LTM keyword search works (but `query_ltm` is missing — see MM-1)
- No embedding or semantic similarity — just substring match

### TODOs
- [x] **RAG-1** Add `RagProvider` base class in `backend/rag_provider.py` ✅
- [x] **RAG-2** Implement `LtmRagProvider` ✅
- [x] **RAG-3** Implement `ChromaRagProvider` ✅
- [x] **RAG-4** Implement `LocalFileRagProvider` ✅
- [x] **RAG-5** Add `RagProviderRegistry` factory ✅
- [x] **RAG-6** Update `graph_factory._execute_rag_search()` to use `RagProviderRegistry` ✅
- [ ] **RAG-7** Add `rag` section to `backend/config.json`; read in `config_manager.py`
- [ ] **RAG-8** Frontend Settings: Add "RAG / Vector Store" card — provider selector,
  collection name, embedding model, test-connection button

---

## AREA 3 — Orchestrator Enhancements

### Current state
- Hardcodes `MCPAutoBinder()`, `GraphFactory()`, `MemoryManager()`, `ObservabilityManager()`
- Does not read `runtime`, `memory`, `observability_hooks` from workflow config
- `build_from_config()` called without `session_id` or `bound_tools`
- No timeout enforcement, no backoff retry, no parallel execution support
- No per-step timing in artifacts

### TODOs
- [x] **ORC-1** 🟠 Config-driven init: reads `memory`/`runtime`/`observability` from workflow config ✅
- [x] **ORC-2** 🟠 Passes `session_id` to `factory.build_from_config()` ✅
- [x] **ORC-3** 🟠 Enforces `runtime.timeout_seconds` via threading.Timer ✅
- [x] **ORC-4** Implement `retry_policy.backoff_strategy` — fixed/exponential sleep between retries ✅
- [x] **ORC-5** Wire `observability_hooks` from workflow config to `ObservabilityManager` ✅
- [x] **ORC-7** 🟡 Human-in-the-loop checkpoint — `HumanApprovalRequired` exception, pause + persist ✅
- [x] **ORC-8** 🟡 Resume from checkpoint — `resume_run(run_id, approval_input)` ✅
- [ ] **ORC-9** Parallel group execution — `asyncio.gather()` for `parallel_execution` groups
- [ ] **ORC-10** `dry_run` mode — build and validate graph without executing

---

## AREA 4 — Run Bundle / Artifact Generation

### Current state
- Bundle is a docs-only ZIP (status JSON + config JSON + README)
- No generated runnable Python code, no requirements, no env template, no deployment guide
- Not deployable without manual work

### TODOs
- [x] **BNDL-1** 🟠 `CodeGenerator` class — emits full standalone agent.py ✅
- [x] **BNDL-2** 🟠 `requirements.txt` generator — config-driven, only needed packages ✅
- [x] **BNDL-3** 🟠 `.env.example` generator — lists required env vars ✅
- [x] **BNDL-4** 🟢 `docker-compose.yml` + `Dockerfile` generator ✅
- [ ] **BNDL-5** Add execution trace to bundle — per-node timing, input/output snapshots,
  guardrail statuses from last run
- [x] **BNDL-6** `/generate_code` API endpoint ✅
- [x] **BNDL-7** Export view — tabbed preview (agent.py, requirements, .env, docker-compose, Dockerfile, README, Validation) + ZIP download ✅
- [ ] **BNDL-8** Bundle versioning — name bundles `{graph_name}_v{version}_{run_id}.zip`,
  keep last N per workflow (default 5)
- [x] **BNDL-NEW** 13-check artifact validator → `validation_report.json` with trust score ✅

---

## AREA 5 — LLM Translator Enhancements

### Current state
- Supports OpenAI `/v1/completions`, LM Studio, and manual mode
- Schema used for prompting is old flat format — missing all new enterprise fields
- No streaming, no multi-turn refinement
- `_call_lm_studio()` uses deprecated completions endpoint

### TODOs
- [x] **TRANS-1** 🔴 `langgraph_workflow.schema.json` updated — full enterprise format ✅
- [x] **TRANS-2** `_build_prompt()` rewritten with enterprise few-shot examples ✅
- [x] **TRANS-3** 🔴 `/v1/chat/completions` support — chat first, fallback to completions ✅
- [ ] **TRANS-4** Add streaming response support — SSE from LM Studio → API → UI
- [ ] **TRANS-5** 🟢 Multi-turn refinement: `refine_workflow(current_json, feedback)` method
- [ ] **TRANS-6** Post-translation normalization: run output through `_normalize_nodes()`
- [ ] **TRANS-7** 🟢 Frontend Translation view: "Refine" mode — current JSON + feedback textarea
- [ ] **TRANS-8** Add Gemini 2.0 Flash / Anthropic Claude as provider options

---

## AREA 6 — Settings View Enhancements

### Current state
- Only LM Studio URL/model + placeholder API Keys card
- No model selector, no connection test, no other providers
- No RAG config, no observability config, no environment selector

### TODOs
- [x] **SET-1** 🟠 LLM Provider selector — tabs: LM Studio | OpenAI | Gemini | Anthropic | Ollama ✅
- [x] **SET-2** 🟠 "Fetch Available Models" from LM Studio and Ollama ✅
- [x] **SET-3** 🟠 Connection test button with latency/status badge — all providers ✅
- [ ] **SET-4** OpenAI model selector — gpt-4o, gpt-4-turbo, gpt-3.5-turbo dropdown
- [ ] **SET-5** Gemini config card — API key, model selector
- [ ] **SET-6** Anthropic config card — API key, model selector
- [ ] **SET-7** Ollama config card — "Pull model" button
- [x] **SET-8** RAG / Vector Store card — provider, collection, persist_dir, top_k, test button ✅
- [x] **SET-9** Observability card — trace toggles, LangSmith key+project, OTel endpoint ✅
- [ ] **SET-10** Environment selector — dev/prod dropdown
- [x] **SET-11** Backend: PUT `/config/lm_studio`, `/config/llm`, POST `/llm/test` ✅
- [ ] **SET-12** API health indicators — status dots next to each provider

---

## AREA 7 — Help & Documentation View

### Current state
- Shows system health + placeholder link lists with no actual content
- No in-app documentation for any builder feature
- No JSON schema viewer, no keyboard shortcuts

### TODOs
- [x] **HELP-1** 🟡 HelpView tabbed layout: Overview | Builder Guide | JSON Schema | API Reference | Troubleshooting ✅
- [x] **HELP-2** 🟡 Builder Guide tab ✅
- [x] **HELP-3** 🟡 JSON Schema tab ✅
- [x] **HELP-4** 🟡 API Reference tab ✅
- [ ] **HELP-5** 🟡 Examples tab — embed enterprise templates with "Open in Builder" button
- [x] **HELP-6** 🟡 Troubleshooting tab ✅
- [ ] **HELP-7** Quick-start wizard — 3-step modal on first visit
- [ ] **HELP-8** Keyboard shortcuts panel
- [ ] **HELP-9** Backend: `/docs/schema` endpoint serving enriched schema JSON
- [ ] **HELP-10** Version/changelog section

---

## AREA 8 — Cross-Cutting / Infrastructure

### Current state
- `config.json` not fully wired into all modules (hardcoded values in orchestrator, api_backend)
- No end-to-end test for the full pipeline
- Monitor & Export views show network errors (missing endpoints)

### TODOs
- [ ] **INF-1** Extend `config_manager.py` to serve RAG, LLM provider, and environment config
- [ ] **INF-2** Wire `config_manager` into `Orchestrator.__init__`
- [ ] **INF-3** Wire `config_manager` into `LLMTranslator`
- [x] **INF-4** `GET /runs` endpoint (paginated run list for Monitor view) ✅
- [x] **INF-5** `GET /artifacts` endpoint (artifact listing for Export view) ✅
- [x] **INF-6** Monitor view — run table, status, timing, clickable detail, execution logs ✅
- [x] **INF-7** Export view — artifact cards, code preview tabs, ZIP download ✅
- [ ] **INF-8** 🟢 End-to-end smoke test `tests/test_e2e_minimal.py`
- [ ] **INF-9** `requirements.txt` audit — add optional extras (`redis`, `chromadb`, etc.)
- [ ] **INF-10** 🟢 `Makefile` — `make dev`, `make test`, `make bundle <run_id>`

---

## AREA 9 — Stub Completion (100% Working Output)

Goal: eliminate all `# TODO` / placeholder stubs from generated `agent.py` so the workbench
ships a zero-handoff, fully runnable agentic bundle.

### TODOs
- [ ] **STUB-1..6** `call_tool()` → real MCP client (stdio JSON-RPC / http POST / rest)
- [ ] **STUB-7..13** `call_rag()` → real RAG clients (LTM SQLite / Chroma / Pinecone / Milvus)
- [ ] **STUB-14..17** `apply_output_guardrails()` → real PII regex, secrets detection, harm blocklist
- [ ] **STUB-18** Update `validate_artifact()` to pass (not warn) once stubs are real
- [ ] **STUB-19** `generate_requirements()` additions for guardrail packages

---

*Last updated: 2026-03-13*


---

## AREA 1 — Memory Manager (STM / LTM / RAG)

### Current state
- STM: in-memory dict only (redis stub logs a warning)
- LTM: SQLite append-only; no TTL, no index, no vector search
- RAG: `_execute_rag_search()` in graph_factory stubs external providers
- No `query_ltm()` method — RAG in graph_factory calls it but it doesn't exist
- No STM max-entries enforcement

### TODOs
- [x] **MM-1** 🔴 Add `query_ltm(session_id, keyword, limit)` method to `MemoryManager` ✅ —
  currently called by `_execute_rag_search()` but missing; causes AttributeError at runtime
- [ ] **MM-2** Enforce `max_stm_entries` — evict oldest entries when STM dict exceeds limit
- [ ] **MM-3** Add LTM TTL pruning — delete rows older than `ltm_ttl_days` on `append_ltm()`
- [ ] **MM-4** Add `query_ltm` full-text keyword search using SQLite `LIKE`
- [ ] **MM-5** Add `reset_ltm(session_id)` method for clean reruns
- [ ] **MM-6** Add `ltm_index_fields` support — store structured JSON fields and allow
  query by field key (e.g. `query_ltm(session_id, field="task", value="research")`)
- [ ] **MM-7** Redis STM: implement basic Redis adapter using `redis-py` behind a feature
  flag — only instantiated when `stm_backend='redis'` and `redis` is importable
- [x] **MM-8** Expose STM/LTM stats via a `get_stats(session_id)` method for the Monitor view ✅
- [ ] **MM-9** Wire `memory_manager` into `Orchestrator` with config-driven init

---

## AREA 2 — RAG Provider Integration

### Current state
- `_execute_rag_search()` has stub hooks for Chroma/Milvus/Pinecone/Weaviate
- Only LTM keyword search works (but `query_ltm` is missing — see MM-1)
- No embedding or semantic similarity — just substring match

### TODOs
- [ ] **RAG-1** Add `RagProvider` base class in new `backend/rag_provider.py` with
  `search(query, collection, top_k, score_threshold) -> List[str]` interface
- [ ] **RAG-2** Implement `LtmRagProvider` — wraps `memory_manager.query_ltm()` (requires MM-1)
- [ ] **RAG-3** Implement `ChromaRagProvider` — uses `chromadb` SDK; graceful ImportError fallback
- [ ] **RAG-4** Implement `LocalFileRagProvider` — reads `.txt`/`.md` files, keyword matching;
  zero-dependency fallback
- [ ] **RAG-5** Add `RagProviderRegistry` — `get_provider(name, config)` factory;
  replaces if/elif stub chain in `_execute_rag_search()`
- [ ] **RAG-6** Update `graph_factory._execute_rag_search()` to use `RagProviderRegistry`
- [ ] **RAG-7** Add `rag` section to `backend/config.json`; read in `config_manager.py`
- [ ] **RAG-8** Frontend Settings: Add "RAG / Vector Store" card — provider selector,
  collection name, embedding model, test-connection button

---

## AREA 3 — Orchestrator Enhancements

### Current state
- Hardcodes `MCPAutoBinder()`, `GraphFactory()`, `MemoryManager()`, `ObservabilityManager()`
- Does not read `runtime`, `memory`, `observability_hooks` from workflow config
- `build_from_config()` called without `session_id` or `bound_tools`
- No timeout enforcement, no backoff retry, no parallel execution support
- No per-step timing in artifacts

### TODOs
- [ ] **ORC-1** 🟠 Config-driven init: read `memory`/`runtime`/`observability` from workflow
  config and pass to constructors
- [ ] **ORC-2** 🟠 Pass `session_id` and `bound_tools` to `factory.build_from_config()`
- [ ] **ORC-3** 🟠 Enforce `runtime.timeout_seconds` using `asyncio.wait_for`
- [ ] **ORC-4** Implement `retry_policy.backoff_strategy` — fixed/exponential sleep between retries
- [ ] **ORC-5** Wire `observability_hooks` from workflow config to `ObservabilityManager`
- [ ] **ORC-6** Per-step timing — record `start_time`/`end_time`/`duration_ms` per node
- [ ] **ORC-7** 🟡 Human-in-the-loop checkpoint — pause at `human_node`, return `awaiting_approval`
- [ ] **ORC-8** 🟡 Resume from checkpoint — `resume_run(run_id, approval_input)` method
- [ ] **ORC-9** Parallel group execution — `asyncio.gather()` for `parallel_execution` groups
- [ ] **ORC-10** `dry_run` mode — build and validate graph without executing; powers "Validate" button

---

## AREA 4 — Run Bundle / Artifact Generation

### Current state
- Bundle is a docs-only ZIP (status JSON + config JSON + README)
- No generated runnable Python code, no requirements, no env template, no deployment guide
- Not deployable without manual work

### TODOs
- [ ] **BNDL-1** 🟠 Add `CodeGenerator` class in `backend/code_generator.py` — emits standalone
  Python script: TypedDict state, one function per node, StateGraph assembly, `main()` entry point
- [ ] **BNDL-2** 🟠 `requirements.txt` generator — inspect config, emit only needed packages
- [ ] **BNDL-3** 🟠 `.env.template` generator — list required env vars based on config
- [ ] **BNDL-4** 🟢 `docker-compose.yml` generator for postgres/redis/Milvus configs
- [ ] **BNDL-5** Add execution trace to bundle — per-node timing, input/output snapshots,
  guardrail statuses from last run
- [ ] **BNDL-6** Add `/generate_code` API endpoint → calls `CodeGenerator`, returns Python for preview
- [ ] **BNDL-7** Frontend Export view: add "Generated Code" tab — syntax-highlighted Python
  with download button
- [ ] **BNDL-8** Bundle versioning — name bundles `{graph_name}_v{version}_{run_id}.zip`,
  keep last N per workflow (default 5)

---

## AREA 5 — LLM Translator Enhancements

### Current state
- Supports OpenAI `/v1/completions`, LM Studio, and manual mode
- Schema used for prompting is old flat format — missing all new enterprise fields
- No streaming, no multi-turn refinement
- `_call_lm_studio()` uses deprecated completions endpoint

### TODOs
- [x] **TRANS-1** 🔴 Update `langgraph_workflow.schema.json` — full enterprise format ✅ —
  `pre_llm`, `context.synthesis`, `context.input_guardrails`, `output_schema`, `validation`,
  `guardrails`, `llm_config`, `runtime.timeout_seconds`, `runtime.error_policy`,
  `runtime.max_concurrency`, `memory.short_term.max_entries`, `memory.long_term.ttl_days`,
  `retry_policy.backoff_strategy`, `retry_policy.retry_on`, `parallel_execution[].timeout_ms`,
  `author`, `tags`, state_schema object format with `description`/`default_value`
- [x] **TRANS-2** Rewrite `_build_prompt()` with compact schema + rich few-shot example ✅
- [x] **TRANS-3** 🔴 Add `/v1/chat/completions` support — tries chat first, falls back to completions ✅
  models require chat format; completions is deprecated
- [ ] **TRANS-4** Add streaming response support — SSE from LM Studio → API → UI
- [ ] **TRANS-5** 🟢 Multi-turn refinement: `refine_workflow(current_json, feedback)` method
- [ ] **TRANS-6** Post-translation normalization: run output through `_normalize_nodes()` to
  validate all node fields are complete
- [ ] **TRANS-7** 🟢 Frontend Translation view: add "Refine" mode — show current JSON + feedback
  textarea → POST to `/customize_json_llm`
- [ ] **TRANS-8** Add Gemini 2.0 Flash / Anthropic Claude as provider options

---

## AREA 6 — Settings View Enhancements

### Current state
- Only LM Studio URL/model + placeholder API Keys card
- No model selector, no connection test, no other providers
- No RAG config, no observability config, no environment selector

### TODOs
- [ ] **SET-1** 🟠 LLM Provider selector — radio/tab: LM Studio | OpenAI | Gemini | Anthropic | Ollama
- [ ] **SET-2** 🟠 "Fetch Available Models" from LM Studio — calls `GET /v1/models`, populates dropdown
- [ ] **SET-3** 🟠 Connection test button — test endpoint, show latency / response / status badge
- [ ] **SET-4** OpenAI model selector — gpt-4o, gpt-4-turbo, gpt-3.5-turbo dropdown
- [ ] **SET-5** Gemini config card — API key, model selector (gemini-2.0-flash, gemini-1.5-pro)
- [ ] **SET-6** Anthropic config card — API key, model selector (claude-3-5-sonnet, claude-3-haiku)
- [ ] **SET-7** Ollama config card — base URL + model name, "Pull model" button
- [ ] **SET-8** RAG / Vector Store card — provider, connection string, collection, test button
- [ ] **SET-9** Observability card — logging toggle, LangSmith key+project, OTel endpoint
- [ ] **SET-10** Environment selector — dev/prod dropdown (mirrors `environments` in `config.json`)
- [ ] **SET-11** Backend: PUT endpoints `/config/llm`, `/config/rag`, `/config/observability`
- [ ] **SET-12** API health indicators — status dots next to each provider (polled on page load)

---

## AREA 7 — Help & Documentation View

### Current state
- Shows system health + placeholder link lists with no actual content
- No in-app documentation for any builder feature
- No JSON schema viewer, no keyboard shortcuts

### TODOs
- [ ] **HELP-1** 🟡 Rewrite HelpView — tabbed layout:
  Overview | Builder Guide | JSON Schema | API Reference | Examples | Troubleshooting
- [ ] **HELP-2** 🟡 Builder Guide tab — full prose docs for every builder section with examples
- [ ] **HELP-3** 🟡 JSON Schema tab — interactive collapsible schema viewer from `langgraph_workflow.schema.json`
- [ ] **HELP-4** 🟡 API Reference tab — endpoints from FastAPI `/openapi.json`
- [ ] **HELP-5** 🟡 Examples tab — embed all enterprise templates with "Open in Builder" button
- [ ] **HELP-6** 🟡 Troubleshooting tab — common errors with diagnosis steps
- [ ] **HELP-7** Quick-start wizard — 3-step modal on first visit
- [ ] **HELP-8** Keyboard shortcuts panel
- [ ] **HELP-9** Backend: `/docs/schema` endpoint serving enriched schema JSON
- [ ] **HELP-10** Version/changelog section

---

## AREA 8 — Cross-Cutting / Infrastructure

### Current state
- `config.json` not fully wired into all modules (hardcoded values in orchestrator, api_backend)
- No end-to-end test for the full pipeline
- Monitor & Export views show network errors (missing endpoints)

### TODOs
- [ ] **INF-1** Extend `config_manager.py` to serve RAG, LLM provider, and environment config
- [ ] **INF-2** Wire `config_manager` into `Orchestrator.__init__`
- [ ] **INF-3** Wire `config_manager` into `LLMTranslator`
- [ ] **INF-4** Add `GET /runs` endpoint (paginated run list for Monitor view)
- [ ] **INF-5** Add `GET /artifacts` endpoint (artifact listing for Export view)
- [ ] **INF-6** Fix Monitor view network error — add run table with run_id, status, timing, clickable detail
- [ ] **INF-7** Fix Export view network error — artifact download cards + "Generate Code" button
- [ ] **INF-8** 🟢 End-to-end smoke test `tests/test_e2e_minimal.py` — 2-node workflow through
  full Orchestrator pipeline, assert on final state
- [ ] **INF-9** `requirements.txt` audit — add `redis`, `chromadb`, `anthropic`,
  `google-generativeai`, `opentelemetry-sdk` as optional extras
- [ ] **INF-10** 🟢 Add `Makefile` — `make dev`, `make test`, `make bundle <run_id>`

---

*Last updated: 2026-03-12*
