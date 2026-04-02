PYTHON ?= python3.11
VENV ?= .venv
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest
PYTHON_BIN := $(VENV)/bin/python

.PHONY: setup test test-all run docker-build docker-up clean

setup:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip setuptools wheel
	$(PIP) install -r requirements.txt

test:
	$(PYTEST) testing_netapp -q

test-all:
	rm -rf chroma_db
	$(PYTEST) testing_netapp -q

run:
	$(PYTHON_BIN) -m uvicorn src.api:app --host 0.0.0.0 --port 5000 --reload

docker-build:
	docker build -t zortenet-netapp .

docker-up:
	docker compose up --build

clean:
	rm -rf $(VENV) .pytest_cache chroma_db
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +

