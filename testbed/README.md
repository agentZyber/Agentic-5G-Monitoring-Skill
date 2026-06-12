# ZorteNet Local Testbed

A **fully local, no-cloud, no-API-key** 5G testbed for the agentic toolkit. Three tiers:

| Tier | RAN | Core | LLM | SDR? | Use it for |
|---|---|---|---|---|---|
| **1 — laptop** (default) | UERANSIM (sim gNB+UE) | Open5GS | Ollama | none | the 60-second demo; agentic O&M; everything except real radio |
| **2 — real RF / O-RAN** | srsRAN (+ OSC RIC) | Open5GS | Ollama | ZMQ or USRP | `ran-opt-copilot`, E2/KPM closed loop |
| **3 — cloud-native** | UERANSIM | Open5GS (Helm) | Ollama/vLLM | none | CI, multi-node |

> ### ⚠️ Validation status (read me)
> The **agentic overlay** in [`docker-compose.yml`](docker-compose.yml) (Ollama + toolkit +
> Prometheus + Grafana) is **syntax-validated** (`docker compose config`). It has **not yet been
> brought up end-to-end** in the authoring environment because no Docker daemon was available
> there. The **Open5GS + UERANSIM core** is delegated to the **verified canonical quickstart**
> (below) rather than a hand-rolled core, so the risky part runs on a known-good upstream.
> First `make testbed-up` on your machine is the real validation — if anything needs a tweak,
> it'll be image tags / host wiring, and it's easy to fix.

## Architecture (Tier 1)

```
   ┌─────────── your machine (Docker) ───────────────────────────────────┐
   │                                                                       │
   │   UERANSIM gNB ── NGAP/GTP ──> Open5GS 5GC (AMF/SMF/UPF/NRF/…)        │
   │        │                              │  NEF + Prometheus metrics      │
   │   UERANSIM UE (traffic)               │                                │
   │                                       ▼                                │
   │   ┌──────────────── agentic overlay (this compose) ───────────────┐   │
   │   │  ZorteNet toolkit  ◀── tools/MCP/A2A ──▶  agents/clients        │   │
   │   │      │  reasons with                                            │   │
   │   │      ▼                                                          │   │
   │   │   Ollama (local LLM)        Prometheus ──▶ Grafana (optional)   │   │
   │   └────────────────────────────────────────────────────────────────┘  │
   └───────────────────────────────────────────────────────────────────────┘
```

## Prerequisites

- Docker + Docker Compose v2
- ~8 GB free RAM (more if you pull a larger Ollama model), a few GB disk
- macOS/Windows Docker Desktop or Linux with the daemon running

## Quickstart (Tier 1)

### 1. Bring up the 5G core + RAN (Open5GS + UERANSIM)

This is the **verified canonical no-SDR combination** (Open5GS documents the pairing directly).
Use one of these known-good upstreams:

- **Open5GS + UERANSIM (official tutorial):** https://open5gs.org/open5gs/docs/ → *"My first 5G Core: Open5GS and UERANSIM"*
- **Compose-native (recommended for a laptop):** Gradiant `openverso` images, or
  `herlesupreeth/docker_open5gs` (per-NF compose with a `.env`).

Provision at least one subscriber (IMSI/Ki/OPc) in the Open5GS WebUI (`http://localhost:9999`)
matching your UERANSIM `ue.yaml`, then start the gNB and UE. Confirm the UE gets a PDU session.

> Make the core reachable from the overlay: either run it on the same Docker network as this
> compose (`zortenet-net`) or rely on the default `host.docker.internal` wiring (Docker Desktop).

### 2. Bring up the agentic overlay (this compose)

```bash
make testbed-up                 # ollama + zortenet toolkit + prometheus
make testbed-models             # pull the default Ollama model (llama3.1:8b)
make testbed-up PROFILE=dashboards   # also start Grafana (optional)
```

Endpoints: toolkit `http://localhost:5000/docs` · Ollama `http://localhost:11434` ·
Prometheus `http://localhost:9090` · Grafana `http://localhost:3000`.

### 3. Run a demo

```bash
# talk to your network, locally, no API keys:
curl "http://localhost:5000/agent/rag/summary"
# (capability-pack demos like `make demo PACK=netops-copilot` land in milestone M1)
```

