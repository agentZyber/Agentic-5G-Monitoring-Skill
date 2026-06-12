# Minimum Infrastructure

"Running this" means different things depending on how deep you go — from *using the library* to a
*full local 5G testbed*. Pick the lowest tier that does what you need; each builds on the previous.

> **TL;DR minimum to do something real:** a laptop with **Python 3.11**, **Ollama** + one small
> model, **8 GB RAM**. No cloud, no API keys, no GPU, no radio hardware. Add **Docker + 16 GB RAM**
> when you want the Open5GS + UERANSIM 5G testbed.

| Tier | What you can run | CPU | RAM | Disk | Extra software |
|---|---|---|---|---|---|
| **0 — Library / interop** | the toolkit as a library; all 28 unit tests; render MCP/A2A/LLM tool schemas | 1 core | ~1 GB | <0.2 GB | Python 3.11 + `requests`/`pytest` |
| **1 — Local agent** | a working LLM agent + tools, fully local | 4 cores | **8 GB** (16 GB comfortable) | ~6–10 GB | + Ollama + 1 small model |
| **2 — Full testbed** | agent **+ live Open5GS 5G core + UERANSIM RAN + Prometheus** | 4+ cores | **16 GB** (8 GB tight) | **≥25 GB free** | + Docker + Compose v2 |
| **3 — Real RF / O-RAN** | srsRAN + OSC RIC, E2/KPM xApps | 6+ cores | 16 GB+ | 30 GB+ | + srsRAN + RIC (± SDR) |

---

## Tier 0 — Library & interop only (smallest possible)

Use `zortenet.core` / `agent` / `interop` / `datasets` as a Python library, render protocol
schemas, and run the test suite. **No LLM, no 5G core, no Docker.**

- **OS:** any (Linux / macOS / Windows)
- **Software:** Python **3.11**, `pip`; packages `requests` (+ `pytest` to run tests). Optional:
  `mcp` (to serve a live MCP server), `fastapi`+`uvicorn` (A2A router — both already in `requirements.txt`).
- **Hardware:** anything; ~1 GB RAM, <200 MB disk.
- **Network:** only to `pip install`; runs offline after.
- **Can:** build tools, generate MCP `inputSchema` / A2A Agent Card / OpenAI/Anthropic/Ollama tool
  schemas, browse the dataset registry, run `make test-toolkit`.
- **Cannot:** no inference, no live network data.

## Tier 1 — Local agent with Ollama (recommended real minimum)

Everything in Tier 0 plus a **local LLM** — this is the smallest setup that actually *reasons*.

- **OS:** Linux / macOS (Apple Silicon is excellent) / Windows.
- **Software:** + **Ollama** + one model:
  - *Minimum:* `llama3.2:3b` or `qwen2.5:3b` (~2 GB download, runs in ~4–6 GB RAM)
  - *Recommended:* `llama3.1:8b` or `qwen2.5:7b` (~4.7 GB, ~8 GB RAM, better tool-calling)
- **Hardware:** **8 GB RAM minimum** (16 GB comfortable), 4 CPU cores, ~6–10 GB disk. **GPU optional**
  — only speeds up tokens/sec; CPU works.
- **Network:** pull Ollama + model on first run; fully offline after.
- **Can:** run the agent, tool-calling, MCP/A2A serving, model benchmarking (when `telco-bench` lands).
- **Cannot:** no live network telemetry (no 5G core yet).

## Tier 2 — Full local testbed (Open5GS + UERANSIM + Ollama)

The complete experience: a simulated 5G network the agent observes and acts on. See
[`testbed/README.md`](../testbed/README.md).

- **OS:** **Linux is ideal** — Open5GS and UERANSIM are Linux-native and UERANSIM needs SCTP + TUN
  (kernel features). On **macOS/Windows** run the core+RAN inside Linux containers via **Docker
  Desktop** (works, small overhead). The agentic overlay runs anywhere Docker runs.
- **Software:** + **Docker Engine 20.10+** and **Docker Compose v2**. The testbed pulls
  `ollama/ollama`, `prom/prometheus`, `grafana/grafana` (optional), and an Open5GS+UERANSIM stack.
- **Hardware:** **16 GB RAM recommended** (an 8B model + 5GC NFs + sim + Prometheus); **8 GB is
  possible** with a 3B model and the lean toolkit (skip the PyTorch-heavy RAG app). **4+ CPU
  cores. ≥25 GB free disk** (Docker images ~5–8 GB + Ollama model 2–5 GB + the legacy app image
  carries **PyTorch ≈3 GB** via `sentence-transformers` + volumes).
- **No special hardware:** UERANSIM is pure software — **no SDR, no radios, no SIM cards, no spectrum.**
- **Network:** first-run image/model/pip pulls (several GB); offline-capable afterward.
- **Can:** simulated UEs attach to Open5GS via UERANSIM, events/telemetry flow, the agent reasons
  over the live(ish) network, Prometheus scrapes NF metrics.

> **Footprint tip:** if you only need the agentic toolkit (not the legacy RAG NetApp), you avoid
> `sentence-transformers`/`chromadb`/PyTorch entirely — the toolkit modules need just `requests`
> (+ `mcp`/`fastapi` for the servers). That cuts the Python image by ~3 GB.

## Tier T — Model training (optional, GPU)

Fine-tuning your own telecom agent model (see [`MODEL_PIPELINE.md`](MODEL_PIPELINE.md)) is the one
activity that genuinely needs GPUs: a single **24 GB** card handles LoRA on a 7–8B model;
**4 × 24 GB** reaches QLoRA-70B and lets a teacher model serve while a student trains. Not needed
for any of Tiers 0–3 — inference runs on CPU.

## Tier 3 — Real RF / O-RAN (advanced, NOT part of the minimum)

For real radio or O-RAN closed-loop xApps. Opt-in only.

- **Software:** + **srsRAN** (gNB/UE) and the **O-RAN SC RIC** (OSC RIC) for E2/KPM.
- **Radio:** either **ZMQ virtual RF** (no hardware) or an **SDR** (e.g. USRP B210). Note: srsUE
  5G-SA is a research prototype — keep UERANSIM as the default and use srsRAN only when you need
  real radio.
- **Hardware:** 6+ CPU cores, 16 GB+ RAM, 30 GB+ disk; SDR + RF cabling if not using ZMQ.

---

## What you do **not** need (any tier 0–2)

- ❌ A cloud account or GPU servers — Ollama runs locally on CPU.
- ❌ API keys — Ollama is the default. (OpenAI/Anthropic are *optional* and need `pip install
  openai`/`anthropic` + a key.)
- ❌ SDR / radios / SIM cards / spectrum licences — UERANSIM simulates the RAN and UEs.
- ❌ A GPU — optional everywhere; it only speeds up LLM inference.

## Quick prerequisite self-check

```bash
python3.11 --version          # need 3.11.x
docker --version              # Tier 2: need Engine 20.10+
docker compose version       # Tier 2: need v2
docker info                  # daemon must be RUNNING (was DOWN in the authoring env)
ollama --version             # Tier 1+: install from https://ollama.com
free -g 2>/dev/null || (sysctl -n hw.memsize | awk '{print int($1/1073741824)" GB RAM"}')   # check RAM
df -h .                      # check free disk
```

*Reference: the authoring machine was 10 cores / 32 GB / 370 GB free — comfortably Tier 2,
but the Docker daemon was stopped and Ollama wasn't installed, so the testbed wasn't brought up
live there.*
