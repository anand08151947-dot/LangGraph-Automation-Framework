# Phoenice Constellation — Enhancement Backlog

> **Scope**: All items below are aligned with the core objective — config-driven, zero/low-code agentic AI orchestration. No item drifts into unrelated SaaS, billing, or non-orchestration concerns.
>
> **Format**: GitHub Issues style — each item has a title, description, area label, and priority (`🔴 High` / `🟡 Medium` / `🟢 Low`).

---

## 🏗️ Orchestration & Graph Execution

---

### [ORCH-1] Enforce execution timeout at the node level, not just step boundary
**Priority**: 🔴 High
**Area**: `orchestrator.py`, `graph_factory.py`

**Description**: The current timer is set at the orchestrator level but only checked between steps. A single long-running LLM node can block indefinitely. Enforce per-node wall-clock timeouts using `asyncio.wait_for` or a thread watchdog, and surface a `TIMEOUT` status to the run artifact and API caller.

---

### [ORCH-2] Add circuit-breaker pattern for repeatedly failing nodes
**Priority**: 🔴 High
**Area**: `orchestrator.py`

**Description**: When a node fails on every retry, the current retry logic still exhausts all attempts before giving up. Implement a circuit-breaker: after N consecutive failures of the same node, open the circuit, skip or reroute execution, and record the failure reason in the run artifact. This prevents wasting LLM tokens on known-broken paths.

---

### [ORCH-3] Validate `initial_state` against declared `state_schema` before run starts
**Priority**: 🔴 High
**Area**: `orchestrator.py`

**Description**: The orchestrator accepts any `initial_state` dict without checking it against the workflow's declared `state_schema`. Mismatched keys silently propagate bad state through the entire graph. Add a pre-run validation step that rejects mismatched state with a clear error message.

---

### [ORCH-4] Add request deduplication / session locking for concurrent STM access
**Priority**: 🔴 High
**Area**: `orchestrator.py`, `memory_manager.py`

**Description**: If the same `session_id` triggers two concurrent workflow runs, both will read and write to the same STM entry, causing state corruption. Add a per-session lock (e.g., `asyncio.Lock` keyed on `session_id`) to serialize concurrent access to the same session's memory.

---

### [ORCH-5] Add jitter to exponential backoff in retry logic
**Priority**: 🟡 Medium
**Area**: `orchestrator.py`

**Description**: Retry backoff is hardcoded with no jitter, which means multiple concurrent failing sessions retry at the same time (thundering herd). Add randomized jitter (±20% of the backoff window) to spread retries and reduce burst load on downstream LLMs or MCP servers.

---

### [ORCH-6] Implement true parallel node execution using LangGraph `Send()`
**Priority**: 🟡 Medium
**Area**: `graph_factory.py`

**Description**: Parallel agent groups are declared in config (e.g., `parallel_groups`) but only sequential fallback edges are created. Implement actual fan-out/fan-in using LangGraph's `Send()` primitive so that nodes in a parallel group genuinely execute concurrently rather than sequentially.

---

### [ORCH-7] Validate `approval_input` schema before accepting a resume request
**Priority**: 🟡 Medium
**Area**: `orchestrator.py`, `api_backend.py`

**Description**: The `/resume/{run_id}` endpoint accepts any dict for `approval_input` and blindly merges it into state without validation. Define an expected schema for approval inputs per workflow checkpoint and reject malformed inputs with a 422 response before attempting state merge.

---

### [ORCH-8] Add example workflows for conditional branching, error paths, and supervisor patterns
**Priority**: 🟢 Low
**Area**: `backend/example_workflows/`

**Description**: The three existing example workflows only cover simple sequential pipelines. Add dedicated examples for: (1) conditional branching (if/else routing), (2) error-handling and retry paths, (3) parallel agent fan-out, and (4) supervisor pattern with fallback routing. These serve as both documentation and integration test fixtures.

---

## 🧠 Memory Management

---

### [MEM-1] Add async/non-blocking DB operations to memory manager
**Priority**: 🔴 High
**Area**: `memory_manager.py`

**Description**: All SQLite operations in the memory manager are synchronous blocking calls. When multiple agent sessions run concurrently, these block the event loop. Migrate to `aiosqlite` for async LTM operations, or run DB operations in a thread pool executor, to prevent concurrency stalls.

---

### [MEM-2] Add error handling and retry for SQLite operations
**Priority**: 🔴 High
**Area**: `memory_manager.py`

**Description**: No exception handling exists around any SQLite call. A locked or corrupted database will raise an unhandled exception that crashes the orchestrator without a useful error message. Wrap all DB operations with proper try/except, log the error with context, and surface a `MEMORY_ERROR` status to the caller.

