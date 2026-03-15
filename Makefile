# Phoenice Constellation — Developer Makefile
# TEST-8: make dev, make test, make bundle
#
# Usage:
#   make dev       — start backend + frontend in dev mode
#   make test      — run all backend pytest tests
#   make bundle    — build frontend production bundle
#   make install   — install all Python + Node dependencies
#   make lint      — run Python linter (flake8/ruff if available)
#   make clean     — remove build artifacts and __pycache__

.PHONY: dev test bundle install lint clean backend frontend

PYTHON  := python
PIP     := pip
NPM     := npm
BACKEND_DIR := backend
FRONTEND_DIR := frontend
TESTS_DIR := tests

# ── dev: start backend and frontend concurrently ─────────────────────────────
dev: backend frontend

backend:
	@echo ">>> Starting FastAPI backend on http://localhost:8000"
	cd $(BACKEND_DIR) && uvicorn api_backend:app --reload --host 0.0.0.0 --port 8000

frontend:
	@echo ">>> Starting Vite frontend on http://localhost:5173"
	cd $(FRONTEND_DIR) && $(NPM) run dev

# ── test: run all pytest tests ───────────────────────────────────────────────
test:
	@echo ">>> Running backend tests with pytest"
	$(PYTHON) -m pytest $(TESTS_DIR) -q --tb=short

test-verbose:
	$(PYTHON) -m pytest $(TESTS_DIR) -v --tb=long

test-coverage:
	$(PYTHON) -m pytest $(TESTS_DIR) --cov=$(BACKEND_DIR) --cov-report=term-missing -q

# ── bundle: build frontend for production ────────────────────────────────────
bundle:
	@echo ">>> Building frontend production bundle"
	cd $(FRONTEND_DIR) && $(NPM) run build
	@echo ">>> Bundle written to $(FRONTEND_DIR)/dist/"

# ── install: install all dependencies ────────────────────────────────────────
install: install-python install-node

install-python:
	@echo ">>> Installing Python dependencies"
	$(PIP) install -r requirements.txt

install-node:
	@echo ">>> Installing Node dependencies"
	cd $(FRONTEND_DIR) && $(NPM) install

# ── lint: run Python linter ──────────────────────────────────────────────────
lint:
	@echo ">>> Running Python linter"
	@if command -v ruff >/dev/null 2>&1; then \
		ruff check $(BACKEND_DIR) $(TESTS_DIR); \
	elif command -v flake8 >/dev/null 2>&1; then \
		flake8 $(BACKEND_DIR) $(TESTS_DIR) --max-line-length=120; \
	else \
		echo "No linter found. Install ruff or flake8."; \
	fi

# ── clean: remove build artifacts ────────────────────────────────────────────
clean:
	@echo ">>> Cleaning build artifacts"
	rm -rf $(FRONTEND_DIR)/dist
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	@echo ">>> Clean complete"
