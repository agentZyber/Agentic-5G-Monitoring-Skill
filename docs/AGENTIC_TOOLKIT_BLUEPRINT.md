# ZorteNet → The Agentic 5G/6G Toolkit — Design Blueprint

> **Status:** v1.1 (2026-06-06). Grounded in two adversarially-verified deep-research passes,
> **both complete and cited below** (pass #1: use cases / frameworks / datasets / testbeds —
> 21 verified claims; pass #2: agent-interop protocols + telecom standards — 23 verified claims).
> The interop matrix (§5) now carries verified, recency-flagged facts.
>
> **Working thesis (hedged inference):** EU 5G/6G projects are saturated in a narrow set of
> *vertical* use cases (verified, §1.1), and **in the projects examined**, where AI appears it is
> typically **non-agentic** (narrow ML or classical RL — a medium-confidence inference, §1.2).
> Making *the network itself* agentic — observe → reason → act, exposed over standard agent
> protocols, runnable locally — is an underexplored, high-leverage, star-worthy gap.

---

## 0. How to read this document

This blueprint evolves the existing **ZorteNet** NetApp (a single-purpose 5G *location/mobility*
monitor) into a **general, multi-domain agentic 5G/6G framework** — the "go-to foundation" an SNS
JU / 5G-PPP project can `git clone` and build on. It is the design that the runnable scaffold
(next milestone) implements. Decisions already locked with the maintainer:

- **Evolve in place** (this repo), not greenfield — ZorteNet's monitoring becomes *one capability pack among many*.
- Deliver a **blueprint + runnable scaffold**: MCP/A2A/ACP servers, an Ollama LLM layer, an Open5GS+UERANSIM+Ollama local testbed, use-case capability packs, and a dataset registry.

---

## 1. The opportunity (research-grounded)

### 1.1 What current EU 5G/6G projects actually do (the saturation map)

Across the SNS JU portfolio (Calls 1–3, 2022–2024 — all named projects confirmed members of the
official portfolio [SNS map]), the *vertical* use cases repeat:

| Project | Use cases (verified from primary sources) | AI character |
|---|---|---|
| **DESIRE6G** (GA 101096466) | (1) VR/AR with perceived-zero-latency; (2) E2E **industrial-robot digital twin**, Device-Edge-Cloud, ms control loop, remote/autonomous robot control [desire6g.eu, CORDIS] | No agentic/LLM use case |
| **FIDAL** (GA 101096146, €14.97M) | 7 UCs: Internet-of-Senses/haptics, Digital Twin for First Responders, City Security, Sports Media, **VR** Networked Music, **XR**-Assisted Public Safety, Smart Village [fidal-he.eu, CORDIS] | DRL + edge video-analysis only |
| **IMAGINE-B5G** (GA 101096452) | XR/holographic media, **UAV** port surveillance, V2X localization, PPDR, eHealth, Industry 4.0, education, agriculture [imagineb5g.eu, CORDIS] | "advanced AI/ML" for energy migration & personalization — non-agentic |
| **6G-SANDBOX** (GA 101096328) | 6G *experimentation facility* (Athens/Berlin/Malaga/Oulu); 10 ambitions incl. generic "AI/ML network evolution", digital twins, XR-haptics; focus is **physical-layer** (RIS, NTN, FR3, deterministic networking) [6g-sandbox.eu, CORDIS] | Generic AI/ML; no LLM agents |

**Saturated verticals:** XR/VR/holographic, drone/UAV, V2X/automotive, public-safety/PPDR,
eHealth, Industry-4.0/robotics digital twins, media/entertainment. This matches exactly the
"limited scope" the maintainer described (video, robot-dog, drones, XR/VR).

### 1.2 The gap (medium-confidence inference, explicitly hedged)

Where AI appears in these projects it is **narrow ML or classical RL, not agentic**. The leading
*open-source* O-RAN closed-loop control work — **REAL** (arXiv:2502.00715, Clemson) — uses **PPO
(actor-critic RL)** to allocate PRBs over the O-RAN E2 interface, and contains **no LLM agent** at
all. Convergent negative evidence across DESIRE6G / FIDAL / IMAGINE-B5G / 6G-SANDBOX / REAL
supports a genuine gap.

> **Honesty guardrail (from the verifier):** the *strong* portfolio-wide claim — "the entire SNS
> catalogue mentions no agentic AI / MCP / A2A / LLMs" — was **refuted** (absence on a page ≠
> absence in the project). Treat "agentic AI is the gap" as a **well-motivated hypothesis built
> from a sample**, not a proven portfolio-wide fact. It is still a strong basis to build on, and
> the framework's value does not depend on the gap being total — only on it being *underserved*,
> which the evidence supports.

### 1.3 Strategic consequence

Don't ship "yet another video-analytics / drone demo." Ship the thing nobody is shipping
turnkey: **the self-driving network** — autonomous LLM agents that *observe, reason about, and act
on the 5G core & RAN*, exposed over **every major agent-interop protocol**, running **fully local**
(Ollama + Open5GS + UERANSIM), with **datasets and a benchmark** baked in. That is both the
catchy GitHub story and the honest "look how narrow the realm is" statement.

---

## 2. Product vision & positioning

**One-liner:** *An open-source, batteries-included toolkit that turns any 5G/6G core+RAN into an
agent-native, multi-protocol, locally-runnable autonomous network — clone, `make up`, talk to your
network.*

**Naming (maintainer's call):** keep **ZorteNet** as the umbrella brand (existing history, license,
recognition) and position the framework layer. Candidate framework names: **ZorteNet Agentic
Toolkit**, **Z5G**, **AgentRAN**, **NetAgent**, **5GENT**. Recommendation: keep `ZorteNet` brand +
tagline *"The Agentic 5G/6G Toolkit."*

**Differentiators (the star magnets):**
1. **Agent-native by default** — first-class **MCP / A2A / ACP / AG-UI** servers, not bolt-on REST.
2. **100% local, zero-cloud** — Ollama + Open5GS + UERANSIM in one `docker compose`. No API keys to try it.
3. **Multi-domain** — location *and* QoS, traffic, slicing, energy, security, RAN-KPI — pluggable.
4. **Turnkey capability packs** — `enable: netops-copilot` and you have a working agent + tools + prompts + dataset.
5. **Datasets + benchmark included** — TeleQnA/Tele-Data/5G3E wired in; "score your local model on telecom" out of the box.
6. **Standards-bridged** — speaks O-RAN A1/E2, 3GPP intent (TS 28.312), TM Forum TMF921 — credible to telco engineers, not just AI hobbyists.

---

## 3. Architecture — evolving ZorteNet

Today ZorteNet is a single vertical slice (location → context → React-agent). The evolution keeps
its proven loop (subscribe → callback → normalize → context/RAG → stream → agent) but
**generalizes every axis** it currently hard-codes (see the 6 narrowness axes recorded in memory).

```
                          ┌──────────────────────────────────────────────────────────────┐
   AGENT CLIENTS          │  Claude / IDEs / other agents / dashboards / ChatOps / rApps   │
   (north-bound)          └──────────────────────────────────────────────────────────────┘
                                 │ MCP  │ A2A  │ ACP  │ AG-UI │ REST/OpenAPI │ gRPC │ A1
   ┌───────────────────────────────────────────────────────────────────────────────────────┐
   │  INTEROP LAYER (zortenet.interop)   — pluggable protocol servers, one core, many faces   │
   ├───────────────────────────────────────────────────────────────────────────────────────┤
   │  CAPABILITY PACKS (zortenet.packs)  — turnkey {tools + prompts + datasets + eval} bundles │
   │   netops-copilot · intent-to-network · self-heal · energy · security-sentinel · ran-opt  │
   │   location-monitor (the legacy ZorteNet pack) · multi-agent-noc                          │
   ├───────────────────────────────────────────────────────────────────────────────────────┤
   │  AGENT RUNTIME (zortenet.agent)     — LangGraph today; runtime-agnostic tool registry     │
   │  LLM PROVIDERS (zortenet.llm)       — Ollama (local) ▸ OpenAI ▸ Anthropic ▸ vLLM          │
   │  MEMORY / RAG (zortenet.memory)     — Chroma over events + knowledge base (specs/datasets) │
   ├───────────────────────────────────────────────────────────────────────────────────────┤
   │  EVENT MODEL + BUS (zortenet.core)  — NetworkEvent (typed) · normalization · pub/sub       │
   ├───────────────────────────────────────────────────────────────────────────────────────┤
   │  CONNECTORS (zortenet.connectors)   — south-bound adapters (generalize FiveGCoreAdapter)   │
   │   5GC: NEF/CAPIF · Open5GS · free5GC · OAI   |  RAN/O-RAN: E2/KPM via OSC RIC, xApp/rApp    │
   │   Telemetry: Prometheus · NWDAF analytics · PCF policy   |  Sim: UERANSIM control           │
   └───────────────────────────────────────────────────────────────────────────────────────┘
                                 │
   ┌───────────────────────────────────────────────────────────────────────────────────────┐
   │  LOCAL TESTBED (testbed/)  Open5GS (+Mongo) · UERANSIM gNB/UE · Ollama · Prometheus/Grafana│
   │  optional: srsRAN/OAI + OSC RIC for real-RF / O-RAN closed loop                            │
   └───────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.1 The four generalizations (what actually changes in code)

1. **`LocationEvent` → `NetworkEvent`** (`zortenet.core.events`): a typed event with a
   `domain` discriminator (`location | qos | throughput | slice | energy | security | ran_kpi |
   signaling | app`) and a `payload`. `LocationEvent` becomes one subtype. The RAG textualizer
   (`vector_store._event_to_text`) becomes per-domain pluggable so semantic search works for *any*
   event, not just cells.
2. **Single `monitoringType:"LOCATION"` → a subscription/telemetry registry.** Connectors declare
   which event domains they can source (3GPP monitoring events: `LOSS_OF_CONNECTIVITY`,
   `UE_REACHABILITY`, `LOCATION_REPORTING`, `COMMUNICATION_FAILURE`, `QOS_MONITORING`, …; plus
   non-3GPP telemetry: Prometheus scrape, E2/KPM, NWDAF analytics).
3. **`FiveGCoreAdapter` → `Connector` registry.** Keep the elegant `FiveGCoreFactory` pattern;
   broaden it: a `Connector` may be read-only (telemetry), or read-write (control: A1 policy,
   xApp action, slice config). This is what turns monitoring into *agentic action*.
4. **Cloud-only LLM → provider abstraction with Ollama default.** A `zortenet.llm` package wraps
   Ollama / OpenAI / Anthropic / vLLM behind one interface; the agent runtime is told which
   provider to use. Default = Ollama (no keys → it just runs).

### 3.2 What we deliberately keep

The FastAPI app, WebSocket/SSE streaming + event bus, Chroma RAG, the multi-core failover manager,
CAPIF/NEF registration, and the LangGraph ReAct loop are all good. We **wrap, not rewrite.**

---

## 4. Capability packs — the turnkey, "catchy" use cases

A **capability pack** is a declarative bundle: `{ connectors, tools, system-prompt, datasets, eval,
demo }`. Enabling one gives a working agent. Packs are chosen to **hit the gaps**, not the
saturated verticals.

| Pack | What the agent does | Why it's a gap / catchy | Connectors used |
|---|---|---|---|
| **`netops-copilot`** ⭐ | NL Q&A + diagnosis over the live network ("why is UE-3 dropping?", "show slice B load") with RAG over telemetry + 3GPP specs | "Talk to your 5G network." The flagship demo. Agentic O&M is the underserved gap (medium-confidence inference; see §1.2) | Open5GS, Prometheus, NWDAF |
| **`intent-to-network`** ⭐ | NL intent → validated config/slice change (TMF921 / 3GPP TS 28.312 / O-RAN A1 policy), with dry-run + human approval | LLM-driven intent-based networking, standards-bridged | PCF, O-RAN A1, UERANSIM |
| **`self-heal`** | Observe anomaly → diagnose (LLM+RAG) → propose/apply remediation, human-in-the-loop | Agentic self-healing vs. classical RL (contrast REAL/PPO) | all telemetry + control |
| **`security-sentinel`** | Signaling/behavioral anomaly + agentic triage; **evolves ZorteNet's geofence/policy** | Natural home for the legacy code; security agents are under-served | Open5GS, location, signaling |
| **`ran-opt-copilot`** | LLM *supervises* a near-RT xApp closed loop over E2/KPM (orchestrates RL rather than replacing it) | Bridges the REAL-style RL world and LLM agents | OSC RIC + srsRAN E2 |
| **`energy-agent`** | Closes the loop on energy KPIs agentically | Energy is a *saturated topic done non-agentically* — we make it agentic | Prometheus, PCF |
| **`location-monitor`** | The current ZorteNet capability, repackaged | Backward-compat; one pack among many | NEF/Open5GS/free5GC |
| **`multi-agent-noc`** | RAN-agent + core-agent + security-agent coordinating via **A2A** | Showcases agent interop; "a NOC of agents" | all |
| **`telco-bench`** | Run TeleQnA against your local Ollama model; report score | "Benchmark your local model on telecom," instant shareable artifact | none (offline) |

Packs ship with a **one-command demo** each (`make demo PACK=netops-copilot`) that drives UERANSIM
to generate events and shows the agent reacting — the "wow in 60 seconds" for the README GIF.

---

## 5. Agentic interop interfaces (ask #7: "MCP, ACP, etc. — propose more")

The design principle: **one capability core, many protocol faces.** Each protocol is a thin server
in `zortenet.interop` that exposes the *same* registered tools/resources. This is the headline
feature and the strongest differentiator vs. ZorteNet's current REST-only function schemas.

### 5.1 General agent protocols (verified, research pass #2 — recency-flagged to mid-2026)

> The landscape has **consolidated into a complementary stack**, not competing protocols:
> **MCP = agent↔tool**, **A2A = agent↔agent**, **AGNTCY = discovery/identity**, **AG-UI =
> agent↔frontend**. MCP, A2A and ACP now sit under the **Linux Foundation Agentic AI Foundation
> (AAIF)** (formed Dec 2025); AG-UI deliberately stayed independent.

| Protocol | Role in the toolkit | Backer / status (verified mid-2026) | Priority |
|---|---|---|---|
| **MCP** (Model Context Protocol) | Expose network **tools + resources + prompts** to any MCP client. The default agent interface. Target **Streamable HTTP** (remote) + **stdio** (local). | Anthropic → **LF AAIF**. Current spec **2025-11-25** (2025-06-18 superseded); a later RC is *expected* to add a stateless core with **no new transports** (forward-looking, unattributed). Avoid the deprecated HTTP+SSE transport. | **P0** |
| **A2A** (Agent2Agent) | Publish an **Agent Card** (`/.well-known/agent-card.json`); let other agents discover & delegate network tasks. Powers `multi-agent-noc`. | Google → **LF** (Jun 2025) → AAIF. **Stable v1.0.0 (Mar 2026)**, v1.0.1 (May 2026); 150+ orgs. | **P0** |
| **ACP** (Agent Communication Protocol) | REST-native agent messaging; **also an AAIF foundational project** alongside MCP/A2A → support via a thin shim and track convergence. | IBM/BeeAI → **LF AAIF**. | **P1** |
| **AG-UI** (Agent-User Interaction) | Standard **agent↔frontend** event stream (~17 event types over a single HTTP POST + SSE) — drives the NOC dashboard / operator chat. | **CopilotKit**-led; *not* a formal standards body; *not* in AAIF (by choice). | **P1** |
| **AGNTCY / Internet of Agents** | Be discoverable in an **Agent Directory**; describe agents/tools via **OASF** (OCI-based, explicitly describes A2A agents **and** MCP servers); **SLIM** low-latency messaging. | Outshift by **Cisco** (Mar 2025) → **LF** (Jul 2025). 6 components (OASF, Agent Directory, SLIM, Identity, Observability, Security). | **P2** |
| **ANP** (Agent Network Protocol) | DID-based **decentralized discovery/identity** for cross-operator agent federation. | Open-source community. *Status not independently verified in pass #2 — treat as experimental.* | **P2 (experimental)** |

### 5.2 Telecom-native interfaces (the credibility layer — bridges agents to real networks)

| Standard | What we bridge | How an agent uses it |
|---|---|---|
| **3GPP NEF / CAPIF** | already in ZorteNet (evolved5g SDK) | subscribe to monitoring events |
| **3GPP intent-driven mgmt — TS 28.312** (verified **v18.8.0, Rel-18**) | IDMS = a Management Service (MnS) in the Service-Based Management Architecture (SBMA); intent lifecycle create/modify/query/activate | `intent-to-network` agent acts as an **IDMS consumer** submitting intents to a 3GPP MnS producer |
| **TM Forum TMF921 / TMF921A** + **Autonomous Networks L0–L5** | TMF921 Intent Management API (v5.0.0, re-released Jan 2026) + the RDF **Intent Ontology (TIO)**; the L0–L5 autonomy ladder | LLM translates NL goals → **TIO-validated Turtle/JSON-LD intent** via TMF921; packs are positioned on L0–L5 |
| **O-RAN — WG1 SMO Intent TR v5.0**, **R1 AI/ML model APIs**, A1/O1/E2 | RAN management via intents; R1 model deploy/retrieve (App Protocols v8.00); A1 policy, E2/KPM | `ran-opt-copilot` authors A1 policies / supervises xApps; uses R1 to deploy/retrieve models |
| 3GPP **NWDAF**, **MDAS/MDAF**; **ETSI ZSM / ENI** | analytics + closed-loop automation patterns | agent consumes analytics; `self-heal` framed as a ZSM closed loop — *(specifics not independently verified in pass #2; treat as design intent)* |

### 5.3 "Propose more" — additional faces worth shipping

- **OpenAPI/REST** (already present) and **gRPC/Protobuf** for high-throughput control.
- **CloudEvents + AsyncAPI** to standardize the existing WS/SSE event stream (machine-discoverable).
- **OpenAI-compatible tool/function schema** (already present) + keep the Anthropic tool schema.
- **LangChain/LangGraph native tool interface** (already the runtime) + adapters for CrewAI/AutoGen.
- **ChatOps**: Slack / Teams / Matrix webhooks for human-in-the-loop approvals.
- **W3C Web of Things (WoT)** Thing Descriptions for IoT/device-edge connectors (optional).

> **Design note:** all of §5.1 sit behind a shared `ToolRegistry`. Writing a tool once
> (`@tool def get_slice_load(...)`) automatically surfaces it via MCP, A2A, REST, and gRPC. That
> single fact is the architectural punchline of the whole framework.

---

## 6. LLM layer — local-first

- **Default: Ollama**, fully local, no keys. Recommended tool-calling models for an 8–24 GB dev box:
  `llama3.1:8b` / `qwen2.5:7b-instruct` / `mistral-nemo` (tool calling), with a note that larger
  `qwen2.5:32b` / `llama3.3:70b` improve telecom reasoning if hardware allows.
- **Cloud (optional):** OpenAI / Anthropic via the same interface for users who want frontier quality.
- **vLLM** path for self-hosted GPU serving at scale.
- **Telecom grounding:** RAG over the **knowledge base** (3GPP excerpts via Tele-Data, project docs)
  so a small local model punches above its weight on telecom Q&A.
- **Built-in eval:** `telco-bench` scores the configured model on **TeleQnA** so users can compare
  local vs. cloud on telecom knowledge — a shareable, viral artifact.

---

## 7. Datasets (ask #2 + #3)

A `zortenet.datasets` **registry**: declarative entries `{name, source, license, loader, role}` with
`zortenet datasets pull <name>`. Roles: **RAG** (ingest into the knowledge base), **eval**
(benchmark the agent/model), **replay** (feed the testbed event bus to simulate live traffic).

| Dataset | Size / form | Role | Status |
|---|---|---|---|
| **TeleQnA** (`netop/TeleQnA`, arXiv:2310.15051) | 10k telecom MCQs, 5 categories | eval (`telco-bench`) | ✅ verified (pass #1) |
| **Tele-Data** (`AliMaatouk/Tele-Data`, arXiv:2409.05314) | ~2.5B tok / 12.1 GB (arXiv + 3GPP + Wiki + CommonCrawl) | RAG knowledge base | ✅ verified (pass #1) |
| **5G3E** (`cedric-cnam/5G3E-dataset`, 6GNet'22) | ~1.1 TB 5G time-series KPI/telemetry | replay / anomaly training | ✅ verified (⚠ no explicit LICENSE file — verify before redistribution) |
| **TSpec-LLM** (`rasoul-nikbakht/TSpec-LLM`) | 3GPP-specification corpus for spec-grounded LLM Q&A | RAG / eval | ✅ source confirmed (pass #2) |
| **TeleQuAD** (`EricssonResearch/TeleQuAD`) | telecom extractive QA (Ericsson Research) | eval / RAG | ◑ repo confirmed (pass #2); size/licence to verify |
| **TelecomTS** (`AliMaatouk/TelecomTS`) | telecom time-series / multimodal observability | replay / anomaly | ◑ candidate; not independently verified |

**Telecom-specialized models** to benchmark/ground against (not datasets, but in scope for
`telco-bench` + RAG): **Tele-LLMs** (`Ali-maatouk/Tele-LLMs`, arXiv:2409.05314, verified pass #1),
**TelecomGPT** (arXiv:2407.09424) and **NetLLM** (arXiv:2402.02338) — all surfaced as primary
sources in pass #2 but with task-level details not independently re-verified; cite cautiously.

> Licensing is a release-blocker concern: the registry records each dataset's license and the
> `pull` command surfaces it; nothing is vendored into the repo — datasets are fetched on demand.

---

## 8. Local testbed (asks #4 + #5)

**Verified canonical stack:** Open5GS + UERANSIM is *the* no-SDR 5G-SA quickstart, documented by
Open5GS itself [open5gs.org/docs]. For real-RF/O-RAN: srsRAN/OAI + Open5GS, and **OSC RIC + srsRAN
E2/E2AP** is the standard open O-RAN closed loop [arXiv:2502.00715].

### 8.1 Tier 1 — "laptop testbed" (default `make up`)

```
docker compose:
  mongo          # Open5GS subscriber DB
  open5gs         # 5GC NFs (AMF/SMF/UPF/NRF/AUSF/UDM/PCF/NEF) — image-based
  ueransim-gnb    # simulated gNB
  ueransim-ue     # one or more simulated UEs (traffic generators)
  ollama          # local LLM serving (model pulled on first run)
  zortenet         # the toolkit (FastAPI + interop servers + agent)
  prometheus       # scrape Open5GS + zortenet metrics
  grafana          # dashboards (optional profile)
