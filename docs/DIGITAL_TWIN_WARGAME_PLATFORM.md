# CORE‑DT — Adversarial Digital‑Twin War‑Game Platform

**A sovereign, modular platform for AI‑enabled decision‑making and training — where a live digital twin of
a contested multi‑domain network is fought over by red and blue agents, scored by a programmatic judge, and
replayed as an operations picture.**

*CORE Lab · NCSR "Demokritos" (NCSRD). `CORE‑DT` is the working platform name for the `corelab` codebase.*

> **How to read this document.** It describes a **core platform** — some of it runs today, some is planned.
> Every capability is tagged **✅ available** (implemented and tested in this repository) or **🔭 roadmap**
> (designed‑for, not yet built). Nothing tagged ✅ is aspirational; nothing tagged 🔭 is claimed as done.
> This separation is deliberate: the platform's central discipline is *measured, not asserted*.

---

## 1 · Vision

Modern operations — military and civil‑critical alike — unfold across **coupled domains**: 5G/6G networks,
massive IoT, ISR sensor feeds, SATCOM/NTN backhaul, UAV swarms, V2X, and the cyber terrain underneath all of
them. Decisions must be made and defenders must be trained **against a thinking adversary**, under doctrine,
with humans in command — and increasingly with AI assistance that has to *earn* trust.

**CORE‑DT is the substrate for that.** It stands up a **digital twin** of the contested environment, runs
**adversarial war‑games** over it, and uses the same substrate to **train and benchmark AI decision agents**
— all locally and sovereignly, with a tamper‑evident audit trail and a human‑approval gate on every
consequential action.

Three products in one platform:

| Pillar | What it delivers |
|---|---|
| **Digital Twin** | a live, event‑sourced replica of the network/battlespace that spans pure simulation → emulation → hardware‑in‑the‑loop |
| **War‑Game** | red/blue adversarial scenarios, a programmatic judge, a doctrine (human‑approval) gate, and a scenario/benchmark database |
| **AI Decision & Training** | sovereign LLM/agent defenders, a gold‑policy teacher, a gated fine‑tuning pipeline, and honest head‑to‑head evaluation |

---

## 2 · Why a digital‑twin war‑game (the problem)

- **Live exercises are expensive and rare.** A digital twin lets you rehearse a theater‑scale engagement in
  ~30 seconds, a thousand times, deterministically.
- **AI for defence must be trustworthy.** Black‑box "it works" is not admissible. CORE‑DT measures every
  agent against a scripted gold line on a fixed benchmark, with a separate judge — improvement is *evidence*.
- **Doctrine and human command are non‑negotiable.** The only consequential action (a countermeasure) is
  gated by human approval and logged — EU‑AI‑Act‑ready evidence of meaningful human control.
- **The threat is multi‑domain and evolving.** The platform is built to *onboard* new domains, protocols,
  sensors, and adversary behaviours as modules — not to be rewritten for each.

---

## 3 · Platform architecture

CORE‑DT is a **layered, plug‑in architecture**. Everything above the substrate is a *module* that couples in
against a stable interface, so partners and follow‑on projects can onboard capabilities without touching the
core.

```
                ┌──────────────────────────────────────────────────────────────┐
   OPERATOR /   │  Mission Control · Live Battlespace Map · Telemetry windows    │  ✅
   TRAINEE /    │  Analysis & After‑Action · Scenario authoring (🔭)             │
   COALITION UX └──────────────────────────────────────────────────────────────┘
                ┌──────────────────────────────────────────────────────────────┐
   DECISION &   │  Red controllers │ Blue controllers │ Multi‑agent teams        │  ✅
   AGENT LAYER  │  Scripted · Reactive(doctrine) · LLM agent · Adaptive(CAM)     │
                │  Sovereign models (QLoRA) · Gate‑disciplined training (G0→G3)  │
                └──────────────────────────────────────────────────────────────┘
                ┌──────────────────────────────────────────────────────────────┐
   INTEROP      │  A2A · MCP · ACP · AG‑UI · ANP · AGNTCY/OASF descriptors        │  ✅
   FABRIC       │  (agent‑to‑agent, tool, and UI protocols — how modules talk)   │
                └──────────────────────────────────────────────────────────────┘
                ┌──────────────────────────────────────────────────────────────┐
   CAPABILITY   │  Packs: security‑sentinel · self‑heal · bpf‑hunt · ran‑opt ·   │  ✅
   MODULES      │  intent‑to‑network · v2x‑ops · ntn‑ops · uav‑ops · massive‑iot │
                │  · xr‑qoe · sensing‑ops · energy‑agent · ai‑native · …         │
                └──────────────────────────────────────────────────────────────┘
                ┌──────────────────────────────────────────────────────────────┐
   JUDGE &      │  Programmatic judge · Doctrine (human‑approval) gate ·          │  ✅
   GOVERNANCE   │  Hash‑chain audit · PQC‑secured transport (🔭) · DLT anchor(🔭) │
                └──────────────────────────────────────────────────────────────┘
                ┌──────────────────────────────────────────────────────────────┐
   DIGITAL‑TWIN │  Event‑sourced WorldState (single source of truth)             │  ✅
   SUBSTRATE    │  ── Fidelity ladder ──▶  Simulation · Emulation · Hardware‑ITL │
                └──────────────────────────────────────────────────────────────┘
                ┌──────────────────────────────────────────────────────────────┐
   CONNECTORS   │  Amarisoft(5G) · Open5GS · UERANSIM · NWDAF · A1/RIC ·          │  ✅
   (DATA PLANE) │  Prometheus · HostSensor(eBPF) · … SDR/EW · C2/FMN (🔭)         │
                └──────────────────────────────────────────────────────────────┘
```