---

### [MEM-3] Add thread-safety lock to LTM write operations
**Priority**: 🔴 High
**Area**: `memory_manager.py`

**Description**: STM is protected by a lock but LTM write operations are not. Concurrent sessions appending to `ltm.db` can interleave writes and corrupt history. Apply a per-session or global write lock to LTM operations to match the protection already applied to STM.

---

### [MEM-4] Validate `step_context` is JSON-serializable before writing to LTM
**Priority**: 🟡 Medium
**Area**: `memory_manager.py`

**Description**: Complex Python objects (e.g., LangChain `AIMessage`, custom classes) passed as `step_context` will raise `TypeError` on `json.dumps()` silently or not at all. Add an explicit serialization check with a fallback to `str()` representation and a warning log when non-serializable data is encountered.

---

### [MEM-5] Add global LTM cleanup / TTL-based pruning across all sessions
**Priority**: 🟡 Medium
**Area**: `memory_manager.py`

**Description**: The prune logic only deletes old entries for the current session. Long-running deployments will accumulate LTM entries from hundreds of sessions indefinitely. Add a background cleanup job (or on-startup sweep) that prunes entries older than a configurable TTL across all sessions.

---

### [MEM-6] Expose STM/LTM memory inspection in the frontend
**Priority**: 🟡 Medium
**Area**: `frontend/views/`, `api_backend.py`

**Description**: The backend exposes `/memory/stm/{session_id}` and `/memory/ltm/{session_id}` endpoints but no frontend UI surfaces them. Add a memory inspection panel in the Monitor view or a dedicated Memory tab so users can introspect agent state and history for debugging without needing a raw API call.

---

## 👁️ Observability

---

### [OBS-1] Implement structured JSON logging throughout the backend
**Priority**: 🔴 High
**Area**: `observability_manager.py`, all backend modules

**Description**: All log output uses basic string formatting. In production, structured logs (JSON with fields: `timestamp`, `level`, `session_id`, `run_id`, `node`, `event`, `duration_ms`) are required for log aggregation tools (Datadog, Loki, CloudWatch). Replace string concatenation in `log_event` with a structured dict formatter.

---

### [OBS-2] Implement OpenTelemetry trace spans for each agent node execution
**Priority**: 🟡 Medium
**Area**: `observability_manager.py`

**Description**: The `ObservabilityManager` has placeholder comments for OpenTelemetry but no actual spans are created. Instrument each agent node execution with an OTEL span (start/end time, node name, session ID, status, error if any) so that distributed traces are available when an OTEL backend is configured.

---

### [OBS-3] Implement Prometheus metrics export (node latency, token usage, error rates)
**Priority**: 🟡 Medium
**Area**: `observability_manager.py`

**Description**: `record_metric()` exists but doesn't aggregate or export anywhere. Wire up a Prometheus `Counter` and `Histogram` for: node execution count, node latency, LLM token usage, retry count, and error rate. Expose a `/metrics` endpoint so users can scrape from Prometheus or Grafana.

---

### [OBS-4] Add hook unregistration and timeout enforcement for plugin hooks
**Priority**: 🟡 Medium
**Area**: `observability_manager.py`

**Description**: Once a hook is registered, it cannot be removed, and there is no timeout on hook execution. A slow or hanging hook callback can block the entire orchestration step. Add `unregister_hook()` and wrap each hook call with a configurable timeout (default: 2s), logging a warning on timeout but continuing execution.

---

### [OBS-5] Persist observability events to a queryable store
**Priority**: 🟡 Medium
**Area**: `observability_manager.py`, `api_backend.py`

**Description**: All observability events are currently ephemeral (in-memory or log file only). Add persistence of structured events to a lightweight store (SQLite table or append-only JSON file) and expose a `/events/{session_id}` endpoint so run events can be retrieved after the fact for debugging and audit.

---

### [OBS-6] Add a size cap to the in-memory `workflow_status` dict in the API
**Priority**: 🟡 Medium
**Area**: `api_backend.py`

**Description**: `workflow_status` is an unbounded in-memory dict that grows forever as runs accumulate. Add an LRU cap (e.g., max 1000 entries) with eviction of oldest entries, and/or persist run status to the runs database so memory usage is bounded regardless of API uptime.

---

## 🔧 MCP Tool Integration

---

### [MCP-1] Implement full tool schema discovery (parameters, required fields, output types)
**Priority**: 🔴 High
**Area**: `mcp_autobinder.py`

**Description**: The auto-binder currently only lists tool names from MCP servers without fetching their argument schemas, required parameters, or return types. Implement the MCP `tools/list` protocol call fully to retrieve tool schemas, and propagate those schemas to the agent's tool binding so LLMs can correctly formulate tool calls.

