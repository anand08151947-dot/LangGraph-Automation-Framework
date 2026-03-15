# Code Generator Role Book

> **Purpose**: Living reference that defines what every field in the workflow JSON config means for
> the code generator, what it produces, and what the developer must wire themselves.
>
> **Update this file** whenever a new config field is added, a generator fix is made, or a new
> capability is delivered.  Run the built-in validator (`CodeGenerator.validate_artifact()`) after
> every change to confirm the score stays ≥ 95.

---

## Baseline Score (Enterprise Full Template)

| Metric | Value |
|--------|-------|
| Template | Document Intelligence Pipeline (Full Enterprise) |
| Generator score | **99 / 100** |
| Passed | **True** (0 failures) |
| Warnings | 1 (tool stub — expected, developer must wire MCP) |
| Last audited | 2026-03-15 |

---

## Config Field Coverage Matrix

### Top-Level Metadata

| Field | Code Generator support | Output |
|-------|------------------------|--------|
| `graph_name` | ✅ Full | Used in header comment, graph/file naming |
| `version` | ✅ Full | Header comment |
| `description` | ✅ Full | Header comment |
| `author` | ✅ Full | Header comment |
| `tags` | ⚠️ Noted only | Not used at runtime — emitted as header comment |

---

### `runtime` Block

| Field | Code Generator support | Output |
|-------|------------------------|--------|
| `runtime.max_iterations` | ✅ Full | `MAX_ITER` constant in `run_workflow()`, loop break guard |
| `runtime.timeout_seconds` | ✅ Full | `_TIMEOUT_SEC` constant; wall-clock check per step via `time.time()` |
| `runtime.error_policy` | ✅ Full | `_ERROR_POLICY` constant; `"continue"` swallows node exceptions, `"stop"` re-raises |
| `runtime.checkpoint_store` | ⚠️ Partial | Drives `requirements.txt` (`psycopg2` for postgres); runtime checkpointing controlled by `checkpointing.enabled` |
| `runtime.max_concurrency` | ❌ Not implemented | LangGraph async concurrency requires `async` graph; planned for future sprint |
| `runtime.observability.tracing` | ✅ Full | `trace_nodes` constant; per-step `[TRACE]` JSON log |
| `runtime.observability.provider` | ⚠️ Logging only | Always uses `print()`; OpenTelemetry/LangSmith provider support is planned |

---

### `memory` Block

| Field | Code Generator support | Output |
|-------|------------------------|--------|
| `memory.short_term.type` | ✅ Full | In-process dict (`_MemoryManager`) |
| `memory.short_term.stmMaxEntries` | ✅ Full | `MAX_STM_ENTRIES` — LRU eviction when exceeded (also accepts `max_entries`) |
| `memory.long_term.type` | ✅ Full | SQLite via `_MemoryManager.append_ltm()` |
| `memory.long_term.provider` | ⚠️ Partial | `ltm`=SQLite ✅; `chroma`, `pinecone`, `milvus` stubs in `call_rag()` — developer extends |
| `memory.long_term.collection` | ✅ Full | Used as the RAG `collection` key in `call_rag()` |
| `memory.long_term.ltmTtlDays` | ✅ Full | `LTM_TTL_DAYS` — rows older than N days auto-deleted on write (also accepts `ttl_days`) |

---

### `mcp_servers` Block

| Field | Code Generator support | Output |
|-------|------------------------|--------|
| `mcp_servers.<name>.type` | ✅ Documented | Header comment; `docker-compose.yml` generates service entry for `http`/`sse` servers |
| `mcp_servers.<name>.endpoint` | ✅ Full | In docker-compose env var + header comment |
| `mcp_servers.<name>.command` | ✅ Documented | Header comment (stdio servers) |
| `mcp_servers.<name>.description` | ✅ Documented | Header comment |
| `mcp_servers.<name>.timeout_ms` | ⚠️ Noted | Emitted in comment; `call_tool()` stub does not enforce per-server timeout — developer wires |

> **Developer action required**: Replace `call_tool()` stub with real MCP HTTP/stdio calls.

---

### `state_schema` Block

