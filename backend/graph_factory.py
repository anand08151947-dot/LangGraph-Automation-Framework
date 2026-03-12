"""
graph_factory.py
Builds LangGraph StateGraphs from config JSON.

Supports two formats:
  - Old format: config_json["agents"] with name/system_prompt/tools/next
  - New enterprise format: config_json["nodes"] with id/type/system_prompt/tools/
      memory_access/routing_logic/checkpoint, plus config_json["edges"],
      config_json["state_schema"], config_json["runtime"], etc.

Per-node enterprise capabilities (new):
  pre_llm       — tool calls and RAG/semantic search executed BEFORE the LLM call;
                  results are injected into the LLM context as grounding material.
                  tool_calls: list of {tool, input_template, output_var, inject_into_context}
                  rag:        {enabled, provider, collection, query_template, top_k,
                               score_threshold, output_var, inject_into_context}
  context       — inject context from: previous_node, stm, ltm, or pre_llm sources.
                  synthesis config controls how multi-source context is consolidated:
                  strategy: concatenate (default) | structured | summarize
                  prompt_template: custom consolidation instruction for 'summarize' mode
  llm_config    — per-node temperature, max_tokens, model override
  context       — inject previous_node output, STM keys, or LTM entries
  output_schema — expected output format (json/text), state_key, required_fields
  validation    — field-level rules (>=, <=, ==, etc.) with on_failure policy
  guardrails    — PII, harmful_content, self_harm, hate_speech, regulated_advice
                  with block / redact / approve actions
"""

try:
    from langgraph.graph import StateGraph, END
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    StateGraph = None  # type: ignore
    END = "__end__"

from typing import TypedDict, Any, Dict, List, Optional, get_type_hints
import json
import logging
import re

logger = logging.getLogger(__name__)

try:
    from guardrails import (
        apply_guardrails, validate_output, build_context_messages,
        apply_input_guardrails, GuardrailViolation,
    )
except ImportError:
    # graceful fallback if guardrails module not found
    def apply_guardrails(text, cfg, node_id=""): return text  # type: ignore
    def apply_input_guardrails(text, cfg, node_id=""): return text  # type: ignore
    def validate_output(text, schema, node_id=""): return True, None, None  # type: ignore
    def build_context_messages(node_cfg, state, mm=None, sid="", pre_llm_results=None): return []  # type: ignore
    class GuardrailViolation(Exception): pass  # type: ignore

# ---------------------------------------------------------------------------
# Type helpers
# ---------------------------------------------------------------------------

# Map from state_schema type strings to Python types
_TYPE_MAP: Dict[str, type] = {
    "string": str,
    "integer": int,
    "float": float,
    "boolean": bool,
    "list": list,
    "dict": dict,
}

# Default factory/value per Python type
_DEFAULT_MAP: Dict[type, Any] = {
    str: "",
    int: 0,
    float: 0.0,
    bool: False,
    list: list,   # callable → will be called to get []
    dict: dict,   # callable → will be called to get {}
}


def _make_state_class(state_schema: Dict[str, Any]):
    """Dynamically create a TypedDict class from the state_schema definition.

    Always includes base fields: messages (list), sender (str),
    metadata (dict), _step_count (int).

    Supports both old string format ("string") and new object format
    ({"type": "string", "description": "...", "default_value": "..."}).
    """
    annotations: Dict[str, type] = {
        "messages": list,
        "sender": str,
        "metadata": dict,
        "_step_count": int,
    }
    for field, ftype_or_obj in state_schema.items():
        # Support both string format and object format
        if isinstance(ftype_or_obj, dict):
            ftype = ftype_or_obj.get("type", "string")
        else:
            ftype = str(ftype_or_obj)
        annotations[field] = _TYPE_MAP.get(ftype, str)
    return TypedDict("WorkflowState", annotations)  # type: ignore[misc]


