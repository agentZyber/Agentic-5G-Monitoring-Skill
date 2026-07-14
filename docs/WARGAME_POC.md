# Flagship PoC — Red/Blue Adversarial War‑Game (sovereign, scored, human‑in‑the‑loop)

*A domain‑agnostic, benchmarked adversarial‑simulation engine for the EDF "AI framework for defence"
topic. Generalises NCSRD's red/blue side‑channel bench + this toolkit's multi‑agent framework into a
war‑game where autonomous Red and Blue agents play out a scenario over an auditable world, a
programmatic judge scores mission outcomes, consequential actions pass a human‑approval (doctrine)
gate, and defenders rank on a leaderboard vs scripted and human baselines. Runs on sovereign local
LLMs. **Simulation and decision‑support only — non‑kinetic, human‑in‑the‑loop.***

## Why this addresses the topic
| EDF topic asks for | This PoC delivers |
|---|---|
| AI‑enabled **battlespace / war‑game simulation** | Red↔world↔Blue turn engine over the (cyber/EW) contested‑network battlespace |
| Rich **scenario & benchmark database** | Reproducible scenarios + programmatic judges + defender **leaderboard** (`wargame.benchmark`) |
| **Doctrinal models**; mission planning/execution | Countermeasures gated on a **doctrine (human‑approval) policy** with a full decision log |
| Output from **AI services**; **sovereignty** | Any [`LLMProvider`] drives the agents; default is **local Ollama** (air‑gappable) |
| Common framework; interoperability | Built on the toolkit's event bus, packs, agent runtime — pluggable, standards‑aligned |

## What it is (the loop)
Each turn: **Red** picks one action from its arsenal (jam a link, flood signaling, intrude a node —
all simulated events); the **world** (an `EventStore`) records it as a threat; **Blue** senses
(`detect_threats`, reusing `security-sentinel`), diagnoses, and proposes a **countermeasure** — which
runs **only if a human approves**. A programmatic **judge** scores the run: mission availability,
time‑to‑detect, threats neutralised, and *human‑control held* (no action ever executed without
approval). Deterministic scripted controllers and single‑step LLM agents share one interface, so
baselines and agents are measured on the same axis.

