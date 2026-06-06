# ZorteNet — The Agentic 5G/6G Toolkit

<p align="center">
  <img src="assets/zortenet-icon.png" alt="ZorteNet icon" width="144">
</p>

> **Clone it, `make testbed-up`, and talk to your 5G network — locally, no API keys.**
> An open-source, batteries-included toolkit that turns a 5G/6G core + RAN into an **agent-native,
> multi-protocol, locally-runnable** autonomous network. Built to be the *foundation* an SNS JU /
> 5G-PPP / 6G research project clones and builds on.

**Why this exists.** EU 5G/6G projects are saturated in a narrow set of *vertical* use cases
(XR/VR, drones, V2X, robotics), and — in the projects examined — where AI appears it is typically
**non-agentic** (narrow ML or classical RL). *(That gap is a hedged, medium-confidence inference,
not a proven fact — see [the blueprint §1.2](docs/AGENTIC_TOOLKIT_BLUEPRINT.md).)* Making *the
network itself* agentic — observe → reason → act, over standard agent protocols, running fully
local — is the underexplored, high-leverage opening this toolkit targets.

> 📐 **Full design & research:** [`docs/AGENTIC_TOOLKIT_BLUEPRINT.md`](docs/AGENTIC_TOOLKIT_BLUEPRINT.md)
> — grounded in two adversarially-verified deep-research passes (44 verified claims, primary sources).

## What makes it different

- 🔌 **Agent-native by default** — one `ToolRegistry`, many protocol faces: **MCP** (agent↔tool),
  **A2A** (agent↔agent), plus OpenAI/Anthropic/Ollama tool schemas. Write a network tool once,
  expose it everywhere.
- 🏠 **100% local, zero-cloud** — **Ollama** is the default LLM; **Open5GS + UERANSIM** is the
  core+RAN. No API keys needed to try it.
- 🧩 **Multi-domain** — a generalized `NetworkEvent` spans location, QoS, throughput, slice, energy,
  security, RAN-KPI, signaling — not just one event type.
- 📦 **Capability packs** — turnkey `{tools + prompt + datasets + connectors}` bundles.
- 📊 **Datasets + benchmark** — TeleQnA / Tele-Data / 5G3E / TSpec-LLM wired into a registry.
- 📡 **Standards-bridged** — designed to speak O-RAN A1/E2, 3GPP intent (TS 28.312), TM Forum TMF921.

## Status

**Milestone 0 (foundation) is in place and unit-tested.** This is an actively-evolving scaffold;
the table is honest about what runs today vs. what's on the roadmap.

| Area | Today (M0) | Roadmap |
|---|---|---|
| Generalized core (`NetworkEvent`) | ✅ + tests | — |
| Local-first LLM layer (Ollama default; OpenAI/Anthropic optional) | ✅ + tests | vLLM |
| Interop schemas (MCP / A2A / OpenAI / Anthropic / Ollama) | ✅ + tests | live MCP/A2A servers wired into the app |
| Capability packs | ✅ `location-monitor` | netops-copilot, intent-to-network, self-heal, … |
| Dataset registry | ✅ 6 datasets | `pull` + RAG ingest + `telco-bench` |
| Local testbed (Ollama + toolkit + Prometheus) | ✅ compose syntax-validated | live-validated bring-up; srsRAN/O-RAN tier |
| Legacy NetApp (location/geofence/RAG) | ✅ unchanged (103 tests) | folded into `location-monitor` |

## Quick start

```bash
# 1) Toolkit unit tests (no heavy deps, no daemon)
make setup            # or: python3.11 -m venv .venv && .venv/bin/pip install requests pytest
make test-toolkit     # 28 passing

# 2) Local testbed (needs Docker; see testbed/README.md for the Open5GS+UERANSIM core)
make testbed-config   # validate compose
make testbed-up       # ollama + toolkit + prometheus
make testbed-models   # pull the default Ollama model (waits for readiness)

# 3) Legacy NetApp API
make run              # uvicorn on :5000  → http://localhost:5000/docs
```

> The testbed compose is **syntax-validated**; first live `make testbed-up` is the real
> end-to-end check (see [`testbed/README.md`](testbed/README.md) for the honest validation note).

## Architecture

```
agent clients ─ MCP · A2A · REST ─┐
  interop  (zortenet.interop)      │  one capability core, many protocol faces
  packs    (zortenet.packs)        │  turnkey {tools+prompt+datasets+connectors}
  agent    (zortenet.agent)        │  LangGraph runtime + shared ToolRegistry
  llm      (zortenet.llm)          │  Ollama ▸ OpenAI ▸ Anthropic ▸ vLLM
  memory   (zortenet.memory)       │  Chroma RAG over events + knowledge base
  core     (zortenet.core)         │  NetworkEvent (typed) + bus
  connectors                       │  NEF/Open5GS/free5GC · O-RAN E2 · Prometheus · UERANSIM
  testbed/                          Open5GS + UERANSIM + Ollama + Prometheus
```

See the [blueprint](docs/AGENTIC_TOOLKIT_BLUEPRINT.md) for the full design, the verified interop
matrix (§5), the capability-pack catalog (§4), datasets (§7), and the implementation roadmap (§9).

## Repository layout

- `src/zortenet/` — the toolkit: `core/`, `llm/`, `agent/`, `interop/`, `packs/`, `datasets/`
- `src/` (top level) — the legacy ZorteNet NetApp (FastAPI app, 5G-core adapters)
- `testbed/` — local Open5GS+UERANSIM+Ollama testbed (compose, configs, README)
- `docs/` — the design blueprint
- `testing_netapp/` — legacy NetApp tests · `tests/` — new toolkit tests

---

## Legacy ZorteNet NetApp (the `location-monitor` capability)

The original ZorteNet is a FastAPI 5G Network Application that consumes 5G core location callbacks,
applies UE policy checks, streams events in real time, and exposes agent-friendly context and RAG
endpoints. It remains fully functional and is becoming the `location-monitor` capability pack.

- Multi-core abstraction for `NEF`, `Open5GS`, and `Free5GC`
- Real-time WebSocket and SSE event streaming
- In-memory + Chroma-backed context store for search and mobility analysis
- LangGraph/LangChain agentic reasoning when AI credentials are available

**Run it:** `cp .env.example .env && docker compose up --build` (or `make run`).
Useful endpoints: `GET /health`, `POST /subscription`, `POST /setPolicy`, `POST /netAppCallback`,
`GET /cores/status`, `GET /agent/context`, `GET /agent/rag/summary`. Interactive docs at
`http://localhost:5000/docs`. Key env vars: `NEF_ADDRESS`/`NEF_USER`/`NEF_PASSWORD`,
`CAPIF_*`, `CALLBACK_ADDRESS`, `CORE_TYPE` (`nef`/`open5gs`/`free5gc`), optional `OPENAI_API_KEY`.

**Tests:** legacy suite `.venv/bin/python -m pytest testing_netapp -q` (103 passed, 1 skipped);
toolkit suite `make test-toolkit` (28 passed).

## CI & License

GitHub Actions CI runs the legacy suite on Python 3.11 (`.github/workflows/ci.yml`).
ZorteNet is licensed under the [Apache License 2.0](LICENSE); see [`NOTICE`](NOTICE) for
third-party attributions (all permissive: Apache-2.0 / MIT / BSD-3-Clause).