---

### [MCP-2] Implement SSE and HTTP MCP server connection types (currently stubs)
**Priority**: 🔴 High
**Area**: `mcp_autobinder.py`

**Description**: SSE and HTTP MCP server types are declared but return simulated tools. Implement real SSE (`EventSource`-based) and REST HTTP clients for MCP tool discovery and invocation to match the stdio implementation.

---

### [MCP-3] Add credential/auth support for MCP server connections
**Priority**: 🔴 High
**Area**: `mcp_autobinder.py`

**Description**: MCP servers may require bearer tokens, API keys, or mTLS. The current implementation passes no credentials. Add a `credentials` field to the MCP server config (referencing secrets from environment variables, never hardcoded) and pass them when opening connections.

---

### [MCP-4] Cache discovered MCP tool lists and invalidate on config change
**Priority**: 🟡 Medium
**Area**: `mcp_autobinder.py`

**Description**: Every workflow run re-discovers tools from all configured MCP servers, which is expensive for large toolsets. Cache the tool list (with TTL or explicit invalidation on config reload) to avoid redundant subprocess/network calls on every orchestration start.

---

### [MCP-5] Implement a real health check in `tool_registry.py`
**Priority**: 🟡 Medium
**Area**: `tool_registry.py`

**Description**: `check_tool_health()` always returns `"healthy"` without actually testing the tool. For each registered tool, implement a lightweight liveness check (e.g., a `ping` call to the MCP server or a known no-op tool invocation) and return the real status. Surface unhealthy tools as warnings before a workflow run starts.

---

### [MCP-6] Add persistent storage for the tool registry
**Priority**: 🟡 Medium
**Area**: `tool_registry.py`

**Description**: The tool registry is entirely in-memory and is wiped on every API restart. Persist registered tools (name, metadata, version, schema) to a SQLite table or JSON file so the registry survives restarts and tools don't need to be re-registered after every deployment.

---

### [MCP-7] Add a Tool Management UI (register, unregister, health status)
**Priority**: 🟡 Medium
**Area**: `frontend/views/`

**Description**: The backend exposes `/tools`, `/tools/register`, `/tools/unregister`, and `/tools/health` endpoints but no frontend UI exposes them. Add a Tools view (or panel within Settings) that lists registered tools, shows their health status, and allows registration/unregistration without needing raw API calls.

---

## 🛡️ Guardrails & Safety

---

### [GUARD-1] Replace `eval()` in condition evaluation with a safe expression parser
**Priority**: 🔴 High
**Area**: `guardrails.py`, `graph_factory.py`

**Description**: `_safe_eval_condition` uses Python's `eval()` with restricted builtins, which is still a code injection risk for adversarial inputs processed through an agent. Replace with a purpose-built expression parser (e.g., `asteval`, `simpleeval`, or a hand-rolled AST walker) that only supports the needed operators.

---

### [GUARD-2] Implement the `summarize` context synthesis strategy (currently truncates)
**Priority**: 🔴 High
**Area**: `guardrails.py`, `graph_factory.py`

**Description**: When `context_synthesis` is set to `"summarize"`, the code falls back to plain truncation. Implement the intended behavior: call the configured LLM with a summarization prompt when context exceeds the token limit, and return the condensed result as the effective context for the next node.

---

### [GUARD-3] Fix harmful content redaction bug in the guardrail loop
**Priority**: 🔴 High
**Area**: `guardrails.py`

**Description**: The redaction loop's `lower` variable is not updated after each substitution, causing subsequent pattern checks to compare against the original string instead of the already-redacted version. This means chained redaction patterns miss content that was introduced or shifted by earlier replacements.

---

### [GUARD-4] Extend PII detection patterns (DOB, passport, IBAN, driving license)
**Priority**: 🟡 Medium
**Area**: `guardrails.py`

**Description**: Current PII patterns cover SSN, email, phone, and credit card. Many enterprise workflows process documents with additional PII types: date of birth, passport numbers, IBAN/bank account numbers, driving license numbers. Extend the pattern set and add a config-driven mechanism to enable/disable individual patterns.

---

### [GUARD-5] Add semantic guardrail support via LLM-based content classification
**Priority**: 🟡 Medium
**Area**: `guardrails.py`

**Description**: Regex-based keyword matching cannot detect implied harmful intent (e.g., "which plants cause illness if consumed?"). Add an optional LLM-based classification pass for guardrail evaluation when `use_semantic_guardrails: true` is set in config. This should only invoke the LLM if regex passes but semantic risk is needed.

---