```
No SDR, no hardware, no cloud, no API keys. `make up` → `make demo PACK=netops-copilot`.

### 8.2 Tier 2 — "real RF / O-RAN" (opt-in profile)

Swap UERANSIM for **srsRAN** (ZMQ virtual RF or USRP) + add **OSC RIC**; enables `ran-opt-copilot`
over real E2/KPM. Documented as an advanced profile; not required for the core experience.

### 8.3 Tier 3 — "cloud-native" (Kubernetes/Helm)

Replace the placeholder Terraform with real Helm values (Open5GS + UERANSIM charts exist upstream)
so the same testbed runs on a K8s cluster for CI and multi-node experiments.

> **Validation discipline:** the compose/Helm will be **brought up and smoke-tested live** during
> the scaffold milestone (`docker compose config` + actual `make up` + an end-to-end event→agent
> assertion) before it's called "runnable." I will not claim it works until I've run it.

---

## 9. Implementation roadmap

**Milestone 0 — Foundation (the runnable scaffold, next):**
- New package layout (§10); generalize `LocationEvent → NetworkEvent`; `Connector` registry; keep tests green.
- `zortenet.llm` with **Ollama** default; wire into the agent runtime.
- **Tier-1 testbed** compose (Open5GS+UERANSIM+Ollama+toolkit+Prometheus) — brought up & smoke-tested.
- **MCP server** exposing the existing tools (fastest credible "agent-native" win).
- `location-monitor` pack = today's behavior, repackaged. Dataset registry + `telco-bench` (TeleQnA).

**Milestone 1 — Agent-native:** A2A Agent Card + server; AG-UI event stream; `netops-copilot` pack with RAG over Tele-Data + Prometheus; README demo GIF.

**Milestone 2 — Standards bridge:** O-RAN A1/E2 connector (OSC RIC); `intent-to-network` (TS 28.312 / TMF921); `ran-opt-copilot`; Tier-2 testbed.

**Milestone 3 — Breadth & polish:** `self-heal`, `security-sentinel`, `energy-agent`, `multi-agent-noc` (A2A); ACP/ANP/AGNTCY adapters; Helm/K8s (Tier-3); docs site; example notebooks.

**Milestone 4 — Community:** contribution guide for new packs/connectors, a pack cookiecutter, a public leaderboard for `telco-bench`, conference/demo collateral.

Each milestone is independently demoable and star-worthy; M0+M1 alone make a compelling launch.

---

## 10. Proposed repo structure (evolve in place)

```
src/zortenet/
  core/        events.py (NetworkEvent), bus.py, normalize.py
  connectors/  base.py (Connector), open5gs.py, free5gc.py, nef.py, oran_e2.py, prometheus.py, nwdaf.py, ueransim.py
  memory/      vector_store.py (generalized), knowledge_base.py
  llm/         base.py, ollama.py, openai.py, anthropic.py, vllm.py
  agent/       runtime.py (LangGraph), tools.py (ToolRegistry)
  interop/     mcp_server.py, a2a_server.py, acp_server.py, agui.py, rest.py (existing api.py), grpc/
  packs/       base.py, netops_copilot/, intent_to_network/, self_heal/, security_sentinel/,
               ran_opt_copilot/, energy_agent/, location_monitor/, multi_agent_noc/, telco_bench/
  datasets/    registry.py, loaders/
  app.py       # FastAPI assembly wiring packs + interop servers
testbed/       docker-compose.yml, profiles/ (oran, grafana), ollama/, open5gs/, ueransim/, README.md
docs/          BLUEPRINT.md (this), architecture/, packs/, interop/, testbed/
examples/      notebooks + curl/MCP/A2A client snippets
```
The current `src/*.py` files migrate under `src/zortenet/` with shims so existing imports/tests keep
passing during the refactor.

---

## 11. Star-collection / DX strategy

- **60-second wow:** `git clone && make up && make demo` → an agent answering questions about a live
  (simulated) 5G network, locally, no keys. README leads with that GIF.
- **"Agent-native" badge:** prominently list MCP/A2A/ACP/AG-UI support — rare in telecom repos.
- **Benchmark hook:** `telco-bench` produces a shareable score card ("Qwen2.5-7B scores X% on TeleQnA").
- **Standards credibility:** the O-RAN/3GPP/TMF bridges make it citable in academic & telco circles → SNS JU adoption.
- **Contribution surface:** packs and connectors are small, self-contained, cookiecutter-generated — easy first PRs.
- **Honest narrative:** a `docs/THE-GAP.md` that lays out (with citations + the hedge) why the realm
  is narrow and what agentic networking unlocks — this *is* the maintainer's "expose how limited the
  realm is" goal, done credibly.

---

## 12. Risks & open decisions

- **Gap thesis is an inference, not proof** (§1.2). Mitigation: frame as "underserved," cite honestly, let the working product speak.
- **Testbed fragility:** srsUE 5G-SA is a prototype "no longer actively developed" with open attach/PDU bugs [srsRAN docs] → keep UERANSIM as the default; srsRAN is the opt-in advanced tier.
- **Interop spec drift:** MCP/A2A/ACP move fast; research-2 reconfirms current status. Adapters are thin and versioned to absorb churn.
- **Scope creep:** 9 packs is the *vision*; M0+M1 (location-monitor + netops-copilot + MCP/A2A) is the *launchable core*.
- **Open decisions for the maintainer:** (a) framework name; (b) license stays Apache-2.0 (current) ✅; (c) which 2 packs headline the launch; (d) Python-only vs. add a TS MCP client for the dashboard.

---

## Appendix — cited sources (research pass #1, adversarially verified)

- SNS JU portfolio map — https://smart-networks.europa.eu/interactive-map-of-sns-projects/
- DESIRE6G — https://desire6g.eu/use-cases/ ; https://cordis.europa.eu/project/id/101096466
- FIDAL — https://fidal-he.eu/use-cases ; https://cordis.europa.eu/project/id/101096146
- IMAGINE-B5G — https://imagineb5g.eu/use/ ; https://cordis.europa.eu/project/id/101096452
- 6G-SANDBOX — https://6g-sandbox.eu/objectives/ ; https://cordis.europa.eu/project/id/101096328
- Open5GS + UERANSIM — https://open5gs.org/open5gs/docs/ ; https://github.com/open5gs/open5gs
- Open5GS + srsRAN single-VM (ZMQ) — https://github.com/ngkore/Open5GS-srsRAN ; https://docs.srsran.com
- srsRAN/OAI dominance — Rouili et al., IEEE NOMS 2024 ; arXiv:2412.21162 ; https://github.com/srsran/srsRAN_Project
- REAL (O-RAN + OSC RIC + PPO) — https://arxiv.org/html/2502.00715 ; https://github.com/srsran/oran-sc-ric
- TeleQnA — https://huggingface.co/datasets/netop/TeleQnA ; arXiv:2310.15051
- Tele-Data / Tele-LLMs — https://huggingface.co/datasets/AliMaatouk/Tele-Data ; arXiv:2409.05314 ; https://github.com/Ali-maatouk/Tele-LLMs
- 5G3E — https://github.com/cedric-cnam/5G3E-dataset ; https://hal.science/hal-03698732

### Research pass #2 — interop protocols + telecom standards (adversarially verified)

- MCP transports — https://modelcontextprotocol.io/specification/2025-11-25/basic/transports (2025-06-18 superseded)
- A2A launch / governance — https://www.linuxfoundation.org/press/linux-foundation-launches-the-agent2agent-protocol-project... ; https://a2a-protocol.org/latest/ ; A2A↔MCP: https://a2a-protocol.org/latest/topics/a2a-and-mcp/
- AGNTCY — https://docs.agntcy.org/ ; OASF https://github.com/agntcy/oasf ; arXiv:2509.18787 (Agent Directory)
- AG-UI — https://docs.copilotkit.ai/agentic-protocols/ag-ui ; https://github.com/ag-ui-protocol/ag-ui
- TM Forum — IG1230 (AN Technical Architecture) ; TMF921A Intent Management API Profile v1.1.0 ; https://github.com/tmforum-apis/TMF921_Intent
- 3GPP intent — https://www.3gpp.org/technologies/intent-management ; TS 28.312 v18.8.0 (Rel-18) ; TS 28.533 (SBMA)
- O-RAN — https://www.o-ran.org/blog/60-new-or-updated-o-ran-technical-documents-released-since-march-2025 (WG1 SMO Intent TR v5.0; R1 v8.00 AI/ML APIs)
- Agentic-telecom SoTA & models — arXiv:2407.09424 (TelecomGPT), arXiv:2409.05314 (Tele-LLMs), arXiv:2402.02338 (NetLLM), arXiv:2507.14230 (LLM intent-based RAN mgmt), arXiv:2511.09087 / arXiv:2511.02532 (multi-agent O&M)
- Datasets — https://huggingface.co/datasets/rasoul-nikbakht/TSpec-LLM ; https://github.com/EricssonResearch/TeleQuAD

**Refuted in pass #2 (do not rely on):** TS 28.312 "v19.1.0 / SA5 began June 2018" (verified version is **v18.8.0, Rel-18**); the exact O-RAN "WG1–WG11" enumeration (WG1 attribution + R1 facts *are* verified).
**Still open (neither pass verified):** ACP technical status & A2A-merge details, ANP, ETSI ZSM/ENI specifics, NWDAF/MDAS-MDAF specifics. Treat these as design intent until confirmed.