**The coupling contract.** A module is onboarded by implementing one of five small interfaces (§7). Because
the world is a single **event log**, every module — a simulated adversary or a real 5G core — speaks the same
substrate, and the judge and agents reason over identical, auditable state.

---

## 4 · The digital‑twin substrate (✅ available)

The "world" is an **append‑only event store**. Red modules inject hostile events (threats); blue modules
resolve them (mitigations); `WorldState` **derives** active threats, node health, and mission availability
from the log. Consequences of this design:

- **One source of truth.** Controllers, the judge, and the operator picture never disagree — they all read
  the same log.
- **Reproducible.** Seeded runs are byte‑for‑byte repeatable; an entire engagement is a replayable stream.
- **Auditable by construction.** The log *is* the evidence. Approvals are hash‑chained (`integrations.py`)
  so the decision record is tamper‑evident.

---

## 5 · The fidelity ladder — sim → emulation → hardware‑in‑the‑loop

A digital twin is only as useful as its coupling to reality. CORE‑DT deliberately spans a **fidelity ladder**,
and the *same* wargame/agents run at every rung:

| Rung | What it is | Status |
|---|---|---|
| **L0 · Pure simulation** | seeded event‑driven theater (28‑node campaign, 4 attack waves, ~216 threats) | ✅ |
| **L1 · Emulation** | UERANSIM RAN + Open5GS core + NWDAF analytics feeding the twin | ✅ connectors |
| **L2 · Hardware‑in‑the‑loop** | live **Amarisoft 5G** (real cell power / CQI faults, gentle & auto‑restored); live **host eBPF** red/blue on isolated VMs (contained backdoor signatures detected over SSH) | ✅ proven live |
| **L3 · Multi‑site / coalition twin** | partner sites federate their sub‑twins into a coalition picture | 🔭 |
| **L4 · Full multi‑domain twin** | cyber + RF/EW + space/NTN + logistics co‑simulated with real feeds | 🔭 |

> **Proven today (L2):** a reversible RF fault on a real Amarisoft cell drives real UE CQI degradation that
> the blue RAN‑ops agent reads and the cell auto‑restores; and a benign eBPF `getdents64`/`tcp_sendmsg`
> rootkit signature planted on an isolated VM is detected by the `bpf‑hunt` blue agent against a trusted
> baseline, then cleanly removed. These are the twin syncing to physical assets — not mock‑ups.

---

## 6 · Module & protocol onboarding (✅ available today)

The extensibility story is the platform story. What is **already onboarded**:

**Connectors (data‑plane in).** `amarisoft` (+ live event bridge), `open5gs`, `ueransim`, `nwdaf`, `a1_ric`
(O‑RAN A1/RIC), `prometheus`, `hostsensor` (read‑only Linux/eBPF forensics).

**Capability packs (mission modules).** 17 onboarded, each a registry of tools an agent can wield — including
**security‑sentinel**, **self‑heal**, **bpf‑hunt**, **ran‑opt‑copilot**, **netops‑copilot**,
**intent‑to‑network**, **spec‑kb**, and a full **multi‑domain set** that maps directly onto war‑game domains:
**v2x‑ops**, **ntn‑ops** (SATCOM/non‑terrestrial), **uav‑ops** (ISR/drones), **massive‑iot**, **xr‑qoe**,
**sensing‑ops** (spectrum/ISAC), **energy‑agent**, **ai‑native**, **location‑monitor**.

**Agent‑interop protocols (the fabric).** `A2A` (agent‑to‑agent + task lifecycle), `MCP` (tool servers),
`ACP`, `AG‑UI` (streaming UI), `ANP` (experimental), and `AGNTCY/OASF` capability descriptors — so external
red teams, blue benches, and C2 tools can plug in as first‑class controllers.

**Adversary/defender controllers.** Scripted (reproducible baselines), Reactive (doctrine gold), single‑step
LLM Agent, Adaptive‑Red (CAM sense→compare→adapt escalation), and External‑Bench (drop‑in third‑party
red/blue). **LLM back‑ends:** Ollama, vLLM, HuggingFace Transformers (+LoRA), OpenAI‑ and Anthropic‑compatible.

**Scenario / benchmark database.** Reproducible scenarios (contested tactical network, ISR‑sensor‑contested,
logistics‑under‑disruption) × adversary profiles (single‑jam, multi‑vector, persistent), scored on one axis
(mission success, availability, time‑to‑detect, threats‑neutralised, human‑control‑held) and ranked on a
leaderboard (`TeleAgentBench`).

---

## 7 · The onboarding contract (for partners & follow‑on work)

Coupling a new module means implementing exactly one small interface — this is what makes CORE‑DT a *platform*
rather than an application:

| To onboard a… | Implement | Gets you |
|---|---|---|
| **Data source / live asset** | a `Connector` (`connectors/base.py`) | telemetry flows into the twin |
| **Capability / effect** | `build_registry()` returning tools | an agent can sense/act with it |
| **Adversary or defender** | `decide(role, obs, registry, turn) → Action` | plays in any scenario, ranked on the board |
| **Scenario / doctrine** | a `WarGameScenario` (init state + arsenals + objectives) | reproducible, judged, replayable |
| **External system / team** | an interop endpoint (A2A/MCP/ACP) | first‑class participant over the wire |
| **Model back‑end** | the `LLMProvider` interface | any sovereign or hosted model as an agent |

Because all six speak the same event‑sourced substrate and the same tool abstraction, a scripted heuristic, a
human, a sovereign fine‑tuned model, and a partner's proprietary bench are **measured on the identical axis**.

---

## 8 · AI‑enabled decision‑making & training (✅ available)

CORE‑DT is a **training and evaluation ground for defence AI**, with anti‑hype discipline built in:

- **Gold‑policy teacher.** A deterministic doctrine defender (sense → prioritise worst‑first by node
  criticality → apply approved countermeasure, surging reserves under load) provides a 100%‑winning reference
  and generates gold trajectories.
- **Sovereign fine‑tuning.** `Qwen3‑8B` runs locally in 4‑bit; QLoRA adapters (r=32) are trained on gold
  trajectories under **G0→G3 gate discipline** (G0 base baseline, G1 curated data, G2 train+eval, G3 ship
  only if it beats base).
- **Honest, head‑to‑head evaluation.** On the fixed 9‑game benchmark: **base agent 0% → fine‑tuned 22% →
  doctrine gold 100%**. We report the 22% plainly — fine‑tuning taught the detect→apply loop (single‑threat
  solved) but sustained multi‑vector pressure is still hard for a single‑step LLM. *The measured gap is the
  product* — it tells an evaluator exactly where the capability is.

**On the roadmap (🔭):** multi‑agent blue *teams* cooperating over A2A inside the war‑game; **reinforcement
self‑play** (red and blue co‑evolving tactics); model cards + "training‑gate‑as‑a‑service"; automated
curriculum from after‑action gaps.

---

## 9 · War‑game engine, judge & doctrine gate (✅ available)

- **Turn engine** with code‑enforced guardrails: per‑side action budgets, only registered tools execute
  (hallucinated actions are dropped, not run), opaque threat handles, and a judge that sees only the world log.
- **Programmatic judge** (no LLM in the loop): mission‑available, threat‑detected‑in‑time, all‑threats‑
  neutralised, human‑control‑held → a run succeeds only if all pass.
- **Doctrine gate:** the sole consequential action requires human approval; approve restores the mission, deny
  holds the gate with **zero unauthorised actions** — the platform's meaningful‑human‑control evidence.

---

## 10 · The live operations picture (✅ available)

The **Live Battlespace Map** streams a full theater engagement (~30 s) — a 28‑node **5G / IoT / tactical**
network with a comms mesh, labelled by domain, under sustained multi‑wave assault. Availability dips under
the surge and recovers as the defender clears the theater. Alongside it, three correlated **live telemetry
windows** replay the engagement at packet and NF level:

- **PCAP · attack traffic** — N1/N2/N3/N4/SBI packets (NGAP, NAS‑5GS, PFCP, GTP‑U, PRACH, HTTP2/SBI).
- **5G Core** — AMF / SMF / UPF / NRF operations and countermeasures.
- **gNB / eNB** — RAN operations (CQI/MCS/RACH collapse, RRC, handover, beam reconfigure).

A **Mission Control** panel runs every scenario, benchmark, and live testbed action from one place; an
**Analysis** page documents the model and algorithms honestly. *(Today the correlated telemetry is
synthetic‑but‑consistent, generated from real simulation events; §11 roadmap promotes it to real capture.)*

