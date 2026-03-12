"""
CodeGenerator: Generates standalone Python workflow scripts, requirements.txt,
and .env.template files from enterprise-format LangGraph workflow config JSON.
"""

from datetime import datetime
from typing import Any, Dict


_TYPE_MAP = {
    "string": "str",
    "integer": "int",
    "float": "float",
    "boolean": "bool",
    "list": "List",
    "dict": "Dict",
}


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

        lines: list[str] = []

        # Header comment
        lines += [
            f"# Generated workflow: {graph_name}",
            f"# Version: {version}",
            f"# Author:  {author}",
            f"# Generated: {timestamp}",
            "",
        ]

        # Imports
        lines += [
            "from typing import TypedDict, Optional, List, Dict, Any",
            "from langgraph.graph import StateGraph, END",
            "import os",
            "from dotenv import load_dotenv",
            "",
            "load_dotenv()",
            "",
        ]

        # WorkflowState
        lines += self._build_state_class(state_schema)
        lines.append("")

        # Node functions
        for node in nodes:
            lines += self._build_node_function(node)
            lines.append("")

        # Graph assembly
        lines += self._build_graph(nodes, edges)
        lines.append("")

        # main()
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
        mcp_servers = config.get("mcp_servers", [])

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

        uses_openai = any(
            "gpt" in (n.get("llm_config", {}).get("model", "")).lower()
            for n in nodes
        ) or any(
            s.get("type") == "http" for s in mcp_servers
        )
        if uses_openai:
            reqs.append("openai>=1.0.0")

        return "\n".join(reqs) + "\n"

    def generate_env_template(self, config: dict) -> str:
        nodes = config.get("nodes", [])
        memory = config.get("memory", {})
        stm = memory.get("short_term", {})
        ltm = memory.get("long_term", {})
        runtime = config.get("runtime", {})
        observability = runtime.get("observability", {})

        lines = [
            "# .env.template — copy to .env and fill in values",
            "LM_STUDIO_BASE_URL=http://localhost:1234",
            "LM_STUDIO_MODEL=local-model",
        ]

        uses_openai = any(
            "gpt" in (n.get("llm_config", {}).get("model", "")).lower()
            for n in nodes
        )
        if uses_openai:
            lines.append("OPENAI_API_KEY=sk-your-key-here")

        uses_redis = (
            stm.get("type") == "redis"
            or ltm.get("provider") == "redis"
            or bool(stm.get("redis_url"))
        )
        if uses_redis:
            lines.append("REDIS_URL=redis://localhost:6379")

        if runtime.get("checkpoint_store") == "postgres":
            lines.append("POSTGRES_URL=postgresql://user:pass@localhost/db")

        if observability.get("provider") == "langsmith":
            lines.append("LANGSMITH_API_KEY=your-key")
            lines.append("LANGSMITH_PROJECT=your-project")

        lines.append("APP_ENV=dev")

        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_state_class(self, state_schema: dict) -> list[str]:
        lines = ["class WorkflowState(TypedDict):"]
        for field, meta in state_schema.items():
            py_type = _TYPE_MAP.get(meta.get("type", "string"), "str")
            lines.append(f"    {field}: {py_type}")
        lines.append("    messages: List[str]")
        lines.append("    metadata: Dict[str, Any]")
        return lines

    def _build_node_function(self, node: dict) -> list[str]:
        node_id: str = node.get("id", "unknown")
        func_name = f"node_{node_id.lower()}"
        system_prompt = node.get("system_prompt", "")
        llm_config = node.get("llm_config", {})
        routing_logic = node.get("routing_logic", {})

        lines = [f"def {func_name}(state: WorkflowState) -> dict:"]

        if system_prompt:
            lines.append(f'    """{system_prompt}"""')

        if llm_config:
            temp = llm_config.get("temperature", "N/A")
            max_tok = llm_config.get("max_tokens", "N/A")
            lines.append(f"    # LLM config: temperature={temp}, max_tokens={max_tok}")

        lines.append(f'    print(f"[{node_id}] executing...")')

        if routing_logic:
            conditions = routing_logic.get("conditions", [])
            for cond in conditions:
                field = cond.get("field", "")
                op = cond.get("operator", "==")
                value = cond.get("value", "")
                target = cond.get("target", "END")
                py_op = self._map_operator(op)
                lines.append(f"    if state.get('{field}') {py_op} {repr(value)}:")
                lines.append(f"        return {{'next_node': '{target}'}}")
            default = routing_logic.get("default", "END")
            lines.append(f"    return {{'next_node': '{default}'}}")
        else:
            lines.append("    return {}")

        return lines

    def _build_graph(self, nodes: list, edges: list) -> list[str]:
        lines = [
            "# --- Graph assembly ---",
            "workflow = StateGraph(WorkflowState)",
        ]

        func_names = {}
        for node in nodes:
            node_id: str = node.get("id", "unknown")
            func_name = f"node_{node_id.lower()}"
            func_names[node_id] = func_name
            lines.append(f'workflow.add_node("{node_id}", {func_name})')

        if nodes:
            first_id = nodes[0].get("id", "")
            lines.append(f'workflow.set_entry_point("{first_id}")')

        # Edges from edges list
        added_edges: set = set()
        for edge in edges:
            src = edge.get("from") or edge.get("source", "")
            dst = edge.get("to") or edge.get("target", "")
            if src and dst:
                if dst.upper() == "END":
                    lines.append(f'workflow.add_edge("{src}", END)')
                else:
                    lines.append(f'workflow.add_edge("{src}", "{dst}")')
                added_edges.add(src)

        # Nodes with next=END and no routing_logic
        for node in nodes:
            node_id = node.get("id", "")
            nxt = node.get("next", "")
            routing_logic = node.get("routing_logic", {})
            if nxt and node_id not in added_edges:
                if nxt.upper() == "END":
                    lines.append(f'workflow.add_edge("{node_id}", END)')
                elif not routing_logic:
                    lines.append(f'workflow.add_edge("{node_id}", "{nxt}")')

        # Conditional edges for nodes with routing_logic
        for node in nodes:
            node_id = node.get("id", "")
            routing_logic = node.get("routing_logic", {})
            if routing_logic:
                conditions = routing_logic.get("conditions", [])
                targets = {c.get("target") for c in conditions}
                targets.add(routing_logic.get("default", "END"))
                mapping = {t: (END if t == "END" else t) for t in targets if t}
                lines.append(
                    f'workflow.add_conditional_edges("{node_id}", {func_names[node_id]}, {mapping!r})'
                )

        lines.append("graph = workflow.compile()")
        return lines

    def _build_main(self, state_schema: dict) -> list[str]:
        lines = ["def main():"]
        lines.append("    initial_state = WorkflowState(")
        for field, meta in state_schema.items():
            default = meta.get("default_value", self._default_for_type(meta.get("type", "string")))
            lines.append(f"        {field}={default!r},")
        lines.append("        messages=[],")
        lines.append("        metadata={},")
        lines.append("    )")
        lines.append("    result = graph.invoke(initial_state)")
        lines.append("    print('Workflow result:', result)")
        lines.append("")
        lines.append("")
        lines.append('if __name__ == "__main__":')
        lines.append("    main()")
        return lines

    @staticmethod
    def _map_operator(op: str) -> str:
        return {"==": "==", "!=": "!=", ">": ">", "<": "<", ">=": ">=", "<=": "<="}.get(op, "==")

    @staticmethod
    def _default_for_type(type_str: str) -> Any:
        return {"string": "", "integer": 0, "float": 0.0, "boolean": False, "list": [], "dict": {}}.get(type_str, "")
