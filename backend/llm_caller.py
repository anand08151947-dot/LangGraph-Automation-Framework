"""
llm_caller.py
Unified LLM dispatch layer for the graph factory.

Reads provider config from config.json (via ConfigManager or env vars),
dispatches to the configured provider, and returns the model's text response.

Supported providers (priority order in config.json llm.mode):
  lm_studio  — local LM Studio via /v1/chat/completions (preferred)
  openai     — OpenAI chat completions API
  gemini     — Google Gemini generateContent API
  anthropic  — Anthropic Messages API
  ollama     — local Ollama /api/chat

All providers:
  - Accept system_prompt + user_prompt + llm_params (temperature, max_tokens, model)
  - Return the raw text string from the model
  - Raise LLMCallError on failure (callers can catch and fall back)
"""

import os
import json
import logging
import requests
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class LLMCallError(Exception):
    """Raised when the LLM call fails after all retries."""
    pass


def _strip_fences(text: str) -> str:
    """Remove markdown ```...``` code fences models sometimes wrap output in."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:] if lines[0].startswith("```") else lines
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

def _call_lm_studio(
    system_prompt: str,
    user_prompt: str,
    base_url: str,
    model: str,
    temperature: float,
    max_tokens: int,
    timeout: int = 180,
) -> str:
    """Call LM Studio /v1/chat/completions (preferred) with fallback to /v1/completions."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    # Prefer chat completions endpoint (works with all modern models in LM Studio)
    chat_url = f"{base_url.rstrip('/')}/v1/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    try:
        resp = requests.post(chat_url, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as chat_err:
        logger.warning("LM Studio chat endpoint failed (%s), trying completions...", chat_err)

    # Fallback: legacy /v1/completions
    comp_url = f"{base_url.rstrip('/')}/v1/completions"
    full_prompt = f"{system_prompt}\n\n{user_prompt}" if system_prompt else user_prompt
    payload_comp = {
        "model": model,
        "prompt": full_prompt,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    resp = requests.post(comp_url, json=payload_comp, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return _strip_fences(data["choices"][0]["text"].strip())


def _call_openai(
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    model: str,
    temperature: float,
    max_tokens: int,
) -> str:
    """Call OpenAI /v1/chat/completions."""
    import openai
    client = openai.OpenAI(api_key=api_key)
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content.strip()


def _call_gemini(
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    model: str,
    temperature: float,
    max_tokens: int,
) -> str:
    """Call Google Gemini generateContent API."""
    full_prompt = f"{system_prompt}\n\n{user_prompt}" if system_prompt else user_prompt
    url = f"https://generativelanguage.googleapis.com/v1/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
    }
    resp = requests.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def _call_anthropic(
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    model: str,
    temperature: float,
    max_tokens: int,
) -> str:
    """Call Anthropic Messages API."""
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload: Dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": user_prompt}],
        "temperature": temperature,
    }
    if system_prompt:
        payload["system"] = system_prompt
    resp = requests.post(url, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return data["content"][0]["text"].strip()


def _call_ollama(
    system_prompt: str,
    user_prompt: str,
    base_url: str,
    model: str,
    temperature: float,
) -> str:
    """Call local Ollama /api/chat endpoint."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})
    url = f"{base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "options": {"temperature": temperature},
        "stream": False,
    }
    resp = requests.post(url, json=payload, timeout=180)
    resp.raise_for_status()
    data = resp.json()
    return data["message"]["content"].strip()


# ---------------------------------------------------------------------------
# Public dispatch function
# ---------------------------------------------------------------------------

def call_llm(
    system_prompt: str,
    user_prompt: str,
    llm_params: Optional[Dict[str, Any]] = None,
    global_config: Optional[Dict[str, Any]] = None,
) -> str:
    """Dispatch an LLM call based on global_config['llm']['mode'].

    Args:
        system_prompt:  The node's system prompt.
        user_prompt:    The assembled context / user message.
        llm_params:     Per-node overrides: temperature, max_tokens, model.
        global_config:  The full config.json dict (from ConfigManager).
                        If None, falls back to environment variables.

    Returns:
        The LLM's text response.

    Raises:
        LLMCallError: If the call fails.
    """
    cfg = global_config or {}
    params = llm_params or {}

    # Resolve provider
    mode = cfg.get("llm", {}).get("mode", os.getenv("LLM_MODE", "lm_studio")).lower()

    # Per-node model override takes priority; then provider default; then sensible global default
    node_model: Optional[str] = params.get("model")
    temperature: float = float(params.get("temperature") or 0.7)
    max_tokens: int = int(params.get("max_tokens") or 1024)

    try:
        if mode == "lm_studio":
            lm_cfg = cfg.get("lm_studio", {})
            # Support both base_url and legacy full url
            base_url = (
                lm_cfg.get("base_url")
                or os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234")
            )
            # Strip /v1/... suffix if user saved old-style URL
            if "/v1/" in base_url:
                base_url = base_url.split("/v1/")[0]
            model = node_model or lm_cfg.get("model") or os.getenv("LM_STUDIO_MODEL", "local-model")
            logger.info("LLM call → LM Studio | model=%s | temp=%.2f | max_tokens=%d", model, temperature, max_tokens)
            return _call_lm_studio(system_prompt, user_prompt, base_url, model, temperature, max_tokens)

        elif mode == "openai":
            api_key = cfg.get("api_keys", {}).get("openai") or os.getenv("OPENAI_API_KEY", "")
            model = node_model or cfg.get("openai", {}).get("model", "gpt-4o")
            logger.info("LLM call → OpenAI | model=%s", model)
            return _call_openai(system_prompt, user_prompt, api_key, model, temperature, max_tokens)

        elif mode == "gemini":
            api_key = cfg.get("api_keys", {}).get("gemini") or os.getenv("GEMINI_API_KEY", "")
            model = node_model or cfg.get("gemini", {}).get("model", "gemini-2.0-flash")
            logger.info("LLM call → Gemini | model=%s", model)
            return _call_gemini(system_prompt, user_prompt, api_key, model, temperature, max_tokens)

        elif mode == "anthropic":
            api_key = cfg.get("api_keys", {}).get("anthropic") or os.getenv("ANTHROPIC_API_KEY", "")
            model = node_model or cfg.get("anthropic", {}).get("model", "claude-3-5-sonnet-20241022")
            logger.info("LLM call → Anthropic | model=%s", model)
            return _call_anthropic(system_prompt, user_prompt, api_key, model, temperature, max_tokens)

        elif mode == "ollama":
            ollama_cfg = cfg.get("ollama", {})
            base_url = ollama_cfg.get("url") or os.getenv("OLLAMA_URL", "http://localhost:11434")
            model = node_model or ollama_cfg.get("model", "llama3")
            logger.info("LLM call → Ollama | model=%s", model)
            return _call_ollama(system_prompt, user_prompt, base_url, model, temperature)

        else:
            raise LLMCallError(f"Unknown LLM mode: '{mode}'. Set llm.mode in config.json.")

    except LLMCallError:
        raise
    except Exception as exc:
        raise LLMCallError(f"LLM call failed (mode={mode}): {exc}") from exc
