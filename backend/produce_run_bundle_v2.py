"""Produce a run bundle that includes a human-friendly README with run metadata and reproduction commands.
Usage: python produce_run_bundle_v2.py <run_id> [--api http://127.0.0.1:8000]
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

# GEN-2: Import CodeGenerator to include deployment artifacts in the bundle
try:
    sys.path.insert(0, os.path.dirname(__file__))
    from code_generator import CodeGenerator as _CodeGenerator
    _code_gen = _CodeGenerator()
    _CODE_GEN_AVAILABLE = True
except Exception:
    _code_gen = None  # type: ignore
    _CODE_GEN_AVAILABLE = False


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
    """Write a human-friendly README for the run bundle."""
    status_str = json.dumps(status.get('result', {}), indent=2)
    config_str = json.dumps(config, indent=2)
    readme = f"""# Run bundle: {run_id}

## Summary

- Run ID: `{run_id}`
- Status: **{status.get('status')}**

## Result Snapshot
```
{status_str}
```

## Stored Config
```
{config_str}
```

## Reproduction Commands

Start the server in the repository root (from a Python venv):
```
python -m uvicorn backend.api_backend:app --host 127.0.0.1 --port 8000
```

Create a run by POSTing the template JSON to /orchestrate_async (example using curl):
```
curl -s -H 'Content-Type: application/json' -d '@config.json' \
  http://127.0.0.1:8000/orchestrate_async
```

Check run status:
```
curl -s http://127.0.0.1:8000/status/{run_id}
```

Fetch stored config for the run:
```
curl -s http://127.0.0.1:8000/runs/{run_id}/config
```

Artifacts included:
- status JSON
- config JSON (if present)
- any existing run artifacts (stm/ltm/events/result)
"""
    with open(path, 'w', encoding='utf-8') as f:
        f.write(readme)


def main():
    if len(sys.argv) < 2:
        print("Usage: python produce_run_bundle_v2.py <run_id> [--api http://127.0.0.1:8000]")
        sys.exit(1)
    run_id = sys.argv[1]
    api = 'http://127.0.0.1:8000'
    if len(sys.argv) >= 3 and sys.argv[2].startswith('--api'):
        api = sys.argv[2].split('=', 1)[1] if '=' in sys.argv[2] else sys.argv[3]

    status_url = urljoin(api, f"/status/{run_id}")
    config_url = urljoin(api, f"/runs/{run_id}/config")

    try:
        status = fetch_json(status_url)
    except Exception as e:
        print(f"Failed to fetch status from {status_url}: {e}")
        sys.exit(2)

    try:
        config_resp = fetch_json(config_url)
        config = config_resp.get('config') if isinstance(config_resp, dict) else config_resp
    except Exception:
        config = None

    artifacts_dir = os.path.join(os.path.dirname(__file__), 'artifacts')
    os.makedirs(artifacts_dir, exist_ok=True)

    readme_path = os.path.join(artifacts_dir, f"{run_id}_README.md")
    write_readme(readme_path, run_id, status, config or {})

    bundle_path = os.path.join(artifacts_dir, f"{run_id}_bundle_with_readme.zip")
    with zipfile.ZipFile(bundle_path, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        # Track filenames we have already added to avoid duplicate entries in the ZIP
        added = set()
        def add_to_zip(path, arcname=None):
            name = arcname or os.path.basename(path)
            if name in added:
                return
            z.write(path, arcname=name)
            added.add(name)

        # Include README and status/config files
        add_to_zip(readme_path)
        status_path = os.path.join(artifacts_dir, f"{run_id}_status.json")
        with open(status_path, 'w', encoding='utf-8') as f:
            json.dump(status, f, indent=2)
        add_to_zip(status_path)
        if config is not None:
            config_path = os.path.join(artifacts_dir, f"{run_id}_config.json")
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
            add_to_zip(config_path)
        # Include any run-specific artifacts already present (skip duplicates)
        pattern = os.path.join(artifacts_dir, f"{run_id}*")
        for path in glob.glob(pattern):
            add_to_zip(path)

        # GEN-2: Include deployment artifacts (Dockerfile, docker-compose.yml, CI workflow)
        if _CODE_GEN_AVAILABLE and config is not None:
            try:
                dockerfile_content = _code_gen.generate_dockerfile(config)
                z.writestr("Dockerfile", dockerfile_content)
            except Exception as _e:
                z.writestr("Dockerfile.error", f"# Failed to generate Dockerfile: {_e}\n")

            try:
                compose_content = _code_gen.generate_docker_compose(config)
                z.writestr("docker-compose.yml", compose_content)
            except Exception as _e:
                z.writestr("docker-compose.error.yml", f"# Failed to generate docker-compose.yml: {_e}\n")

            try:
                ci_content = _code_gen.generate_github_actions(config)
                z.writestr(".github/workflows/ci.yml", ci_content)
            except Exception as _e:
                z.writestr(".github/workflows/ci.error.yml", f"# Failed to generate ci.yml: {_e}\n")

    print("Bundle created:", bundle_path)


if __name__ == '__main__':
    main()