---

## 11 · Roadmap — future implementation that serves the purpose

Grouped by horizon; all 🔭. These are chosen to deepen the twin, harden trust, and widen the AI training loop
— the things an EDF‑grade decision‑and‑training platform needs next.

### Horizon 1 — deepen fidelity & the training loop
- **Real PCAP ingestion & replay** — feed the PCAP window from live `tshark`/captured `.pcap` via a connector,
  so attack traffic is genuine capture, not illustration.
- **Emulation‑to‑live promotion pipeline** — one scenario, run at L0/L1/L2 with a single flag; auto‑diff twin
  vs. reality to quantify fidelity.
- **Scenario/doctrine authoring GUI** — compose laydowns, waves, and rules of engagement without code;
  map threats to **MITRE ATT&CK** and doctrinal task lists.
- **Multi‑agent blue team in the war‑game** + **RL self‑play** red/blue co‑evolution.
- **After‑Action Review (AAR)** analytics — automatic engagement reports, replay scrubbing, gap → curriculum.

### Horizon 2 — trust, coalition & hardware
- **PQC‑secured transport + DLT‑anchored audit** — post‑quantum‑protected A2A/MCP and a Besu quantum‑resistant
  ledger anchoring the approval hash‑chain, for cross‑coalition non‑repudiation (NCSRD assets).
- **Federated coalition wargaming** — partner sites federate sub‑twins into one coalition operating picture,
  with data‑sovereignty boundaries.
- **Hardware‑in‑the‑loop expansion** — SDR/EW spectrum twin, real gNB fleets, UAV/ISR telemetry, sensor rigs.
- **C2 integration** — NATO **FMN**/MIP and civil SIEM/SOAR as onboarded interop endpoints.
- **Human‑machine teaming UX** — 3D/AR battlespace, explainable course‑of‑action overlays.

### Horizon 3 — full multi‑domain, certifiable autonomy
- **Full multi‑domain twin** — cyber + RF/EW + space/NTN + logistics co‑simulated with live feeds.
- **Autonomous course‑of‑action generation** with mandatory human veto and full provenance.
- **Cross‑coalition scenario/benchmark exchange** — a shared, versioned library in an interoperable format.
- **Continuous doctrine co‑evolution** and an **EU‑AI‑Act high‑risk certification pack** produced from the
  platform's own audit trail.

---

## 12 · Trust, sovereignty & governance (✅ today / 🔭 roadmap)

- **Sovereign** ✅ — models run locally in 4‑bit; no data leaves the box.
- **Human‑in‑the‑loop** ✅ — doctrine gate on every consequential action, fully logged.
- **Auditable** ✅ — append‑only event log + tamper‑evident hash‑chain over approvals.
- **Honest by construction** ✅ — programmatic judge + scripted gold line; improvement is measured.
- **Post‑quantum & DLT‑anchored** 🔭 — PQC transport + Besu ledger for coalition‑grade non‑repudiation.
- **Regulatory** 🔭 — EU AI Act high‑risk documentation generated from the audit trail.

---

## 13 · Standards & framework alignment

3GPP 5G (NGAP/NAS/PFCP/GTP‑U, NWDAF) · O‑RAN (A1/RIC) · TM Forum **TMF921** intent & 3GPP **TS 28.312** ·
agent interop **A2A / MCP / ACP / AG‑UI / AGNTCY‑OASF** · threat modelling **MITRE ATT&CK** (🔭 mapping) ·
coalition **NATO FMN/MIP** (🔭) · **EU AI Act** meaningful‑human‑control evidence.

---

## 14 · Maturity & evidence

- **Codebase:** `corelab` — 8 connectors, 17 capability packs, 5 interop protocols, 5 model back‑ends, the
  full war‑game engine + campaign twin + control UI. **288 automated tests green.**
- **Proven live:** real Amarisoft RF red/blue; real host eBPF‑backdoor red/blue across two machines.
- **Indicative TRL 5–6** for the simulation/emulation core and the live‑testbed bridges; roadmap items are
  TRL 2–4 by design.
- **See it:** `python training/wargame_control.py` → Mission Control, the Live Battlespace Map (`/map`), and
  the Analysis page (`/analysis`). Tutorial: [`docs/WARGAME_TUTORIAL.md`](WARGAME_TUTORIAL.md);
  design detail: [`docs/WARGAME_POC.md`](WARGAME_POC.md).

---

*CORE‑DT positions NCSRD's simulation, sovereign‑AI, PQC/crypto‑agility, and agentic red/blue assets as one
coherent, extensible platform for AI‑enabled decision‑making and training in contested multi‑domain
environments — built to be **coupled, onboarded, and measured**.*