### [GUARD-6] Persist guardrail violations for compliance audit
**Priority**: 🟡 Medium
**Area**: `guardrails.py`, `observability_manager.py`

**Description**: Guardrail violations are currently only logged at runtime and lost after the process ends. Persist violations (timestamp, session_id, run_id, rule triggered, content snippet hash) to a dedicated audit table so compliance teams can review what was blocked and why.

---

## 🔍 RAG Integration

---

### [RAG-1] Add relevance scoring to `LocalFileRagProvider`
**Priority**: 🔴 High
**Area**: `rag_provider.py`

**Description**: The local file RAG provider does plain keyword matching and returns results in file-system order with no relevance ranking. Implement TF-IDF or BM25 scoring so results are ordered by relevance to the query, and apply `score_threshold` filtering consistently with the Chroma provider.

---

### [RAG-2] Add result deduplication across RAG providers
**Priority**: 🟡 Medium
**Area**: `rag_provider.py`

**Description**: When multiple RAG sources are queried (e.g., Chroma + LTM), the same document can appear in multiple result sets. Add deduplication by content hash before returning the merged result list to the agent.

---

### [RAG-3] Add metadata filtering support to RAG queries
**Priority**: 🟡 Medium
**Area**: `rag_provider.py`

**Description**: The RAG query interface accepts a query string and optional session ID but no metadata filters. Add support for filtering by document tags, date range, or custom metadata fields so agents can scope retrieval to relevant document subsets (e.g., "only customer documents from the last 30 days").

---

### [RAG-4] Fix `LocalFileRagProvider` ignoring its `config` parameter
**Priority**: 🟡 Medium
**Area**: `rag_provider.py`

**Description**: `LocalFileRagProvider` receives a `config` dict but always uses a hardcoded directory path, ignoring the configured `documents_path`. Fix it to use the path from config, and raise a clear error if the directory doesn't exist rather than returning empty results.

---

### [RAG-5] Add RAG result caching with configurable TTL
**Priority**: 🟢 Low
**Area**: `rag_provider.py`

**Description**: The same RAG query may be issued multiple times across agent steps, hitting the vector store or file system each time. Add an in-memory LRU cache keyed on `(provider, query_hash, top_k)` with a configurable TTL to avoid redundant retrieval within a single workflow run.

---

## 🔒 Access Control & Security

---

### [SEC-1] Remove hardcoded JWT fallback secret and enforce env var requirement
**Priority**: 🔴 High
**Area**: `access_control.py`

**Description**: If `JWT_SECRET` is not set, the code falls back to the literal string `"secret"`, making all tokens trivially forgeable. Remove the fallback entirely. If the env var is absent at startup, raise a `ConfigurationError` that prevents the API from starting, forcing operators to set a proper secret.

---

### [SEC-2] Add JWT expiration (`exp` claim) validation
**Priority**: 🔴 High
**Area**: `access_control.py`

**Description**: Tokens are decoded but the `exp` claim is never checked, meaning expired tokens remain valid forever. Add explicit expiration validation in the token verification path and return a `401 Token Expired` response with a clear message so clients know to re-authenticate.

---

### [SEC-3] Add config reload locking to prevent race with concurrent runs
**Priority**: 🔴 High
**Area**: `api_backend.py`, `config_manager.py`

**Description**: The `/config/reload` endpoint triggers a config reload with no locking mechanism. If a workflow run is mid-execution while config reloads, the run may see a partially updated config. Add a read-write lock (config reads shared, reload exclusive) and reject reloads while active runs are in progress.

---

### [SEC-4] Redact nested secrets from config summary and API responses
**Priority**: 🔴 High
**Area**: `api_backend.py`

**Description**: The config summary redaction only masks top-level `api_keys`. Secrets nested in MCP server configs, observability backend credentials, or RAG provider tokens are returned in plaintext. Implement a recursive redaction pass over any dict key matching a blocklist pattern (`*key*`, `*secret*`, `*token*`, `*password*`).

---

### [SEC-5] Add access control to `/config/summary`, `/config/reload`, and `/audit` endpoints
**Priority**: 🔴 High
**Area**: `api_backend.py`

**Description**: These endpoints return sensitive system information or perform destructive operations but have no access control checks. Apply the existing `require_role("admin")` decorator (or equivalent) to all three endpoints immediately.

---

### [SEC-6] Add API key rotation and expiration support
**Priority**: 🟡 Medium
**Area**: `access_control.py`

**Description**: API keys are static once configured. Add a key rotation mechanism (generate new key, keep old key valid for a grace period, then revoke) and an optional `expires_at` field. Expose rotation via a secured admin endpoint so keys can be cycled without redeploying.

