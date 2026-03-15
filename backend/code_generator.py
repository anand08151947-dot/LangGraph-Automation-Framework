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
    """Resolve default value from state_schema field metadata, coercing to the correct Python type."""
    if isinstance(meta, dict):
        raw = meta.get("default_value")
        field_type = meta.get("type", "string")
        if raw is not None:
            return _coerce_default(raw, field_type)
        return _default_for_type(field_type)
    if isinstance(meta, str):
        return _default_for_type(meta)
    return ""


def _coerce_default(value: Any, type_str: str) -> Any:
    """Coerce a default value (possibly a string from JSON) to the correct Python type."""
    try:
        if type_str == "float":
            return float(value)
        if type_str == "integer":
            return int(value)
        if type_str == "boolean":
            if isinstance(value, bool):
                return value
            return str(value).lower() in ("true", "1", "yes")
        if type_str == "list":
            return value if isinstance(value, list) else []
        if type_str == "dict":
            return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return _default_for_type(type_str)
    return str(value) if value is not None else ""


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
        parallel_groups = config.get("parallel_execution", [])

        lines: list = []

        # ── Header ───────────────────────────────────────────────────────
        lines += [
            f"# Generated workflow: {graph_name}",
            f"# Version: {version}",
            f"# Author:  {author}",
            f"# Generated: {timestamp}",
            "#",
            "# Fully runnable standalone script. Run: python agent.py --help",
            "# All per-node settings (guardrails, pre_llm, context, validation)",
            "# are baked in from the workflow config.",
            "",
        ]

        # ── Imports ───────────────────────────────────────────────────────
        lines += [
            "from typing import TypedDict, Optional, List, Dict, Any",
            "from langgraph.graph import StateGraph, END",
            "import os, json, math, time, sqlite3, threading, requests",
            "from dotenv import load_dotenv",
            "",
        ]
        # Conditional: Send() for parallel fan-out
        if parallel_groups:
            lines += [
                "try:",
                "    from langgraph.types import Send",
                "except ImportError:",
                "    try:",
                "        from langgraph.constants import Send  # type: ignore",
                "    except ImportError:",
                "        Send = None  # type: ignore  # parallel fan-out unavailable",
                "",
            ]
        # Conditional: SqliteSaver for checkpointing
        if checkpointing.get("enabled"):
            lines += [
                "try:",
                "    from langgraph.checkpoint.sqlite import SqliteSaver",
                "except ImportError:",
                "    SqliteSaver = None  # type: ignore  # pip install langgraph-checkpoint-sqlite",
                "",
            ]
        lines += [
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
        lines += self._build_graph(nodes, edges, checkpointing, parallel_groups)
        lines.append("")

        # ── Memory helpers (STM eviction + LTM TTL) ───────────────────────
        memory_cfg = config.get("memory", {})
        lines += self._build_memory_helpers(memory_cfg)
        lines.append("")

        # ── WorkflowRunner (retry/backoff + observability) ────────────────
        lines += self._build_workflow_runner(config, retry_policy, obs_hooks)
        lines.append("")

        # ── main() ────────────────────────────────────────────────────────
        lines += self._build_main(state_schema, retry_policy)

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
        checkpointing = config.get("checkpointing", {})

        # Add langgraph-checkpoint-sqlite when checkpointing is enabled
        if checkpointing.get("enabled"):
            reqs.append("langgraph-checkpoint-sqlite>=3.0.0")

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
        # Retry env overrides
        retry_policy = config.get("retry_policy", {})
        max_retries = int(retry_policy.get("max_retries", 3))
        backoff = retry_policy.get("backoff_strategy", "exponential")
        base_sec = float(retry_policy.get("backoff_base_seconds", 1.0))
        lines += [
            "",
            "# LLM Retry/Backoff (overrides baked-in workflow defaults)",
            f"AGENT_MAX_RETRIES={max_retries}",
            f"AGENT_BACKOFF_STRATEGY={backoff}",
            f"AGENT_BACKOFF_BASE_SEC={base_sec}",
        ]
        return "\n".join(lines) + "\n"

    def generate_docker_compose(self, config: dict) -> str:
        """
        Generate a docker-compose.yml for deploying the workflow agent.

        Services included based on config:
        - agent        — always (the generated agent.py)
        - redis        — if STM backend=redis or LTM provider=redis
        - postgres     — if runtime.checkpoint_store=postgres
        - chroma       — if any RAG provider=chroma or LTM provider=chroma
        - milvus       — if any RAG provider=milvus
        - lm-studio    — always commented out (local; can't be containerised easily)

        MCP servers of type=http or type=sse get their own service entry.
        """
        graph_name = config.get("graph_name", "workflow").lower().replace(" ", "_").replace("-", "_")
        memory = config.get("memory", {})
        stm = memory.get("short_term", {})
        ltm = memory.get("long_term", {})
        runtime = config.get("runtime", {})
        nodes = config.get("nodes", [])
        mcp_servers = config.get("mcp_servers", {}) if isinstance(config.get("mcp_servers"), dict) else {}
        observability = runtime.get("observability", {})

        needs_redis = stm.get("backend") == "redis" or ltm.get("backend") == "redis" \
                   or stm.get("type") == "redis" or ltm.get("provider") == "redis"
        needs_postgres = runtime.get("checkpoint_store") == "postgres"

        rag_providers = {(n.get("pre_llm") or {}).get("rag", {}).get("provider", "") for n in nodes}
        needs_chroma = "chroma" in rag_providers or ltm.get("provider") == "chroma" or ltm.get("backend") == "chroma"
        needs_milvus = "milvus" in rag_providers or ltm.get("provider") == "milvus"

        http_mcp = {k: v for k, v in mcp_servers.items()
                    if isinstance(v, dict) and v.get("type") in ("http", "sse", "rest")}

        depends = []
        if needs_redis:
            depends.append("redis")
        if needs_postgres:
            depends.append("postgres")
        if needs_chroma:
            depends.append("chroma")

        # ── Preamble ──────────────────────────────────────────────────────
        lines = [
            f"# docker-compose.yml - {graph_name}",
            f"# Generated by LangGraph Automation Workbench",
            f"# Usage:",
            f"#   docker-compose up --build",
            f"#   docker-compose down",
            f"#",
            f"# Before running:",
            f"#   1. Copy .env.example to .env and fill in values",
            f"#   2. Ensure LM Studio is running on the host at port 1234",
            f"#      (or update LM_STUDIO_BASE_URL in .env to point elsewhere)",
            "",
            "version: '3.9'",
            "",
            "services:",
        ]

        # ── Agent service ─────────────────────────────────────────────────
        lines += [
            f"  {graph_name}_agent:",
            f"    build:",
            f"      context: .",
            f"      dockerfile: Dockerfile",
            f"    container_name: {graph_name}_agent",
            f"    env_file: .env",
            f"    environment:",
        ]
        # Route LM Studio calls to host machine
        lines += [
            f"      - LM_STUDIO_BASE_URL=${{LM_STUDIO_BASE_URL:-http://host.docker.internal:1234}}",
        ]
        if needs_redis:
            lines.append(f"      - REDIS_URL=redis://redis:6379")
        if needs_postgres:
            lines.append(f"      - POSTGRES_URL=postgresql://pguser:pgpass@postgres:5432/{graph_name}_db")
        if needs_chroma:
            lines.append(f"      - CHROMA_HOST=chroma")
            lines.append(f"      - CHROMA_PORT=8000")
        if needs_milvus:
            lines.append(f"      - MILVUS_HOST=milvus")
            lines.append(f"      - MILVUS_PORT=19530")
        for mcp_name, mcp_cfg in http_mcp.items():
            endpoint = mcp_cfg.get("endpoint", f"http://{mcp_name}:7070")
            lines.append(f"      - MCP_{mcp_name.upper()}_URL={endpoint}")
        lines += [
            f"    volumes:",
            f"      - ./ltm.db:/app/ltm.db",
            f"      - ./logs:/app/logs",
        ]
        if depends:
            lines.append(f"    depends_on:")
            for d in depends:
                lines.append(f"      - {d}")
        lines += [
            f"    restart: unless-stopped",
            f"    extra_hosts:",
            f"      - 'host.docker.internal:host-gateway'",
            "",
        ]

        # ── Redis ─────────────────────────────────────────────────────────
        if needs_redis:
            lines += [
                "  redis:",
                "    image: redis:7-alpine",
                "    container_name: redis",
                "    ports:",
                "      - '6379:6379'",
                "    volumes:",
                "      - redis_data:/data",
                "    restart: unless-stopped",
                "",
            ]

        # ── PostgreSQL ────────────────────────────────────────────────────
        if needs_postgres:
            lines += [
                "  postgres:",
                "    image: postgres:16-alpine",
                "    container_name: postgres",
                "    environment:",
                "      POSTGRES_USER: pguser",
                "      POSTGRES_PASSWORD: pgpass",
                f"      POSTGRES_DB: {graph_name}_db",
                "    ports:",
                "      - '5432:5432'",
                "    volumes:",
                "      - pg_data:/var/lib/postgresql/data",
                "    restart: unless-stopped",
                "",
            ]

        # ── Chroma ────────────────────────────────────────────────────────
        if needs_chroma:
            lines += [
                "  chroma:",
                "    image: chromadb/chroma:latest",
                "    container_name: chroma",
                "    ports:",
                "      - '8000:8000'",
                "    volumes:",
                "      - chroma_data:/chroma/.chroma/index",
                "    restart: unless-stopped",
                "",
            ]

        # ── Milvus (standalone) ───────────────────────────────────────────
        if needs_milvus:
            lines += [
                "  milvus:",
                "    image: milvusdb/milvus:v2.4.0",
                "    container_name: milvus",
                "    command: milvus run standalone",
                "    environment:",
                "      ETCD_USE_EMBED: 'true'",
                "      ETCD_DATA_DIR: /var/lib/milvus/etcd",
                "      COMMON_STORAGETYPE: local",
                "    ports:",
                "      - '19530:19530'",
                "      - '9091:9091'",
                "    volumes:",
                "      - milvus_data:/var/lib/milvus",
                "    restart: unless-stopped",
                "",
            ]

        # ── HTTP MCP servers ──────────────────────────────────────────────
        for mcp_name, mcp_cfg in http_mcp.items():
            endpoint = mcp_cfg.get("endpoint", "http://localhost:7070")
            try:
                port = int(endpoint.rstrip("/").rsplit(":", 1)[-1])
            except (ValueError, IndexError):
                port = 7070
            lines += [
                f"  {mcp_name}:",
                f"    image: {mcp_cfg.get('image', f'your-{mcp_name}-image:latest')}  # replace with real image",
                f"    container_name: {mcp_name}",
                f"    ports:",
                f"      - '{port}:{port}'",
                f"    restart: unless-stopped",
                "",
            ]

        # ── Volumes ───────────────────────────────────────────────────────
        volume_names = []
        if needs_redis:
            volume_names.append("redis_data")
        if needs_postgres:
            volume_names.append("pg_data")
        if needs_chroma:
            volume_names.append("chroma_data")
        if needs_milvus:
            volume_names.append("milvus_data")

        if volume_names:
            lines += ["volumes:"]
            for v in volume_names:
                lines.append(f"  {v}:")
            lines.append("")

        return "\n".join(lines)

    def generate_github_actions(self, config: dict) -> str:
        """Generate a GitHub Actions CI/CD workflow for the agent bundle."""
        graph_name = config.get("graph_name", "agent")
        safe_name = graph_name.lower().replace(" ", "-").replace("_", "-")
        return "\n".join([
            "name: Agent CI",
            "",
            "on:",
            "  push:",
            "    branches: [main]",
            "  pull_request:",
            "    branches: [main]",
            "",
            "jobs:",
            f"  validate-and-test-{safe_name}:",
            "    runs-on: ubuntu-latest",
            "    steps:",
            "      - uses: actions/checkout@v4",
            "",
            "      - name: Set up Python",
            "        uses: actions/setup-python@v5",
            "        with:",
            "          python-version: '3.11'",
            "",
            "      - name: Install dependencies",
            "        run: pip install -r requirements.txt",
            "",
            "      - name: Validate agent script syntax",
            "        run: python -m py_compile agent.py",
            "",
            "      - name: Smoke-test agent (dry-run)",
            "        run: |",
            "          timeout 30 python agent.py --input '{}' --output-format json || true",
            "        env:",
            "          LM_STUDIO_BASE_URL: http://localhost:1234",
            "",
            "  build-docker:",
            f"    name: Docker build ({safe_name})",
            "    runs-on: ubuntu-latest",
            "    needs: validate-and-test-" + safe_name,
            "    steps:",
            "      - uses: actions/checkout@v4",
            "      - name: Build Docker image",
            "        run: docker build -t " + safe_name + ":latest .",
        ]) + "\n"
        """Generate a minimal Dockerfile for running the agent."""
        return "\n".join([
            "FROM python:3.11-slim",
            "",
            "WORKDIR /app",
            "",
            "# Install dependencies",
            "COPY requirements.txt .",
            "RUN pip install --no-cache-dir -r requirements.txt",
            "",
            "# Copy agent",
            "COPY agent.py .",
            "COPY .env* ./",
            "",
            "# Run",
            "CMD [\"python\", \"agent.py\"]",
        ]) + "\n"


    # Private helpers
    # ------------------------------------------------------------------

    def _build_llm_helper(self) -> list:
        return [
            "# ── LLM helper ──────────────────────────────────────────────────────────",
            "LM_STUDIO_BASE_URL = os.getenv('LM_STUDIO_BASE_URL', 'http://localhost:1234')",
            "LM_STUDIO_MODEL    = os.getenv('LM_STUDIO_MODEL', 'local-model')",
            "",
            "# Retry config is baked from workflow template retry_policy",
            "_RETRY_MAX      = int(os.getenv('AGENT_MAX_RETRIES', '3'))",
            "_RETRY_BACKOFF  = os.getenv('AGENT_BACKOFF_STRATEGY', 'exponential')  # 'fixed' or 'exponential'",
            "_RETRY_BASE_SEC = float(os.getenv('AGENT_BACKOFF_BASE_SEC', '1.0'))",
            "",
            "def call_llm(system_prompt: str, user_prompt: str,",
            "             temperature: float = 0.7, max_tokens: int = 1024,",
            "             model: str = None) -> str:",
            '    """Call LM Studio /v1/chat/completions with automatic retry + exponential backoff.',
            "    Swap base URL / auth headers for OpenAI, Anthropic, Gemini, or Ollama.",
            '    """',
            "    _model = model or LM_STUDIO_MODEL",
            "    messages = []",
            "    if system_prompt:",
            "        messages.append({'role': 'system', 'content': system_prompt})",
            "    messages.append({'role': 'user', 'content': user_prompt})",
            "    last_exc: Exception = RuntimeError('LLM call failed')",
            "    for attempt in range(_RETRY_MAX + 1):",
            "        try:",
            "            resp = requests.post(",
            "                f'{LM_STUDIO_BASE_URL}/v1/chat/completions',",
            "                json={'model': _model, 'messages': messages,",
            "                      'temperature': temperature, 'max_tokens': max_tokens, 'stream': False},",
            "                timeout=120,",
            "            )",
            "            resp.raise_for_status()",
            "            return resp.json()['choices'][0]['message']['content'].strip()",
            "        except Exception as exc:",
            "            last_exc = exc",
            "            if attempt < _RETRY_MAX:",
            "                _sleep = _RETRY_BASE_SEC * math.pow(2, attempt) if _RETRY_BACKOFF == 'exponential' else _RETRY_BASE_SEC",
            "                print(f'[LLM RETRY {attempt+1}/{_RETRY_MAX}] {exc!r} — sleeping {_sleep:.1f}s')",
            "                time.sleep(min(_sleep, 30.0))",
            "    print(f'[LLM ERROR] {last_exc}')",
            "    return f'[LLM_ERROR: {last_exc}]'",
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
            '    """RAG search: LTM (SQLite) by default; extend for Chroma/Pinecone/Milvus."""',
            "    if provider == 'ltm':",
            "        try:",
            "            conn = sqlite3.connect(_memory.LTM_PATH)",
            "            rows = conn.execute(",
            "                'SELECT step_context FROM ltm WHERE session_id=? AND step_context LIKE ? LIMIT ?',",
            "                (collection, f'%{query[:80]}%', top_k),",
            "            ).fetchall()",
            "            conn.close()",
            "            if rows:",
            "                results = [json.loads(r[0]) for r in rows]",
            "                return json.dumps(results, ensure_ascii=False)[:2000]",
            "        except Exception as _e:",
            "            print(f'[RAG/ltm] {_e}')",
            "    # For chroma: import chromadb; client = chromadb.Client(); ...",
            "    # For pinecone: import pinecone; idx = pinecone.Index(collection); ...",
            "    print(f'[RAG] provider={provider}, collection={collection}, query={query[:60]}')",
            "    return f'[RAG_RESULT:{collection}] no results'",
        ]
        return lines

    def _build_guardrail_stubs(self) -> list:  # noqa: C901
        return [
            "# ── Guardrail engine ─────────────────────────────────────────────────────",
            "import re as _re",
            "",
            "# PII patterns (email, phone, SSN, credit card, IP address)",
            "_PII_PATTERNS = [",
            "    ('email',       _re.compile(r'\\b[A-Za-z0-9._%+\\-]+@[A-Za-z0-9.\\-]+\\.[A-Za-z]{2,}\\b')),",
            "    ('phone',       _re.compile(r'\\b(\\+?1[\\s.\\-]?)?\\(?\\d{3}\\)?[\\s.\\-]?\\d{3}[\\s.\\-]?\\d{4}\\b')),",
            "    ('ssn',         _re.compile(r'\\b\\d{3}-\\d{2}-\\d{4}\\b')),",
            "    ('credit_card', _re.compile(r'\\b(?:\\d{4}[\\s\\-]?){3}\\d{4}\\b')),",
            "    ('ip_address',  _re.compile(r'\\b(?:\\d{1,3}\\.){3}\\d{1,3}\\b')),",
            "]",
            "# Prompt injection patterns",
            "_INJECT_RE = _re.compile(",
            "    r'(?:ignore\\s+(?:all\\s+)?(?:previous|prior|above)\\s+instructions?'",
            "    r'|override\\s+(?:system|your)\\s+(?:prompt|instructions?|rules?)'",
            "    r'|forget\\s+(?:everything|all)\\s+(?:you\\s+)?(?:know|were\\s+told)'",
            "    r'|you\\s+are\\s+now\\s+(?:a\\s+)?(?:different|new|evil|unrestricted)'",
            "    r'|disregard\\s+(?:your|all)\\s+(?:instructions?|guidelines?|safety)'",
            "    r'|jailbreak|DAN\\s+mode|developer\\s+mode\\s+enabled)',",
            "    _re.IGNORECASE,",
            ")",
            "# Harmful content keywords",
            "_HARMFUL_KW = [",
            "    'how to make a bomb','synthesize drugs','manufacture weapons',",
            "    'instructions for violence','ddos attack','create malware','make explosives',",
            "]",
            "# Hate speech",
            "_HATE_RE = _re.compile(",
            "    r'\\b(all\\s+\\w+\\s+should\\s+(?:die|be\\s+killed|be\\s+exterminated)'",
            "    r'|inferior\\s+race|ethnic\\s+cleansing|racial\\s+extermination)\\b',",
            "    _re.IGNORECASE,",
            ")",
            "# Secrets / credentials",
            "_SECRET_PATTERNS = [",
            "    ('api_key',      _re.compile(r'\\b(?:sk|pk|rk|ak)[_\\-][A-Za-z0-9]{20,}\\b')),",
            "    ('bearer_token', _re.compile(r'\\bBearer\\s+[A-Za-z0-9\\-._~+/]{20,}\\b', _re.IGNORECASE)),",
            "    ('private_key',  _re.compile(r'-----BEGIN (?:RSA |EC )?PRIVATE KEY-----')),",
            "    ('github_token', _re.compile(r'\\bgh[pousr]_[A-Za-z0-9]{36,}\\b')),",
            "]",
            "",
            "def _apply_pii(text: str, action: str) -> str:",
            "    for pii_type, pat in _PII_PATTERNS:",
            "        if action == 'block' and pat.search(text):",
            "            raise ValueError(f'PII detected ({pii_type}) — blocked by guardrail')",
            "        if action == 'redact':",
            "            text = pat.sub(f'[{pii_type.upper()}_REDACTED]', text)",
            "    return text",
            "",
            "def apply_input_guardrails(text: str, guardrails_cfg: dict, node_id: str = '') -> str:",
            '    """Apply input guardrails: length truncation, PII redaction, prompt injection, secrets."""',
            "    # Length truncation",
            "    max_chars = (guardrails_cfg.get('context_length') or {}).get('max_chars')",
            "    if max_chars and len(text) > max_chars:",
            "        text = text[:max_chars] + '... [TRUNCATED]'",
            "    # PII on input",
            "    pii_cfg = guardrails_cfg.get('pii') or {}",
            "    if pii_cfg:",
            "        text = _apply_pii(text, pii_cfg.get('action', 'redact'))",
            "    # Prompt injection detection",
            "    inj_cfg = guardrails_cfg.get('prompt_injection') or {}",
            "    if inj_cfg and _INJECT_RE.search(text):",
            "        action = inj_cfg.get('action', 'block')",
            "        if action == 'block':",
            "            raise ValueError(f'[{node_id}] Prompt injection detected — blocked')",
            "        print(f'[GUARDRAIL:{node_id}] Prompt injection warning')",
            "    # Secrets detection",
            "    sec_cfg = guardrails_cfg.get('secrets_detection') or {}",
            "    if sec_cfg:",
            "        for sec_type, pat in _SECRET_PATTERNS:",
            "            if pat.search(text):",
            "                action = sec_cfg.get('action', 'redact')",
            "                if action == 'block':",
            "                    raise ValueError(f'[{node_id}] Secret/credential detected ({sec_type}) — blocked')",
            "                text = pat.sub(f'[{sec_type.upper()}_REDACTED]', text)",
            "    return text",
            "",
            "def apply_output_guardrails(text: str, guardrails_cfg: dict, node_id: str = '') -> str:",
            '    """Apply output guardrails: PII redaction, harmful content, hate speech detection."""',
            "    # PII",
            "    pii_cfg = guardrails_cfg.get('pii') or {}",
            "    if pii_cfg:",
            "        text = _apply_pii(text, pii_cfg.get('action', 'redact'))",
            "    # Harmful content",
            "    harm_cfg = guardrails_cfg.get('harmful_content') or {}",
            "    if harm_cfg:",
            "        low = text.lower()",
            "        for kw in _HARMFUL_KW:",
            "            if kw in low:",
            "                action = harm_cfg.get('action', 'block')",
            "                if action == 'block':",
            "                    raise ValueError(f'[{node_id}] Harmful content detected — blocked')",
            "                text = text.replace(kw, '[HARMFUL_CONTENT_REDACTED]')",
            "                break",
            "    # Hate speech",
            "    hate_cfg = guardrails_cfg.get('hate_speech') or {}",
            "    if hate_cfg and _HATE_RE.search(text):",
            "        action = hate_cfg.get('action', 'block')",
            "        if action == 'block':",
            "            raise ValueError(f'[{node_id}] Hate speech detected — blocked')",
            "        text = _HATE_RE.sub('[HATE_SPEECH_REDACTED]', text)",
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
                    # Collect the actual variable names generated by tool_calls and rag above
                    pre_llm_vars = []
                    for tc in (pre_llm.get("tool_calls") or []):
                        v = tc.get("output_var") or f"tc_{tc.get('id', tc.get('tool', 'tc'))}"
                        if tc.get("inject_into_context", True):
                            pre_llm_vars.append(v)
                    rag_out = (pre_llm.get("rag") or {}).get("output_var") or "rag_results"
                    if (pre_llm.get("rag") or {}).get("inject_into_context", True) and (pre_llm.get("rag") or {}).get("enabled"):
                        pre_llm_vars.append(rag_out)
                    if pre_llm_vars:
                        vars_list = ", ".join(f'str({v})' for v in pre_llm_vars)
                        lines.append(f'    _ctx_prellm = "\\n".join(v for v in [{vars_list}] if v)')
                    else:
                        lines.append(f'    _ctx_prellm = ""')
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

    def _build_graph(self, nodes: list, edges: list, checkpointing: dict, parallel_groups: list = None) -> list:  # noqa: C901
        """Generate graph assembly code with parallel Send() fan-out and SqliteSaver checkpointing."""
        checkpoint_nodes = checkpointing.get("nodes", [])
        checkpointing_enabled = checkpointing.get("enabled", False)
        cp_db_path = checkpointing.get("db_path", "artifacts/langgraph_checkpoints.sqlite")
        parallel_groups = parallel_groups or []

        # Build a map: node_id → group info (for nodes participating in parallel groups)
        parallel_node_ids: set = set()
        for group in parallel_groups:
            for nid in group.get("nodes", []):
                parallel_node_ids.add(nid)

        lines = [
            "# ── Graph Assembly ───────────────────────────────────────────────────────",
            "workflow = StateGraph(WorkflowState)",
        ]

        node_id_set = {n.get("id", "") for n in nodes}

        for node in nodes:
            node_id: str = node.get("id", "unknown")
            func_name = f"node_{node_id.lower()}"
            cp_comment = "  # checkpoint" if node_id in checkpoint_nodes else ""
            lines.append(f'workflow.add_node("{node_id}", {func_name}){cp_comment}')

        if nodes:
            first_id = nodes[0].get("id", "")
            lines.append(f'workflow.set_entry_point("{first_id}")')

        # ── Parallel fan-out groups via Send() ────────────────────────────
        added_edges: set = set()
        if parallel_groups:
            lines += [
                "",
                "# ── Parallel fan-out dispatcher(s) (Send() API) ─────────────────────",
            ]
            for group in parallel_groups:
                group_name = group.get("group", "fanout")
                group_nodes = [n for n in group.get("nodes", []) if n in node_id_set]
                fan_in = group.get("fan_in")
                dispatcher_id = f"__dispatch_{group_name}__"

                if len(group_nodes) < 2:
                    lines.append(f"# Parallel group '{group_name}': <2 valid nodes, skipped")
                    continue

                # Dispatcher node: passthrough (just forwards state to both branches)
                lines += [
                    f"def _dispatch_{group_name}(state: WorkflowState):",
                    f'    """Fan-out to parallel group: {group_nodes}"""',
                    f"    if Send is not None:",
                    f"        return [Send(t, state) for t in {group_nodes!r}]",
                    f"    # Send() unavailable: sequential fallback",
                    f'    return "{group_nodes[0]}"',
                    f"workflow.add_node({dispatcher_id!r}, lambda s: s)",
                    f"workflow.add_conditional_edges(",
                    f"    {dispatcher_id!r},",
                    f"    _dispatch_{group_name},",
                    f"    {{{', '.join(repr(n) + ': ' + repr(n) for n in group_nodes)}}},",
                    f")",
                ]
                added_edges.add(dispatcher_id)

                # Wire fan-in: all group nodes → fan_in node
                if fan_in and fan_in in node_id_set:
                    for nid in group_nodes:
                        lines.append(f'workflow.add_edge("{nid}", "{fan_in}")')
                        added_edges.add(nid)
            lines.append("")

        # ── Edges from explicit edges list ────────────────────────────────
        for edge in edges:
            src = edge.get("from") or edge.get("source", "")
            dst = edge.get("to") or edge.get("target", "")
            condition = edge.get("condition")
            if src and dst and not condition and src not in added_edges:
                dst_target = "END" if dst.upper() == "END" else f'"{dst}"'
                lines.append(f'workflow.add_edge("{src}", {dst_target})')
                added_edges.add(src)

        # ── Simple next edges from node config ────────────────────────────
        for node in nodes:
            node_id = node.get("id", "")
            nxt = node.get("next", "")
            routing_logic = node.get("routing_logic") or []
            if nxt and node_id not in added_edges and not routing_logic:
                dst_target = "END" if nxt.upper() == "END" else f'"{nxt}"'
                lines.append(f'workflow.add_edge("{node_id}", {dst_target})')

        # ── Conditional edges for nodes with routing_logic ────────────────
        for node in nodes:
            node_id = node.get("id", "")
            routing_logic = node.get("routing_logic")
            if not isinstance(routing_logic, list) or not routing_logic:
                continue
            route_func = f"route_{node_id.lower()}"
            targets = {r.get("next") for r in routing_logic if r.get("next")}
            targets.add("END")
            mapping = {t: ("END" if t == "END" else t) for t in targets}
            mapping_str = "{" + ", ".join(
                f'"{k}": {"END" if v == "END" else repr(v)}'
                for k, v in mapping.items()
            ) + "}"
            lines.append(f'workflow.add_conditional_edges("{node_id}", {route_func}, {mapping_str})')

        # ── Compile with optional SqliteSaver checkpointer ────────────────
        lines.append("")
        if checkpointing_enabled:
            lines += [
                "# ── LangGraph Checkpointing (SqliteSaver) ───────────────────────────",
                f"_CHECKPOINT_DB = os.getenv('CHECKPOINT_DB', {cp_db_path!r})",
                "os.makedirs(os.path.dirname(_CHECKPOINT_DB) or '.', exist_ok=True)",
                "_checkpointer = None",
                "if SqliteSaver is not None:",
                "    try:",
                "        _checkpointer = SqliteSaver.from_conn_string(_CHECKPOINT_DB)",
                "        print(f'[CHECKPOINT] SqliteSaver enabled at {_CHECKPOINT_DB!r}')",
                "    except Exception as _ce:",
                "        print(f'[CHECKPOINT] SqliteSaver init failed: {_ce} — running without checkpointer')",
                "graph = workflow.compile(checkpointer=_checkpointer) if _checkpointer else workflow.compile()",
            ]
        else:
            lines.append("graph = workflow.compile()")

        return lines

    def _build_memory_helpers(self, memory_cfg: dict) -> list:
        """Generate a self-contained MemoryManager with STM eviction (MM-2) and LTM TTL (MM-3)."""
        stm = memory_cfg.get("short_term", {}) if memory_cfg else {}
        ltm = memory_cfg.get("long_term", {}) if memory_cfg else {}
        # Support both camelCase (stmMaxEntries) and snake_case (max_entries) field names
        max_entries = int(stm.get("stmMaxEntries", stm.get("max_entries", 0)))
        # Support both camelCase (ltmTtlDays) and snake_case (ttl_days) field names
        ttl_days = float(ltm.get("ltmTtlDays", ltm.get("ttl_days", 0)))
        ltm_path = ltm.get("path", "ltm.db")

        return [
            "# ── Memory Manager ───────────────────────────────────────────────────────",
            f"# STM: in-process dict, max_entries={max_entries or 'unlimited'} (LRU eviction)",
            f"# LTM: SQLite at {ltm_path!r}, ttl_days={ttl_days or 'unlimited'}",
            "class _MemoryManager:",
            f"    MAX_STM_ENTRIES: int = {max_entries}  # 0 = unlimited; oldest session evicted when exceeded",
            f"    LTM_TTL_DAYS: float = {ttl_days}     # 0 = no pruning; rows older than N days auto-deleted",
            f"    LTM_PATH: str = {ltm_path!r}",
            "",
            "    def __init__(self):",
            "        self._stm: Dict[str, Any] = {}  # insertion-ordered for LRU",
            "        self._lock = threading.Lock()",
            "        self._init_ltm()",
            "",
            "    def _init_ltm(self) -> None:",
            "        conn = sqlite3.connect(self.LTM_PATH)",
            "        conn.execute(",
            "            'CREATE TABLE IF NOT EXISTS ltm'",
            "            '(session_id TEXT, step_idx INTEGER, step_context TEXT, timestamp REAL DEFAULT 0)'",
            "        )",
            "        try:",
            "            conn.execute('ALTER TABLE ltm ADD COLUMN timestamp REAL DEFAULT 0')",
            "        except sqlite3.OperationalError:",
            "            pass  # column already exists",
            "        conn.commit()",
            "        conn.close()",
            "",
            "    def save_stm(self, session_id: str, state: Dict[str, Any]) -> None:",
            '        """Persist latest state for session. Evicts oldest session if over MAX_STM_ENTRIES."""',
            "        with self._lock:",
            "            self._stm.pop(session_id, None)   # re-insert at end (most-recent)",
            "            self._stm[session_id] = state",
            "            if self.MAX_STM_ENTRIES > 0:",
            "                while len(self._stm) > self.MAX_STM_ENTRIES:",
            "                    del self._stm[next(iter(self._stm))]  # evict oldest",
            "",
            "    def load_stm(self, session_id: str) -> Optional[Dict[str, Any]]:",
            '        """Load last-saved state for a session (for resume support)."""',
            "        with self._lock:",
            "            return self._stm.get(session_id)",
            "",
            "    def append_ltm(self, session_id: str, entry: Dict[str, Any]) -> None:",
            '        """Append a step record to LTM. Prunes rows older than LTM_TTL_DAYS."""',
            "        conn = sqlite3.connect(self.LTM_PATH)",
            "        now = time.time()",
            "        row = conn.execute(",
            "            'SELECT MAX(step_idx) FROM ltm WHERE session_id=?', (session_id,)",
            "        ).fetchone()",
            "        idx = (row[0] or 0) + 1",
            "        conn.execute(",
            "            'INSERT INTO ltm VALUES (?, ?, ?, ?)',",
            "            (session_id, idx, json.dumps(entry), now),",
            "        )",
            "        if self.LTM_TTL_DAYS > 0:",
            "            cutoff = now - (self.LTM_TTL_DAYS * 86400)",
            "            conn.execute(",
            "                'DELETE FROM ltm WHERE session_id=? AND timestamp > 0 AND timestamp < ?',",
            "                (session_id, cutoff),",
            "            )",
            "        conn.commit()",
            "        conn.close()",
            "",
            "    def load_ltm(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:",
            '        """Load full LTM history for a session (for debugging or analytics)."""',
            "        conn = sqlite3.connect(self.LTM_PATH)",
            "        rows = conn.execute(",
            "            'SELECT step_context FROM ltm WHERE session_id=? ORDER BY step_idx LIMIT ?',",
            "            (session_id, limit),",
            "        ).fetchall()",
            "        conn.close()",
            "        return [json.loads(r[0]) for r in rows]",
            "",
            "",
            "_memory = _MemoryManager()",
        ]

    def _build_workflow_runner(self, config: dict, retry_policy: dict, obs_hooks: dict) -> list:
        """Generate run_workflow() — iterates the graph, persists memory, emits observability logs.

        NOTE: LLM retry/backoff is handled inside call_llm() itself (that's where transient
        failures occur). run_workflow() focuses on: STM resume, step-level memory persistence,
        and structured observability output per step.
        """
        trace_nodes = bool(obs_hooks.get("trace_nodes", True))
        log_transitions = bool(obs_hooks.get("log_state_transitions", True))
        capture_outputs = bool(obs_hooks.get("capture_agent_outputs", True))
        runtime_cfg = config.get("runtime") or {}
        max_iter = int(runtime_cfg.get("max_iterations", 20))
        timeout_seconds = float(runtime_cfg.get("timeout_seconds", 0))  # 0 = no wall-clock limit
        error_policy = str(runtime_cfg.get("error_policy", "stop"))     # "continue" | "stop"
        max_retries = int(retry_policy.get("max_retries", 3))
        backoff_strategy = retry_policy.get("backoff_strategy", "fixed")
        backoff_base = float(retry_policy.get("backoff_base_seconds", 1.0))

        checkpointing_enabled = bool((config.get("checkpointing") or {}).get("enabled"))

        lines = [
            "# ── Workflow Runner ──────────────────────────────────────────────────────",
            f"# LLM retry: max={max_retries}, backoff={backoff_strategy}, base={backoff_base}s (baked into call_llm)",
            f"# Observability: trace_nodes={trace_nodes}, log_transitions={log_transitions}, capture_outputs={capture_outputs}",
            f"# Runtime: max_iterations={max_iter}, timeout_seconds={timeout_seconds or 'unlimited'}, error_policy={error_policy!r}",
            "def run_workflow(initial_state: dict, session_id: str = 'run-001',",
            "                 resume: bool = False) -> dict:",
            '    """Run (or resume) the workflow, saving STM/LTM at every step.',
            "",
            "    Args:",
            "        initial_state: Starting state dict (WorkflowState fields).",
            "        session_id:    Unique ID for this run — used as the STM/LTM key.",
            "        resume:        If True, load saved STM state for session_id and continue",
            "                       from where the last run left off.",
            '    """',
            "    # ── Resume support: load prior STM state if requested",
            "    if resume:",
            "        saved = _memory.load_stm(session_id)",
            "        if saved:",
            "            state = dict(saved)",
            "            print(f'[RESUME] Loaded STM for session {session_id} ({len(state)} keys)')",
            "        else:",
            "            print(f'[RESUME] No saved state found for {session_id!r} — starting fresh')",
            "            state = dict(initial_state)",
            "    else:",
            "        state = dict(initial_state)",
            "",
            f"    MAX_ITER = {max_iter}",
            f"    _TIMEOUT_SEC = {timeout_seconds}  # 0 = no limit",
            f"    _ERROR_POLICY = {error_policy!r}  # 'continue' swallows node errors; 'stop' re-raises",
            "    step_idx = 0",
            "    _run_start = time.time()",
            "",
        ]

        # Build the graph.stream() call — wrap in error policy + timeout handling
        stream_open = "    for step_output in graph.stream(state, config=_stream_cfg):" if checkpointing_enabled \
                      else "    for step_output in graph.stream(state):"
        if checkpointing_enabled:
            lines += [
                "    # GRAPH-3: pass thread_id so SqliteSaver checkpointer scopes state to this session",
                "    _stream_cfg = {'configurable': {'thread_id': session_id}} if _checkpointer else None",
            ]
        lines += [
            f"    {stream_open.strip()}",
            "        # Timeout: abort if wall-clock time exceeds runtime.timeout_seconds",
            "        if _TIMEOUT_SEC > 0 and (time.time() - _run_start) > _TIMEOUT_SEC:",
            "            print(f'[TIMEOUT] Workflow exceeded {_TIMEOUT_SEC}s — stopping at step {step_idx}')",
            "            break",
            "        for node_name, node_updates in step_output.items():",
            "            try:",
            "                if isinstance(node_updates, dict):",
            "                    state.update(node_updates)",
            "            except Exception as _node_exc:",
            "                if _ERROR_POLICY == 'continue':",
            "                    print(f'[ERROR:{node_name}] {_node_exc!r} — error_policy=continue, proceeding')",
            "                else:",
            "                    raise",
        ]

        # Observability — log_state_transitions: print step summary
        if log_transitions:
            lines += [
                "            # Observability: step transition log",
                "            print(f'[STEP {step_idx}] node={node_name} sender={state.get(\"sender\", \"\")} keys={list(node_updates.keys()) if isinstance(node_updates, dict) else \"?\"}')",
            ]

        # Observability — trace_nodes: structured JSON trace per step
        if trace_nodes:
            lines += [
                "        # Observability: structured node trace",
                "        _trace_entry = {",
                "            'step': step_idx,",
                "            'nodes': list(step_output.keys()),",
                "            'sender': state.get('sender', ''),",
                "        }",
                "        print(f'[TRACE] {json.dumps(_trace_entry)}')",
            ]

        # Memory: always persist STM; optionally persist LTM per step
        lines.append("        # Memory: persist step to STM (and LTM if capture_outputs enabled)")
        lines.append("        _memory.save_stm(session_id, state)")
        if capture_outputs:
            lines += [
                "        _ltm_entry = {",
                "            'step': step_idx,",
                "            'nodes': list(step_output.keys()),",
                "            'sender': state.get('sender', ''),",
                "            'state_keys': list(state.keys()),",
                "        }",
                "        _memory.append_ltm(session_id, _ltm_entry)",
            ]

        lines += [
            "        step_idx += 1",
            f"        if step_idx >= MAX_ITER:",
            "            print(f'[WARN] max_iterations={MAX_ITER} reached — stopping')",
            "            break",
            "",
            "    return state",
        ]
        return lines

    def _build_main(self, state_schema: dict, retry_policy: dict = None) -> list:
        rp = retry_policy or {}
        max_retries = int(rp.get("max_retries", 3))
        backoff = rp.get("backoff_strategy", "exponential")
        base_sec = float(rp.get("backoff_base_seconds", 1.0))
        lines = [
            "# ── Entry Point ──────────────────────────────────────────────────────────",
            "# LLM retry/backoff env overrides (baked from workflow retry_policy):",
            f"# AGENT_MAX_RETRIES={max_retries}, AGENT_BACKOFF_STRATEGY={backoff!r}, AGENT_BACKOFF_BASE_SEC={base_sec}",
            "# Set these env vars to override at deploy time without editing code.",
            "",
            "def main():",
            "    import argparse, sys, uuid",
            "    parser = argparse.ArgumentParser(",
            "        description='Run the generated agentic workflow.',",
            "        formatter_class=argparse.RawDescriptionHelpFormatter,",
            "        epilog=(",
            "            'Examples:\\n'",
            "            \"  python agent.py --input '{\\\"document_text\\\": \\\"hello world\\\"}'\\n\"",
            "            '  python agent.py --input-file input.json --output-format json\\n'",
            "            '  python agent.py --session-id abc123 --resume'",
            "        ),",
            "    )",
            "    parser.add_argument('--input', '-i', default=None,",
            "        help='Initial state as a JSON string (e.g. {\"key\": \"value\"})'",
            "    )",
            "    parser.add_argument('--input-file', '-f', default=None,",
            "        help='Path to a JSON file containing the initial state'",
            "    )",
            "    parser.add_argument('--session-id', '-s', default=None,",
            "        help='Session ID for memory persistence (auto-generated if omitted)'",
            "    )",
            "    parser.add_argument('--resume', '-r', action='store_true',",
            "        help='Resume from last saved STM state for the given session-id'",
            "    )",
            "    parser.add_argument('--output-format', '-o', choices=['pretty', 'json'], default='pretty',",
            "        help='Output format: pretty (human-readable) or json (machine-readable)'",
            "    )",
            "    args = parser.parse_args()",
            "",
            "    # Load initial state override from --input or --input-file",
            "    state_override = {}",
            "    if args.input_file:",
            "        try:",
            "            with open(args.input_file, encoding='utf-8') as _fh:",
            "                state_override = json.load(_fh)",
            "        except Exception as _e:",
            "            print(f'[ERROR] Failed to load --input-file: {_e}', file=sys.stderr)",
            "            sys.exit(1)",
            "    elif args.input:",
            "        try:",
            "            state_override = json.loads(args.input)",
            "        except Exception as _e:",
            "            print(f'[ERROR] --input is not valid JSON: {_e}', file=sys.stderr)",
            "            sys.exit(1)",
            "",
            "    session_id = args.session_id or str(uuid.uuid4())",
            "    if not args.resume:",
            "        print(f'[AGENT] session_id={session_id}', file=sys.stderr)",
            "    else:",
            "        print(f'[AGENT] Resuming session_id={session_id}', file=sys.stderr)",
            "",
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
            "    # Merge state_override (from --input / --input-file) into initial_state",
            "    merged = {**initial_state, **state_override}",
            "",
            "    try:",
            "        result = run_workflow(merged, session_id=session_id, resume=args.resume)",
            "    except Exception as _exc:",
            "        print(f'[ERROR] Workflow failed: {_exc}', file=sys.stderr)",
            "        sys.exit(1)",
            "",
            "    # Strip messages list for cleaner output (still present in full JSON)",
            "    output = {k: v for k, v in result.items() if k != 'messages'}",
            "    if args.output_format == 'json':",
            "        print(json.dumps(output, indent=2, default=str))",
            "    else:",
            "        print('\\n=== Workflow Result ===')",
            "        for k, v in output.items():",
            "            print(f'  {k}: {v}')",
            "    ltm_steps = len(_memory.load_ltm(session_id))",
            "    print(f'[AGENT] Done. {ltm_steps} LTM step(s) recorded for session {session_id!r}.',",
            "          file=sys.stderr)",
            "    sys.exit(0)",
            "",
            "",
            'if __name__ == "__main__":',
            "    main()",
        ]
        return lines

    @staticmethod
    def _template_cond_to_python(condition: str) -> str:
        """Convert template condition (confidence_score < 0.6) to Python state access.
        
        Rules:
        - Bare state variable names (lowercase_with_underscores) → state.get("name")
        - String literals ('medical', "legal") → left as-is
        - Python keywords → left as-is
        - Numbers → left as-is
        """
        keywords = {"and", "or", "not", "True", "False", "None", "in", "is",
                    "if", "else", "elif", "for", "while", "return", "import"}

        def replace_var(m):
            name = m.group(0)
            if name in keywords:
                return name
            # Only replace bare lowercase identifiers that look like state vars
            if re.match(r'^[a-z][a-z0-9_]*$', name):
                return f'state.get("{name}")'
            return name

        # Tokenize: skip string literals and numbers, only replace bare identifiers
        result = []
        i = 0
        while i < len(condition):
            # String literals — pass through unchanged
            if condition[i] in ('"', "'"):
                q = condition[i]
                j = i + 1
                while j < len(condition) and condition[j] != q:
                    if condition[j] == '\\':
                        j += 1
                    j += 1
                result.append(condition[i:j+1])
                i = j + 1
            # Numbers — pass through
            elif condition[i].isdigit() or (condition[i] == '.' and i+1 < len(condition) and condition[i+1].isdigit()):
                j = i
                while j < len(condition) and (condition[j].isdigit() or condition[j] == '.'):
                    j += 1
                result.append(condition[i:j])
                i = j
            # Identifiers
            elif condition[i].isalpha() or condition[i] == '_':
                j = i
                while j < len(condition) and (condition[j].isalnum() or condition[j] == '_'):
                    j += 1
                token = condition[i:j]
                result.append(replace_var(type('m', (), {'group': lambda self, n: token})()))
                i = j
            else:
                result.append(condition[i])
                i += 1
        return ''.join(result)

    @staticmethod
    def _map_operator(op: str) -> str:
        return {"==": "==", "!=": "!=", ">": ">", "<": "<", ">=": ">=", "<=": "<="}.get(op, "==")

    # ------------------------------------------------------------------
    # Artifact Validation
    # ------------------------------------------------------------------

    def validate_artifact(self, code: str, config: dict) -> dict:
        """
        Validate a generated agent.py against its workflow config.

        Returns a ValidationReport dict:
        {
            "passed": bool,
            "score": int,          # 0-100
            "checks": [            # ordered list of check results
                {
                    "id": str,
                    "category": str,
                    "description": str,
                    "status": "pass" | "warn" | "fail",
                    "detail": str | None,
                }
            ],
            "summary": {
                "pass": int, "warn": int, "fail": int, "total": int
            }
        }
        """
        import ast

        checks: list[dict] = []

        def _check(check_id, category, description, status, detail=None):
            checks.append({
                "id": check_id,
                "category": category,
                "description": description,
                "status": status,
                "detail": detail,
            })

        nodes = config.get("nodes", [])
        edges = config.get("edges", [])
        state_schema = config.get("state_schema", {})
        known_node_ids = {n.get("id", "") for n in nodes if n.get("id")}
        valid_targets = known_node_ids | {"END"}
        code_lines = code.splitlines()

        # ── 1. Syntax check ─────────────────────────────────────────────
        try:
            tree = ast.parse(code)
            _check("syntax", "Syntax", "Python syntax is valid", "pass")
        except SyntaxError as e:
            _check("syntax", "Syntax", "Python syntax error",
                   "fail", f"Line {e.lineno}: {e.msg} — {e.text!r}")
            # If syntax fails, skip AST-dependent checks
            tree = None

        # ── Extract top-level definitions if AST is available ──────────
        defined_funcs: set[str] = set()
        if tree:
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    defined_funcs.add(node.name)

        # ── 2. Node function completeness ────────────────────────────────
        for n in nodes:
            nid = n.get("id", "")
            expected = f"node_{nid.lower()}"
            if expected in defined_funcs:
                _check(f"node_func_{nid}", "Node Functions",
                       f"Node function '{expected}' present", "pass")
            else:
                _check(f"node_func_{nid}", "Node Functions",
                       f"Node function '{expected}' missing",
                       "fail", f"Expected 'def {expected}(state)' — not found in generated code")

        # ── 3. Routing function completeness ─────────────────────────────
        for n in nodes:
            nid = n.get("id", "")
            routing_logic = n.get("routing_logic", [])
            if isinstance(routing_logic, list) and routing_logic:
                expected = f"route_{nid.lower()}"
                if expected in defined_funcs:
                    _check(f"route_func_{nid}", "Routing",
                           f"Routing function '{expected}' present", "pass")
                else:
                    _check(f"route_func_{nid}", "Routing",
                           f"Routing function '{expected}' missing",
                           "fail", f"Node '{nid}' has routing_logic but 'def {expected}(state)' not found")

        # ── 4. Routing target validity ────────────────────────────────────
        for n in nodes:
            nid = n.get("id", "")
            routing_logic = n.get("routing_logic", [])
            if not isinstance(routing_logic, list):
                continue
            for rule in routing_logic:
                target = rule.get("next", "END")
                if target in valid_targets:
                    _check(f"route_target_{nid}_{target}", "Routing",
                           f"Route target '{target}' from '{nid}' is a valid node/END", "pass")
                else:
                    _check(f"route_target_{nid}_{target}", "Routing",
                           f"Route target '{target}' from '{nid}' is unknown",
                           "fail", f"'{target}' is not in known nodes {sorted(known_node_ids)} or END")

        # ── 5. Edge wiring completeness ──────────────────────────────────
        code_joined = "\n".join(code_lines)
        for edge in edges:
            src = edge.get("from") or edge.get("source", "")
            dst = edge.get("to") or edge.get("target", "")
            if not src or not dst:
                continue
            condition = edge.get("condition")
            if condition:
                # Conditional edge → expect add_conditional_edges
                if f'add_conditional_edges("{src}"' in code_joined:
                    _check(f"edge_{src}_cond", "Edges",
                           f"Conditional edge from '{src}' wired via add_conditional_edges", "pass")
                else:
                    _check(f"edge_{src}_cond", "Edges",
                           f"Conditional edge from '{src}' not found in graph assembly",
                           "fail", f"Expected add_conditional_edges(\"{src}\", ...)")
            else:
                if f'add_edge("{src}"' in code_joined:
                    _check(f"edge_{src}_{dst}", "Edges",
                           f"Edge '{src}' → '{dst}' wired", "pass")
                else:
                    _check(f"edge_{src}_{dst}", "Edges",
                           f"Edge '{src}' → '{dst}' not found in graph assembly",
                           "fail", f"Expected add_edge(\"{src}\", \"{dst}\")")

        # ── 6. entry_point set ───────────────────────────────────────────
        if nodes:
            entry_id = nodes[0].get("id", "")
            if f'set_entry_point("{entry_id}")' in code_joined:
                _check("entry_point", "Graph", f"Entry point '{entry_id}' set correctly", "pass")
            else:
                _check("entry_point", "Graph", f"Entry point '{entry_id}' not set",
                       "fail", "workflow.set_entry_point() call not found or uses wrong node ID")

        # ── 7. graph.compile() present ───────────────────────────────────
        if "workflow.compile(" in code_joined:
            _check("compile", "Graph", "workflow.compile() called", "pass")
        else:
            _check("compile", "Graph", "workflow.compile() missing",
                   "fail", "workflow.compile() not found — graph won't be runnable")

        # ── 8. State schema coverage ─────────────────────────────────────
        missing_fields = []
        for field in state_schema:
            if field in ("messages", "metadata", "sender"):
                continue  # always auto-added
            if field not in code_joined:
                missing_fields.append(field)
        if not missing_fields:
            _check("state_schema", "State", f"All {len(state_schema)} state fields present in generated code", "pass")
        else:
            _check("state_schema", "State",
                   f"{len(missing_fields)} state field(s) missing from generated code",
                   "warn", f"Missing: {missing_fields[:10]}")

        # ── 9. LLM call wired per node ───────────────────────────────────
        for n in nodes:
            nid = n.get("id", "")
            node_type = n.get("type", "")
            if node_type in ("human", "checkpoint", "human_node"):
                continue  # no LLM call expected for human nodes
            func_name = f"node_{nid.lower()}"
            # Find the function body in code
            in_func = False
            has_llm = False
            for line in code_lines:
                if f"def {func_name}(" in line:
                    in_func = True
                if in_func:
                    if line.startswith("def ") and f"def {func_name}(" not in line:
                        break
                    if "call_llm(" in line:
                        has_llm = True
                        break
            if has_llm:
                _check(f"llm_call_{nid}", "LLM Wiring", f"Node '{nid}' has call_llm()", "pass")
            else:
                _check(f"llm_call_{nid}", "LLM Wiring", f"Node '{nid}' has no call_llm()",
                       "warn", f"'{func_name}' does not call call_llm() — may be intentional for human/tool-only nodes")

        # ── 10. Stub detection ───────────────────────────────────────────
        stubs = []
        for i, line in enumerate(code_lines, 1):
            s = line.strip()
            if s.startswith("# TODO"):
                stubs.append(f"Line {i}: {s}")
            elif "placeholder" in s.lower() and "return" in s:
                stubs.append(f"Line {i}: {s}")
        if not stubs:
            _check("stubs", "Completeness", "No stub placeholders detected", "pass")
        else:
            _check("stubs", "Completeness",
                   f"{len(stubs)} stub(s) require developer implementation",
                   "warn",
                   "\n".join(stubs[:20]) + ("\n..." if len(stubs) > 20 else ""))

        # ── 11. MCP servers commented/documented ────────────────────────
        mcp_servers = config.get("mcp_servers", {})
        if mcp_servers:
            documented = all(
                f"MCP server '{name}'" in code_joined or f"# MCP server" in code_joined
                for name in (mcp_servers if isinstance(mcp_servers, dict) else {})
            )
            if documented:
                _check("mcp_docs", "MCP", "MCP server configs documented in generated code", "pass")
            else:
                _check("mcp_docs", "MCP", "MCP server configs not documented",
                       "warn", "Some MCP server definitions from config not reflected in agent.py header")

        # ── 12. Guardrail hooks present where configured ─────────────────
        for n in nodes:
            nid = n.get("id", "")
            guardrails = n.get("guardrails") or {}
            in_guards = (n.get("context") or {}).get("input_guardrails") or {}
            if (guardrails or in_guards):
                func_name = f"node_{nid.lower()}"
                in_func = False
                has_guard = False
                for line in code_lines:
                    if f"def {func_name}(" in line:
                        in_func = True
                    if in_func:
                        if line.startswith("def ") and f"def {func_name}(" not in line:
                            break
                        if "apply_output_guardrails(" in line or "apply_input_guardrails(" in line:
                            has_guard = True
                            break
                if has_guard:
                    _check(f"guardrail_{nid}", "Guardrails",
                           f"Node '{nid}' guardrail hooks wired", "pass")
                else:
                    _check(f"guardrail_{nid}", "Guardrails",
                           f"Node '{nid}' has guardrail config but no hook in generated code",
                           "warn", f"'{func_name}' missing apply_input/output_guardrails() calls")

        # ── 13. Validation hooks present where configured ─────────────────
        for n in nodes:
            nid = n.get("id", "")
            val_cfg = n.get("validation") or {}
            out_schema = n.get("output_schema") or {}
            if val_cfg.get("enabled") or out_schema.get("format"):
                func_name = f"node_{nid.lower()}"
                in_func = False
                has_val = False
                for line in code_lines:
                    if f"def {func_name}(" in line:
                        in_func = True
                    if in_func:
                        if line.startswith("def ") and f"def {func_name}(" not in line:
                            break
                        if "validate_output(" in line:
                            has_val = True
                            break
                if has_val:
                    _check(f"validation_{nid}", "Validation",
                           f"Node '{nid}' output validation wired", "pass")
                else:
                    _check(f"validation_{nid}", "Validation",
                           f"Node '{nid}' has validation config but no validate_output() call",
                           "warn", f"'{func_name}' missing validate_output() call")

        # ── Compute summary ──────────────────────────────────────────────
        pass_count = sum(1 for c in checks if c["status"] == "pass")
        warn_count = sum(1 for c in checks if c["status"] == "warn")
        fail_count = sum(1 for c in checks if c["status"] == "fail")
        total = len(checks)

        # Score: pass=1pt, warn=0.5pt, fail=0pt — out of total
        score = int(round(((pass_count + warn_count * 0.5) / total) * 100)) if total else 100
        passed = fail_count == 0

        return {
            "passed": passed,
            "score": score,
            "checks": checks,
            "summary": {
                "pass": pass_count,
                "warn": warn_count,
                "fail": fail_count,
                "total": total,
            },
        }

