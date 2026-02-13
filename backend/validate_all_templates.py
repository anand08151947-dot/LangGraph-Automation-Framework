import json
import glob
import os
import sys
from jsonschema import validate, ValidationError

ROOT = os.path.dirname(__file__)
SCHEMA_PATH = os.path.join(ROOT, "langgraph_workflow.schema.json")

# Patterns to look for: all prompt_templates JSON files and any top-level templates file
PATTERNS = [os.path.join(ROOT, "prompt_templates_*.json"), os.path.join(ROOT, "prompt_templates", "*.json")]


def load_schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def iter_template_entries(path):
    """Yield tuples (entry_desc, config_dict) for each template found in file."""
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    # If data is a list, each element is a template wrapper with template_json
    if isinstance(data, list):
        for i, item in enumerate(data):
            cfg = item.get("template_json") or item
            desc = f"{os.path.basename(path)}[{i}]"
            yield desc, cfg
    elif isinstance(data, dict):
        # Single object; may be a wrapper with template_json
        cfg = data.get("template_json") or data
        desc = os.path.basename(path)
        yield desc, cfg
    else:
        raise ValueError(f"Unrecognized JSON structure in {path}")


def main():
    schema = load_schema()
    files = []
    for pat in PATTERNS:
        files.extend(glob.glob(pat))

    files = sorted(set(files))
    if not files:
        print("No template files found with patterns:")
        for p in PATTERNS:
            print("  ", p)
        return 0

    total = 0
    failures = []
    for path in files:
        print(f"Checking file: {path}")
        try:
            for desc, cfg in iter_template_entries(path):
                total += 1
                try:
                    validate(instance=cfg, schema=schema)
                    print(f"  OK: {desc}")
                except ValidationError as e:
                    print(f"  INVALID: {desc} -> {e.message}")
                    failures.append((path, desc, str(e)))
        except Exception as e:
            print(f"  ERROR reading {path}: {e}")
            failures.append((path, None, str(e)))

    print("\nSummary:")
    print(f"  Files scanned: {len(files)}")
    print(f"  Templates checked: {total}")
    print(f"  Failures: {len(failures)}")
    if failures:
        for f in failures:
            print("    -", f)
        return 2
    print("All templates valid.")
    return 0


if __name__ == '__main__':
    rc = main()
    sys.exit(rc)
