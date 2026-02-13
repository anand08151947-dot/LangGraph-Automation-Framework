import json
from typing import Optional
from pathlib import Path
import argparse

from llm_translator import LLMTranslator

SCHEMA_PATH = Path(__file__).parent / "langgraph_workflow.schema.json"

SYSTEM_PROMPT = """
You are an expert AI workflow architect. Given a user's English description of a multi-agent workflow, generate a JSON configuration for a LangGraph-based agentic system. 
- The output must strictly follow the provided JSON schema.
- Use the schema below:
{schema}
- Only output valid JSON, no comments or explanations.
""".strip()


def english_to_json(user_intent: str, output_path: Optional[str] = None, mode: str = "openai") -> dict:
    translator = LLMTranslator(mode=mode)
    if mode == "manual":
        # Manual: prints prompt and waits for pasted LLM output
        return translator.english_to_json(user_intent)
    else:
        return translator.english_to_json(user_intent)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("intent", help="Describe your workflow in English")
    parser.add_argument("output", nargs="?", help="Optional output JSON path")
    parser.add_argument("--mode", choices=["openai", "manual"], default="openai", help="LLM mode: automated openai or manual copy/paste")
    args = parser.parse_args()

    user_intent = args.intent
    output_path = args.output
    mode = args.mode

    config = english_to_json(user_intent, output_path=output_path, mode=mode)
    if output_path and mode != "manual":
        with open(output_path, "w") as f:
            json.dump(config, f, indent=2)
    print(json.dumps(config, indent=2))
