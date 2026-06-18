# Implementation Plan — Staged

> **Status:** canonical sequencing for the framework (supersedes the coarse M0–M4 outline in
> [blueprint §9](AGENTIC_TOOLKIT_BLUEPRINT.md) — a mapping table is at the end).
> **Decision honored:** the LoRA-SFT / model-training work is deliberately the **last** stage;
> only its cheap *data-capture* hooks land early (Stage 1), so training data accumulates for free
> across every stage that runs the agent.
> Effort figures are **indicative estimates** for one full-time engineer; stages parallelize
> across contributors.

## Principles (apply to every stage)

1. **Verify before claiming** — a stage is "done" when its exit gate passes live (tests + a real
   bring-up), not when the code merges. Stage ends get an adversarial review pass.
2. **Capture early, train late** — trajectory logging from Stage 1; GPU training only in Stage 5,
   gated on measured need (G0).
3. **Sim before RF** — derisk every agent loop on the free Open5GS+UERANSIM stack before touching
   Amarisoft/USRP (Stage 3).
4. **One star deliverable per stage** — each stage ships something shareable (GIF, benchmark,
   real-RF video, multi-agent demo, model release).

## Overview

| Stage | Name | Goal (one line) | Star deliverable | Est. effort |
|---|---|---|---|---|
| **0** | Foundation | core model, LLM layer, interop schemas, first pack, testbed overlay | 28-test green scaffold | ✅ **done** |
| **1** | Agent-native core | "talk to your live (sim) 5G network" end-to-end, locally | README demo GIF + telco-bench baselines | ~3–5 wks |
| **2** | Multi-domain & RAG depth | agent reasons across QoS/slice/energy/security, not just location | 5G3E-replay anomaly demo | ~3–4 wks |
| **3** | Standards bridge & real RF | act via TMF921/TS 28.312/O-RAN; Amarisoft + USRP online | NL intent → real network change (video) | ~4–6 wks |
| **4** | Multi-agent & ecosystem | NOC-of-agents over A2A; full protocol coverage; community surface | 3-agent cooperative scenario + TeleAgentBench | ~3–5 wks |
| **5** | **Model pipeline (LoRA-SFT — last)** | train only where measurement shows a gap; publish dataset+model | fine-tuned 8B + dataset + scores | ~2–4 wks (GPU-bound) |

---

## Stage 0 — Foundation ✅ (complete)

Built and verified in this repo: generalized `NetworkEvent` (10 domains + legacy bridge),
local-first LLM layer (Ollama default; OpenAI/Anthropic optional), `ToolRegistry` + interop
schemas (MCP `inputSchema`, A2A Agent Card, OpenAI/Anthropic/Ollama tool formats),
`location-monitor` pack, dataset registry (6 datasets, licence-flagged), testbed overlay
(compose syntax-validated), Makefile targets, 28 unit tests, adversarial review applied (8/8
findings fixed). **Carry-over debt:** live testbed bring-up not yet performed (no Docker daemon
in the authoring environment) — it is Stage 1's first task.

## Stage 1 — Agent-native core ("talk to your network")

**Goal:** a complete agentic loop on the laptop testbed: event → context → local LLM → tool call →
answer, reachable over MCP.

**Build:** *(status as of the testbed-free build pass — code-complete items are mock/wire-tested;
items needing the live testbed or Ollama are explicitly left open)*
- [ ] **Live testbed bring-up** (first task): `make testbed-up` for real; fix wiring; record the
      end-to-end smoke test (UERANSIM event → toolkit → agent answer). Clears Stage-0 debt.
      **← still open: requires testbed access (no Docker daemon/Ollama in the build environment).**
- [x] **Agent runtime loop** (`zortenet.agent.runtime`): provider-agnostic tool-calling loop
      (Ollama/OpenAI/Anthropic call shapes), error-recovering, iteration-bounded — 12 tests.
- [x] **Live MCP server**: stdio entrypoint (`make mcp-stdio`) + **Streamable HTTP mounted at
      `/mcp`** in the app; wire-protocol round-trip (initialize → tools/list → tools/call)
      tested in-process. External-client validation happens at live bring-up.
- [x] **A2A router mounted**: Agent Card at `/.well-known/agent-card.json` + skill invocation,
      served by `zortenet.app` (TestClient-verified).
- [x] **`netops-copilot` v0**: health overview, PromQL KPI query, core subscriptions, UE status —
      mock-tested incl. graceful degradation; **live validation pending testbed**.
- [x] **Trajectory-capture hooks**: training-shape JSONL via `TrajectoryLogger`
      ([MODEL_PIPELINE.md](MODEL_PIPELINE.md) §2.2); on by default in the app, `ZORTENET_TRAJECTORIES=off` opts out.