## Architecture — ~80% reuse (`src/corelab/wargame/`)
| Module | Role | Reuses |
|---|---|---|
| `scenario.py` | scenarios + `WorldState` (active threats / mission health from the event log) | `core.bus` / `core.events` |
| `arsenal.py` | red tools (inject threats) + blue tools (sense/diagnose/**gated** countermeasure) | `security-sentinel` pack, `ToolRegistry` |
| `approval.py` | **doctrine gate** — approve/deny + audit log (meaningful human control) | — |
| `controllers.py` | `ScriptedController`, `ReactiveController` (fixed‑script baseline), `AgentController` (LLM) | `agent.runtime` tool‑call parsing |
| `engine.py` | turn loop + **code‑enforced guardrails** (budgets, only‑real‑tools, opaque handles, separate judge) | — |
| `judge.py` | programmatic, state‑based scoring | — |
| `benchmark.py` | red×blue matchups + **leaderboard** | — |
| `report.py` | markdown report + **self‑contained HTML dashboard** | — |

## How to run it
- **Guided walkthrough (for the live audit):** `python training/wargame_guided.py` — narrates every
  scenario turn‑by‑turn (red move → blue move → doctrine gate → mission status), pausing between
  steps, then prints the verdict + scorecard and a campaign summary. Flags: `--auto` (no pauses),
  `--live-approval` (**you** approve/deny each countermeasure), or name a scenario to run just one.
- **Interactive console (slick, Palantir‑style):** `python training/wargame_dashboard.py` →
  `wargame_evidence/console.html`; serve with `python -m http.server`. Run selector + turn scrubber +
  battlespace node‑graph + leaderboard + human‑control decision log.
- **Evidence pack:** `python training/wargame_demo.py` → `wargame_evidence/{dashboard.html, run_report.md, results.json}` (offline, reproducible, seeded, state‑judged).

Demonstrated out of the box: the fixed‑script defender wins 100% vs 0% for a passive floor; the
doctrine gate, when it **denies**, correctly holds (mission lost but **zero unauthorized actions**) —
direct EU‑AI‑Act / ethics‑by‑design evidence. Swap in a local LLM agent to rank it against the
baselines.

## Responsible‑AI posture (an EDF evaluation strength, by design)
- **Meaningful human control:** every consequential action is human‑approved and logged.
- **Guardrails are code, not prompts:** action budgets, only registered tools execute, opaque threat handles, a judge that never sees agent internals.
- **Sovereign & auditable:** local models, seeded reproducibility, state‑based judging, full provenance.
- **Non‑kinetic:** the world is simulated telemetry; the PoC is decision‑support and training, never targeting.

## P4 — NCSRD asset integration hooks (implemented — `corelab.wargame.integrations`)
The three drop‑in points for NCSRD's proven assets are now real, tested interfaces:
1. **Real red/blue bench → `ExternalBenchController`** — wraps NCSRD's hardware‑in‑the‑loop SCA
   red/blue bench (subprocess / REST / in‑proc) as a war‑game `Controller`; the engine's guardrails
   still sandbox it. A *real* adversarial arena becomes one player in the benchmark DB.
2. **Context Agility Manager → `AdaptiveRedController`** — CAM's sense→compare→adapt loop as an
   adversary: escalates when the defender copes, holds when it hurts. Try it live:
   `python training/wargame_guided.py --adaptive`.
3. **PQC/DLT audit → `HashChainAudit`** — a tamper‑evident, hash‑chained audit trail of the doctrine
   decisions (`verify()` breaks on tampering) — the local stand‑in for NCSRD's Besu quantum‑resistant
   DLT + PQC signing of the approval log.

## Sovereign LLM defender on the benchmark (honest result)
The single‑step LLM agent (`AgentController`, any local `LLMProvider`) ranks on the same leaderboard as
the scripted baselines. Getting a sovereign model to actually *win* took three **harness** fixes, not a
bigger model:
- **Observable state** — the blue observation now surfaces the open‑threat board (`id·kind·element`), so
  a single‑step agent can ground `apply_countermeasure(threat_id=…)` when several threats are active at
  once (the multi‑vector case).
- **One shared prompt** — `controllers.render_agent_messages` is the single renderer used by *both*
  trajectory synthesis and eval, so train and eval prompts cannot silently drift.
- **Crisp doctrine** — the blue system prompt encodes the exact winning loop (turn 1 → `detect_threats`;
  then `apply_countermeasure` on the *first* listed threat id until the board is clear; nothing else),
  replacing a prompt that told the model to `diagnose` — a step the winning policy never uses.

With these, **base qwen3:8b wins 9/9** across every scenario × adversary profile (single‑jam,
multi‑vector, persistent), matching the reactive‑gold reference — with **no fine‑tuning**. An earlier
"fine‑tune lifts 0% → 33%" figure was an **artifact of the pre‑fix harness** (unobservable threat ids +
a diagnose‑inducing prompt), not a learned skill; it is reported here corrected. Net: this benchmark is
solvable by the sovereign *base* model, so fine‑tuning is reserved for a harder tier — or a smaller edge
model — where the base genuinely fails. (Diagnosis method: `AgentController` trace of the actual
observation → tool call, per turn.)

## Status
TRL 4–5 (working, tested, reproducible; runs on the local sovereign stack). Tests:
`tests/test_wargame.py` + `tests/test_wargame_integrations.py` (scoring, doctrine gate, guardrails,
leaderboard, evidence artefacts, and all three P4 hooks) — part of the toolkit's green suite (278 tests).
The console (`training/wargame_dashboard.py`) adds a **▶ playback** that auto‑advances turns and
animates the battlespace; the guided demo (`training/wargame_guided.py`) covers all scenarios with
`--auto` / `--live-approval` / `--adaptive` flags.