def _make_default_state(state_schema: Dict[str, Any]) -> Dict[str, Any]:
    """Build an initial state dict with all fields set to their defaults.

    Supports both old string format and new object format with default_value.
    """
    state: Dict[str, Any] = {
        "messages": [],
        "sender": "",
        "metadata": {},
        "_step_count": 0,
    }
    for field, ftype_or_obj in state_schema.items():
        # Support both string format and object format
        if isinstance(ftype_or_obj, dict):
            ftype = ftype_or_obj.get("type", "string")
            default_value_str = ftype_or_obj.get("default_value")
        else:
            ftype = str(ftype_or_obj)
            default_value_str = None

        py_type = _TYPE_MAP.get(ftype, str)

        if default_value_str is not None and default_value_str != "":
            # Parse the default_value string based on the target type
            try:
                if py_type == bool:
                    state[field] = default_value_str.lower() in ("true", "1", "yes")
                elif py_type == int:
                    state[field] = int(default_value_str)
                elif py_type == float:
                    state[field] = float(default_value_str)
                elif py_type == list:
                    state[field] = json.loads(default_value_str) if default_value_str.startswith("[") else []
                elif py_type == dict:
                    state[field] = json.loads(default_value_str) if default_value_str.startswith("{") else {}
                else:
                    state[field] = default_value_str
            except (ValueError, json.JSONDecodeError):
                default = _DEFAULT_MAP.get(py_type, "")
                state[field] = default() if callable(default) else default
        else:
            default = _DEFAULT_MAP.get(py_type, "")
            # Mutable defaults (list/dict) are factories; call them
            state[field] = default() if callable(default) else default
    return state


def _safe_eval_condition(condition: str, state: Dict[str, Any]) -> bool:
    """Safely evaluate a condition string against the current state dict.

    Supports comparison expressions like:
      task == 'research'
      confidence_score < 0.7
      missing_data == true
      retry_count > 3

    JSON booleans (true/false/null) are replaced with Python equivalents
    before eval(). eval() is executed with an empty builtins namespace so
    that only state fields are in scope.
    """
    expr = condition.strip()
    expr = re.sub(r'\btrue\b', 'True', expr)
    expr = re.sub(r'\bfalse\b', 'False', expr)
    expr = re.sub(r'\bnull\b', 'None', expr)
    try:
        return bool(eval(expr, {"__builtins__": {}}, state))  # noqa: S307
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Pre-LLM helpers: template rendering, tool calls, RAG
# ---------------------------------------------------------------------------

def _render_template(template: str, state: Dict[str, Any]) -> str:
    """Replace {state.VAR} placeholders with current state values.

    Example: "{state.task}" → state.get("task", "")
    Plain text (no placeholders) is returned as-is.
    """
    def _replacer(m: re.Match) -> str:
        key = m.group(1)
        val = state.get(key, "")
        return str(val) if val is not None else ""

    return re.sub(r'\{state\.([^}]+)\}', _replacer, template)


def _execute_tool_call(
    tool_name: str,
    tool_input: str,
    bound_tools: Optional[Dict[str, Any]] = None,
) -> str:
    """Execute a named tool and return its string result.

    If `bound_tools` contains a callable for `tool_name` it is invoked.
    Otherwise returns a descriptive placeholder so the pipeline keeps moving.
    """
    if bound_tools:
        tool = bound_tools.get(tool_name)
        if callable(tool):
            try:
                result = tool(tool_input)
                return str(result) if result is not None else ""
            except Exception as exc:
                logger.warning("Tool %s raised: %s", tool_name, exc)
                return f"[Tool error: {exc}]"
    # Stub — records intent; replace with live MCP call when bound
    return (
        f"[Tool:{tool_name}] Called with input: {tool_input[:200]}"
        f"{'...' if len(tool_input) > 200 else ''}"
    )


def _execute_rag_search(
    rag_cfg: Dict[str, Any],
    query: str,
    memory_manager=None,
    session_id: str = "",
) -> str:
    """Execute a RAG/semantic search and return formatted retrieved chunks.

    Supports:
      - LTM-backed search via memory_manager (provider == 'ltm' or no provider)
      - Extensible: swap in chromadb / milvus / pinecone in production

    Returns a formatted multi-chunk string or a placeholder if no results.
    """
    top_k: int = rag_cfg.get("top_k", 5)
    collection: str = rag_cfg.get("collection", "")
    provider: str = rag_cfg.get("provider", "ltm").lower()
    score_threshold: float = rag_cfg.get("score_threshold", 0.0)

    # ── LTM-backed search ─────────────────────────────────────────────
    if memory_manager is not None and provider in ("ltm", "local", ""):
        try:
            entries = memory_manager.query_ltm(
                session_id=session_id,
                keyword=query,
                limit=top_k,
            )
            if entries:
                chunks = [
                    f"[Doc {i+1}] {e.get('content', str(e))}"
                    for i, e in enumerate(entries)
                ]
                return "\n\n".join(chunks)
        except Exception as exc:
            logger.warning("LTM RAG search failed: %s", exc)

    # ── External provider stubs (wire in SDK calls here) ──────────────
    # chroma / milvus / pinecone / weaviate → implement via provider SDK
    # Example hook (replace with real implementation):
    #   if provider == "chroma":
    #       from chromadb import Client
    #       client = Client(); coll = client.get_collection(collection)
    #       results = coll.query(query_texts=[query], n_results=top_k)
    #       return "\n\n".join([f"[Doc {i+1}] {d}" for i,d in enumerate(results["documents"][0])])

    # Placeholder so pipeline keeps moving
    return (
        f"[RAG:{provider}/{collection}] Search query='{query[:100]}' top_k={top_k} "
        f"— no live provider wired yet. Wire SDK in _execute_rag_search()."
    )