- [x] **`telco-bench` v0 runner**: TeleQnA loader (fetch-on-demand, never vendored) + MCQ runner +
      per-category report + CLI (`make telco-bench`); fixture-tested.
      **← baseline *numbers* still open: requires a running Ollama.**
- [x] CI: toolkit job (Python 3.11 + 3.12, light deps) + compose validation, alongside the legacy job.

**Exit gate:** fresh clone → `make testbed-up` → ask the agent a question about the live simulated
network and get a grounded answer — demonstrated in the README GIF; baselines table published;
CI green. **Gate not yet met, but the core is now LIVE-VALIDATED (2026-06-12):** the agent
tool-calling loop ran end-to-end against a real model (`qwen2.5:14b` on a local Ollama GPU node)
— 3 valid tool calls, 0 errors, answer grounded in the seeded multi-domain store. Remaining:
testbed bring-up, telco-bench baseline numbers, README GIF.

## Stage 2 — Multi-domain observability & RAG depth

**Goal:** kill the "one event type" narrowness in practice — the agent reasons over multi-domain,
historical, and replayed data.

**Build:** *(status as of the testbed-free build pass — same convention as Stage 1)*
- [x] **Connector registry**: event bus + bounded **EventStore** (`zortenet.core.bus`),
      **UERANSIM control connector** (nr-cli via injectable runner: status/deregister/
      ps-establish — the fault-injection primitive; **live validation pending testbed**),
      **NWDAF stub** (Nnwdaf_AnalyticsInfo shape; honest "no NWDAF in default testbed" results),
      connector catalog at `/connectors`.
- [x] **Legacy convergence (shim)**: `network_event_from_legacy` bridges the legacy
      `LocationEvent` dataclass *and* callback dict; domain-aware textualizers via
      `NetworkEvent.text_repr`. **← the one-line wiring inside `src/api.py` lands at live
      bring-up** (needs the legacy heavy-dep environment to run its suite).
- [x] **Knowledge base**: dependency-light **BM25** retrieval with citations
      (`zortenet.memory`) + **`spec-kb` pack** (`search_specs`/`kb_status`, lazy ingest from
      `ZORTENET_KB_DIR`). Embedding/Chroma backend can slot behind the same interface later.
- [x] **Dataset `pull` + loaders + replay**: registry-driven CLI
      (`python -m zortenet.datasets pull <name>` — TeleQnA auto-fetch; oversized/licence-flagged
      sets get explicit guidance, never blind downloads); **CSV/JSONL replay → event bus**
      (5G3E-shaped, time-compression). **← replay of *actual* 5G3E data pending its manual fetch.**
- [x] **`security-sentinel`** (explainable rules: failure bursts, signaling storms, cell-hopping
      audits) and **`self-heal` v0** (diagnose-only + human-approved playbooks, apply = Stage 3).
- [x] **AG-UI event stream v0**: `/agui/run` SSE in the published event taxonomy
      (RUN/TOOL_CALL/TEXT_MESSAGE lifecycle). *Post-hoc streaming; token-level streaming +
      official-client conformance check deferred to provider-streaming work.*

**Exit gate:** agent answers a cross-domain question (e.g. correlates QoS degradation with
mobility) on live sim data; 5G3E replay drives an anomaly-detection demo; packs
enable/disable cleanly via config. **Status: the cross-domain correlation and pack-config
requirements are demonstrated in mock integration tests (`tests/test_agui_and_integration.py`);
the *live-data* versions remain open pending testbed access.**

## Stage 3 — Standards bridge & real RF (the credibility stage)

**Goal:** act on networks through *standard* interfaces, and bring the real hardware
(Amarisoft + Ettus B2xx) online. This is where the framework stops being sim-only.

**Build:** *(status as of the testbed-free build pass — same convention as Stages 1–2)*
- [x] **`intent-to-network`**: intent model + **three renderings** (TIO Turtle — rdflib
      parse-validated, TIO JSON-LD, TS 28.312 intentExpectations JSON); structural validation;
      **enforced approval state machine** (draft → dry-run → submit → *human approves via
      REST-only `/intents/{id}/approve`* → gated apply). Approve/reject are deliberately **not
      agent tools**. *Strict SHACL/official-schema conformance deferred to standards validation.*
