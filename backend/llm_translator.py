"""
llm_translator.py
LLM-powered English-to-JSON translation and customization utility
Features:
- Translate English instructions to workflow JSON using LLM (OpenAI/Gemini)
- Validate output against schema
- Error handling and retry logic
- Manual adapter mode (prints PROMPT+CONTEXT to STDOUT for manual LLM use)
"""

import os
import json
from typing import Dict, Any, Optional

# You can swap this for Gemini or other LLM providers
import openai
import requests

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schemas", "langgraph_workflow.schema.json")

# LM Studio defaults — chat completions endpoint preferred for modern models
LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234")
LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", f"{LM_STUDIO_BASE_URL}/v1/completions")
LM_STUDIO_CHAT_URL = os.getenv("LM_STUDIO_CHAT_URL", f"{LM_STUDIO_BASE_URL}/v1/chat/completions")
LM_STUDIO_MODEL = os.getenv("LM_STUDIO_MODEL", "local-model")

class LLMTranslator:
    """Translator with pluggable modes: 'openai', 'lm_studio', or 'manual'."""
    # LLM-1: default model read from env var; falls back to a stable GPT-4 model
    DEFAULT_OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4-1106-preview")

    def __init__(self, schema_path: str = SCHEMA_PATH, openai_api_key: Optional[str] = None, mode: str = "openai",
                 lm_studio_url: Optional[str] = None, lm_studio_model: Optional[str] = None,
                 openai_model: Optional[str] = None):
        self.schema = self._load_schema(schema_path)
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        openai.api_key = self.openai_api_key
        self.mode = mode.lower()
        # LLM-1: configurable OpenAI model (constructor arg > env var > default)
        self.openai_model = openai_model or self.DEFAULT_OPENAI_MODEL
        # Derive base URL so we can build both endpoints from one config value
        base = (lm_studio_url or os.getenv("LM_STUDIO_BASE_URL", LM_STUDIO_BASE_URL)).rstrip("/")
        if "/v1/" in base:
            # Legacy: caller passed full completions URL — strip to base
            base = base.split("/v1/")[0]
        self.lm_studio_base_url = base
        self.lm_studio_url = f"{base}/v1/completions"
        self.lm_studio_chat_url = f"{base}/v1/chat/completions"
        self.lm_studio_model = lm_studio_model or os.getenv("LM_STUDIO_MODEL", LM_STUDIO_MODEL)

    def _load_schema(self, path: str) -> Dict[str, Any]:
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _call_lm_studio(self, prompt: str, temperature: float = 0.2) -> str:
        """Send a prompt to LM Studio. Tries chat/completions endpoint first (preferred for modern models),
        falls back to legacy completions if chat returns an error."""
        return self._call_lm_studio_chat(prompt, temperature)

    def _call_lm_studio_chat(self, prompt: str, temperature: float = 0.2) -> str:
        """Use /v1/chat/completions — preferred format for modern LM Studio models."""
        payload = {
            "model": self.lm_studio_model,
            "messages": [
                {"role": "system", "content": "You are an expert AI workflow architect. Always respond with valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "stream": False,
            "max_tokens": 4096,
        }
        try:
            response = requests.post(self.lm_studio_chat_url, json=payload, timeout=180)
            response.raise_for_status()
            data = response.json()
            text = data["choices"][0]["message"]["content"].strip()
        except Exception:
            # Fall back to legacy completions endpoint
            text = self._call_lm_studio_completions(prompt, temperature)
        return self._strip_code_fences(text)

    def _call_lm_studio_completions(self, prompt: str, temperature: float = 0.2) -> str:
        """Legacy /v1/completions endpoint — fallback for older LM Studio versions."""
        payload = {
            "model": self.lm_studio_model,
            "prompt": prompt,
            "temperature": temperature,
            "stream": False,
            "max_tokens": 4096,
        }
        response = requests.post(self.lm_studio_url, json=payload, timeout=180)
        response.raise_for_status()
        data = response.json()
        text = data["choices"][0]["text"].strip()
        return self._strip_code_fences(text)

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        """Remove markdown ```json ... ``` fences that models sometimes wrap output in."""
        if text.startswith("```"):
            lines = text.splitlines()
            lines = lines[1:] if lines[0].startswith("```") else lines
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        return text

    def _build_prompt(self, instructions: str, base_json: Optional[Dict[str, Any]] = None, customization: bool = False) -> str:
        # Compact schema — avoids token bloat while keeping field names visible
        schema_str = json.dumps(self.schema, separators=(',', ':'))
        few_shot = (
            '{"graph_name":"ResearchWorkflow","version":"1.0","nodes":[{'
            '"id":"Planner","type":"agent","system_prompt":"Plan the task","next":"Researcher"},'
            '{"id":"Researcher","type":"agent","tools":["web_search"],'
            '"pre_llm":{"rag":{"enabled":true,"provider":"ltm","query_template":"{state.task}","top_k":5}},'
            '"llm_config":{"temperature":0.3,"max_tokens":1024},'
            '"context":{"sources":[{"type":"stm","keys":["task"]},{"type":"pre_llm","result_id":"rag_results"}],'
            '"synthesis":{"strategy":"concatenate"}},'
            '"guardrails":{"pii":{"enabled":true,"action":"redact"}},'
            '"output_schema":{"format":"json","state_key":"research_result"},"next":"END"}],'
            '"edges":[{"from":"Planner","to":"Researcher"}],'
            '"state_schema":{"task":{"type":"string","description":"The user task","default_value":""},'
            '"research_result":{"type":"string","default_value":""}}}'
        )
        if customization and base_json is not None:
            prompt = (
                "You are an expert AI workflow architect specialising in LangGraph enterprise workflows.\n"
                "Given the base JSON config and the customization instructions below, output ONLY a valid JSON "
                "config conforming to this schema (no explanation, no markdown fences):\n"
                f"SCHEMA: {schema_str}\n"
                f"BASE JSON: {json.dumps(base_json, separators=(',', ':'))}\n"
                f"CUSTOMIZATION: {instructions}\n"
                "OUTPUT (JSON only):"
            )
        else:
            prompt = (
                "You are an expert AI workflow architect specialising in LangGraph enterprise workflows.\n"
                "Output ONLY a valid JSON config (no explanation, no markdown fences) conforming to this schema.\n"
                f"SCHEMA: {schema_str}\n"
                f"EXAMPLE OUTPUT: {few_shot}\n"
                f"INSTRUCTIONS: {instructions}\n"
                "OUTPUT (JSON only):"
            )
        return prompt

    def _parse_json_and_validate(self, json_str: str) -> Dict[str, Any]:
        try:
            config = json.loads(json_str)
        except Exception as e:
            raise ValueError(f"Failed to parse JSON from LLM response: {e}\nResponse was:\n{json_str}")
        self._validate(config)
        return config

    def get_prompt(self, instructions: str, base_json: Optional[Dict[str, Any]] = None, customization: bool = False) -> str:
        """Return the full prompt (useful for APIs that need to return prompt to user)."""
        return self._build_prompt(instructions, base_json=base_json, customization=customization)

    def parse_llm_response(self, response_text: str) -> Dict[str, Any]:
        """Parse & validate an LLM response string (JSON expected)."""
        return self._parse_json_and_validate(response_text)

    def english_to_json(self, instructions: str, retries: int = 2) -> Dict[str, Any]:
        prompt = self._build_prompt(instructions, customization=False)
        if self.mode == "manual":
            # Print prompt to STDOUT and read pasted model output
            print("\n===== COPY the PROMPT below into your LLM/interpreter =====\n")
            print(prompt)
            print("\n===== END PROMPT =====")
            print("\nAfter invoking your LLM with the prompt, paste the LLM output (JSON only). End your paste with a single line containing only '###END###'.")
            lines = []
            while True:
                try:
                    line = input()
                except EOFError:
                    break
                if line.strip() == "###END###":
                    break
                lines.append(line)
            json_str = "\n".join(lines).strip()
            return self._parse_json_and_validate(json_str)

        if self.mode == "lm_studio":
            for attempt in range(retries + 1):
                try:
                    json_str = self._call_lm_studio(prompt)
                    return self._parse_json_and_validate(json_str)
                except Exception as e:
                    if attempt == retries:
                        raise ValueError(f"LM Studio translation failed after {retries+1} attempts: {e}")
            raise ValueError("LM Studio translation failed.")

        # Automated (OpenAI) path
        for attempt in range(retries + 1):
            try:
                response = openai.ChatCompletion.create(
                    model=self.openai_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                )
                json_str = response["choices"][0]["message"]["content"]
                config = json.loads(json_str)
                self._validate(config)
                return config
            except Exception as e:
                if attempt == retries:
                    raise ValueError(f"LLM translation failed after {retries+1} attempts: {e}")
        raise ValueError("LLM translation failed.")

    def customize_json(self, base_json: Dict[str, Any], custom_instructions: str, retries: int = 2) -> Dict[str, Any]:
        prompt = self._build_prompt(custom_instructions, base_json=base_json, customization=True)
        if self.mode == "manual":
            print("\n===== COPY the PROMPT below into your LLM/interpreter =====\n")
            print(prompt)
            print("\n===== END PROMPT =====")
            print("\nAfter invoking your LLM with the prompt, paste the LLM output (JSON only). End your paste with a single line containing only '###END###'.")
            lines = []
            while True:
                try:
                    line = input()
                except EOFError:
                    break
                if line.strip() == "###END###":
                    break
                lines.append(line)
            json_str = "\n".join(lines).strip()
            return self._parse_json_and_validate(json_str)

        if self.mode == "lm_studio":
            for attempt in range(retries + 1):
                try:
                    json_str = self._call_lm_studio(prompt)
                    return self._parse_json_and_validate(json_str)
                except Exception as e:
                    if attempt == retries:
                        raise ValueError(f"LM Studio customization failed after {retries+1} attempts: {e}")
            raise ValueError("LM Studio customization failed.")

        for attempt in range(retries + 1):
            try:
                response = openai.ChatCompletion.create(
                    model=self.openai_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                )
                json_str = response["choices"][0]["message"]["content"]
                config = json.loads(json_str)
                self._validate(config)
                return config
            except Exception as e:
                if attempt == retries:
                    raise ValueError(f"LLM customization failed after {retries+1} attempts: {e}")
        raise ValueError("LLM customization failed.")

    def _validate(self, config: Dict[str, Any]):
        if self.schema:
            from jsonschema import validate, ValidationError as SchemaValidationError
            try:
                validate(instance=config, schema=self.schema)
            except SchemaValidationError as e:
                raise ValueError(f"Config validation failed: {e}")

# Usage examples (CLI):
# translator = LLMTranslator(mode="manual")
# config = translator.english_to_json("Create a workflow where a researcher looks up stock prices and a coder writes a python script to graph them.")
# custom_config = translator.customize_json(config, "Add a reviewer step before the writer.")

