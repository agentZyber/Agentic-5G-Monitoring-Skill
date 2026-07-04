# CORE Lab NCSRD — The Agentic 5G/6G Toolkit

<p align="center">
  <img src="assets/corelab-icon.png" alt="CORE Lab NCSRD icon" width="144">
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

| Area | Today (Stages 1–5 code-complete) | Roadmap |
|---|---|---|
| Generalized core (`NetworkEvent`) + **event bus/store** | ✅ + tests — multi-domain ring-buffer store, `/events` ingest + query, legacy shim | durable persistence |
| LLM layer (local-first) | ✅ Ollama default + **vLLM (GPU serving, tool calling)** + OpenAI/Anthropic | token streaming |
| Agent runtime + trajectory capture | ✅ tool-calling loop + training-shape JSONL logging | — |
| Interop faces | ✅ **MCP (stdio + Streamable HTTP, wire-tested)** · **A2A (card + full task lifecycle at `/a2a`)** · **ACP shim** · **AG-UI SSE** · **OASF record** · **ANP (experimental)** · REST | official-SDK conformance runs; AAIF convergence tracking |
| **Multi-agent NOC** | ✅ ran/core/security **specialist agents** behind A2A task managers; orchestrator delegates via A2A `message/send` envelopes (≥3-agent cooperative scenario tested) | cross-host multi-instance run |
| **Intent layer (standards bridge)** | ✅ TMF921/TIO + TS 28.312 renderings, validation, **enforced human-approval ledger** (approval is *not* an agent tool) | SHACL strictness; live KPI-observed apply |
| Capability packs | ✅ 8 (incl. **`multi-agent-noc`**) + **pack generator** (`make new-pack`, contract-tested output) | community packs |
| **TeleAgentBench** | ✅ v0: 5 scenarios, **programmatic state-based judges** (incl. the safety gate scenario); judges proven to discriminate competent/lazy/unsafe agents | live model scores; held-out set (S5) |
| Knowledge base (RAG) | ✅ dependency-light **BM25 + citations** (`spec-kb`) | embedding backend |
| Connectors | ✅ Prometheus, Open5GS, UERANSIM control, NWDAF stub, **Amarisoft**, **A1/RIC** — `/connectors` catalog with honest statuses | live validation (callbox/RIC) |
| Datasets & bench | ✅ registry + `pull` CLI + replay → bus + `telco-bench` runner | baseline scores (needs Ollama) |
| **Training pipeline (gated G0→G3)** | ✅ baseline harness ("no gap → don't train" encoded), curation + **contamination guard**, machine-validated synth, mixture honesty, **enforced gate ledger**, GPU presets, hedged model card — `make train ARGS=status` | **the GPU runs** (G0 numbers, LoRA-SFT, publication) |
| Deployment | ✅ compose (syntax-validated) + **Helm chart (lint + template pass, CI-checked)**; Tier-2/3 documented | **live bring-up = the open gate item** |
| Legacy NetApp | ✅ unchanged (103 tests) | one-line bus wiring at live bring-up |
| CI | ✅ legacy + toolkit matrix (3.11/3.12) + compose check + **helm lint** | — |

## Quick start

> 🖥️ **Requirements:** minimum is a laptop with Python 3.11 + Ollama + 8 GB RAM (no cloud, no GPU,
> no radio). Full tiered breakdown in [`docs/INFRASTRUCTURE.md`](docs/INFRASTRUCTURE.md).

```bash
# 1) Toolkit setup + unit tests (light deps — no PyTorch, no daemon)
make setup-toolkit    # venv + requirements-toolkit.txt
make test-toolkit     # full toolkit suite

# 2) Run the agent-native toolkit app (REST + A2A + MCP-over-HTTP at /mcp)
make run-toolkit      # :5001 → /docs, /agent/ask, /.well-known/agent-card.json, /mcp
make mcp-stdio        # or serve the MCP face over stdio (Claude Code/Desktop etc.)

# 3) Benchmark a local model on telecom knowledge (needs Ollama running)
make telco-bench ARGS="--limit 200"

# 4) Local testbed (needs Docker; see testbed/README.md for the Open5GS+UERANSIM core)
make testbed-config   # validate compose
make testbed-up       # ollama + toolkit + prometheus
make testbed-models   # pull the default Ollama model (waits for readiness)

# 5) Legacy NetApp API
make run              # uvicorn on :5000  → http://localhost:5000/docs
```

> The testbed compose is **syntax-validated**; first live `make testbed-up` is the real
> end-to-end check (see [`testbed/README.md`](testbed/README.md) for the honest validation note).

## Architecture

```
agent clients ─ MCP · A2A · REST ─┐
  interop  (corelab.interop)      │  one capability core, many protocol faces
  packs    (corelab.packs)        │  turnkey {tools+prompt+datasets+connectors}
  agent    (corelab.agent)        │  LangGraph runtime + shared ToolRegistry
  llm      (corelab.llm)          │  Ollama ▸ OpenAI ▸ Anthropic ▸ vLLM
  memory   (corelab.memory)       │  Chroma RAG over events + knowledge base
  core     (corelab.core)         │  NetworkEvent (typed) + bus
  connectors                       │  NEF/Open5GS/free5GC · O-RAN E2 · Prometheus · UERANSIM
  testbed/                          Open5GS + UERANSIM + Ollama + Prometheus
```

See the [blueprint](docs/AGENTIC_TOOLKIT_BLUEPRINT.md) for the full design, the verified interop
matrix (§5), the capability-pack catalog (§4), datasets (§7), and the implementation roadmap (§9).

## Repository layout

- `src/corelab/` — the toolkit: `core/`, `llm/`, `agent/`, `interop/`, `packs/`, `datasets/`
- `src/` (top level) — the legacy CORE Lab NCSRD NetApp (FastAPI app, 5G-core adapters)
- `testbed/` — local Open5GS+UERANSIM+Ollama testbed (compose, configs, README)
- `docs/` — [design blueprint](docs/AGENTIC_TOOLKIT_BLUEPRINT.md) · [implementation plan](docs/IMPLEMENTATION_PLAN.md) (Stages 0–5) · [infrastructure tiers](docs/INFRASTRUCTURE.md) · [model pipeline](docs/MODEL_PIPELINE.md)
- `testing_netapp/` — legacy NetApp tests · `tests/` — new toolkit tests

---

## Legacy CORE Lab NCSRD NetApp (the `location-monitor` capability)

The original CORE Lab NCSRD is a FastAPI 5G Network Application that consumes 5G core location callbacks,
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
CORE Lab NCSRD is licensed under the [Apache License 2.0](LICENSE); see [`NOTICE`](NOTICE) for
third-party attributions (all permissive: Apache-2.0 / MIT / BSD-3-Clause).
