"""
graph_factory.py
Builds LangGraph StateGraphs from config JSON.

Supports two formats:
  - Old format: config_json["agents"] with name/system_prompt/tools/next
  - New enterprise format: config_json["nodes"] with id/type/system_prompt/tools/
      memory_access/routing_logic/checkpoint, plus config_json["edges"],
      config_json["state_schema"], config_json["runtime"], etc.
"""

try:
    from langgraph.graph import StateGraph, END
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    StateGraph = None  # type: ignore
    END = "__end__"

from typing import TypedDict, Any, Dict, List, Optional, get_type_hints
import re

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


def _make_state_class(state_schema: Dict[str, str]):
    """Dynamically create a TypedDict class from the state_schema definition.

    Always includes base fields: messages (list), sender (str),
    metadata (dict), _step_count (int).
    """
    annotations: Dict[str, type] = {
        "messages": list,
        "sender": str,
        "metadata": dict,
        "_step_count": int,
    }
    for field, ftype in state_schema.items():
        annotations[field] = _TYPE_MAP.get(ftype, str)
    return TypedDict("WorkflowState", annotations)  # type: ignore[misc]


def _make_default_state(state_schema: Dict[str, str]) -> Dict[str, Any]:
    """Build an initial state dict with all fields set to their defaults."""
    state: Dict[str, Any] = {
        "messages": [],
        "sender": "",
        "metadata": {},
        "_step_count": 0,
    }
    for field, ftype in state_schema.items():
        py_type = _TYPE_MAP.get(ftype, str)
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
# Format normalisation
# ---------------------------------------------------------------------------

def _normalize_nodes(config_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalise old agents[] or new nodes[] into a common list of node dicts.

    Every returned node dict contains:
      id, type, system_prompt, tools, memory_access,
      routing_logic, checkpoint, next
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
            })

    return nodes


# ---------------------------------------------------------------------------
# Node-function factories
# ---------------------------------------------------------------------------

def _agent_node_func(node: Dict[str, Any]):
    """Return a LangGraph node function for a standard LLM agent node."""
    node_id = node["id"]
    system_prompt = node.get("system_prompt", "")
    tools = node.get("tools", [])

    def agent_node(state: Dict[str, Any]) -> Dict[str, Any]:
        new_messages = list(state.get("messages", []))
        new_messages.append({
            "sender": node_id,
            "content": system_prompt,
            "tools_available": tools,
        })
        new_metadata = dict(state.get("metadata", {}))
        new_metadata[node_id] = {
            "system_prompt": system_prompt,
            "tools": tools,
            "executed": True,
        }
        return {
            **state,
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


def _pick_node_func(node: Dict[str, Any]):
    """Select and return the appropriate node function based on node type."""
    ntype = node.get("type", "agent")
    if ntype == "tool_node":
        return _tool_node_func(node)
    if ntype == "conditional":
        return _conditional_node_func(node)
    if ntype == "human_node":
        return _human_node_func(node)
    return _agent_node_func(node)  # default: agent


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
# GraphFactory
# ---------------------------------------------------------------------------

class GraphFactory:
    """Builds LangGraph StateGraphs from config JSON.

    Supports both the old agents[] format and the new enterprise nodes[] format.
    """

    def __init__(self, agent_state_cls=None, mcp_tool_binder=None):
        """
        agent_state_cls: Ignored; kept for backward compatibility.
                         State is now TypedDict-based.
        mcp_tool_binder: Optional MCPAutoBinder for tool discovery/binding.
        """
        self.mcp_tool_binder = mcp_tool_binder

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_from_config(self, config_json: Dict[str, Any]):
        """Build and compile a LangGraph StateGraph from config_json.

        Detects format (old agents[] vs new nodes[]), normalises nodes,
        builds TypedDict state, adds nodes/edges, and compiles the graph.
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
        state_schema: Dict[str, str] = config_json.get("state_schema", {})
        explicit_edges: List[Dict[str, Any]] = config_json.get("edges", [])
        max_iterations: int = config_json.get("runtime", {}).get("max_iterations", 20)

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
            builder.add_node(node["id"], _pick_node_func(node))

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
