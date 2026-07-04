PYTHON ?= python3.11
VENV ?= .venv
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest
PYTHON_BIN := $(VENV)/bin/python

OLLAMA_MODEL ?= llama3.1:8b
PROFILE ?=
PROFILE_FLAG := $(if $(PROFILE),--profile $(PROFILE))

.PHONY: setup setup-toolkit test test-all test-toolkit run run-toolkit mcp-stdio \
        telco-bench teleagent-bench new-pack train \
        docker-build docker-up clean \
        testbed-config testbed-up testbed-down testbed-logs testbed-models

setup:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip setuptools wheel
	$(PIP) install -r requirements.txt

test:
	$(PYTEST) testing_netapp -q

test-all:
	rm -rf chroma_db
	$(PYTEST) testing_netapp -q

# New agentic-toolkit unit tests (core / llm / datasets / interop) — no heavy deps required.
test-toolkit:
	$(PYTEST) tests -q

# Toolkit venv with the light dependency set (uses the newest python3.1x available).
TOOLKIT_PY := $(shell command -v python3.11 || command -v python3.12 || command -v python3)
setup-toolkit:
	$(TOOLKIT_PY) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements-toolkit.txt

# Run the new toolkit app (REST /agent/ask + A2A + MCP-over-HTTP at /mcp) on :5001.
run-toolkit:
	PYTHONPATH=src $(PYTHON_BIN) -m uvicorn corelab.app:app --host 0.0.0.0 --port 5001

# Serve the MCP face over stdio (for local MCP clients, e.g. Claude Code/Desktop).
mcp-stdio:
	PYTHONPATH=src $(PYTHON_BIN) -m corelab.interop.mcp_server

# Score the configured model on TeleQnA (fetches the dataset on first run).
telco-bench:
	PYTHONPATH=src $(PYTHON_BIN) -m corelab.packs.telco_bench --data datasets/TeleQnA.txt $(ARGS)

# Scenario-based agentic benchmark (programmatic, state-based judges).
teleagent-bench:
	PYTHONPATH=src $(PYTHON_BIN) -m corelab.bench $(ARGS)

# Scaffold a new capability pack (NAME=my-pack DESC="what it does").
new-pack:
	PYTHONPATH=src $(PYTHON_BIN) -m corelab.packs.new $(NAME) --description "$(DESC)"

# The gated training pipeline (ARGS="status" | "g0 ..." | "curate" | "synth" | "mixture" | "config" | "card").
train:
	PYTHONPATH=src $(PYTHON_BIN) -m corelab.train $(ARGS)

# --- Local testbed (testbed/) ------------------------------------------------
testbed-config:
	cd testbed && docker compose config

testbed-up:
	cd testbed && docker compose $(PROFILE_FLAG) up -d --build

testbed-down:
	cd testbed && docker compose down

testbed-logs:
	cd testbed && docker compose logs -f

testbed-models:
	@until docker exec corelab-ollama ollama list >/dev/null 2>&1; do echo "waiting for ollama to be ready..."; sleep 2; done
	docker exec corelab-ollama ollama pull $(OLLAMA_MODEL)

run:
	$(PYTHON_BIN) -m uvicorn src.api:app --host 0.0.0.0 --port 5000 --reload

docker-build:
	docker build -t corelab-netapp .

docker-up:
	docker compose up --build

clean:
	rm -rf $(VENV) .pytest_cache chroma_db
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +

