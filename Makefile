PYTHON ?= python3.11
VENV ?= .venv
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest
PYTHON_BIN := $(VENV)/bin/python

OLLAMA_MODEL ?= llama3.1:8b
PROFILE ?=
PROFILE_FLAG := $(if $(PROFILE),--profile $(PROFILE))

.PHONY: setup test test-all test-toolkit run docker-build docker-up clean \
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
	@until docker exec zortenet-ollama ollama list >/dev/null 2>&1; do echo "waiting for ollama to be ready..."; sleep 2; done
	docker exec zortenet-ollama ollama pull $(OLLAMA_MODEL)

run:
	$(PYTHON_BIN) -m uvicorn src.api:app --host 0.0.0.0 --port 5000 --reload

docker-build:
	docker build -t zortenet-netapp .

docker-up:
	docker compose up --build

clean:
	rm -rf $(VENV) .pytest_cache chroma_db
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +

