# 6G Use-Case Coverage & Multi-UC Training Plan

*How ZorteNet's agentic toolkit maps onto the full ITU-R IMT-2030 (6G) use-case space, the tooling
that delivers it, and the plan to train one generalist agent that operates across all of it.*

Status: tooling for all IMT-2030 scenarios is **built and tested** (this iteration); the multi-UC
model is **planned with the data generator implemented** (`synth_uc_trajectories`). See §5–§6.

---

## 1. The framing (why this is the gap, not the saturated verticals)

The deep-research pass found the *vertical* 6G use cases — XR, V2X, UAV, digital twins, eHealth —
are **saturated** with EU SNS JU pilots (DESIRE6G, IMAGINE-B5G, FIDAL, 6G-SANDBOX). What is *not*
served is the **agentic operations layer** for them: the agent that diagnoses, correlates, and
recommends across the network serving each use case. So ZorteNet does not re-build the verticals —
it provides one **agentic-ops pack per use case** that teaches the *same* reusable loop:

> **`overview → assess → correlate → recommend`** — observe the domain, assess an entity, correlate
> across peers/signals to decide **entity-specific vs systemic**, and recommend an action (actuation
> always routes through the approval-gated `intent-to-network` pack; the UC packs are read-only).

This reconciles "be the go-to for *all* 6G use cases" (breadth → stars) with "fill the real gap"
(agentic ops → differentiation). One generalist model + many UC packs.

## 2. ITU-R IMT-2030 taxonomy → pack coverage

IMT-2030 (Rec. ITU-R M.2160) defines **6 usage scenarios** and **4 overarching design aspects**.
Every one now maps to at least one pack (✅ new this iteration, ▫️ pre-existing):

| IMT-2030 scenario / aspect | Primary pack | Supporting packs |
|---|---|---|
| **Immersive Communication** (XR/holographic) | ✅ `xr-qoe` | ▫️ ran-opt-copilot, netops-copilot |
| **Massive Communication** (mMTC) | ✅ `massive-iot` | ▫️ security-sentinel (signaling storms) |
| **Hyper-Reliable Low-Latency** (URLLC/V2X) | ✅ `v2x-ops` | ▫️ ran-opt-copilot, intent-to-network |
| **Ubiquitous Connectivity** (NTN, aerial) | ✅ `ntn-ops`, ✅ `uav-ops` | ▫️ location-monitor |
| **Integrated AI & Communication** (NWDAF) | ✅ `ai-native` | ▫️ multi-agent-noc |
| **Integrated Sensing & Communication** (ISAC) | ✅ `sensing-ops` | — (new `sensing` event domain) |
| *Aspect:* **Sustainability** | ✅ `energy-agent` | ▫️ ran-opt-copilot |
| *Aspect:* **Security / Resilience / Privacy** | ▫️ security-sentinel | ▫️ self-heal |
| *Aspect:* **Connecting the unconnected** | ✅ ntn-ops, ✅ uav-ops | — |
| *Aspect:* **Ubiquitous intelligence** | ✅ ai-native | ▫️ multi-agent-noc, the whole framework |
| *Cross-cutting ops* | ▫️ netops-copilot, intent-to-network, spec-kb, amarisoft | — |

**17 loadable packs total** (9 prior + 8 new). Load the 6G family with
`load_packs(["6g"])` / `ZORTENET_PACKS=6g`, or individually.

## 3. The 8 new use-case packs

Each is read-only, store-backed, and exposes the identical 4-tool template (so the model learns one
transferable loop). All have unit tests; the full suite is green (253 tests).

| Pack | Domain(s) read | The correlation it teaches |
|---|---|---|
| `energy-agent` | energy + throughput | power-vs-load → sleep candidate; systemic over-provisioning vs cell-specific |
| `xr-qoe` | qos + throughput | per-flow QoE vs XR budget → flow/app-specific vs network-wide |
| `massive-iot` | signaling + throughput | RACH/attach storm → cell-specific cluster vs network-wide storm |
| `v2x-ops` | qos + ran_kpi | URLLC budget breach → vehicle radio vs cell-wide congestion |
| `ntn-ops` | ran_kpi + qos | NTN link (delay/doppler/SINR) per beam → terminal-specific vs beam/satellite-wide |
| `ai-native` | slice + qos | NWDAF predicted-vs-observed → entity-specific vs systemic model drift |
| `sensing-ops` | sensing + throughput | ISAC detection SNR vs comms load → comms contention vs target/clutter |
| `uav-ops` | ran_kpi + location | aerial interference / handover thrash → UE-specific vs cell-wide LoS interference |

Template/exemplar: `src/zortenet/packs/energy_agent/`. New event domain: `EventDomain.SENSING`.

## 4. The shared agentic behavior (why one adapter suffices)

The **UC-specific knowledge lives in the tools and event domains**; the **agentic behavior is
UC-agnostic** — every pack is diagnose→correlate→conclude→recommend. Therefore we train **one
generalist QLoRA adapter** on a mixture spanning all UCs, not 8 specialist adapters. The model
generalizes the loop; the packs supply the per-UC facts at inference. This is the central design
decision of the training plan.

## 5. Multi-UC training plan

### 5.1 Data sources (per UC)
1. **Synthetic (bulk, machine-validated)** — `zortenet.train.synth.synth_uc_trajectories()`
   *(implemented)*: seeds a real EventStore with one degraded entity among peers, runs each pack's
   **real** `assess_*` + `correlate_*` tools, emits an outcome-grounded trajectory. One call →
   training data for all 8 UCs. Scales to hundreds/UC, reproducible by seed.
2. **Real live capture** — for UCs inducible on the Amarisoft testbed (energy via `cell_gain` power,
   coverage/interference via gain, mobility), reuse `training/degrade_capture.py` /
   `training/batch_capture.py` (hardened-English, log-only-clean). Anchors realism + serves as
   held-out eval signal.
3. **Dataset replay** — 5G3E / TelecomTS KPI time-series replayed through the bridge to seed
   realistic per-UC events (`zortenet.datasets`).

### 5.2 Mixture (extends `DEFAULT_RATIOS`)
Proposed v2.5 weights (add a `synth-uc` bucket; keep general data to prevent forgetting):

| bucket | v1 | **v2.5 (multi-UC)** |
|---|---|---|
| `trajectory` (real live) | 0.40 | 0.25 |
| `synth-uc` (all 8 UCs) | — | **0.30** |
| `synth-intent` | 0.20 | 0.15 |
| `synth-diagnosis` | 0.15 | 0.10 |
| `general` (anti-forgetting) | 0.25 | 0.20 |

Volume target for a meaningful v2.5: ~**120/UC synthetic (~960)** + ~300 real trajectories +
existing intent/diagnosis + general ≈ **3–5k samples**. `mixture.py` already reports shortfalls
loudly (no silent rebalancing).

### 5.3 Measurement — per-UC TeleAgentBench scenarios
Add one held-out scenario per UC (mirroring `qos-mobility-correlation`), e.g.
`xr-qoe-correlation`, `v2x-reliability-correlation`, `energy-saving-correlation`, … Each judged
**programmatically**: did the agent call `assess_*` then `correlate_*` and reach the correct
entity-specific/systemic verdict for a seeded scenario? These gate G0 (per-UC gap) and G2 (beat base).

### 5.4 Gates (per-UC, same ledger discipline)
- **G0** — base+RAG fails the per-UC correlation scenarios (establish the gap exists per UC).
- **G1** — per-UC dataset assembled; contamination guard + English filter applied.
- **G2** — tuned adapter beats base on the per-UC bench scenarios, **no general regression** (BFCL/TeleQnA within ε).
- **G3** — license-clear, model card with per-UC evidence, publish + leaderboard.

### 5.5 Hardware (existing setup)
One **qwen3:8b QLoRA** adapter on a single **NVIDIA L4 24GB** (`.159`) — the proven, only-trainable
tier on a single L4. The 24–32B quality tier (`qwen3-32b`) is the fallback **only if** 8B
underperforms on the broader multi-UC eval, and needs 2–4×24GB (multi-GPU/FSDP — not available on a
single L4 today). Model stays Apache-2.0.

## 6. Phased rollout & immediate next steps

| Phase | Work | State |
|---|---|---|
| **A** | 8 UC packs + `SENSING` domain + `synth_uc_trajectories` + tests | ✅ done |
| **B** | `synth-uc`→`mixture.py`(`SIXG_RATIOS`)+`train` CLI (`synth --uc-per`, `mixture --multi-uc`); 8 per-UC bench scenarios (`sixg_scenarios`) + contamination-guarded; **G0 multi-UC run** | ✅ done |
| **C** | multi-UC dataset assembled (synth-uc 675 + general 375 + intent 225 + diagnosis 180 + 19 real → 1401/73), G1 | ✅ done |
| **D** | v2.5 QLoRA retrain (4-bit, loss 0.68→0.38) + **G2 per-UC eval** | ✅ ran — **NEGATIVE** |
| **E** | **G3** publish — **BLOCKED by G2 regression** | blocked |

### G2 multi-UC result (base vs v2.5 fine-tuned, same TransformersProvider) → `training/g2_sixg.json`
**Honest negative: base 5/8 → fine-tuned 3/8 (`improved=False`) — a REGRESSION.** The fine-tune
*fixed* `ai-native` (fail→pass) but *broke* `xr`, `massive-iot`, `v2x` (pass→fail). Root cause is
precise: on every regressed scenario the FT **failed `used:assess_*`** — i.e. it **skipped the
per-entity assessment step and jumped to `correlate_*`**, the exact habit the synth-uc trajectories
were built to teach. So the SFT instilled the *conclusion pattern* but not the *procedure* (likely
underfit the multi-step behaviour at LoRA-r16/2-epochs, and/or overfit the synth phrasing). The
gate ledger did its job: **G2 fails → G3 publish blocked** (the framework refuses to ship a regressed model).

**Next (v2.6) — diagnose & fix the procedure regression:**
1. Confirm the skip on raw FT traces (rule out a judge/parse artifact).
2. Make `assess` *necessary*: add trajectories where skipping it yields a wrong conclusion (hard negatives), not just positive demos.
3. Tune capacity: higher LoRA rank / more epochs (the procedure underfit while the easy conclusion text was memorised); keep/raise the general slice against forgetting.
4. Lock the eval engine (base scored 4/8 on Ollama vs 5/8 on Transformers — engine-sensitive); evaluate base and FT identically.

### G0 multi-UC result (base qwen3:8b, live on `.159`, 2026-06-22) → `training/g0_sixg.json`
**Base passes 4/8** per-UC correlation scenarios (PASS: energy, v2x, ntn, uav; FAIL: xr, massive-iot,
ai-native, sensing). All 4 failures share one learnable pattern: the base **skips the per-entity
`assess_*` step and jumps straight to `correlate_*`** (it does correlate and name the degraded
entity, but omits the diagnostic assessment). The gap is real and specific — exactly the
assess→correlate chaining the `synth_uc_trajectories` data demonstrates. **Training justified.**

**Immediate next step (Phase C):** `python -m zortenet.train synth --uc-per 120` + curate real live
captures + `python -m zortenet.train mixture --multi-uc` (marks G1), then Phase D is the v2.5 QLoRA
retrain that tests whether one adapter closes the correlation gap **across all 6G use cases at once**.
