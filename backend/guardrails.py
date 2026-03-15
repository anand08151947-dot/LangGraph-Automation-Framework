"""
guardrails.py — Per-node safety and content guardrail checks.

OUTPUT guardrails (applied to LLM output before entering workflow state):
  - PII detection (email, phone, SSN, credit card, IP)
  - Harmful content / dangerous instructions
  - Self-harm content
  - Hate speech
  - Regulated advice (medical, legal, financial)

INPUT / CONTEXT guardrails (applied to context assembled before the LLM call):
  - PII redaction on input (stop PII reaching external LLMs)
  - Prompt injection detection (jailbreak / override attempts)
  - Secrets detection (API keys, Bearer tokens, private keys, passwords)
  - Context length enforcement (max_chars with truncate / summarize / error)
  - Profanity / offensive language filter
  - Data classification guard ([CONFIDENTIAL] / [SECRET] / [RESTRICTED] markers)
  - Encoding sanitization (HTML tags, null bytes, control characters)
  - Language enforcement (reject context not in expected language)

Actions per check:
  block   — raise GuardrailViolation (workflow stops this node)
  redact  — replace matched patterns with [TYPE_REDACTED]
  approve — log violation but allow content through (audit mode)
"""

import re
import json
import logging
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class GuardrailViolation(Exception):
    """Raised when content is blocked by a guardrail (action == 'block')."""
    def __init__(self, check: str, detail: str):
        self.check = check
        self.detail = detail
        super().__init__(f"[Guardrail:{check}] {detail}")


# ---------------------------------------------------------------------------
# PII patterns
# ---------------------------------------------------------------------------

