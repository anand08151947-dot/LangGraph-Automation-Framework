"""Produce a run bundle that includes a human-friendly README with run metadata and reproduction commands.
Usage: python produce_run_bundle.py <run_id> [--api http://127.0.0.1:8000]
"""
import sys
import os
import json
import glob
import zipfile
from urllib.parse import urljoin
try:
    import requests
except Exception:
    requests = None


def fetch_json(url):
    if requests:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.json()
    else:
        # fallback to urllib
        from urllib.request import urlopen, Request
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=10) as fh:
            return json.load(fh)


def write_readme(path, run_id, status, config):
    lines = [
        f"# Run bundle: {run_id}\n",
        "## Summary\n",
        f"- Run ID: `{run_id}`\n",
        f"- Status: **{status.get('status')}**\n",
        "\n",
        "## Result Snapshot\n",
        "```",
        json.dumps(status.get('result', {}), indent=2),
        "```",
        "\n",
        "## Stored Config\n",
        "```",
        json.dumps(config, indent=2),
        "```",
        "\n",
        "## Reproduction Commands\n",
        "Start the server in the repository root (from a Python venv):\n",
        "```
python -m uvicorn backend.api_backend:app --host 127.0.0.1 --port 8000
```",
        "\n",
        "Create a run by POSTing the template JSON to /orchestrate_async (example using curl):\n",
        "```
curl -s -H 'Content-Type: application/json' -d '@config.json' \
  http://127.0.0.1:8000/orchestrate_async
```",
        "\n",
        "Check run status:\n",
        "```
curl -s http://127.0.0.1:8000/status/",
        f"{run_id}\n```",