## Configuration

Set via environment (see `docker-compose.yml`):

| Var | Default | Meaning |
|---|---|---|
| `OLLAMA_MODEL` | `llama3.1:8b` | local model to pull/use |
| `CORE_TYPE` | `open5gs` | which core adapter the toolkit drives |
| `OPEN5GS_BASE_URL` | `http://host.docker.internal:29508` | Open5GS SBI/NEF reachable from the toolkit. **Default fits the host-published topology (Docker Desktop).** If you instead attach Open5GS to `zortenet-net` (the shared-network option above), set this to the core's container/service name, e.g. `http://open5gs-amf:7777` — `host.docker.internal` will *not* reach a sibling container. |

## Tier 2 — real RF / O-RAN (opt-in, advanced)

Swap UERANSIM for **srsRAN** (ZMQ virtual RF — no SDR — or a USRP) and add the **OSC RIC** for an
E2/KPM closed loop. This is the verified open-source O-RAN setup (OSC RIC + srsRAN over E2AP).
Note: srsUE 5G-SA is a research prototype with known attach/PDU bugs — keep UERANSIM as the
default and use srsRAN only when you need real radio or O-RAN xApps.

The toolkit's RIC face is the **A1 policy client** (`a1-ric` connector): point `A1_BASE_URL` at
the OSC A1 mediator and `ran-opt-copilot` can read policy types/policies; policy *writes* flow
through the intent approval ledger.

## Tier 3 — Amarisoft + USRP B2xx (real RF lab — commercial callbox)

For labs with an **Amarisoft callbox** and **Ettus B2xx** SDRs (real COTS phones attach):

- **Amarisoft runs on its own host** (licensed software — nothing to add to this compose). Enable
  its remote API and point the toolkit at it: `AMARISOFT_WS_URL=ws://<callbox>:9001`. The
  `amarisoft` connector reads stats/UE lists and executes **approval-gated** control
  (`config_set`, handover, channel-sim fault injection). Install the optional transport dep:
  `pip install websockets`.
- **Executor selection:** `ZORTENET_EXECUTOR=amarisoft` switches intent application from the
  default `SimulatedExecutor` to real Amarisoft `config_set` calls — approved intents then change
  the real network. Leave unset for simulated (the honest default).
- **RF discipline:** prefer a **conducted/shielded** setup (cabled RF or a shield box) — OTA 5G
  needs spectrum authorization; use **programmable test SIMs** matching the callbox's configured
  PLMN/Ki/OPc.
- **vLLM for quality:** serve a large model on the GPU host
  (`vllm serve <model> --tensor-parallel-size 4`, plus `--enable-auto-tool-choice` and the
  model-matching `--tool-call-parser` for tool calling) and point the toolkit at it:
  `ZORTENET_LLM=vllm VLLM_BASE_URL=http://<gpu-host>:8000`.

> **Validation status:** the Amarisoft/A1 connectors are mock-tested against the documented API
> shapes; the catalog marks both **live-pending** until they're exercised against the real
> callbox/RIC here. Field schemas vary by Amarisoft release — expect small adapter tweaks on
> first contact.

## Tier 3 — Kubernetes / Helm

Open5GS + UERANSIM Helm charts exist upstream (e.g. Gradiant `openverso-charts`, `towards5gs`);
deploy the same overlay (Ollama + toolkit + Prometheus) alongside them for CI / multi-node runs.

## Troubleshooting

- **Toolkit can't reach Open5GS** → two supported topologies: (a) **host-published** (Docker
  Desktop) keep the `host.docker.internal` default; (b) **shared network** — attach Open5GS to
  `zortenet-net` and set `OPEN5GS_BASE_URL` to the core's container/service name (e.g.
  `http://open5gs-amf:7777`). `host.docker.internal` does *not* reach a sibling container, and on
  Linux without Docker Desktop the core must be host-published on a reachable interface.
- **Ollama slow / OOM** → pull a smaller model: `make testbed-models OLLAMA_MODEL=qwen2.5:7b`.
- **No Open5GS metrics in Prometheus** → enable the `metrics` module in `amf.yaml`/`smf.yaml`/`upf.yaml`.