---

### [SEC-7] Add rate limiting to authentication endpoints
**Priority**: 🟡 Medium
**Area**: `access_control.py`, `api_backend.py`

**Description**: There is no rate limiting on login or API key validation endpoints, making brute-force attacks trivial. Add per-IP rate limiting (e.g., 10 attempts/minute) using a middleware or decorator, with progressive backoff and lockout after repeated failures.

---

## ⚙️ Configuration & Templates

---

### [CFG-1] Add environment variable templating in `config.json` values
**Priority**: 🔴 High
**Area**: `config_manager.py`

**Description**: API keys and secrets are currently stored inline in `config.json`. Implement `${ENV_VAR_NAME}` substitution so values can reference environment variables, keeping secrets out of config files entirely. Raise a clear error at load time if a referenced env var is not set.

---

### [CFG-2] Add dot-notation `get()` for nested config access
**Priority**: 🟡 Medium
**Area**: `config_manager.py`

**Description**: All config consumers use chained `.get()` calls (e.g., `config.get("memory", {}).get("backend", "sqlite")`). Add a `config.get("memory.backend", default="sqlite")` shorthand using dot-notation path resolution to reduce boilerplate and make config access less error-prone.

---

### [CFG-3] Implement database-backed template storage (currently stub)
**Priority**: 🟡 Medium
**Area**: `template_manager.py`

**Description**: `save_to_db()` and `load_from_db()` are empty stub methods. Implement SQLite-backed template storage as an alternative to file-based storage. This enables: concurrent-safe writes, versioning with conflict detection, and template metadata (author, created_at, modified_at) without filesystem reliance.

---

### [CFG-4] Add template versioning conflict detection and diff
**Priority**: 🟡 Medium
**Area**: `template_manager.py`

**Description**: Saving a template with an existing version number silently overwrites without warning. Add conflict detection (reject save if version exists) and an optional diff endpoint (`/templates/diff/{name}/{v1}/{v2}`) so users can compare template versions before overwriting.

---

### [CFG-5] Expose config validation and simulation endpoints in the frontend
**Priority**: 🟡 Medium
**Area**: `frontend/views/`, `api_backend.py`

**Description**: The backend has `/config/validate` and `/config/simulate` endpoints that are not exposed in the frontend. Add a "Validate" button in the Builder view that calls these endpoints before orchestration, surfacing schema errors to the user rather than letting invalid configs fail at runtime.

---

### [CFG-6] Add config file watching for hot-reload without API restart
**Priority**: 🟢 Low
**Area**: `config_manager.py`

**Description**: Config changes currently require an explicit `/config/reload` API call. Add an optional file watcher (using `watchdog` or `inotify`) that detects changes to `config.json` and triggers a safe reload automatically in development mode, reducing the edit-reload cycle.

---

## 🤖 LLM Translation

---

### [LLM-1] Make model selection configurable in `llm_translator.py`
**Priority**: 🔴 High
**Area**: `llm_translator.py`

**Description**: The translator is hardcoded to `gpt-4-1106-preview`. Users running local LLMs (LM Studio), Gemini, or different OpenAI models can't use this feature without editing source code. Read the model from the active config (falling back to a sensible default) and document the config key clearly.

---

### [LLM-2] Add token count estimation and context window warning
**Priority**: 🟡 Medium
**Area**: `llm_translator.py`

**Description**: Long English instructions combined with large schema context can silently exceed the model's context window, producing truncated or hallucinated JSON. Add a token count estimate (using `tiktoken` or character-based heuristic) before the LLM call and warn (or error) if the prompt exceeds 80% of the model's context limit.

---

### [LLM-3] Harden JSON extraction from LLM responses
**Priority**: 🟡 Medium
**Area**: `llm_translator.py`

**Description**: The current JSON extraction uses regex to strip code fences. This fails on edge cases: no fence, multiple code blocks, JSON with nested backticks, or YAML-formatted output. Add a multi-strategy extractor: try direct parse → extract from code fence → try jsonrepair → fail with clear message.

---

### [LLM-4] Add streaming response support for long translations
**Priority**: 🟢 Low
**Area**: `llm_translator.py`, `api_backend.py`

**Description**: Translation of complex workflows can take 20–60 seconds with no intermediate feedback. Add streaming support (`stream=True` for OpenAI-compatible endpoints) so the frontend can show a progressive preview of the generated JSON as it arrives, improving perceived performance.

---

## 🖥️ Frontend — Builder View

---

### [FE-BUILD-1] Implement visual node/edge graph editor in BuilderView
**Priority**: 🔴 High
**Area**: `frontend/views/BuilderView`