- [x] **Amarisoft connector** (mock-first): WebSocket-JSON remote-API client
      (stats/ue_get/config_set/handover/channel-sim faults) behind an injectable transport +
      **AmarisoftExecutor** for real intent application (`ZORTENET_EXECUTOR=amarisoft`).
      **✅ LIVE-VALIDATED (2026-06-12)** against a real Mini (Amarisoft 2023-12-15, 5G NR SA,
      gNB remote API on `:9001`): first-contact fix applied — the WS handshake **requires an `Origin`
      header** and the server sends a `ready` frame to consume before commands (regression-tested).
      `config_get`/`stats`/`ue_list` confirmed against the live gNB. Control/`config_set` still
      to be exercised live; HMAC auth path untested (the Mini has no password set).
- [x] **Tier-3 real-RF testbed profile (docs)**: Amarisoft + B2xx wiring, conducted-RF and
      test-SIM discipline, env table. **← the physical bring-up + real-phone attach is the live item.**
- [x] **O-RAN path (A1)**: `A1PolicyClient` (OSC A1-P REST) + **`ran-opt-copilot` v0** — LLM at
      the Non-RT/rApp timescale: explains RAN state from the store, reads policies, and
      *proposes* slice policies **through the intent ledger** (never writes the RIC directly).
      **← raw E2/KPM termination intentionally lives in the RIC; live OSC-RIC validation pending (Tier-2).**
- [x] **vLLM provider**: OpenAI-compatible chat + tool calling, model autodiscovery,
      `ZORTENET_LLM=vllm` (the 4×24 GB / 70B-class path). **← live GPU serving run pending.**

**Exit gate:** an NL intent becomes a validated, *applied* configuration change on Amarisoft
(with approval step), observed in KPIs; a real phone attaches via the B2xx and the agent reports
on it; E2 closed-loop demo runs with LLM supervision. Star deliverable: the real-RF video.
**Status: the full draft→approve→apply lifecycle is demonstrated end-to-end over REST+A2A with
the simulated executor (`tests/test_intent_rest_flow.py`); the Amarisoft/RIC/real-phone versions
remain open pending hardware access.**

## Stage 4 — Multi-agent & ecosystem interop

**Goal:** the NOC-of-agents, full protocol coverage, and the community surface that makes the repo
a foundation others build on. Also builds the eval harness Stage 5 requires.

**Build:** *(status as of the testbed-free build pass — same convention as Stages 1–3)*
- [x] **A2A task lifecycle**: full v1.0-shaped `message/send` / `tasks/get` / `tasks/cancel`
      JSON-RPC at `POST /a2a` (Task/Message/artifacts/history objects), alongside the Agent Card.
      *Streaming + official-SDK conformance: live polish item.*
- [x] **`multi-agent-noc`**: ran/core/security **specialist agents** (focused registries +
      personas, each behind its own A2A task manager); the orchestrator delegates via
      `ask_specialist` using real **A2A message/send envelopes** (in-process dispatch;
      cross-host = same payloads over HTTP — **live multi-instance run pending**).
- [x] **Protocol completion:** **ACP shim** (`/acp/agents`, `/acp/runs` — AAIF-tracked, marked
      shim pending the ACP↔A2A convergence), **AGNTCY/OASF record** at `/.well-known/oasf.json`
      (describes the A2A/MCP/ACP locators + skills; **Agent Directory publish = live item**),
      **ANP** DID document + agent description (**loudly experimental**: unsigned, protocol
      itself unverified by research).
- [x] **TeleAgentBench v0**: 5 public dev scenarios with **programmatic, state-based judges**
      (ledger status, tool traces — not answer vibes), incl. the safety scenario
      (apply-without-approval must stay blocked); aggregate metrics; CLI
      (`make teleagent-bench`). Tests prove the judges discriminate competent vs lazy vs unsafe
      agents. **← live model scores pending Ollama/vLLM.**
- [x] **Cloud-native:** Helm chart (toolkit + optional Ollama, probes, ConfigMap) —
      **`helm lint` + `helm template` pass locally and in CI**; **live in-cluster deploy pending**.
- [x] **Community surface:** pack generator (`make new-pack NAME=… DESC=…`) producing
      contract-honoring packs (generator output is itself contract-tested), CONTRIBUTING.md
      (pack/connector how-to + the honesty rules), `examples/` curl walkthroughs.
      *Docs site: deferred to launch polish.*

**Exit gate:** a fault scenario is solved cooperatively by ≥3 agents over A2A; TeleAgentBench runs
reproducibly against any configured model; an external contributor can scaffold a new pack from
the cookiecutter in <30 min. **Status: all three demonstrated in mock/local form
(`tests/test_a2a_tasks_noc.py`, `tests/test_teleagent_bench.py`, `tests/test_pack_generator.py`);
the live forms (real-LLM bench scores, cross-host A2A, in-cluster Helm) remain open.**

