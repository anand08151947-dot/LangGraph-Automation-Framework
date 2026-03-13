# Phoenice Constellation — Command Cheatsheet

Quick-reference for all frequently used PowerShell / CLI commands.  
All paths assume the repo root is `C:\Anand\AI-WorkSpace\Phoenice-Constellation`.

---

## 1 · Environment Setup

```powershell
# Create virtual environment (first time only)
python -m venv .venv

# Activate virtual environment (run this every new terminal)
.\.venv\Scripts\Activate.ps1

# Install / update Python dependencies
pip install -r requirements.txt

# Deactivate virtual environment
deactivate
```

---

## 2 · Backend

```powershell
# Start backend (standard)
python -m uvicorn backend.api_backend:app --host 0.0.0.0 --port 8000

# Start backend with auto-reload (development)
python -m uvicorn backend.api_backend:app --reload

# Start backend in background (detached, returns PID)
Start-Process -NoNewWindow -FilePath "python" `
  -ArgumentList "-m uvicorn backend.api_backend:app --host 0.0.0.0 --port 8000" `
  -PassThru | Select-Object Id

# Stop background backend by PID (replace 12345)
Stop-Process -Id 12345
```

---

## 3 · Frontend

```powershell
# Install Node dependencies (first time / after pulling)
cd frontend
npm install

# Start Vite dev server  →  http://localhost:3000
npm run dev

# Production build
npx vite build

# Preview production build locally
npx vite preview
```

---

## 4 · Testing

```powershell
# Run all backend tests
pytest tests/

# Run a specific test file
pytest tests/test_api.py -v

# Run with coverage
pytest tests/ --cov=backend --cov-report=term-missing
```

---

## 5 · LM Studio Health Checks

```powershell
# List loaded models
curl -s http://localhost:1234/v1/models

# Quick completions smoke-test
$body = '{"model":"llama-3.2-3b-instruct","prompt":"Say hello in one word.","temperature":0.2,"stream":false,"max_tokens":20}'
curl -s -X POST http://localhost:1234/v1/completions `
  -H "Content-Type: application/json" -d $body

# Chat completions smoke-test
$body = '{"model":"llama-3.2-3b-instruct","messages":[{"role":"user","content":"Say hello."}],"temperature":0.2,"max_tokens":20}'
curl -s -X POST http://localhost:1234/v1/chat/completions `
  -H "Content-Type: application/json" -d $body
```

---

## 6 · Backend API Smoke Tests

```powershell
# Health check
curl -s http://localhost:8000/health

# English → JSON translation
$body = '{"instructions":"Create a two-agent workflow: a researcher and a writer."}'
curl -s -X POST http://localhost:8000/english_to_json `
  -H "Content-Type: application/json" -d $body | Select-Object -First 40

# List all templates
curl -s http://localhost:8000/templates

# List all runs
curl -s http://localhost:8000/runs

# Poll run status (replace <run_id>)
curl -s http://localhost:8000/status/<run_id>

# Get generated artifact code files
curl -s http://localhost:8000/artifacts/<run_id>/code

# Download artifact ZIP bundle
curl -s -o bundle.zip http://localhost:8000/download_bundle/<run_id>
```

---

## 7 · Git

```powershell
# Show git status
git --no-pager status

# Show staged diff
git --no-pager diff --staged

# List ALL tracked files (useful for auditing what is committed)
git ls-files --cached

# Check for files that SHOULD be gitignored but are still tracked
git ls-files --cached | Where-Object {
  $_ -match "__pycache__|\.pyc$|\.pyo$|/artifacts/|node_modules|/dist/|dist-ssr|\.db$|\.zip$|\.log$|\.env|\.coverage|htmlcov"
}

# Remove a mistakenly tracked file from git index (without deleting it)
git rm --cached path/to/file

# Commit with Copilot co-author trailer
git commit -m "feat: your message

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## 8 · Code Inspection (PowerShell)

```powershell
# Search for specific patterns inside a Python file
Get-Content "backend\api_backend.py" | Select-String `
  -Pattern "import sys|_run_workflow_async|orchestrate_async|workflow_status\[run_id\]|if __name__" |
  Select-Object LineNumber, Line | Format-Table -AutoSize

# Count lines in a file
(Get-Content "backend\api_backend.py").Count

# Find all Python files containing a string
Get-ChildItem -Recurse -Filter "*.py" |
  Select-String -Pattern "MemoryManager" |
  Select-Object Filename, LineNumber, Line | Format-Table -AutoSize
```

---

## 9 · Artifact Management

```powershell
# List all run artifact folders
Get-ChildItem backend\artifacts -Directory | Select-Object Name, LastWriteTime

# Inspect generated agent.py for a run
Get-Content "backend\artifacts\<run_id>\agent.py" | Select-Object -First 60

# Check validation report score
Get-Content "backend\artifacts\<run_id>\validation_report.json"
```

---

## 10 · Useful One-Liners

```powershell
# Tail backend logs (if writing to a file)
Get-Content -Wait backend\logs\app.log

# Count TODO stubs remaining in generated code
Select-String -Path "backend\artifacts\*\agent.py" -Pattern "TODO" | Measure-Object

# Quick Python syntax check on a generated agent
python -m py_compile "backend\artifacts\<run_id>\agent.py" && Write-Host "Syntax OK"

# Open the workbench in the browser
Start-Process "http://localhost:3000"
```