**Description**: The BuilderView is the central UI for creating workflows but has no visual graph editor. The types and interfaces for nodes/edges are defined but no canvas exists. Implement a drag-and-drop node editor (using React Flow or similar) where users can add agent nodes, draw routing edges, and configure node properties visually — translating directly to the JSON config schema.

---

### [FE-BUILD-2] Add per-node LLM configuration panel (model, temperature, max_tokens)
**Priority**: 🔴 High
**Area**: `frontend/views/BuilderView`

**Description**: Each agent node in the config supports `llm_config` (model, temperature, max_tokens, system_prompt) but no UI exposes these settings per-node. Add a node property panel (sidebar or modal) that allows configuring LLM parameters for each agent node without editing raw JSON.

---

### [FE-BUILD-3] Add MCP server and tool binding configuration UI
**Priority**: 🔴 High
**Area**: `frontend/views/BuilderView`

**Description**: MCP server definitions and tool bindings are core to Phoenice's value proposition but can only be configured via raw JSON. Add a UI panel where users can define MCP servers (URL, type, credentials) and assign discovered tools to agent nodes, with a "Discover Tools" button that queries the MCP server and populates available tools.

---

### [FE-BUILD-4] Add conditional routing / edge logic editor
**Priority**: 🔴 High
**Area**: `frontend/views/BuilderView`

**Description**: Conditional routing between nodes (based on output content, state values, or keywords) is a core config capability that has no visual equivalent. Add an edge property dialog that lets users define routing conditions (keyword match, field comparison, regex) and map them to target nodes — the backbone of non-linear workflow logic.

---

### [FE-BUILD-5] Add guardrails configuration UI per node (PII, harmful content, output schema)
**Priority**: 🟡 Medium
**Area**: `frontend/views/BuilderView`

**Description**: Input/output guardrails (PII detection, harmful content blocking, output schema enforcement) are configured in JSON but not exposed in the UI. Add a Guardrails tab in the node property panel with toggles for each guardrail type and fields for custom patterns or output schemas.

---

### [FE-BUILD-6] Add workflow validation before orchestration
**Priority**: 🟡 Medium
**Area**: `frontend/views/BuilderView`

**Description**: Users can submit invalid workflow configs that only fail at runtime (wasting LLM calls). Wire up the `/config/validate` backend endpoint as a pre-flight check when clicking "Run" in the builder, displaying schema errors inline before execution begins.

---

### [FE-BUILD-7] Add RAG source configuration UI per node
**Priority**: 🟡 Medium
**Area**: `frontend/views/BuilderView`

**Description**: RAG provider settings (provider type, collection, top_k, score_threshold) are JSON-only. Add a RAG configuration panel in the node editor that maps to the `context.sources` config section, enabling users to enable and configure retrieval without touching JSON.

---

## 🖥️ Frontend — Monitor View

---

### [FE-MON-1] Wire up "Rerun" and "Stop" buttons in MonitorView
**Priority**: 🔴 High
**Area**: `frontend/views/MonitorView`

**Description**: The "Rerun" and "Stop" action buttons have no `onClick` handlers — they are visually present but entirely non-functional. Wire them to the `/orchestrate` (for rerun) and a new `/runs/{run_id}/cancel` backend endpoint (for stop) respectively.

---

### [FE-MON-2] Add human-in-loop approval workflow UI
**Priority**: 🔴 High
**Area**: `frontend/views/MonitorView`

**Description**: The backend supports human approval checkpoints (`/approval/{run_id}`) and resume (`/resume/{run_id}`), but the frontend has no UI for them. When a run status is `awaiting_approval`, display an approval panel with the checkpoint context, an approval/rejection form, and a submit button that calls the resume endpoint.

---

### [FE-MON-3] Implement real-time log streaming via WebSocket
**Priority**: 🔴 High
**Area**: `frontend/views/MonitorView`, `api_backend.py`

**Description**: The Monitor view currently mocks log animation for running workflows. The backend has a WebSocket endpoint for status updates but it's not connected to the frontend. Implement a proper WebSocket client in the monitor view that streams live log events as they are produced by the orchestrator.

---

### [FE-MON-4] Add auto-refresh polling for active run status
**Priority**: 🟡 Medium
**Area**: `frontend/views/MonitorView`, `hooks/useMonitorRuns`

**Description**: Users must manually refresh to see updated run status. Add a polling interval (configurable, default: 5s) that re-fetches run status for any run in `RUNNING` or `awaiting_approval` state, and stops polling when the run reaches a terminal state (`COMPLETED`, `FAILED`, `CANCELLED`).

---

### [FE-MON-5] Add run log search and export
**Priority**: 🟡 Medium
**Area**: `frontend/views/MonitorView`