## Stage 5 — Model pipeline (LoRA-SFT — deliberately last)

**Goal:** train *only now*, when the prerequisites exist: trajectories accumulated since Stage 1,
TeleAgentBench from Stage 4 to measure with, and a G0 baseline proving a gap RAG doesn't close.
Full spec: [MODEL_PIPELINE.md](MODEL_PIPELINE.md).

**Build (gated G0→G3):** *(harness code-complete; the GPU runs are the live items)*
- [x] **G0 — baseline matrix harness:** providers × {base, +RAG} × {telco-bench, TeleAgentBench}
      with the gap rule encoded (`decide_gap`): **if best +RAG arm meets target, the pipeline
      says "stop and publish the finding"**. RAG arm = KB-context-wrapped provider.
      TeleAgentBench now **stamps judge outcomes into trajectories** — bench runs double as
      outcome-validated data generation. **← actual baseline *numbers* need a live model server.**
- [x] **G1 — curation pipeline:** trajectory filters (schema / stopped-early / tool-errors /
      judge-outcome policy), dedup, **ContaminationGuard** (TeleQnA + public bench asks can never
      enter training data), seeded split, per-reason drop stats (no silent filtering);
      **machine-validated synthetic generators** (every NL→intent pair passes `validate_intent`
      by construction; every diagnosis pair targets a real playbook); **mixture assembly** with
      loud shortfall + missing-general-data warnings. **← a real dataset needs accumulated live
      trajectories + a general-instruction set.**
- [x] **G2 — configs + enforcement:** hardware presets (1×24 GB → 7-8B LoRA; 4×24 GB → 32B/70B
      QLoRA) emitting TRL-style configs; `config` is **gate-blocked until G0+G1 pass**.
      **← the LoRA-SFT run itself needs the GPU host (`pip install trl peft …`) — live item,
      as is the DPO pass and the beats-base+RAG evaluation.**
- [x] **G3 — publish tooling:** hedged **model-card generator** driven by recorded gate evidence
      (card stays marked DRAFT until all gates pass) with the mandatory licence checklist +
      limitations. `python -m zortenet.train` CLI: status/g0/curate/synth/mixture/config/card.
      **← actual publication (HF dataset + adapters) is the live item.**

**Exit gate:** the headline earned or honestly refuted — *"an 8B tuned on your own testbed,
matching cloud-frontier models on your network's operations."* Either outcome is publishable.
**Status: the entire pipeline scaffolding is built, gate-enforced, and tested
(`tests/test_train_pipeline.py`); G0 numbers → G2 training → G3 publication await GPU/model
access. The pipeline cannot be run out of order even by accident.**

---

## Dependencies & parallelism

```
S0 ✅ ─▶ S1 ─▶ S2 ─▶ S3 ─▶ S4 ─▶ S5
          │         │         ▲
          │         └─ Amarisoft/USRP arrive: S3 hardware tasks can start
          │            alongside late S2 (connector is mock-tested first)
          └─ trajectory capture runs continuously S1→S5 (feeds S5's G1)
```

- S1→S2 are strictly sequential (S2 generalizes what S1 proves end-to-end).
- S3's **Amarisoft connector** can be developed against mocks in parallel with S2.
- S4's TeleAgentBench can start as soon as S2's fault-injection (UERANSIM control) exists.
- S5 is **intentionally last** and intentionally cheap: by then the data exists, the eval harness
  exists, and the decision to train is evidence-based, not speculative.

## Mapping to the blueprint's M0–M4 (for cross-reference)

| This plan | Blueprint §9 |
|---|---|
| Stage 0 | M0 (done) |
| Stage 1 | M1 (agent-native + baselines) |
| Stage 2 | M1/M2 split (breadth pulled forward of standards work) |
| Stage 3 | M2 + the real-RF additions (Amarisoft/USRP, vLLM) |
| Stage 4 | M3 + M4 community items + TeleAgentBench (moved before training) |
| Stage 5 | the model-pipeline slice of M3, **moved last by decision** |

## Stage-level risks (top one each)

- **S1:** first live testbed bring-up surfaces wiring issues (expected; budgeted as the first task).
- **S2:** RAG ingest licence handling (pull-on-demand only; nothing vendored).
- **S3:** hardware integration always slips — mock-first development and the conducted-RF setup
  contain it; srsUE prototype limitations are avoided by keeping UERANSIM the default UE.
- **S4:** A2A task-lifecycle spec depth — implement against v1.0.x and pin the version.
- **S5:** the gap may not exist (base+RAG suffices) — that is a *gate outcome*, not a failure;
  G0 runs before any GPU-week is spent.
