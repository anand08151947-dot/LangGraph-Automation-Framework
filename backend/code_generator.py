"""
CodeGenerator: Generates standalone Python workflow scripts, requirements.txt,
and .env.template files from enterprise-format LangGraph workflow config JSON.

Handles all per-node enterprise fields:
  llm_config, pre_llm (tool_calls + rag), context (sources + synthesis +
  input_guardrails), output_schema, validation, guardrails, memory_access,
  routing_logic (list format [{condition, next}]).
"""

from datetime import datetime
from typing import Any, Dict
import json
import re


_TYPE_MAP = {
    "string": "str",
    "integer": "int",
    "float": "float",
    "boolean": "bool",
    "list": "List",
    "dict": "Dict",
}


def _schema_field_type(meta: Any) -> str:
    """Resolve state_schema field type from either 'string' or {'type':'string'} format."""
    if isinstance(meta, dict):
        return _TYPE_MAP.get(meta.get("type", "string"), "str")
    if isinstance(meta, str):
        return _TYPE_MAP.get(meta, "str")
    return "str"


def _schema_field_default(meta: Any) -> Any:
    """Resolve default value from state_schema field metadata."""
    if isinstance(meta, dict):
        raw = meta.get("default_value")
        if raw is not None:
            return raw
        return _default_for_type(meta.get("type", "string"))
    if isinstance(meta, str):
        return _default_for_type(meta)
    return ""


def _default_for_type(type_str: str) -> Any:
    return {
        "string": "", "integer": 0, "float": 0.0,
        "boolean": False, "list": [], "dict": {}
    }.get(type_str, "")


class CodeGenerator:
    """Generates runnable workflow code artifacts from a workflow config dict."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_workflow_script(self, config: dict) -> str:
        graph_name = config.get("graph_name", "GeneratedWorkflow")
        version = config.get("version", "1.0")
        author = config.get("author", "CodeGenerator")
        timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        nodes = config.get("nodes", [])
        edges = config.get("edges", [])
        state_schema = config.get("state_schema", {})
        mcp_servers = config.get("mcp_servers", {})
        retry_policy = config.get("retry_policy", {})
        checkpointing = config.get("checkpointing", {})
        obs_hooks = config.get("observability_hooks", {})

        lines: list = []

        # ── Header ───────────────────────────────────────────────────────
        lines += [
            f"# Generated workflow: {graph_name}",
            f"# Version: {version}",
            f"# Author:  {author}",
            f"# Generated: {timestamp}",
            "#",
            "# This is a scaffold — fill in LLM/tool call implementations.",
            "# All per-node settings (guardrails, pre_llm, context, validation)",
            "# are represented as structured comments and stub calls.",
            "",
        ]

        # ── Imports ───────────────────────────────────────────────────────
        lines += [
            "from typing import TypedDict, Optional, List, Dict, Any",
            "from langgraph.graph import StateGraph, END",
            "import os, json, requests",
            "from dotenv import load_dotenv",
            "",
            "load_dotenv()",
            "",
        ]

        # ── LLM helper ───────────────────────────────────────────────────
        lines += self._build_llm_helper()
        lines.append("")

        # ── Tool / RAG stubs ─────────────────────────────────────────────
        if any(n.get("pre_llm") or n.get("tools") for n in nodes):
            lines += self._build_tool_stubs(mcp_servers)
            lines.append("")

        # ── Guardrail stubs ───────────────────────────────────────────────
        needs_guardrails = any(
            n.get("guardrails") or (n.get("context") or {}).get("input_guardrails")
            for n in nodes
        )
        if needs_guardrails:
            lines += self._build_guardrail_stubs()
            lines.append("")

        # ── WorkflowState ─────────────────────────────────────────────────
        lines += self._build_state_class(state_schema)
        lines.append("")

        # ── Node functions ────────────────────────────────────────────────
        for node in nodes:
            lines += self._build_node_function(node)
            lines.append("")

        # ── Routing functions for conditional nodes ───────────────────────
        for node in nodes:
            routing_logic = node.get("routing_logic", [])
            if isinstance(routing_logic, list) and routing_logic:
                lines += self._build_routing_func(node)
                lines.append("")

        # ── Graph assembly ────────────────────────────────────────────────
        lines += self._build_graph(nodes, edges, checkpointing)
        lines.append("")

        # ── Config summary comment ────────────────────────────────────────
        if retry_policy or obs_hooks:
            lines += [
                "# ── Runtime config ─────────────────────────────────────────",
                f"# retry_policy: {json.dumps(retry_policy)}",
                f"# observability_hooks: {json.dumps(obs_hooks)}",
                "",
            ]

        # ── main() ────────────────────────────────────────────────────────
        lines += self._build_main(state_schema)

        return "\n".join(lines)

    def generate_requirements(self, config: dict) -> str:
        reqs = [
            "langgraph>=0.2.0",
            "langchain-core>=0.2.0",
            "python-dotenv>=1.0.0",
            "requests>=2.31.0",
        ]

        memory = config.get("memory", {})
        stm = memory.get("short_term", {})
        ltm = memory.get("long_term", {})
        runtime = config.get("runtime", {})
        nodes = config.get("nodes", [])
        mcp_servers = config.get("mcp_servers", {})

        if stm.get("type") == "redis" or ltm.get("provider") == "redis":
            reqs.append("redis>=5.0.0")
        if ltm.get("provider") == "chroma":
            reqs.append("chromadb>=0.4.0")
        if ltm.get("provider") == "milvus":
            reqs.append("pymilvus>=2.3.0")
        if ltm.get("provider") == "pinecone":
            reqs.append("pinecone-client>=3.0.0")
        if runtime.get("checkpoint_store") == "postgres":
            reqs.append("psycopg2-binary>=2.9.0")

        # Check any node with a GPT model override
        uses_openai = any(
            "gpt" in (n.get("llm_config", {}).get("model") or "").lower()
            for n in nodes
        )
        if uses_openai:
            reqs.append("openai>=1.0.0")

        # RAG providers
        rag_providers = {
            (n.get("pre_llm") or {}).get("rag", {}).get("provider", "")
            for n in nodes
        }
        if "chroma" in rag_providers:
            reqs.append("chromadb>=0.4.0")

        return "\n".join(sorted(set(reqs))) + "\n"

    def generate_env_template(self, config: dict) -> str:
        nodes = config.get("nodes", [])
        memory = config.get("memory", {})
        stm = memory.get("short_term", {})
        ltm = memory.get("long_term", {})
        runtime = config.get("runtime", {})
        observability = runtime.get("observability", {})
        mcp_servers = config.get("mcp_servers", {})

        lines = [
            "# .env.template — copy to .env and fill in values",
            "",
            "# LM Studio (default local LLM)",
            "LM_STUDIO_BASE_URL=http://localhost:1234",
            "LM_STUDIO_MODEL=local-model",
        ]

        if any("gpt" in (n.get("llm_config", {}).get("model") or "").lower() for n in nodes):
            lines += ["", "# OpenAI", "OPENAI_API_KEY=sk-your-key-here"]

        if any("claude" in (n.get("llm_config", {}).get("model") or "").lower() for n in nodes):
            lines += ["", "# Anthropic", "ANTHROPIC_API_KEY=your-key-here"]

        if stm.get("type") == "redis" or ltm.get("provider") == "redis" or stm.get("redis_url"):
            lines += ["", "# Redis (STM/LTM)", "REDIS_URL=redis://localhost:6379"]

        if runtime.get("checkpoint_store") == "postgres":
            lines += ["", "# PostgreSQL (checkpointing)", "POSTGRES_URL=postgresql://user:pass@localhost/db"]

        if observability.get("provider") == "langsmith":
            lines += ["", "# LangSmith (tracing)", "LANGSMITH_API_KEY=your-key", "LANGSMITH_PROJECT=your-project"]

        # MCP server env vars
        if isinstance(mcp_servers, dict):
            http_servers = [k for k, v in mcp_servers.items() if isinstance(v, dict) and v.get("type") == "http"]
            for name in http_servers:
                lines += [f"", f"# MCP server: {name}", f"MCP_{name.upper()}_URL={mcp_servers[name].get('endpoint', 'http://localhost:7070')}"]

        lines += ["", "# Environment", "APP_ENV=dev"]
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_llm_helper(self) -> list:
        return [
            "# ── LLM helper ──────────────────────────────────────────────────────────",
            "LM_STUDIO_BASE_URL = os.getenv('LM_STUDIO_BASE_URL', 'http://localhost:1234')",
            "LM_STUDIO_MODEL    = os.getenv('LM_STUDIO_MODEL', 'local-model')",
            "",
            "def call_llm(system_prompt: str, user_prompt: str,",
            "             temperature: float = 0.7, max_tokens: int = 1024,",
            "             model: str = None) -> str:",
            '    """Call LM Studio /v1/chat/completions. Swap for OpenAI/Anthropic as needed."""',
            "    _model = model or LM_STUDIO_MODEL",
            "    messages = []",
            "    if system_prompt:",
            "        messages.append({'role': 'system', 'content': system_prompt})",
            "    messages.append({'role': 'user', 'content': user_prompt})",
            "    try:",
            "        resp = requests.post(",
            "            f'{LM_STUDIO_BASE_URL}/v1/chat/completions',",
            "            json={'model': _model, 'messages': messages,",
            "                  'temperature': temperature, 'max_tokens': max_tokens, 'stream': False},",
            "            timeout=120,",
            "        )",
            "        resp.raise_for_status()",
            "        return resp.json()['choices'][0]['message']['content'].strip()",
            "    except Exception as e:",
            "        print(f'[LLM ERROR] {e}')",
            "        return f'[LLM_ERROR: {e}]'",
        ]

    def _build_tool_stubs(self, mcp_servers: dict) -> list:
        lines = [
            "# ── Tool / MCP stubs ─────────────────────────────────────────────────────",
        ]
        if isinstance(mcp_servers, dict):
            for name, cfg in mcp_servers.items():
                endpoint = cfg.get("endpoint", "")
                lines.append(f"# MCP server '{name}': type={cfg.get('type')}, endpoint={endpoint or cfg.get('command','')}")
        lines += [
            "",
            "def call_tool(tool_name: str, input_text: str) -> str:",
            '    """Stub: replace with real MCP tool call or direct API call."""',
            "    print(f'[TOOL] {tool_name}: {input_text[:80]}')",
            "    return f'[TOOL_RESULT:{tool_name}] placeholder'",
            "",
            "def call_rag(collection: str, query: str, top_k: int = 5, provider: str = 'ltm') -> str:",
            '    """Stub: replace with real RAG/vector search (Chroma, LTM, Milvus, etc.)."""',
            "    print(f'[RAG] collection={collection}, query={query[:60]}')",
            "    return f'[RAG_RESULT:{collection}] placeholder'",
        ]
        return lines

    def _build_guardrail_stubs(self) -> list:
        return [
            "# ── Guardrail stubs ──────────────────────────────────────────────────────",
            "import re",
            "",
            "def apply_input_guardrails(text: str, guardrails_cfg: dict, node_id: str = '') -> str:",
            '    """Apply input context guardrails (PII redaction, length truncation, etc.)."""',
            "    max_chars = (guardrails_cfg.get('context_length') or {}).get('max_chars')",
            "    if max_chars and len(text) > max_chars:",
            "        text = text[:max_chars] + '... [TRUNCATED]'",
            "    # TODO: add PII redaction, prompt injection detection, secrets scanning",
            "    return text",
            "",
            "def apply_output_guardrails(text: str, guardrails_cfg: dict, node_id: str = '') -> str:",
            '    """Apply output safety guardrails (PII, harmful content, hate speech, etc.)."""',
            "    # TODO: wire to guardrails.py apply_guardrails()",
            "    return text",
            "",
            "def validate_output(text: str, output_schema: dict, validation_cfg: dict, node_id: str = '') -> tuple:",
            '    """Validate LLM output against schema rules. Returns (ok, error_msg, parsed)."""',
            "    fmt = output_schema.get('format', 'text')",
            "    parsed = None",
            "    if fmt == 'json':",
            "        try:",
            "            parsed = json.loads(text)",
            "        except Exception:",
            "            return False, 'Output is not valid JSON', None",
            "        req = output_schema.get('required_fields', []) + validation_cfg.get('required_fields', [])",
            "        missing = [f for f in req if f not in parsed]",
            "        if missing:",
            "            return False, f'Missing required fields: {missing}', parsed",
            "        for rule in validation_cfg.get('rules', []):",
            "            field, op, val = rule.get('field'), rule.get('operator'), rule.get('value')",
            "            fval = parsed.get(field)",
            "            if fval is not None:",
            "                ok = eval(f'{fval!r} {op} {val!r}', {}, {})  # noqa",
            "                if not ok:",
            "                    return False, f'Validation failed: {field} {op} {val} (got {fval})', parsed",
            "    return True, None, parsed",
        ]

    def _build_state_class(self, state_schema: dict) -> list:
        lines = ["# ── Workflow State ───────────────────────────────────────────────────────",
                 "class WorkflowState(TypedDict):"]
        for field, meta in state_schema.items():
            py_type = _schema_field_type(meta)
            desc = meta.get("description", "") if isinstance(meta, dict) else ""
            comment = f"  # {desc}" if desc else ""
            lines.append(f"    {field}: Optional[{py_type}]{comment}")
        lines.append("    messages: List[Dict[str, Any]]")
        lines.append("    metadata: Dict[str, Any]")
        lines.append("    sender: str")
        return lines

    def _build_node_function(self, node: dict) -> list:
        node_id: str = node.get("id", "unknown")
        node_type: str = node.get("type", "agent")
        func_name = f"node_{node_id.lower()}"
        system_prompt = node.get("system_prompt", "")
        description = node.get("description", "")
        llm_cfg = node.get("llm_config") or {}
        pre_llm = node.get("pre_llm") or {}
        ctx_cfg = node.get("context") or {}
        output_schema = node.get("output_schema") or {}
        validation_cfg = node.get("validation") or {}
        guardrails_cfg = node.get("guardrails") or {}
        memory_access = node.get("memory_access") or []
        tools = node.get("tools") or []
        routing_logic = node.get("routing_logic") or []

        lines = []

        # Human node — minimal stub
        if node_type == "human_node":
            lines.append(f"def {func_name}(state: WorkflowState) -> dict:")
            if description:
                lines.append(f'    """[HUMAN NODE] {description}"""')
            lines.append(f'    # Workflow pauses here awaiting human input/approval')
            lines.append(f'    print(f"[{node_id}] Human approval required — checkpoint.")')
            lines.append(f'    return {{**state, "sender": "{node_id}"}}')
            return lines

        # Tool node — runs tools only, no LLM
        if node_type == "tool_node":
            lines.append(f"def {func_name}(state: WorkflowState) -> dict:")
            if description:
                lines.append(f'    """[TOOL NODE] {description}"""')
            for t in tools:
                lines.append(f'    result_{t} = call_tool("{t}", str(state.get("document_text", "")))')
            lines.append(f'    return {{**state, "sender": "{node_id}"}}')
            return lines

        # Agent node — full pipeline
        lines.append(f"def {func_name}(state: WorkflowState) -> dict:")
        doc_parts = []
        if description:
            doc_parts.append(description)
        if memory_access:
            doc_parts.append(f"Memory access: {', '.join(memory_access)}")
        if tools:
            doc_parts.append(f"Tools: {', '.join(tools)}")
        if doc_parts:
            lines.append(f'    """{"  ".join(doc_parts)}"""')

        lines.append(f'    print(f"[{node_id}] starting...")')
        lines.append(f'    new_msgs = list(state.get("messages", []))')
        lines.append('')

        # ── Pre-LLM: tool calls
        tool_calls = pre_llm.get("tool_calls", [])
        if tool_calls:
            lines.append(f'    # ── Pre-LLM: Tool Calls ─────────────────────────────────')
            for tc in tool_calls:
                tc_id = tc.get("id", tc.get("tool", "tc"))
                tool = tc.get("tool", "")
                tmpl = tc.get("input_template", "")
                out_var = tc.get("output_var") or f"tc_{tc_id}"
                inject = tc.get("inject_into_context", True)
                lines.append(f'    # Tool call: {tc_id} → {tool}')
                lines.append(f'    _tc_input_{tc_id} = f"{tmpl}"  # {{state.VAR}} replaced at runtime')
                lines.append(f'    {out_var} = call_tool("{tool}", _tc_input_{tc_id})')
                if inject:
                    lines.append(f'    # {out_var} will be injected into LLM context')
            lines.append('')

        # ── Pre-LLM: RAG
        rag_cfg = pre_llm.get("rag") or {}
        if rag_cfg.get("enabled"):
            lines.append(f'    # ── Pre-LLM: RAG / Semantic Search ────────────────────────')
            provider = rag_cfg.get("provider", "ltm")
            collection = rag_cfg.get("collection", "")
            top_k = rag_cfg.get("top_k", 5)
            score_thresh = rag_cfg.get("score_threshold", 0.0)
            out_var = rag_cfg.get("output_var") or "rag_results"
            qtmpl = rag_cfg.get("query_template", "")
            lines.append(f'    # RAG: provider={provider}, collection={collection}, top_k={top_k}, score_threshold={score_thresh}')
            lines.append(f'    _rag_query = f"{qtmpl}"  # {{state.VAR}} replaced at runtime')
            lines.append(f'    {out_var} = call_rag("{collection}", _rag_query, top_k={top_k}, provider="{provider}")')
            if rag_cfg.get("inject_into_context"):
                lines.append(f'    # {out_var} will be injected into LLM context')
            lines.append('')

        # ── Context assembly
        sources = ctx_cfg.get("sources") or []
        ig_cfg = ctx_cfg.get("input_guardrails") or {}
        synthesis = ctx_cfg.get("synthesis") or {}
        if sources:
            lines.append(f'    # ── Context Sources ─────────────────────────────────────────')
            lines.append(f'    context_parts = []')
            for src in sources:
                src_type = src.get("type", "stm")
                label = src.get("label", src_type)
                if src_type == "previous_node":
                    nid = src.get("node_id", "")
                    ref = f'state["metadata"].get("{nid}", {{}}).get("output", "")' if nid else 'new_msgs[-1]["content"] if new_msgs else ""'
                    lines.append(f'    # Context source: previous_node ({nid or "last"}) — label: {label}')
                    lines.append(f'    _ctx_{src_type} = str({ref})')
                elif src_type == "stm":
                    keys = src.get("keys") or []
                    lines.append(f'    # Context source: STM keys={keys} — label: {label}')
                    if keys:
                        lines.append(f'    _ctx_stm = " | ".join(str(state.get(k, "")) for k in {keys!r})')
                    else:
                        lines.append(f'    _ctx_stm = str(state)')
                elif src_type == "ltm":
                    query = src.get("query", "")
                    limit = src.get("limit", 5)
                    lines.append(f'    # Context source: LTM query="{query}" limit={limit} — label: {label}')
                    lines.append(f'    _ctx_ltm = call_rag("ltm", "{query}", top_k={limit})')
                elif src_type == "pre_llm":
                    lines.append(f'    # Context source: pre_llm results — label: {label}')
                    lines.append(f'    _ctx_prellm = "\\n".join([v for v in [locals().get("rag_results",""), locals().get("tc_results","")] if v])')
                lines.append(f'    context_parts.append(f"[{label}]: {{_ctx_{src_type}}}")')
            strategy = synthesis.get("strategy", "concatenate")
            lines.append(f'    # Synthesis strategy: {strategy}')
            lines.append(f'    context_text = "\\n\\n".join(context_parts)')
            lines.append('')

        # ── Input guardrails
        if ig_cfg:
            lines.append(f'    # ── Input Guardrails ─────────────────────────────────────────')
            lines.append(f'    # Config: {json.dumps(ig_cfg)}')
            lines.append(f'    context_text = apply_input_guardrails(context_text, {ig_cfg!r}, "{node_id}")')
            lines.append('')
        elif sources:
            pass  # context_text already assembled

        # ── LLM call
        temp = llm_cfg.get("temperature", 0.7)
        max_tok = llm_cfg.get("max_tokens", 1024)
        model = llm_cfg.get("model")
        lines.append(f'    # ── LLM Call ──────────────────────────────────────────────────')
        lines.append(f'    # temperature={temp}, max_tokens={max_tok}, model={model!r}')
        sys_prompt_repr = system_prompt.replace('"', '\\"')
        lines.append(f'    system_prompt = "{sys_prompt_repr}"')
        ctx_var = "context_text" if sources else 'str(state.get("document_text", ""))'
        lines.append(f'    llm_output = call_llm(system_prompt, {ctx_var},')
        lines.append(f'                          temperature={temp}, max_tokens={max_tok}, model={model!r})')
        lines.append('')

        # ── Output guardrails
        if guardrails_cfg:
            lines.append(f'    # ── Output Guardrails ────────────────────────────────────────')
            lines.append(f'    # Config: {json.dumps(guardrails_cfg)}')
            lines.append(f'    llm_output = apply_output_guardrails(llm_output, {guardrails_cfg!r}, "{node_id}")')
            lines.append('')

        # ── Output validation
        if output_schema or validation_cfg.get("enabled"):
            state_key = output_schema.get("state_key")
            fmt = output_schema.get("format", "text")
            lines.append(f'    # ── Output Schema & Validation ───────────────────────────────')
            lines.append(f'    # format={fmt}, state_key={state_key!r}')
            lines.append(f'    _valid_ok, _valid_err, _parsed = validate_output(')
            lines.append(f'        llm_output, {output_schema!r}, {validation_cfg!r}, "{node_id}")')
            lines.append(f'    if not _valid_ok:')
            on_fail = validation_cfg.get("on_failure", "warn")
            lines.append(f'        print(f"[{node_id}] Validation {on_fail}: {{_valid_err}}")')
            if on_fail == "error":
                lines.append(f'        return {{**state, "sender": "{node_id}", "messages": new_msgs}}')
            lines.append(f'    _output = _parsed if _parsed is not None else llm_output')
            if state_key:
                lines.append(f'    state = {{**state, "{state_key}": _output}}')
            lines.append('')
        else:
            lines.append(f'    _output = llm_output')

        # ── Return
        lines.append(f'    new_msgs.append({{"sender": "{node_id}", "content": str(_output)}})')
        lines.append(f'    return {{**state, "messages": new_msgs, "sender": "{node_id}"}}')
        return lines

    def _build_routing_func(self, node: dict) -> list:
        """Generate a routing function for conditional nodes (enterprise list format)."""
        node_id = node["id"]
        routing_logic = node.get("routing_logic", [])
        func_name = f"route_{node_id.lower()}"
        lines = [
            f"def {func_name}(state: WorkflowState) -> str:",
            f'    """Routing function for {node_id}."""',
        ]
        for rule in routing_logic:
            condition = rule.get("condition", "")
            nxt = rule.get("next", "END")
            # Convert template-style condition to Python-evaluable expression
            py_cond = self._template_cond_to_python(condition)
            lines.append(f"    if {py_cond}:")
            lines.append(f'        return "{nxt}"')
        lines.append(f'    return "END"')
        return lines

    def _build_graph(self, nodes: list, edges: list, checkpointing: dict) -> list:
        checkpoint_nodes = checkpointing.get("nodes", [])

        lines = [
            "# ── Graph Assembly ───────────────────────────────────────────────────────",
            "workflow = StateGraph(WorkflowState)",
        ]

        func_names = {}
        for node in nodes:
            node_id: str = node.get("id", "unknown")
            func_name = f"node_{node_id.lower()}"
            func_names[node_id] = func_name
            cp_comment = "  # checkpoint" if node_id in checkpoint_nodes else ""
            lines.append(f'workflow.add_node("{node_id}", {func_name}){cp_comment}')

        if nodes:
            first_id = nodes[0].get("id", "")
            lines.append(f'workflow.set_entry_point("{first_id}")')

        # Edges from explicit edges list
        added_edges: set = set()
        for edge in edges:
            src = edge.get("from") or edge.get("source", "")
            dst = edge.get("to") or edge.get("target", "")
            condition = edge.get("condition")
            if src and dst and not condition:
                dst_target = "END" if dst.upper() == "END" else f'"{dst}"'
                lines.append(f'workflow.add_edge("{src}", {dst_target})')
                added_edges.add(src)

        # Simple next edges from node config (for nodes without routing_logic)
        for node in nodes:
            node_id = node.get("id", "")
            nxt = node.get("next", "")
            routing_logic = node.get("routing_logic") or []
            if nxt and node_id not in added_edges and not routing_logic:
                dst_target = "END" if nxt.upper() == "END" else f'"{nxt}"'
                lines.append(f'workflow.add_edge("{node_id}", {dst_target})')

        # Conditional edges for nodes with routing_logic (list format)
        for node in nodes:
            node_id = node.get("id", "")
            routing_logic = node.get("routing_logic")
            if not isinstance(routing_logic, list) or not routing_logic:
                continue
            route_func = f"route_{node_id.lower()}"
            targets = {r.get("next") for r in routing_logic if r.get("next")}
            targets.add("END")
            mapping = {t: ("END" if t == "END" else t) for t in targets}
            # Replace END string with actual END constant in output
            mapping_str = "{" + ", ".join(
                f'"{k}": {"END" if v == "END" else repr(v)}'
                for k, v in mapping.items()
            ) + "}"
            lines.append(f'workflow.add_conditional_edges("{node_id}", {route_func}, {mapping_str})')

        lines.append("graph = workflow.compile()")
        return lines

    def _build_main(self, state_schema: dict) -> list:
        lines = [
            "# ── Entry Point ──────────────────────────────────────────────────────────",
            "def main():",
            "    initial_state = WorkflowState(",
        ]
        for field, meta in state_schema.items():
            default = _schema_field_default(meta)
            lines.append(f"        {field}={default!r},")
        lines += [
            "        messages=[],",
            "        metadata={},",
            '        sender="",',
            "    )",
            "    result = graph.invoke(initial_state)",
            "    print('Workflow result:')",
            "    print(json.dumps({k: v for k, v in result.items() if k != 'messages'}, indent=2, default=str))",
            "",
            "",
            'if __name__ == "__main__":',
            "    main()",
        ]
        return lines

    @staticmethod
    def _template_cond_to_python(condition: str) -> str:
        """Convert template condition (confidence_score < 0.6) to Python state access."""
        # Replace bare field names with state.get("field") lookups
        # Match identifiers not preceded by quote or dot (simple heuristic)
        def replace_var(m):
            name = m.group(0)
            keywords = {"and", "or", "not", "True", "False", "None", "in", "is"}
            if name in keywords:
                return name
            # Check if it looks like a state variable (lowercase/underscore)
            if re.match(r'^[a-z][a-z0-9_]*$', name):
                return f'state.get("{name}")'
            return name
        result = re.sub(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', replace_var, condition)
        return result

    @staticmethod
    def _map_operator(op: str) -> str:
        return {"==": "==", "!=": "!=", ">": ">", "<": "<", ">=": ">=", "<=": "<="}.get(op, "==")