**Description**: Logs for complex multi-agent runs can be hundreds of lines. Add a search/filter input to the log panel (client-side filtering by keyword or log level) and a "Download Logs" button that exports the full run log as a `.txt` or `.json` file for offline analysis.

---

### [FE-MON-6] Add run configuration viewer
**Priority**: 🟡 Medium
**Area**: `frontend/views/MonitorView`

**Description**: The backend exposes `/runs/{run_id}/config` but the frontend doesn't surface it. Add a "View Config" tab or expandable section in the run detail panel showing the exact workflow config that was used for that run, enabling reproducibility and debugging.

---

## 🖥️ Frontend — Dashboard & General UX

---

### [FE-UX-1] Replace hardcoded mock activity feed with live data from the API
**Priority**: 🔴 High
**Area**: `frontend/views/DashboardView`

**Description**: The Dashboard's activity feed is populated with hardcoded mock data that never changes. Replace it with a live query to the runs API (fetching the most recent N runs) so the dashboard reflects actual system activity.

---

### [FE-UX-2] Add a global toast/notification system for user feedback
**Priority**: 🔴 High
**Area**: `frontend/` (global)

**Description**: User-triggered actions (start run, save template, register tool) produce no visible confirmation or error feedback. Add a lightweight toast notification system (e.g., react-hot-toast or a custom component) so every API call result — success or failure — surfaces a brief, dismissible notification.

---

### [FE-UX-3] Add loading skeleton screens for data-fetching views
**Priority**: 🟡 Medium
**Area**: `frontend/views/` (all views)

**Description**: Views show blank content or a spinner while data loads. Replace generic spinners with skeleton screens that match the shape of the incoming content, reducing perceived load time and preventing layout shift.

---

### [FE-UX-4] Add a global error boundary with retry capability
**Priority**: 🟡 Medium
**Area**: `frontend/` (global)

**Description**: Unhandled React errors currently crash the entire UI. Add a React Error Boundary component at the app root (and per-view level) that catches render errors, displays a helpful message, and provides a "Retry" button that resets the component state.

---

### [FE-UX-5] Implement syntax highlighting for JSON config in Translation and Export views
**Priority**: 🟡 Medium
**Area**: `frontend/views/TranslationView`, `frontend/views/ExportView`

**Description**: Generated JSON config and code artifacts are displayed in plain `<textarea>` elements with no syntax highlighting. Integrate a lightweight code editor (e.g., CodeMirror or Monaco) for JSON and Python output, significantly improving readability for complex configs.

---

### [FE-UX-6] Add pagination for run history and template lists
**Priority**: 🟡 Medium
**Area**: `frontend/views/DashboardView`, `frontend/views/TemplatesView`

**Description**: All runs and templates are fetched and rendered in a single list with no pagination. As the number of runs grows, this becomes a performance and usability problem. Add client-side or server-side pagination (or virtual scrolling) to both lists.

---

### [FE-UX-7] Add template versioning UI (view versions, diff, restore)
**Priority**: 🟡 Medium
**Area**: `frontend/views/TemplatesView`

**Description**: The backend exposes `/templates/versions/{base_name}` but the frontend doesn't surface template version history. Add a "Versions" tab or modal in the template detail view listing all saved versions with timestamps, and allow users to restore a previous version.

---

### [FE-UX-8] Add an Audit Log viewer in the frontend
**Priority**: 🟢 Low
**Area**: `frontend/views/` (new view or Settings panel)

**Description**: The backend has an `/audit` endpoint returning access and action logs. Add a read-only Audit Log panel (accessible to admin role) in the Settings view or as a dedicated view, displaying who did what and when — important for teams sharing a Phoenice instance.

---

## 🧪 Testing

---

### [TEST-1] Add tests for all RAG provider implementations
**Priority**: 🔴 High
**Area**: `tests/`

**Description**: Despite `rag_provider.py` implementing three providers (`LtmRagProvider`, `ChromaRagProvider`, `LocalFileRagProvider`), there are zero unit or integration tests for any of them. Add tests covering: basic retrieval, empty result handling, score threshold filtering, session isolation, and error conditions for each provider.

---

### [TEST-2] Add error handling and edge case tests for the API
**Priority**: 🔴 High
**Area**: `tests/test_api.py`

**Description**: Existing API tests cover the happy path but not failure modes. Add tests for: malformed JSON payloads (400), missing required fields (422), unknown session IDs (404), concurrent run submissions with the same session ID, and oversized request bodies.

---

### [TEST-3] Add tests for concurrent workflow execution (race conditions, STM integrity)
**Priority**: 🔴 High
**Area**: `tests/`

**Description**: The orchestrator and memory manager are used concurrently but no tests verify thread/async safety. Add tests that launch multiple simultaneous workflow runs with overlapping session IDs and assert that STM state does not corrupt between sessions.

---

### [TEST-4] Add tests for guardrail enforcement (PII, harmful content, output schema)
**Priority**: 🟡 Medium
**Area**: `tests/`

**Description**: `guardrails.py` is not covered by any test. Add unit tests for: PII pattern detection (with positive and negative examples), harmful content blocking, output schema validation (valid and invalid outputs), context length truncation, and the redaction loop correctness fix for [GUARD-3].

---

### [TEST-5] Add human-in-loop checkpoint and resume workflow tests
**Priority**: 🟡 Medium
**Area**: `tests/test_orchestrator.py`

**Description**: The approval and resume flow is a key differentiator but has no dedicated test. Add an integration test that: (1) starts a workflow with a human checkpoint node, (2) asserts the run pauses at `awaiting_approval`, (3) submits an approval decision, and (4) asserts the run resumes and completes correctly.

---

### [TEST-6] Add LLM provider failover / fallback tests
**Priority**: 🟡 Medium
**Area**: `tests/`

**Description**: No tests verify behavior when an LLM provider is unavailable. Add tests using a mock that simulates OpenAI returning a 500 error or timeout, and assert that the configured fallback provider (e.g., LM Studio) is attempted, or that a clear `LLM_UNAVAILABLE` error is surfaced.

---

### [TEST-7] Add end-to-end smoke test covering the full workflow lifecycle
**Priority**: 🟡 Medium
**Area**: `tests/`

**Description**: `ToDo.md` references a planned `tests/test_e2e_minimal.py` (item INF-8) that was never created. Implement it: submit a minimal workflow config, poll until completion, assert artifacts were written, and validate the status schema matches the expected terminal state.

---

### [TEST-8] Add a `Makefile` with `make dev`, `make test`, and `make bundle` targets
**Priority**: 🟢 Low
**Area**: Project root

**Description**: `ToDo.md` references a planned `Makefile` (item INF-10) that was never created. Add a minimal `Makefile` with: `make dev` (starts backend + frontend concurrently), `make test` (runs pytest + frontend build check), and `make bundle` (packages a run artifact bundle). This reduces onboarding friction and standardizes developer workflows.

---

## 🔌 API Completeness

---

### [API-1] Implement `/config/generate_llm` endpoint (currently placeholder)
**Priority**: 🟡 Medium
**Area**: `api_backend.py`

**Description**: The `/config/generate_llm` endpoint is present in the API but is a stub that does not call any LLM. Implement it to accept a natural language description of a desired workflow and return a validated JSON config, reusing the existing `llm_translator.py` logic.

---

### [API-2] Implement `/customize_template` Option 1 (LLM-based customization)
**Priority**: 🟡 Medium
**Area**: `api_backend.py`

**Description**: The `/customize_template` endpoint comments mark "Option 1" as "not implemented here". Implement the LLM-driven path that takes `custom_instructions` and the base template, sends them through `llm_translator`, and returns a customized template JSON — completing the intended two-path customization feature.

---

### [API-3] Add a `POST /runs/{run_id}/cancel` endpoint
**Priority**: 🟡 Medium
**Area**: `api_backend.py`

**Description**: There is no endpoint to cancel a running workflow. Add `POST /runs/{run_id}/cancel` that sets a cancellation flag for the given run, which the orchestrator checks between steps and terminates cleanly — writing a `CANCELLED` status artifact before stopping.

---

### [API-4] Add pagination to runs list and audit endpoints
**Priority**: 🟡 Medium
**Area**: `api_backend.py`

**Description**: `/runs` and `/audit` return all records with no pagination. For deployments with thousands of runs, this will exhaust memory and time out. Add `limit` and `offset` (or cursor-based) query parameters to both endpoints.

---

---

## Summary Stats

| Priority | Count |
|----------|-------|
| 🔴 High  | 26    |
| 🟡 Medium | 29   |
| 🟢 Low   | 5     |
| **Total** | **60** |

| Area | Count |
|------|-------|
| Orchestration & Graph | 8 |
| Memory Management | 6 |
| Observability | 6 |
| MCP Tool Integration | 7 |
| Guardrails & Safety | 6 |
| RAG Integration | 5 |
| Access Control & Security | 7 |
| Configuration & Templates | 6 |
| LLM Translation | 4 |
| Frontend — Builder | 7 |
| Frontend — Monitor | 6 |
| Frontend — UX/General | 8 |
| Testing | 8 |
| API Completeness | 4 |