_PII_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("email",
     re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b')),
    ("phone",
     re.compile(r'\b(\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}\b')),
    ("ssn",
     re.compile(r'\b\d{3}-\d{2}-\d{4}\b')),
    ("credit_card",
     re.compile(r'\b(?:\d{4}[\s\-]?){3}\d{4}\b')),
    ("ip_address",
     re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')),
]

# ---------------------------------------------------------------------------
# Harmful content keywords (exact substring match on lowercased text)
# ---------------------------------------------------------------------------

_HARMFUL_KEYWORDS = [
    "how to make a bomb",
    "synthesize drugs",
    "manufacture weapons",
    "instructions for violence",
    "ddos attack",
    "exploit vulnerability",
    "create malware",
    "make explosives",
]

# ---------------------------------------------------------------------------
# Self-harm patterns
# ---------------------------------------------------------------------------

_SELF_HARM_RE = re.compile(
    r"\b(suicide|self[\s\-]?harm|self[\s\-]?injury|cutting myself|"
    r"end my life|want to die|overdose|methods of suicide|pills to die)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Hate speech patterns
# ---------------------------------------------------------------------------

_HATE_SPEECH_RE = re.compile(
    r"\b(all\s+\w+\s+should\s+(?:die|be\s+killed|be\s+exterminated)|"
    r"inferior\s+race|ethnic\s+cleansing|racial\s+extermination)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Regulated advice patterns
# ---------------------------------------------------------------------------

_REGULATED_PATTERNS: Dict[str, re.Pattern] = {
    "medical": re.compile(
        r"\b(you\s+have\s+(?:cancer|diabetes|disease)|prescribe\s+you|"
        r"take\s+this\s+medication|medical\s+diagnosis)\b",
        re.IGNORECASE,
    ),
    "legal": re.compile(
        r"\b(i\s+am\s+your\s+lawyer|legal\s+advice|you\s+should\s+sue|"
        r"this\s+constitutes\s+legal\s+counsel)\b",
        re.IGNORECASE,
    ),
    "financial": re.compile(
        r"\b(guaranteed\s+returns|you\s+should\s+buy\s+(?:stock|crypto)|"
        r"this\s+is\s+financial\s+advice|invest\s+all\s+your)\b",
        re.IGNORECASE,
    ),
}

# ---------------------------------------------------------------------------
# INPUT CONTEXT — Prompt injection patterns
# ---------------------------------------------------------------------------

_PROMPT_INJECTION_RE = re.compile(
    r"(?:"
    r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?"
    r"|override\s+(?:system|your)\s+(?:prompt|instructions?|rules?)"
    r"|forget\s+(?:everything|all)\s+(?:you\s+)?(?:know|were\s+told)"
    r"|you\s+are\s+now\s+(?:a\s+)?(?:different|new|evil|unrestricted)"
    r"|disregard\s+(?:your|all)\s+(?:instructions?|guidelines?|safety)"
    r"|pretend\s+you\s+(?:have\s+no|are\s+without)\s+(?:rules?|restrictions?)"
    r"|jailbreak|DAN\s+mode|developer\s+mode\s+enabled"
    r"|act\s+as\s+(?:if\s+you\s+(?:have\s+no|are\s+without)\s+(?:rules?|restrictions?))"
    r"|new\s+system\s+prompt|system:\s*you\s+are"
    r")",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# INPUT CONTEXT — Secrets / credential patterns
# ---------------------------------------------------------------------------

_SECRETS_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("api_key",
     re.compile(r'\b(?:sk|pk|rk|ak)[_\-][A-Za-z0-9]{20,}\b')),          # OpenAI, Stripe, etc.
    ("bearer_token",
     re.compile(r'\bBearer\s+[A-Za-z0-9\-._~+/]{20,}\b', re.IGNORECASE)),
    ("private_key",
     re.compile(r'-----BEGIN (?:RSA |EC )?PRIVATE KEY-----')),
    ("aws_key",
     re.compile(r'\b(?:AKIA|AIPA|AIHA|AIFA|AIGA|AIOA|AROA|ANPA|ANVA|ASIA)[A-Z0-9]{16}\b')),
    ("github_token",
     re.compile(r'\bgh[pousr]_[A-Za-z0-9]{36,}\b')),
    ("password_field",
     re.compile(r'\b(?:password|passwd|secret|api_key|token)\s*[:=]\s*\S+', re.IGNORECASE)),
    ("jwt_token",
     re.compile(r'\bey[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\b')),
]

# ---------------------------------------------------------------------------
# INPUT CONTEXT — Profanity (lightweight; extend as needed)
# ---------------------------------------------------------------------------

_PROFANITY_RE = re.compile(
    r'\b(f+u+c+k+|sh[i1]t+|a[s$]+h+[o0]+l+e+|b[i1]+t+c+h+|'
    r'd[i1]+c+k+|c+u+n+t+|b[a@]+s+t+[a@]+r+d+)\b',
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# INPUT CONTEXT — Data classification markers
# ---------------------------------------------------------------------------

_DATA_CLASSIFICATION_RE = re.compile(
    r'\b(?:CONFIDENTIAL|SECRET|TOP[\s\-]SECRET|RESTRICTED|'
    r'PROPRIETARY|INTERNAL[\s\-]ONLY|NOT[\s\-]FOR[\s\-]DISTRIBUTION|'
    r'CLASSIFIED)\b',
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# INPUT CONTEXT — HTML / encoding patterns
# ---------------------------------------------------------------------------

_HTML_TAG_RE = re.compile(r'<[^>]{1,200}>')
_CONTROL_CHAR_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')

# ---------------------------------------------------------------------------
# INPUT CONTEXT — Language detection (very lightweight heuristic)
# ---------------------------------------------------------------------------

# Common high-frequency words per language — enough for basic heuristics
_LANG_MARKERS: Dict[str, List[str]] = {
    "en": ["the", "and", "is", "are", "was", "this", "that", "with", "for", "have"],
    "fr": ["le", "la", "les", "est", "une", "des", "que", "qui", "dans", "pour"],
    "de": ["der", "die", "das", "ist", "und", "mit", "für", "nicht", "sind", "ein"],
    "es": ["el", "la", "los", "es", "una", "que", "con", "por", "para", "son"],
    "zh": ["的", "了", "是", "在", "我", "有", "和", "就", "不", "人"],
}

def _detect_language(text: str) -> str:
    """Very lightweight language heuristic — returns best-guess ISO 639-1 code."""
    lower_words = set(re.findall(r'\b[a-z]{2,}\b', text.lower()))
    cjk_count = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    if cjk_count > 10:
        return "zh"
    best_lang = "en"
    best_score = 0
    for lang, markers in _LANG_MARKERS.items():
        if lang == "zh":
            continue
        score = sum(1 for m in markers if m in lower_words)
        if score > best_score:
            best_score = score
            best_lang = lang
    return best_lang


def _check_pii(text: str, action: str) -> Tuple[str, List[str]]:
    """Return (processed_text, list_of_findings). Redacts if action=='redact'."""
    findings: List[str] = []
    result = text
    for name, pattern in _PII_PATTERNS:
        matches = pattern.findall(result)
        if matches:
            findings.append(f"{name}({len(matches)})")
            if action == "redact":
                result = pattern.sub(f"[{name.upper()}_REDACTED]", result)
    return result, findings


def _check_harmful(text: str) -> List[str]:
    lower = text.lower()
    return [kw for kw in _HARMFUL_KEYWORDS if kw in lower]


def _check_self_harm(text: str) -> bool:
    return bool(_SELF_HARM_RE.search(text))


def _check_hate_speech(text: str) -> bool:
    return bool(_HATE_SPEECH_RE.search(text))


def _check_regulated(text: str, allowed: Optional[List[str]] = None) -> List[str]:
    found = []
    for category, pattern in _REGULATED_PATTERNS.items():
        if allowed and category not in allowed:
            continue
        if pattern.search(text):
            found.append(category)
    return found


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def apply_guardrails(
    text: str,
    guardrails_config: Dict[str, Any],
    node_id: str = "",
) -> str:
    """Apply all configured guardrails to *text* and return the (possibly
    redacted) result.

    Guardrail config format (each key is optional):
    {
      "pii":              {"enabled": true,  "action": "redact"},
      "harmful_content":  {"enabled": true,  "action": "block"},
      "self_harm":        {"enabled": true,  "action": "block"},
      "hate_speech":      {"enabled": true,  "action": "block"},
      "regulated_advice": {"enabled": true,  "action": "block",
                           "checks": ["medical", "legal", "financial"]}
    }

    Raises GuardrailViolation when action=='block' and a violation is found.
    """
    prefix = f"[{node_id}] " if node_id else ""
    result = text

    # ── PII ────────────────────────────────────────────────────────────────────
    pii_cfg = guardrails_config.get("pii") or {}
    if pii_cfg.get("enabled"):
        action = pii_cfg.get("action", "redact")
        result, findings = _check_pii(result, action)
        if findings:
            msg = f"{prefix}PII detected: {', '.join(findings)}"
            logger.warning("Guardrail [pii] %s", msg)
            if action == "block":
                raise GuardrailViolation("pii", msg)
            # approve: already logged, pass through

    # ── Harmful content ────────────────────────────────────────────────────────
    harm_cfg = guardrails_config.get("harmful_content") or {}
    if harm_cfg.get("enabled"):
        action = harm_cfg.get("action", "block")
        matches = _check_harmful(result)
        if matches:
            msg = f"{prefix}Harmful instructions detected: {matches[:3]}"
            logger.warning("Guardrail [harmful_content] %s", msg)
            if action == "block":
                raise GuardrailViolation("harmful_content", msg)
            elif action == "redact":
                # GUARD-3 fix: use regex sub on the live `result` so each substitution
                # is applied to the already-redacted text, preventing missed matches.
                for kw in matches:
                    result = re.sub(re.escape(kw), "[HARMFUL_REDACTED]", result, flags=re.IGNORECASE)

    # ── Self-harm ──────────────────────────────────────────────────────────────
    sh_cfg = guardrails_config.get("self_harm") or {}
    if sh_cfg.get("enabled"):
        action = sh_cfg.get("action", "block")
        if _check_self_harm(result):
            msg = f"{prefix}Self-harm content detected"
            logger.warning("Guardrail [self_harm] %s", msg)
            if action == "block":
                raise GuardrailViolation("self_harm", msg)
            elif action == "redact":
                result = _SELF_HARM_RE.sub("[SELF_HARM_REDACTED]", result)

    # ── Hate speech ────────────────────────────────────────────────────────────
    hs_cfg = guardrails_config.get("hate_speech") or {}
    if hs_cfg.get("enabled"):
        action = hs_cfg.get("action", "block")
        if _check_hate_speech(result):
            msg = f"{prefix}Hate speech detected"
            logger.warning("Guardrail [hate_speech] %s", msg)
            if action == "block":
                raise GuardrailViolation("hate_speech", msg)
            elif action == "redact":
                result = _HATE_SPEECH_RE.sub("[HATE_SPEECH_REDACTED]", result)

    # ── Regulated advice ───────────────────────────────────────────────────────
    ra_cfg = guardrails_config.get("regulated_advice") or {}
    if ra_cfg.get("enabled"):
        action = ra_cfg.get("action", "block")
        allowed_checks = ra_cfg.get("checks", ["medical", "legal", "financial"])
        found_cats = _check_regulated(result, allowed_checks)
        if found_cats:
            msg = f"{prefix}Regulated advice detected: {found_cats}"
            logger.warning("Guardrail [regulated_advice] %s", msg)
            if action == "block":
                raise GuardrailViolation("regulated_advice", msg)
            elif action == "redact":
                for cat in found_cats:
                    result = _REGULATED_PATTERNS[cat].sub(
                        f"[{cat.upper()}_ADVICE_REDACTED]", result
                    )

    return result


def guardrail_result(
    text: str,
    guardrails_config: Dict[str, Any],
    node_id: str = "",
) -> Dict[str, Any]:
    """
    Like apply_guardrails but never raises; returns a structured result dict:
    {
      "status":    "passed" | "blocked" | "redacted",
      "text":      <processed text or None if blocked>,
      "violation": <check name or None>,
      "detail":    <detail string or None>
    }
    """
    try:
        processed = apply_guardrails(text, guardrails_config, node_id)
        status = "redacted" if processed != text else "passed"
        return {"status": status, "text": processed, "violation": None, "detail": None}
    except GuardrailViolation as e:
        return {"status": "blocked", "text": None, "violation": e.check, "detail": e.detail}


def validate_output(
    output_text: str,
    output_schema: Dict[str, Any],
    node_id: str = "",
) -> Tuple[bool, Optional[str], Optional[Dict]]:
    """Validate LLM output against an output_schema config.

    output_schema format:
    {
      "format":   "json" | "text" | "markdown",
      "schema":   {"field": "type", ...},   // for json format
      "state_key": "output_field_name",     // where to store result in state
      "required_fields": ["field1", ...],   // must be present
      "validation": {
        "rules": [{"field": "confidence", "operator": ">=", "value": 0.5}],
        "on_failure": "retry" | "error" | "warn"
      }
    }

    Returns: (success, error_message, parsed_obj)
    """
    fmt = output_schema.get("format", "text")
    prefix = f"[{node_id}] " if node_id else ""

    if fmt != "json":
        # Non-JSON: always passes format validation
        return True, None, {"text": output_text}

    # ── Parse JSON ─────────────────────────────────────────────────────────────
    parsed = None
    # Strip markdown fences
    clean = output_text.strip()
    if clean.startswith("```"):
        lines = clean.split("\n")
        clean = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError as e:
        return False, f"{prefix}Output is not valid JSON: {e}", None

    # ── Required fields ─────────────────────────────────────────────────────────
    required = output_schema.get("required_fields") or []
    if required and isinstance(parsed, dict):
        missing = [f for f in required if f not in parsed]
        if missing:
            return False, f"{prefix}Missing required fields: {missing}", parsed

    # ── Validation rules ───────────────────────────────────────────────────────
    # GUARD-1: replaced eval() with a safe whitelist comparison to prevent
    # code-injection via operator or value fields in the rule config.
    _SAFE_OPS = {
        "==": lambda a, b: a == b,
        "!=": lambda a, b: a != b,
        "<":  lambda a, b: a < b,
        "<=": lambda a, b: a <= b,
        ">":  lambda a, b: a > b,
        ">=": lambda a, b: a >= b,
        "in": lambda a, b: a in b,
        "not in": lambda a, b: a not in b,
    }
    rules = output_schema.get("validation", {}).get("rules") or []
    for rule in rules:
        field = rule.get("field", "")
        operator = rule.get("operator", "==")
        expected = rule.get("value")
        if isinstance(parsed, dict) and field in parsed:
            actual = parsed[field]
            cmp_fn = _SAFE_OPS.get(operator)
            if cmp_fn is None:
                continue  # unknown operator — skip silently (was eval-able before)
            try:
                ok = cmp_fn(actual, expected)
                if not ok:
                    return (
                        False,
                        f"{prefix}Validation failed: {field} {operator} {expected} "
                        f"(actual: {actual})",
                        parsed,
                    )
            except Exception:
                pass  # Skip if comparison raises (e.g., incompatible types)

    return True, None, parsed


def build_context_messages(
    node_config: Dict[str, Any],
    state: Dict[str, Any],
    memory_manager=None,
    session_id: str = "",
    pre_llm_results: Optional[List[str]] = None,
) -> List[Dict[str, str]]:
    """Build the list of context messages to inject before the node's system_prompt.

    Supported source types:
      previous_node — injects the output of a specific (or the most recent) prior node
      stm           — injects specific keys from STM (short-term memory / workflow state)
      ltm           — injects recent LTM entries (long-term memory), with optional keyword filter
      pre_llm       — injects results from the pre-LLM tool calls / RAG that ran in step 0
                      (pass pre_llm_results list from _agent_node_func)

    Synthesis:
      If context.synthesis is configured, all collected chunks are consolidated into a
      single message using the chosen strategy (concatenate / structured / summarize).
      - concatenate  : join chunks with separators (default)
      - structured   : label each chunk with its source type and index
      - summarize    : prefix with a consolidation instruction (LLM does the merging)

    Returns list of {"role": ..., "content": ...} dicts.
    """
    ctx_config = node_config.get("context") or {}
    sources = ctx_config.get("sources") or []
    inject_as = ctx_config.get("inject_as", "user")
    synthesis_cfg = ctx_config.get("synthesis") or {}
    messages: List[Dict[str, str]] = []

    # ── Collect raw chunks per source ──────────────────────────────────────
    chunks: List[Dict[str, str]] = []   # [{source_type, label, content}]

    for source in sources:
        src_type = source.get("type", "")
        label = source.get("label") or src_type

        if src_type == "previous_node":
            # Inject the output of a specific node (by node_id) or the last message
            node_id_filter = source.get("node_id") or ""
            msgs = state.get("messages", [])
            if node_id_filter:
                # Find last message from that specific sender
                match = next(
                    (m for m in reversed(msgs)
                     if isinstance(m, dict) and m.get("sender") == node_id_filter),
                    None,
                )
                content = match.get("content", "") if match else ""
            else:
                # Fall back to most recent message
                last = msgs[-1] if msgs else {}
                content = last.get("content", "") if isinstance(last, dict) else str(last)
            if content:
                chunks.append({"source_type": src_type, "label": label, "content": content})

        elif src_type == "stm":
            if memory_manager and session_id:
                stm_state = memory_manager.load_stm(session_id) or {}
            else:
                stm_state = state  # Fall back to current workflow state
            keys = source.get("keys") or list(stm_state.keys())
            stm_snippet = {k: stm_state[k] for k in keys if k in stm_state}
            if stm_snippet:
                chunks.append({
                    "source_type": src_type,
                    "label": label,
                    "content": json.dumps(stm_snippet, default=str, indent=2),
                })

        elif src_type == "ltm":
            if memory_manager and session_id:
                ltm_entries = memory_manager.load_ltm(session_id)
                query = (source.get("query") or "").lower()
                if query:
                    ltm_entries = [e for e in ltm_entries
                                   if query in json.dumps(e).lower()]
                limit = source.get("limit", 5)
                ltm_entries = ltm_entries[-limit:]
                if ltm_entries:
                    chunks.append({
                        "source_type": src_type,
                        "label": label,
                        "content": json.dumps(ltm_entries, default=str, indent=2),
                    })

        elif src_type == "pre_llm":
            # Inject specific or all pre-LLM results (tool calls + RAG)
            if pre_llm_results:
                target_id = source.get("result_id")  # optional: pick specific tool call id
                if target_id:
                    # pre_llm_results items are strings; filter by prefix
                    matched = [r for r in pre_llm_results
                               if r.startswith(f"[Tool: {target_id}]") or
                                  r.startswith(f"[RAG:") and target_id in r]
                    content = "\n\n".join(matched) if matched else ""
                else:
                    content = "\n\n".join(pre_llm_results)
                if content:
                    chunks.append({
                        "source_type": src_type,
                        "label": label or "Pre-LLM Results",
                        "content": content,
                    })

    if not chunks:
        return messages

    # ── Apply synthesis strategy when multiple sources ──────────────────────
    strategy = synthesis_cfg.get("strategy", "concatenate")
    synthesis_prompt = synthesis_cfg.get("prompt_template", "")

    if len(chunks) == 1 or strategy == "concatenate":
        # Simple concatenation: one message per chunk with its label header
        for chunk in chunks:
            messages.append({
                "role": inject_as,
                "content": f"[{chunk['label']}]\n{chunk['content']}",
            })

    elif strategy == "structured":
        # Single message with all chunks labelled and numbered
        parts = []
        for i, chunk in enumerate(chunks, 1):
            parts.append(f"### Source {i}: {chunk['label']}\n{chunk['content']}")
        messages.append({
            "role": inject_as,
            "content": "--- Consolidated Context ---\n\n" + "\n\n".join(parts),
        })

    elif strategy == "summarize":
        # Prefix with a synthesis instruction so the LLM consolidates inline
        parts = []
        for i, chunk in enumerate(chunks, 1):
            parts.append(f"[Source {i} – {chunk['label']}]\n{chunk['content']}")
        combined = "\n\n".join(parts)
        instruction = (
            synthesis_prompt
            if synthesis_prompt
            else (
                "You have received context from multiple sources below. "
                "Before answering, silently synthesize these into a coherent understanding. "
                "Do not repeat the raw sources in your response."
            )
        )
        messages.append({
            "role": inject_as,
            "content": f"[Synthesis Instruction]\n{instruction}\n\n{combined}",
        })

    return messages


# ---------------------------------------------------------------------------
# INPUT / CONTEXT GUARDRAILS
# ---------------------------------------------------------------------------

def apply_input_guardrails(
    context_text: str,
    input_guardrails_config: Dict[str, Any],
    node_id: str = "",
) -> str:
    """Apply all configured guardrails to the assembled context (LLM input).

    Called BEFORE the LLM receives the context, protecting against:
      - PII leaking to external LLMs
      - Prompt injection / jailbreak attempts
      - Leaked secrets / credentials
      - Context length budget violations
      - Profanity in user-sourced context
      - Data classification violations
      - Encoding / HTML injection
      - Wrong language in context

    input_guardrails_config format:
    {
      "pii":                 {"enabled": true, "action": "redact"},
      "prompt_injection":    {"enabled": true, "action": "block"},
      "secrets_detection":   {"enabled": true, "action": "block"},
      "context_length":      {"enabled": true, "max_chars": 8000,
                              "on_exceed": "truncate"},
      "profanity":           {"enabled": true, "action": "redact"},
      "data_classification": {"enabled": true, "action": "block"},
      "encoding_sanitization": {"enabled": true},
      "language_enforcement": {"enabled": true, "expected_language": "en",
                               "action": "block"}
    }

    Raises GuardrailViolation when action=='block' and a violation is detected.
    Returns the (possibly redacted / truncated) context text.
    """
    prefix = f"[{node_id}] " if node_id else ""
    result = context_text

    # ── Encoding sanitization — always run first to normalise text ─────────────
    enc_cfg = input_guardrails_config.get("encoding_sanitization") or {}
    if enc_cfg.get("enabled"):
        original_len = len(result)
        result = _HTML_TAG_RE.sub(' ', result)
        result = _CONTROL_CHAR_RE.sub('', result)
        # Normalise unicode to NFC (prevents homoglyph substitution)
        result = unicodedata.normalize('NFC', result)
        # Collapse excessive whitespace
        result = re.sub(r'[ \t]{3,}', ' ', result)
        result = re.sub(r'\n{4,}', '\n\n\n', result)
        if len(result) != original_len:
            logger.info("Guardrail [encoding_sanitization] %sStripped %d chars",
                        prefix, original_len - len(result))

    # ── PII on input — redact before sending to LLM ────────────────────────────
    in_pii_cfg = input_guardrails_config.get("pii") or {}
    if in_pii_cfg.get("enabled"):
        action = in_pii_cfg.get("action", "redact")
        result, findings = _check_pii(result, action)
        if findings:
            msg = f"{prefix}Input PII detected: {', '.join(findings)}"
            logger.warning("Guardrail [input.pii] %s", msg)
            if action == "block":
                raise GuardrailViolation("input.pii", msg)

    # ── Secrets detection ─────────────────────────────────────────────────────
    sec_cfg = input_guardrails_config.get("secrets_detection") or {}
    if sec_cfg.get("enabled"):
        action = sec_cfg.get("action", "block")
        found_secrets: List[str] = []
        for name, pattern in _SECRETS_PATTERNS:
            matches = pattern.findall(result)
            if matches:
                found_secrets.append(name)
                if action == "redact":
                    result = pattern.sub(f"[{name.upper()}_REDACTED]", result)
        if found_secrets:
            msg = f"{prefix}Secrets detected in context: {found_secrets}"
            logger.warning("Guardrail [input.secrets_detection] %s", msg)
            if action == "block":
                raise GuardrailViolation("input.secrets_detection", msg)

    # ── Prompt injection detection ─────────────────────────────────────────────
    pi_cfg = input_guardrails_config.get("prompt_injection") or {}
    if pi_cfg.get("enabled"):
        action = pi_cfg.get("action", "block")
        match = _PROMPT_INJECTION_RE.search(result)
        if match:
            msg = f"{prefix}Prompt injection detected: '{match.group(0)[:60]}'"
            logger.warning("Guardrail [input.prompt_injection] %s", msg)
            if action == "block":
                raise GuardrailViolation("input.prompt_injection", msg)
            elif action == "redact":
                result = _PROMPT_INJECTION_RE.sub("[INJECTION_REDACTED]", result)

    # ── Data classification guard ──────────────────────────────────────────────
    dc_cfg = input_guardrails_config.get("data_classification") or {}
    if dc_cfg.get("enabled"):
        action = dc_cfg.get("action", "block")
        match = _DATA_CLASSIFICATION_RE.search(result)
        if match:
            msg = f"{prefix}Classified data marker found: '{match.group(0)}'"
            logger.warning("Guardrail [input.data_classification] %s", msg)
            if action == "block":
                raise GuardrailViolation("input.data_classification", msg)
            elif action == "redact":
                result = _DATA_CLASSIFICATION_RE.sub("[CLASSIFIED_REDACTED]", result)

    # ── Profanity filter ───────────────────────────────────────────────────────
    prof_cfg = input_guardrails_config.get("profanity") or {}
    if prof_cfg.get("enabled"):
        action = prof_cfg.get("action", "redact")
        if _PROFANITY_RE.search(result):
            msg = f"{prefix}Profanity detected in context"
            logger.warning("Guardrail [input.profanity] %s", msg)
            if action == "block":
                raise GuardrailViolation("input.profanity", msg)
            elif action == "redact":
                result = _PROFANITY_RE.sub("[PROFANITY_REDACTED]", result)

    # ── Language enforcement ───────────────────────────────────────────────────
    lang_cfg = input_guardrails_config.get("language_enforcement") or {}
    if lang_cfg.get("enabled") and lang_cfg.get("expected_language"):
        action = lang_cfg.get("action", "block")
        expected = lang_cfg["expected_language"].lower()
        detected = _detect_language(result)
        if detected != expected:
            msg = (f"{prefix}Language mismatch — expected '{expected}', "
                   f"detected '{detected}'")
            logger.warning("Guardrail [input.language_enforcement] %s", msg)
            if action == "block":
                raise GuardrailViolation("input.language_enforcement", msg)
            # redact / approve: just log, continue

    # ── Context length limit — applied last so redactions reduce length ────────
    cl_cfg = input_guardrails_config.get("context_length") or {}
    if cl_cfg.get("enabled"):
        max_chars = int(cl_cfg.get("max_chars") or 8000)
        on_exceed = cl_cfg.get("on_exceed", "truncate")
        if len(result) > max_chars:
            msg = (f"{prefix}Context length {len(result)} chars exceeds "
                   f"limit {max_chars}")
            logger.warning("Guardrail [input.context_length] %s", msg)
            if on_exceed == "error":
                raise GuardrailViolation("input.context_length", msg)
            elif on_exceed == "truncate":
                # Truncate from the middle to preserve start (system prompt)
                # and end (most recent message).  Keep 60% start / 40% end.
                keep_start = int(max_chars * 0.60)
                keep_end   = max_chars - keep_start
                omitted = len(result) - max_chars
                result = (
                    result[:keep_start]
                    + f"\n\n[...{omitted} chars omitted by context_length guardrail...]\n\n"
                    + result[-keep_end:]
                )
            # GUARD-2: Extractive summarization — pick highest-scoring sentences
            # using word-frequency scoring (TF-like) until budget is filled.
            elif on_exceed == "summarize":
                import re as _re
                # Sentence-split (period/exclamation/question followed by space or end)
                _sent_re = _re.compile(r'(?<=[.!?])\s+')
                sentences = _sent_re.split(result)
                if len(sentences) <= 1:
                    # Can't split — fall back to truncation
                    result = result[:max_chars]
                else:
                    # Word-frequency scoring
                    words = _re.findall(r'\w+', result.lower())
                    freq: dict = {}
                    for w in words:
                        freq[w] = freq.get(w, 0) + 1
                    max_freq = max(freq.values()) or 1
                    norm_freq = {w: f / max_freq for w, f in freq.items()}

                    def _score(sent: str) -> float:
                        ws = _re.findall(r'\w+', sent.lower())
                        return sum(norm_freq.get(w, 0) for w in ws) / max(len(ws), 1)

                    # Sort sentences by score descending; preserve order while filling budget
                    scored = sorted(
                        enumerate(sentences), key=lambda t: _score(t[1]), reverse=True
                    )
                    budget = max_chars - 80  # leave room for header
                    selected: list = []
                    for idx, sent in scored:
                        if budget <= 0:
                            break
                        selected.append((idx, sent))
                        budget -= len(sent) + 1
                    # Reconstruct in original order
                    selected.sort(key=lambda t: t[0])
                    summary = " ".join(s for _, s in selected)
                    result = f"[Summarized from {len(result)} chars]\n{summary}"

    return result


def input_guardrail_result(
    context_text: str,
    input_guardrails_config: Dict[str, Any],
    node_id: str = "",
) -> Dict[str, Any]:
    """Like apply_input_guardrails but never raises; returns a structured dict.

    {
      "status":    "passed" | "blocked" | "redacted" | "truncated",
      "text":      <processed text or None if blocked>,
      "violation": <check name or None>,
      "detail":    <detail string or None>,
      "char_count_in":  <original length>,
      "char_count_out": <processed length>
    }
    """
    original_len = len(context_text)
    try:
        processed = apply_input_guardrails(context_text, input_guardrails_config, node_id)
        if processed == context_text:
            status = "passed"
        elif len(processed) < original_len - 50:
            status = "truncated"
        else:
            status = "redacted"
        return {
            "status": status, "text": processed,
            "violation": None, "detail": None,
            "char_count_in": original_len, "char_count_out": len(processed),
        }
    except GuardrailViolation as e:
        return {
            "status": "blocked", "text": None,
            "violation": e.check, "detail": e.detail,
            "char_count_in": original_len, "char_count_out": 0,
        }