def _normalize_nodes(config_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalise old agents[] or new nodes[] into a common list of node dicts.

    Every returned node dict contains:
      id, type, system_prompt, tools, memory_access,
      routing_logic, checkpoint, next,
      llm_config, context, output_schema, validation, guardrails
    """
    nodes: List[Dict[str, Any]] = []

    if "nodes" in config_json:
        # ── New enterprise format ──────────────────────────────────────────
        for node in config_json["nodes"]:
            nodes.append({
                "id": node["id"],
                "type": node.get("type", "agent"),
                "system_prompt": node.get("system_prompt", ""),
                "tools": node.get("tools", []),
                "memory_access": node.get("memory_access", {}),
                "routing_logic": node.get("routing_logic", []),
                "checkpoint": node.get("checkpoint", False),
                "next": node.get("next"),
                # ── Per-node advanced config ────────────────────────────
                "pre_llm": node.get("pre_llm") or {},
                "llm_config": node.get("llm_config") or {},
                "context": node.get("context") or {},
                "output_schema": node.get("output_schema") or {},
                "validation": node.get("validation") or {},
                "guardrails": node.get("guardrails") or {},
            })

    elif "agents" in config_json:
        # ── Old simple format ──────────────────────────────────────────────
        for agent in config_json["agents"]:
            nodes.append({
                "id": agent["name"],
                "type": "agent",
                "system_prompt": agent.get("system_prompt", ""),
                "tools": agent.get("tools", []),
                "memory_access": {},
                "routing_logic": [],
                "checkpoint": False,
                "next": agent.get("next", "END"),
                "pre_llm": {},
                "llm_config": {},
                "context": {},
                "output_schema": {},
                "validation": {},
                "guardrails": {},
            })

    return nodes


# ---------------------------------------------------------------------------
# Node-function factories
# ---------------------------------------------------------------------------

def _agent_node_func(
    node: Dict[str, Any],
    memory_manager=None,
    session_id: str = "",
    bound_tools: Optional[Dict[str, Any]] = None,
):
    """Return a LangGraph node function for a standard LLM agent node.

    Pipeline (in order):
      0. Execute pre-LLM steps (tool calls + RAG search) — results injected into context
      1. Build context from sources (previous_node / STM / LTM)
      2. Apply INPUT guardrails to context text (PII, injection, secrets, length…)
      3. Compose effective prompt (system_prompt + pre_llm results + safe context)
      4. Call LLM (simulated; replace with real call in production)
      5. Apply OUTPUT guardrails to LLM response
      6. Validate output against output_schema rules
      7. Store result in state_key
    """
    node_id = node["id"]
    system_prompt = node.get("system_prompt", "")
    tools = node.get("tools", [])
    pre_llm_cfg = node.get("pre_llm") or {}
    llm_cfg = node.get("llm_config") or {}
    output_schema = node.get("output_schema") or {}
    guardrails_cfg = node.get("guardrails") or {}
    validation_cfg = node.get("validation") or {}
    ctx_config = node.get("context") or {}
    input_guardrails_cfg = ctx_config.get("input_guardrails") or {}
    state_key = output_schema.get("state_key") or None

    def agent_node(state: Dict[str, Any]) -> Dict[str, Any]:
        new_messages = list(state.get("messages", []))
        new_metadata = dict(state.get("metadata", {}))
        pre_llm_results: List[str] = []
        pre_llm_summary: List[Dict[str, Any]] = []

        # ── 0. Pre-LLM: Tool Calls ────────────────────────────────────────
        for tc in pre_llm_cfg.get("tool_calls", []):
            tc_id = tc.get("id", tc.get("tool", "unknown"))
            tool_name = tc.get("tool", "")
            input_template = tc.get("input_template", "")
            inject = tc.get("inject_into_context", True)
            out_var = tc.get("output_var")

            rendered_input = _render_template(input_template, state)
            result_text = _execute_tool_call(tool_name, rendered_input, bound_tools)

            if out_var:
                state = {**state, out_var: result_text}
            if inject:
                pre_llm_results.append(f"[Tool: {tool_name}]\n{result_text}")
            pre_llm_summary.append({
                "id": tc_id, "tool": tool_name,
                "input": rendered_input[:200], "inject": inject,
                "output_var": out_var,
            })
            logger.info("Node %s pre_llm tool_call: %s", node_id, tc_id)

        # ── 0b. Pre-LLM: RAG / Semantic Search ───────────────────────────
        rag_cfg = pre_llm_cfg.get("rag") or {}
        if rag_cfg.get("enabled"):
            query_template = rag_cfg.get("query_template", "")
            query = _render_template(query_template, state)
            rag_text = _execute_rag_search(rag_cfg, query, memory_manager, session_id)
            out_var = rag_cfg.get("output_var")
            inject = rag_cfg.get("inject_into_context", True)
            if out_var:
                state = {**state, out_var: rag_text}
            if inject:
                pre_llm_results.append(f"[RAG: {rag_cfg.get('provider','ltm')}/{rag_cfg.get('collection','')}]\n{rag_text}")
            pre_llm_summary.append({
                "type": "rag", "provider": rag_cfg.get("provider"),
                "collection": rag_cfg.get("collection"), "query": query[:200],
                "inject": inject, "output_var": out_var,
            })
            logger.info("Node %s pre_llm RAG: query='%s'", node_id, query[:80])

        # ── 1. Build context from sources ─────────────────────────────────
        ctx_messages = build_context_messages(
            node, state, memory_manager, session_id,
            pre_llm_results=pre_llm_results,
        )

        # ── 2. Apply INPUT guardrails to assembled context text ────────────
        context_text = "\n".join(m["content"] for m in ctx_messages)
        input_guardrail_status = "passed"
        if context_text and input_guardrails_cfg:
            original_ctx = context_text
            try:
                context_text = apply_input_guardrails(
                    context_text, input_guardrails_cfg, node_id
                )
                if context_text != original_ctx:
                    input_guardrail_status = "processed"
            except GuardrailViolation as gv:
                input_guardrail_status = "blocked"
                logger.warning("Node %s input blocked by guardrail: %s", node_id, gv)
                new_metadata[node_id] = {
                    "system_prompt": system_prompt,
                    "executed": True,
                    "input_guardrail_status": "blocked",
                    "input_guardrail_violation": {"check": gv.check, "detail": str(gv)},
                }
                new_messages.append({
                    "sender": node_id,
                    "content": f"[INPUT BLOCKED by guardrail:{gv.check}] {gv.detail}",
                    "input_guardrail_status": "blocked",
                })
                return {
                    **state,
                    "messages": new_messages,
                    "sender": node_id,
                    "metadata": new_metadata,
                    "_step_count": state.get("_step_count", 0) + 1,
                }

        # ── 3. Compose effective prompt (system_prompt + pre_llm + context) ─
        effective_prompt = system_prompt
        sections: List[str] = []
        if pre_llm_results:
            sections.append("--- Grounding Material (Tool Calls & RAG) ---\n" +
                            "\n\n".join(pre_llm_results))
        if context_text:
            sections.append("--- Context ---\n" + context_text)
        if sections:
            effective_prompt = system_prompt + "\n\n" + "\n\n".join(sections)

        # ── 4. LLM config (passed to real LLM caller downstream) ──────────
        llm_params = {
            "temperature": llm_cfg.get("temperature", 0.7),
            "max_tokens": llm_cfg.get("max_tokens", 1024),
            "model": llm_cfg.get("model") or None,
        }

        # ── 5. Simulated LLM output (replace with real call in production) ─
        simulated_output = effective_prompt

        # ── 6. Apply OUTPUT guardrails to the LLM response ────────────────
        guardrail_status = "passed"
        guardrail_violation = None
        processed_output = simulated_output
        if guardrails_cfg:
            try:
                processed_output = apply_guardrails(
                    simulated_output, guardrails_cfg, node_id
                )
                if processed_output != simulated_output:
                    guardrail_status = "redacted"
            except GuardrailViolation as gv:
                guardrail_status = "blocked"
                guardrail_violation = {"check": gv.check, "detail": str(gv)}
                logger.warning("Node %s output blocked by guardrail: %s", node_id, gv)
                new_metadata[node_id] = {
                    "system_prompt": system_prompt,
                    "llm_config": llm_params,
                    "tools": tools,
                    "executed": True,
                    "input_guardrail_status": input_guardrail_status,
                    "guardrail_status": "blocked",
                    "guardrail_violation": guardrail_violation,
                }
                new_messages.append({
                    "sender": node_id,
                    "content": f"[BLOCKED by guardrail:{gv.check}] {gv.detail}",
                    "guardrail_status": "blocked",
                })
                return {
                    **state,
                    "messages": new_messages,
                    "sender": node_id,
                    "metadata": new_metadata,
                    "_step_count": state.get("_step_count", 0) + 1,
                }

        # ── 7. Validate output schema ──────────────────────────────────────
        validation_ok = True
        validation_error = None
        parsed_output = None
        if output_schema.get("format") or validation_cfg.get("enabled"):
            merged_schema = dict(output_schema)
            if validation_cfg.get("rules"):
                merged_schema.setdefault("validation", {})["rules"] = validation_cfg["rules"]
            if validation_cfg.get("required_fields"):
                merged_schema["required_fields"] = validation_cfg["required_fields"]
            validation_ok, validation_error, parsed_output = validate_output(
                processed_output, merged_schema, node_id
            )
            if not validation_ok:
                on_failure = validation_cfg.get("on_failure") or output_schema.get("on_failure", "warn")
                logger.warning("Node %s validation failed: %s", node_id, validation_error)
                if on_failure == "error":
                    new_messages.append({
                        "sender": node_id,
                        "content": f"[VALIDATION ERROR] {validation_error}",
                        "validation_status": "failed",
                    })
                    new_metadata[node_id] = {
                        "executed": True, "validation_status": "failed",
                        "validation_error": validation_error,
                    }
                    return {
                        **state,
                        "messages": new_messages,
                        "sender": node_id,
                        "metadata": new_metadata,
                        "_step_count": state.get("_step_count", 0) + 1,
                    }

        # ── 8. Store result in state_key if defined ────────────────────────
        state_updates: Dict[str, Any] = {}
        if state_key and state_key in state:
            state_updates[state_key] = parsed_output if parsed_output is not None else processed_output

        # ── 9. Append message + metadata ──────────────────────────────────
        new_messages.append({
            "sender": node_id,
            "content": processed_output,
            "tools_available": tools,
            "llm_config": llm_params,
            "pre_llm": pre_llm_summary if pre_llm_summary else None,
            "input_guardrail_status": input_guardrail_status,
            "guardrail_status": guardrail_status,
            "validation_ok": validation_ok,
        })
        new_metadata[node_id] = {
            "system_prompt": system_prompt,
            "llm_config": llm_params,
            "tools": tools,
            "pre_llm": pre_llm_summary if pre_llm_summary else None,
            "executed": True,
            "input_guardrail_status": input_guardrail_status,
            "guardrail_status": guardrail_status,
            "validation_ok": validation_ok,
            "validation_error": validation_error,
            "state_key": state_key,
        }
        return {
            **state,
            **state_updates,
            "messages": new_messages,
            "sender": node_id,
            "metadata": new_metadata,
            "_step_count": state.get("_step_count", 0) + 1,
        }

    agent_node.__name__ = node_id
    return agent_node


def _tool_node_func(node: Dict[str, Any]):
    """Return a node function for a tool-only node (no LLM)."""
    node_id = node["id"]
    tools = node.get("tools", [])

    def tool_node(state: Dict[str, Any]) -> Dict[str, Any]:
        new_messages = list(state.get("messages", []))
        new_messages.append({
            "sender": node_id,
            "content": f"Tool node executed: {tools}",
            "tools": tools,
        })
        return {
            **state,
            "messages": new_messages,
            "sender": node_id,
            "_step_count": state.get("_step_count", 0) + 1,
        }

    tool_node.__name__ = node_id
    return tool_node


def _conditional_node_func(node: Dict[str, Any]):
    """Return a routing-only node (no execution, just passes state through)."""
    node_id = node["id"]

    def conditional_node(state: Dict[str, Any]) -> Dict[str, Any]:
        return {**state, "sender": node_id}

    conditional_node.__name__ = node_id
    return conditional_node


def _human_node_func(node: Dict[str, Any]):
    """Return a human-approval checkpoint node (pauses for human input)."""
    node_id = node["id"]

    def human_node(state: Dict[str, Any]) -> Dict[str, Any]:
        new_messages = list(state.get("messages", []))
        new_messages.append({
            "sender": node_id,
            "content": "[HUMAN APPROVAL REQUIRED] Workflow paused at checkpoint.",
        })
        return {
            **state,
            "messages": new_messages,
            "sender": node_id,
            "_step_count": state.get("_step_count", 0) + 1,
        }

    human_node.__name__ = node_id
    return human_node


def _pick_node_func(
    node: Dict[str, Any],
    memory_manager=None,
    session_id: str = "",
    bound_tools: Optional[Dict[str, Any]] = None,
):
    """Select and return the appropriate node function based on node type."""
    ntype = node.get("type", "agent")
    if ntype == "tool_node":
        return _tool_node_func(node)
    if ntype == "conditional":
        return _conditional_node_func(node)
    if ntype == "human_node":
        return _human_node_func(node)
    return _agent_node_func(node, memory_manager, session_id, bound_tools)  # default: agent


# ---------------------------------------------------------------------------
# Routing function factory
# ---------------------------------------------------------------------------

def _make_routing_func(node: Dict[str, Any], max_iterations: int):
    """Build a routing function for add_conditional_edges.

    Evaluates routing_logic conditions against state in order and returns
    the label of the first matching rule. Falls back to "__end__" when
    max_iterations is exceeded or no condition matches.
    """
    routing_logic = node.get("routing_logic", [])
    node_id = node["id"]

    def routing_func(state: Dict[str, Any]) -> str:
        # Guard: enforce max_iterations
        if state.get("_step_count", 0) >= max_iterations:
            return "__end__"
        # Evaluate rules in declaration order
        for rule in routing_logic:
            condition = rule.get("condition", "")
            next_node = rule.get("next", "END")
            if not condition or _safe_eval_condition(condition, state):
                return next_node if next_node != "END" else "__end__"
        return "__end__"

    routing_func.__name__ = f"route_{node_id}"
    return routing_func


# ---------------------------------------------------------------------------
# Observability + error-policy wrapper
# ---------------------------------------------------------------------------

def _wrap_node_with_observability(
    node_func,
    node_id: str,
    obs_hooks: Dict[str, Any],
    error_policy: str,
) -> Any:
    """Wrap a node function with observability logging and error policy enforcement.

    obs_hooks keys:
      trace_nodes          — log entry/exit for every node
      log_state_transitions — log which state keys changed after the node
      capture_agent_outputs — log the last message content (first 200 chars)

    error_policy:
      fail_fast — re-raise exceptions (default LangGraph behavior)
      continue  — catch, log, and return state unchanged so workflow proceeds
    """
    trace_nodes = obs_hooks.get("trace_nodes", False)
    log_transitions = obs_hooks.get("log_state_transitions", False)
    capture_outputs = obs_hooks.get("capture_agent_outputs", False)

    def wrapped(state: Dict[str, Any]) -> Dict[str, Any]:
        if trace_nodes:
            logger.info("Node [%s] ENTER — step=%s", node_id, state.get("_step_count", 0))

        prev_keys = set(state.keys()) if log_transitions else set()
        prev_vals = {k: v for k, v in state.items()} if log_transitions else {}

        try:
            result = node_func(state)
        except Exception as exc:
            if error_policy == "continue":
                logger.error("Node [%s] error (error_policy=continue, skipping): %s", node_id, exc)
                # Return state with incremented step count so workflow keeps moving
                result = {**state, "_step_count": state.get("_step_count", 0) + 1}
            else:  # fail_fast (default)
                logger.error("Node [%s] error (error_policy=fail_fast): %s", node_id, exc)
                raise

        if log_transitions and prev_vals:
            changed = [k for k in result if result.get(k) != prev_vals.get(k) and k != "messages"]
            if changed:
                logger.info("Node [%s] state changed: %s", node_id, changed)

        if capture_outputs:
            msgs = result.get("messages", [])
            if msgs:
                last_msg = msgs[-1] if isinstance(msgs[-1], dict) else {}
                content = str(last_msg.get("content", ""))
                if content:
                    logger.info("Node [%s] output: %s", node_id, content[:200])

        if trace_nodes:
            logger.info("Node [%s] EXIT — step=%s", node_id, result.get("_step_count", 0))

        return result

    wrapped.__name__ = node_id
    return wrapped


# ---------------------------------------------------------------------------
# GraphFactory
# ---------------------------------------------------------------------------

class GraphFactory:
    """Builds LangGraph StateGraphs from config JSON.

    Supports both the old agents[] format and the new enterprise nodes[] format.
    """

    def __init__(self, agent_state_cls=None, mcp_tool_binder=None, memory_manager=None):
        """
        agent_state_cls: Ignored; kept for backward compatibility.
                         State is now TypedDict-based.
        mcp_tool_binder: Optional MCPAutoBinder for tool discovery/binding.
        memory_manager:  Optional MemoryManager for STM/LTM context injection.
        """
        self.mcp_tool_binder = mcp_tool_binder
        self.memory_manager = memory_manager

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_from_config(
        self,
        config_json: Dict[str, Any],
        session_id: str = "",
        bound_tools: Optional[Dict[str, Any]] = None,
    ):
        """Build and compile a LangGraph StateGraph from config_json.

        Detects format (old agents[] vs new nodes[]), normalises nodes,
        builds TypedDict state, adds nodes/edges, and compiles the graph.

        session_id   — passed to per-node functions for STM/LTM access.
        bound_tools  — dict of {tool_name: callable} for pre_llm tool execution.
                       If None, tool calls produce descriptive placeholders.
        """
        if not LANGGRAPH_AVAILABLE:
            raise ImportError(
                "langgraph is not installed. Run: pip install langgraph"
            )

        # ── Optional MCP tool binding ──────────────────────────────────
        if self.mcp_tool_binder is not None:
            try:
                config_json = self.mcp_tool_binder.bind_tools_to_agents(config_json)
            except Exception:
                pass  # Non-fatal; continue with original config

        # ── Extract top-level config sections ─────────────────────────
        runtime_cfg: Dict[str, Any] = config_json.get("runtime", {})
        state_schema: Dict[str, Any] = config_json.get("state_schema", {})
        explicit_edges: List[Dict[str, Any]] = config_json.get("edges", [])
        max_iterations: int = runtime_cfg.get("max_iterations", 20)

        # ── Runtime: timeout, error policy, concurrency ───────────────
        timeout_seconds = runtime_cfg.get("timeout_seconds")
        error_policy: str = runtime_cfg.get("error_policy", "fail_fast")
        max_concurrency = runtime_cfg.get("max_concurrency", 4)
        if timeout_seconds:
            logger.info(
                "Workflow timeout_seconds=%s noted — enforce via asyncio/threading in production.",
                timeout_seconds,
            )
        if max_concurrency:
            logger.info(
                "Workflow max_concurrency=%s noted — enforce via LangGraph thread config.",
                max_concurrency,
            )

        # ── Memory: warn on redis STM ─────────────────────────────────
        memory_cfg: Dict[str, Any] = config_json.get("memory", {})
        stm_cfg = memory_cfg.get("short_term", {})
        if stm_cfg.get("type") == "redis":
            redis_url = stm_cfg.get("redis_url", "")
            logger.warning(
                "STM type 'redis' requires external Redis setup. "
                "redis_url=%s. Install redis-py and wire MemoryManager accordingly.",
                redis_url or "(not set)",
            )

        # ── Observability hooks ────────────────────────────────────────
        obs_hooks: Dict[str, Any] = config_json.get("observability_hooks", {})
        apply_obs = bool(obs_hooks) or error_policy != "fail_fast"

        # ── Retry policy ───────────────────────────────────────────────
        retry_policy_cfg: Dict[str, Any] = config_json.get("retry_policy", {})
        max_retries: int = retry_policy_cfg.get("max_retries", 3)
        backoff_strategy: str = retry_policy_cfg.get("backoff_strategy", "fixed")
        retry_on: List[str] = retry_policy_cfg.get("retry_on", ["node_error"])
        if max_retries > 0:
            logger.info(
                "Retry policy: max_retries=%s backoff=%s retry_on=%s "
                "(increment state counter on each retry; re-raise for LangGraph retry).",
                max_retries, backoff_strategy, retry_on,
            )

        # ── Checkpointing ──────────────────────────────────────────────
        checkpointing_cfg: Dict[str, Any] = config_json.get("checkpointing", {})
        checkpoint_nodes_list: List[str] = checkpointing_cfg.get("nodes", [])

        # ── Normalise nodes ────────────────────────────────────────────
        nodes = _normalize_nodes(config_json)
        if not nodes:
            raise ValueError(
                "config_json must contain either 'agents' (old format) "
                "or 'nodes' (enterprise format)"
            )

        node_ids = [n["id"] for n in nodes]

        # ── Build TypedDict state class and StateGraph ─────────────────
        WorkflowState = _make_state_class(state_schema)
        builder = StateGraph(WorkflowState)

        # ── Add nodes ──────────────────────────────────────────────────
        for node in nodes:
            # Apply checkpoint flag from top-level checkpointing.nodes list
            if node["id"] in checkpoint_nodes_list:
                node["checkpoint"] = True

            node_func = _pick_node_func(node, self.memory_manager, session_id, bound_tools)

            # Wrap with observability logging and error-policy enforcement
            if apply_obs:
                node_func = _wrap_node_with_observability(
                    node_func, node["id"], obs_hooks, error_policy
                )

            builder.add_node(node["id"], node_func)

        # ── Set entry point (first node) ───────────────────────────────
        builder.set_entry_point(node_ids[0])

        # ── Add edges ──────────────────────────────────────────────────
        # Track nodes whose outgoing edges have already been configured
        edges_set: set = set()

        # 1. Conditional edges derived from routing_logic on each node
        for node in nodes:
            nid = node["id"]
            routing_logic = node.get("routing_logic", [])
            if not routing_logic:
                continue

            routing_func = _make_routing_func(node, max_iterations)

            # Build label→target mapping for add_conditional_edges
            edge_map: Dict[str, Any] = {"__end__": END}
            for rule in routing_logic:
                next_node = rule.get("next", "END")
                edge_map[next_node] = END if next_node == "END" else next_node

            builder.add_conditional_edges(nid, routing_func, edge_map)
            edges_set.add(nid)

        # 2. Explicit edges from config_json["edges"]
        for edge in explicit_edges:
            src = edge.get("from")
            dst = edge.get("to")
            condition = edge.get("condition")
            if not src or not dst or src in edges_set:
                continue

            dst_target = END if dst == "END" else dst

            if condition:
                # Wrap condition as a simple conditional edge
                label = dst if dst != "END" else "__end__"

                def _make_cond(cond: str, lbl: str):
                    def cond_func(state: Dict[str, Any]) -> str:
                        return lbl if _safe_eval_condition(cond, state) else "__end__"
                    return cond_func

                builder.add_conditional_edges(
                    src,
                    _make_cond(condition, label),
                    {label: dst_target, "__end__": END},
                )
            else:
                builder.add_edge(src, dst_target)

            edges_set.add(src)

        # 3. Simple edges from node.next (old format or enterprise next field)
        for node in nodes:
            nid = node["id"]
            if nid in edges_set:
                continue

            next_node = node.get("next")
            if next_node:
                builder.add_edge(nid, END if next_node == "END" else next_node)
                edges_set.add(nid)
            elif nid == node_ids[-1]:
                # Last node with no outgoing edge → connect to END
                builder.add_edge(nid, END)
                edges_set.add(nid)

        # 4. Parallel execution groups — sequential fallback
        # True parallel fan-out requires LangGraph 0.2+ Send() API.
        # We add sequential edges between group nodes as a safe fallback.
        parallel_groups = config_json.get("parallel_execution", [])
        if parallel_groups:
            logger.warning(
                "parallel_execution detected (%d group(s)). True parallel fan-out "
                "requires LangGraph 0.2+ with Send() API. "
                "Adding sequential fallback edges between group nodes.",
                len(parallel_groups),
            )
            valid_node_ids = set(node_ids)
            for group in parallel_groups:
                group_name = group.get("group", "")
                group_nodes = group.get("nodes", [])
                timeout_ms = group.get("timeout_ms")
                if timeout_ms:
                    logger.info(
                        "Parallel group '%s' timeout_ms=%s — enforce via asyncio in production.",
                        group_name, timeout_ms,
                    )
                # Add sequential edges for group nodes not yet wired
                for i, nid in enumerate(group_nodes):
                    if nid not in valid_node_ids or nid in edges_set:
                        continue
                    if i < len(group_nodes) - 1:
                        next_nid = group_nodes[i + 1]
                        if next_nid in valid_node_ids:
                            builder.add_edge(nid, next_nid)
                            edges_set.add(nid)

        return builder.compile()

    def make_default_state(self, config_json: Dict[str, Any]) -> Dict[str, Any]:
        """Return the default initial state dict for a given config_json."""
        return _make_default_state(config_json.get("state_schema", {}))


# ---------------------------------------------------------------------------
# Backward compatibility shim
# ---------------------------------------------------------------------------

class AgentState:
    """Legacy class kept for backward compatibility with existing imports."""

    def __init__(self, messages=None, sender=None, metadata=None, **kwargs):
        self.messages = messages or []
        self.sender = sender or ""
        self.metadata = metadata or {}
        for k, v in kwargs.items():
            setattr(self, k, v)

    def to_dict(self) -> Dict[str, Any]:
        return {"messages": self.messages, "sender": self.sender, "metadata": self.metadata}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("Usage: python graph_factory.py <workflow_config.json>")
        sys.exit(1)

    with open(sys.argv[1]) as f:
        cfg = json.load(f)

    factory = GraphFactory()
    graph = factory.build_from_config(cfg)
    print("LangGraph StateGraph compiled successfully.")
