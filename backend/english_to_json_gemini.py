
import json
import os
from typing import Optional
from pathlib import Path
from google import genai
import jsonschema

SCHEMA_PATH = Path(__file__).parent / "langgraph_workflow.schema.json"

with open(SCHEMA_PATH, "r") as f:
    WORKFLOW_SCHEMA = json.load(f)

SYSTEM_PROMPT = """
You are an expert AI workflow architect. Given a user's English description of a multi-agent workflow, generate a JSON configuration for a LangGraph-based agentic system. 
- The output must strictly follow the provided JSON schema.
- Use the schema below:
{schema}
- Only output valid JSON, no comments or explanations.
""".strip()

def validate_config(config: dict) -> Optional[str]:
    try:
        jsonschema.validate(instance=config, schema=WORKFLOW_SCHEMA)
        return None
    except jsonschema.ValidationError as e:
        return str(e)

def english_to_json_gemini(user_intent: str, output_path: Optional[str] = None, max_attempts: int = 3) -> dict:
    os.environ["GEMINI_API_KEY"] = "AIzaSyDfBSxIKVn386klL1tX63OkQ3hTvvVNokg"
    client = genai.Client()
    prompt = SYSTEM_PROMPT.format(schema=json.dumps(WORKFLOW_SCHEMA, indent=2))
    attempt = 0
    error_context = ""
    while attempt < max_attempts:
        if attempt == 0:
            full_prompt = f"{prompt}\nUser Intent: {user_intent}\nOutput:"
        else:
            full_prompt = f"{prompt}\nUser Intent: {user_intent}\nPrevious attempt failed: {error_context}\nPlease try again and ensure the output is valid JSON and matches the schema. Output:"
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=full_prompt
        )
        json_str = response.text.strip()
        try:
            config = json.loads(json_str)
        except json.JSONDecodeError as e:
            error_context = f"Error: Output is not valid JSON. Details: {e}. Output: {json_str}"
            print(error_context)
            attempt += 1
            continue
        validation_error = validate_config(config)
        if validation_error:
            error_context = f"Error: Output does not match schema. Details: {validation_error}. Output: {json.dumps(config, indent=2)}"
            print(error_context)
            attempt += 1
            continue
        if output_path:
            with open(output_path, "w") as f:
                json.dump(config, f, indent=2)
        return config
    print(f"Failed to generate valid config after {max_attempts} attempts. Please review the workflow description or try again later. Last error: {error_context}")
    return None

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python english_to_json_gemini.py 'Describe your workflow...' [output.json]")
        exit(1)
    user_intent = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    config = english_to_json_gemini(user_intent, output_path)
    if config:
        print(json.dumps(config, indent=2))
