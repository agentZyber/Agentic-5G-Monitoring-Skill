# ZorteNet 5G NetApp

<p align="center">
  <img src="assets/zortenet-icon.png" alt="ZorteNet icon" width="144">
</p>

ZorteNet is a FastAPI-based 5G Network Application that consumes 5G core location callbacks, applies UE policy checks, streams events in real time, and exposes agent-friendly context and RAG endpoints.

## Highlights

- FastAPI service with health, subscription, policy, streaming, and agent endpoints
- Multi-core abstraction for `NEF`, `Open5GS`, and `Free5GC`
- Real-time WebSocket and SSE event streaming
- In-memory plus Chroma-backed context store for search and mobility analysis
- LangGraph/LangChain integrations for agentic reasoning when AI credentials are available
- Automated tests covering API, core adapters, and agent/context logic

## Repository Layout

- `src/`: application source code
- `testing_netapp/`: automated tests plus a manual live integration harness
- `iac/`: infrastructure-related artifacts
- `pac/`: Jenkins pipeline scripts

## Requirements

- Python `3.11`
- Docker and Docker Compose for containerized usage
- A reachable 5G core / NEF environment if you want live subscriptions
- Optional `OPENAI_API_KEY` for the agent endpoints that use OpenAI-backed models

## Quick Start

### Local Python

```bash
cp .env.example .env
python3.11 -m venv .venv
.venv/bin/pip install --upgrade pip setuptools wheel
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn src.api:app --host 0.0.0.0 --port 5000 --reload
```

### Docker

```bash
cp .env.example .env
docker compose up --build
```

The container startup path uses `src/prepare.sh` to render the CAPIF registration file and then launch the API on port `5000`.

## Environment

Start from `.env.example`. The main variables are:

- `NEF_ADDRESS`, `NEF_USER`, `NEF_PASSWORD`
- `CAPIF_HOSTNAME`, `CAPIF_PORT_HTTP`, `CAPIF_PORT_HTTPS`
- `CALLBACK_ADDRESS`
- `PATH_TO_CERTS`
- `NETAPP_HOSTNAME`
- Optional `CORE_TYPE` to switch between `nef`, `open5gs`, and `free5gc`
- Optional `OPENAI_API_KEY` for agent initialization against OpenAI models

## Testing

```bash
.venv/bin/python -m pytest testing_netapp -q
```

Current verified result:

- `103 passed, 1 skipped` on Python `3.11`

The skipped test in `testing_netapp/test_netapp_endpoints.py` is a manual live integration harness. Run that file directly only when a real NetApp target is already available.

## API Usage

Once running, FastAPI serves interactive docs at:

- `http://localhost:5000/docs`
- `http://localhost:5000/redoc`

Useful endpoints include:

- `GET /health`
- `POST /subscription`
- `POST /setPolicy`
- `POST /netAppCallback`
- `GET /cores/status`
- `GET /agent/context`
- `GET /agent/rag/summary`
- `GET /stream/status`

## Agentic 5G Workflow

ZorteNet fits naturally into an agentic 5G loop where an LLM-driven operator, assistant, or automation watches live network events and turns them into context-aware actions.

1. The agent creates subscriptions against `NEF`, `Open5GS`, or `Free5GC` through the NetApp API.
2. Live callbacks arrive at `/netAppCallback`, where ZorteNet normalizes events, checks policies, and stores context for retrieval.
3. The agent queries `/agent/context`, `/agent/rag/summary`, or the streaming endpoints to understand what changed for a UE, area, or policy scope.
4. Based on that context, the agent can alert an operator, trigger another workflow, adapt service behavior, or request follow-up actions from surrounding systems.

In practice, that means ZorteNet can act as the memory and event bridge between 5G core telemetry and an orchestration agent that needs both real-time signals and searchable historical context.

## CI

GitHub Actions CI is included in `.github/workflows/ci.yml` and runs the test suite on Python `3.11`.

## Release Notes

See `CHANGELOG.md` for the current release summary.

## Final Public Release Checklist

- Choose and add an explicit open-source license before making the repository public
- Replace placeholder environment values in your local `.env`
- Confirm any deployment-specific CAPIF / NEF details for your target environment
- Tag a release after CI passes on GitHub