| Field | Code Generator support | Output |
|-------|------------------------|--------|
| `state_schema.<field>.type` | ✅ Full | Maps to Python type in `WorkflowState(TypedDict)` |
| `state_schema.<field>.description` | ✅ Full | Inline comment on TypedDict field |
| `state_schema.<field>.default_value` | ✅ Full | Used in `main()` initial state construction; coerced to correct Python type |
| Auto-added fields | ✅ Full | `messages: List[Dict]`, `metadata: Dict`, `sender: str` always added |

---

### `nodes[]` — Per-Node Fields

| Field | Code Generator support | Output |
|-------|------------------------|--------|
| `id` | ✅ Full | Function name `node_<id>()`, graph `add_node()` |
| `type` | ✅ Full | `agent` → full pipeline; `human_node` → pause stub; `tool_node` → tool-only stub |
| `description` | ✅ Full | Docstring of node function |
| `system_prompt` | ✅ Full | `system_prompt` variable, passed to `call_llm()` |
| `next` | ✅ Full | `workflow.add_edge()` |
| `tools` | ✅ Documented | Docstring + `call_tool()` invocations for pre_llm tools |
| `memory_access` | ✅ Documented | Docstring; STM read via `state.*`, LTM via `call_rag("ltm", ...)` |
| `checkpoint` | ✅ Noted | Commented on `add_node()` line; LangGraph SqliteSaver handles actual checkpointing |

#### `nodes[].llm_config`

| Field | Code Generator support | Output |
|-------|------------------------|--------|
| `llm_config.temperature` | ✅ Full | Passed to `call_llm()` |
| `llm_config.max_tokens` | ✅ Full | Passed to `call_llm()` |
| `llm_config.model` | ✅ Full | Passed to `call_llm(model=...)`; `None` → uses `LM_STUDIO_MODEL` env var |

#### `nodes[].pre_llm`

| Field | Code Generator support | Output |
|-------|------------------------|--------|
| `pre_llm.tool_calls[].id` | ✅ Full | Variable name `_tc_input_<id>`, comment |
| `pre_llm.tool_calls[].tool` | ✅ Full | `call_tool("<tool>", ...)` |
| `pre_llm.tool_calls[].input_template` | ✅ Full | f-string template (developer replaces `{state.VAR}` syntax) |
| `pre_llm.tool_calls[].output_var` | ✅ Full | Local variable name for the result |
| `pre_llm.tool_calls[].inject_into_context` | ✅ Full | If true, variable collected into `context_parts` via `pre_llm` context source |
| `pre_llm.rag.enabled` | ✅ Full | Gates RAG block generation |
| `pre_llm.rag.provider` | ✅ Full | Passed to `call_rag()` |
| `pre_llm.rag.collection` | ✅ Full | Passed to `call_rag()` |
| `pre_llm.rag.query_template` | ✅ Full | f-string template |
| `pre_llm.rag.top_k` | ✅ Full | Passed to `call_rag()` |
| `pre_llm.rag.score_threshold` | ✅ Documented | Emitted as comment; `call_rag()` stub does not filter by score — extend for vector DBs |
| `pre_llm.rag.output_var` | ✅ Full | Local variable name |
| `pre_llm.rag.inject_into_context` | ✅ Full | If true, included in `pre_llm` context part |

#### `nodes[].context`

| Field | Code Generator support | Output |
|-------|------------------------|--------|
| `context.sources[].type = "stm"` | ✅ Full | Reads state keys into `_ctx_stm` |
| `context.sources[].keys` | ✅ Full | Only requested keys joined into context string |
| `context.sources[].type = "previous_node"` | ✅ Full | Reads `state["metadata"][node_id]["output"]` |
| `context.sources[].type = "ltm"` | ✅ Full | `call_rag("ltm", query, limit)` |
| `context.sources[].type = "pre_llm"` | ✅ Full | Collects `output_var` variables from tool_calls + RAG blocks |
| `context.sources[].label` | ✅ Full | Prefixed to each context part string |
| `context.inject_as` | ⚠️ Partial | Always injected as `user` turn; `system` injection not yet differentiated |
| `context.synthesis.strategy` | ⚠️ Partial | Emitted as comment; all strategies concatenate with `\n\n` — `summarize` does not call LLM pre-synthesis |
| `context.synthesis.prompt_template` | ⚠️ Noted | Emitted as comment only; not used at runtime |
| `context.input_guardrails` | ✅ Full | `apply_input_guardrails(context_text, cfg, node_id)` |

#### `nodes[].context.input_guardrails`

| Field | Code Generator support | Output |
|-------|------------------------|--------|
| `context_length.max_chars` + `on_exceed` | ✅ Full | Truncates context string to `max_chars` |
| `encoding_sanitization.enabled` | ⚠️ Noted | Field accepted; sanitization not yet implemented |
| `pii.enabled` + `action` | ✅ Full | `_apply_pii()` with `redact` or `block` |
| `prompt_injection.enabled` + `action` | ✅ Full | `_INJECT_RE` regex; `block` raises, `warn` prints |
| `secrets_detection.enabled` + `action` | ✅ Full | `_SECRET_PATTERNS` regex; `redact` or `block` |

#### `nodes[].output_schema`

| Field | Code Generator support | Output |
|-------|------------------------|--------|
| `output_schema.format` | ✅ Full | `json` → JSON parse + field check; `text` → raw string |
| `output_schema.state_key` | ✅ Full | `state[state_key] = _output` update |
| `output_schema.required_fields` | ✅ Full | Merged into `validate_output()` required check |

#### `nodes[].validation`

| Field | Code Generator support | Output |
|-------|------------------------|--------|
| `validation.enabled` | ✅ Full | Gates `validate_output()` call |
| `validation.required_fields` | ✅ Full | Checked in `validate_output()` |
| `validation.rules[].field/operator/value` | ✅ Full | Evaluated per rule; fails on `on_failure` policy |
| `validation.on_failure` | ✅ Full | `warn` → print; `error` → early return with partial state |

#### `nodes[].guardrails` (output)

| Field | Code Generator support | Output |
|-------|------------------------|--------|
| `guardrails.pii.enabled` + `action` | ✅ Full | `apply_output_guardrails()` → `_apply_pii()` |
| `guardrails.harmful_content.enabled` + `action` | ✅ Full | Keyword scan; `block` raises |
| `guardrails.hate_speech.enabled` + `action` | ✅ Full | Regex scan; `block` raises |
| `guardrails.self_harm.enabled` + `action` | ⚠️ Partial | Config accepted; not yet matched by dedicated pattern — caught by harmful_content keywords |
| `guardrails.regulated_advice.enabled` + `checks` | ⚠️ Noted | Config accepted and printed; no runtime rule enforced yet |

#### `nodes[].routing_logic`

| Field | Code Generator support | Output |
|-------|------------------------|--------|
| `routing_logic[].condition` | ✅ Full | Converted to Python `state.get("var")` expression |
| `routing_logic[].next` | ✅ Full | Returned from `route_<node>()` function |
| Wiring | ✅ Full | `workflow.add_conditional_edges()` with full target map |

---

### `edges[]` Block

| Field | Code Generator support | Output |
|-------|------------------------|--------|
| `edges[].from` / `edges[].source` | ✅ Full | `workflow.add_edge(src, dst)` |
| `edges[].to` / `edges[].target` | ✅ Full | `workflow.add_edge(src, dst)` or `END` |
| `edges[].condition` | ✅ Full | If present → `add_conditional_edges()` via routing function |
| `edges[].label` | ⚠️ Not used | Label is UI metadata only; no runtime effect |

---

### `parallel_execution[]` Block

| Field | Code Generator support | Output |
|-------|------------------------|--------|
| `parallel_execution[].group` | ✅ Full | Dispatcher node `__dispatch_<group>__` |
| `parallel_execution[].nodes` | ✅ Full | `[Send(t, state) for t in targets]` fan-out |
| `parallel_execution[].fan_in` | ✅ Full | All group nodes wired to fan-in node |
| Graceful fallback | ✅ Full | Sequential fallback when `Send` not available or <2 nodes |

---

### `retry_policy` Block

| Field | Code Generator support | Output |
|-------|------------------------|--------|
| `retry_policy.max_retries` | ✅ Full | `_RETRY_MAX` in `call_llm()` |
| `retry_policy.backoff_strategy` | ✅ Full | `exponential` or `fixed` in `call_llm()` |
| `retry_policy.backoff_base_seconds` | ✅ Full | Base sleep duration |
| `retry_policy.increment_state` | ⚠️ Partial | Field noted; state increment not automated — node logic must update the field |
| `retry_policy.retry_on` | ⚠️ Partial | Accepted but not filtered; all LLM exceptions trigger retry regardless of type |

---

### `checkpointing` Block

| Field | Code Generator support | Output |
|-------|------------------------|--------|
| `checkpointing.enabled` | ✅ Full | Conditional `SqliteSaver.from_conn_string()` + `graph.compile(checkpointer=...)` |
| `checkpointing.nodes` | ✅ Noted | Commented on `add_node()` — LangGraph checkpoints at all interrupt nodes when using SqliteSaver |
| `checkpointing.db_path` | ✅ Full | `CHECKPOINT_DB` env var with config default |

---

### `observability_hooks` Block

| Field | Code Generator support | Output |
|-------|------------------------|--------|
| `observability_hooks.trace_nodes` | ✅ Full | Per-step `[TRACE] {...}` JSON log |
| `observability_hooks.log_state_transitions` | ✅ Full | Per-node `[STEP N] node=... keys=...` log |
| `observability_hooks.capture_agent_outputs` | ✅ Full | LTM entry written per step with node/sender/state_keys |

---

## Exported Artifacts

| Artifact | Generator method | Status |
|----------|-----------------|--------|
| `agent.py` | `generate_workflow_script()` | ✅ Runnable CLI with argparse |
| `requirements.txt` | `generate_requirements()` | ✅ Auto-adds packages for RAG, checkpointing, LLM providers |
| `.env.template` | `generate_env_template()` | ✅ All env vars with defaults |
| `Dockerfile` | `generate_dockerfile()` | ✅ python:3.11-slim, COPY agent.py + requirements |
| `docker-compose.yml` | `generate_docker_compose()` | ✅ Agent + Redis/Postgres/Chroma/Milvus/MCP services |
| `.github/workflows/ci.yml` | `generate_github_actions()` | ✅ Syntax check + smoke test + Docker build |

---

## Developer Responsibilities (What Code Generator Does NOT Automate)

These require manual wiring per deployment:

| Responsibility | Why | Guidance |
|---------------|-----|----------|
| **MCP tool wiring** | `call_tool()` is a stub | Replace with HTTP call to your MCP server endpoint, or use `mcp` Python SDK |
| **Vector DB RAG** | Only SQLite LTM search is built-in | For Chroma/Pinecone/Milvus, extend `call_rag()` with the provider's client |
| **LLM provider swap** | `call_llm()` targets LM Studio | Change `LM_STUDIO_BASE_URL` env var, or edit `call_llm()` for OpenAI/Anthropic/Gemini auth |
| **Synthesis strategies** | Only concatenation is built-in | For `summarize` strategy, add a pre-synthesis `call_llm()` call before the main LLM call |
| **Parallel async** | `Send()` is sync fan-out | For true `async` concurrency with `max_concurrency`, use LangGraph async API + `asyncio` |
| **Self-harm guardrail** | No dedicated pattern | Extend `_HARMFUL_KW` list in `_build_guardrail_stubs()` |
| **Regulated advice guardrail** | No runtime check | Add domain-specific checks in `apply_output_guardrails()` |
| **OTEL/LangSmith tracing** | Only `print()` logs | Swap `print(f'[TRACE]...')` for your provider SDK |

---

## Validator Usage

```python
from backend.code_generator import CodeGenerator
gen = CodeGenerator()
code = gen.generate_workflow_script(config)
report = gen.validate_artifact(code, config)
print(f"Score: {report['score']}  Passed: {report['passed']}")
for c in report['checks']:
    print(f"  [{c['status'].upper()}] {c['category']}: {c['description']}")
```

**Score interpretation**:
- 100 = All checks pass, no stubs (green)
- 90–99 = Minor stubs/warnings (acceptable)
- <90 = Failures — investigate before shipping

---

## Changelog

| Date | Change | Score before → after |
|------|--------|----------------------|
| 2026-03-15 | Initial audit: enterprise full template | 96 → 99 |
| 2026-03-15 | Fix: validator compile check false positive (checkpointed form) | fail → pass |
| 2026-03-15 | Fix: `stmMaxEntries`/`ltmTtlDays` key aliases | partial → full |
| 2026-03-15 | Fix: `runtime.timeout_seconds` wall-clock enforcement | ❌ → ✅ |
| 2026-03-15 | Fix: `runtime.error_policy` continue/stop | ❌ → ✅ |
| 2026-03-15 | Fix: validator skip LLM warn for `human_node` type | warn → suppressed |
