# Model Pipeline — Fine-Tuning a Telecom *Agent* Model

> **Status:** design doc, now **implemented as scaffolding** in `src/corelab/train/`
> (Stage 5 of [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)): G0 baseline harness, curation +
> contamination guard, machine-validated synth generators, mixture assembly, the enforced G0→G3
> gate ledger, config presets, and the hedged model-card generator — all tested. The GPU runs
> themselves (G0 numbers, G2 LoRA-SFT, G3 publication) are the remaining live items.
> Grounded in the two adversarially-verified research passes; engineering numbers (GPU budgets,
> sample counts, mixture ratios) are **estimates / starting points**, labeled as such.
> Reference hardware config: 4 × 24 GB GPUs (96 GB VRAM total) + Amarisoft + Ettus B2xx testbed;
> the pipeline is written generally and scales down to a single 24 GB card.
> CLI: `make train ARGS="status"` (then `g0 | curate | synth | mixture | config | card`).

## 0. TL;DR — the decision

**Don't retrain — generate.** Pretraining and continual-pretraining a telecom LLM add little value
(Tele-LLMs already exist). What does *not* exist is a model tuned for **telecom agency** — reliable
tool-calling against network APIs, NL→intent translation, KPI-grounded diagnosis — and no public
dataset of that behavior exists either. The testbed is uniquely positioned to **generate** that
supervision. The pipeline therefore is:

```
testbed scenarios ──▶ trajectory capture ──▶ validate/filter ──▶ LoRA fine-tune ──▶ eval gates ──▶ publish
   (data factory)        (agent runs)        (outcome-checked)     (1–4 × 24 GB)      (telco-bench+)   (dataset+model+recipe)
```

The durable assets, in order of value: **(1) the dataset**, **(2) the benchmark**, **(3) the
pipeline-as-a-feature**, and only then **(4) the model weights** (which depreciate with every new
base-model generation).

## 1. Why each training depth does / doesn't make sense

| Depth | Verdict | Why |
|---|---|---|
| **Pretrain from scratch** | ❌ never | Trillions of tokens, GPU clusters far beyond 4×24 GB; zero marginal value over open bases. |
| **Continual pretraining** (knowledge injection) | ❌ mostly redundant | **Tele-LLMs already did this** on Tele-Data (~2.5 B tokens; arXiv:2409.05314, verified) and published weights. Each new base generation outdates the run. Knowledge is also the part **RAG already covers** (Tele-Data + TSpec-LLM in the knowledge base). |
| **SFT / instruction-tune (LoRA) for agentic behavior** | ✅ **the one to do** | The verified gap is telecom *agency*, not telecom *knowledge*. No published model is tuned for network tool-calling / intent translation / outcome-grounded diagnosis; no public dataset of it exists. |
| **Preference pass (DPO/KTO)** | ✅ cheap add-on | Correct-vs-plausible-wrong diagnoses and valid-vs-invalid intent JSON are easy to pair-generate and machine-check. |

## 2. The data factory — testbed-generated supervision

The inversion that makes this work: **the testbed is not just the eval environment, it is the data
factory.** Amarisoft (scriptable UEs, fault injection, remote API) + Open5GS/UERANSIM + the
toolkit's event bus and `ToolRegistry` can generate supervision that does not exist publicly — and
*validate every sample mechanically* before it enters the training set.

### 2.1 Data sources

| # | Source | What it teaches | How it's generated | Mechanical validator |
|---|---|---|---|---|
| 1 | **Tool-call trajectories** (core) | state → reasoning → tool calls → outcome | strong teacher model (or scripted policies) driven through testbed scenarios via the MCP tools / Amarisoft API | JSON-Schema check against each tool's `parameters`; **outcome check** — did the action achieve the goal in the testbed? |
| 2 | **NL → intent pairs** | operator goal → TMF921/TIO intent (Turtle/JSON-LD), TS 28.312 intent, or Amarisoft config call | template + paraphrase generation over the intent ontologies | TIO/Turtle syntax validation (e.g. `rdflib`); schema validation; round-trip apply in testbed |
| 3 | **Fault-diagnosis traces** | KPI window + logs → diagnosis rationale → remediation | inject real faults (attach storms, interference via B2xx, misconfig, rogue UE) and capture the window | **remediation clears the fault** (checkable in the testbed) — the outcome-grounded special sauce |
| 4 | **KPI-to-text grounding** | telemetry windows → summaries / anomaly explanations | windows from **5G3E** (~1.1 TB, verified) + own Prometheus/Amarisoft telemetry | consistency checks (numbers quoted must appear in the window) |
| 5 | **Retention spec-QA** | 3GPP/spec knowledge upkeep | TeleQuAD-style QA over TSpec-LLM excerpts | answer-span verification |
| 6 | **General instruction data** | prevents catastrophic forgetting of general/tool ability | existing open instruct sets | n/a (use as-is) |

### 2.2 Format & mixture

- **Format:** chat + tool-call JSONL matching the `ToolRegistry` schemas (OpenAI-style
  `tool_calls`), so training data and runtime traffic are the *same shape*. Each trajectory:
  system (pack prompt) → user → assistant tool calls → tool results → final answer.
- **Mixture (starting hypothesis — tune empirically):** trajectories ~30 %, intents ~15 %,
  diagnosis ~15 %, KPI-to-text ~10 %, spec-QA ~10 %, **general instruct ~20–30 %**. Skipping the
  general slice is the classic domain-SFT failure mode (forgetting general tool-calling).
- **Volume (heuristic):** ~5–10 k validated trajectories is a minimum viable set; 50 k+ is
  comfortable. Quality (outcome-validated) beats volume.

### 2.3 Contamination rules (hard)

- **Never train on TeleQnA** — it is the held-out benchmark; contamination invalidates `telco-bench`.
- Dedupe eval scenarios from training scenarios (scenario IDs, not just text).
- Hold out entire **fault types** (not just instances) for out-of-distribution evaluation.

## 3. Training recipe & GPU budgets (estimates)

Reference: 4 × 24 GB (96 GB total). All numbers are engineering estimates, not verified facts.

| Run | Fits? | Notes |
|---|---|---|
| **LoRA / QLoRA 7–8B** | ✅ single 24 GB card | hours per epoch on a 10–50 k set; the default first run |
| **LoRA 14–32B** | ✅ 1–2 cards (quantized) to 4 cards | the likely sweet spot for quality/cost |
| **QLoRA 70B** | ✅ across 4 cards (FSDP) | days; do this only if 32B measurably falls short |
| Full FT 7–8B | ⚠️ borderline | bf16 + AdamW ≳ 120 GB; needs ZeRO-3/offload — not worth it vs LoRA |
| Continual pretrain 7–8B on ~2.5 B tokens | ⚠️ feasible but days–weeks | low marginal value (§1) — skip |
| **Serving for data-gen/eval** | ✅ | 70B 4-bit ≈ 2 cards tensor-parallel (vLLM), leaving 2 cards for training — teacher and student can run concurrently |

- **Tooling:** any of TRL / Axolotl / torchtune / Unsloth; DPO via TRL. Keep configs in `training/`
  in-repo so the run is reproducible (`corelab train` CLI is the M3 design intent — capture →
  curate → tune → eval as one loop).
- **Base model — chosen by G0's bake-off, not asserted** (`corelab.train.configs.G0_SHORTLIST`).
  The framework's demand on the base is overwhelmingly **tool calling + structured output +
  multi-step**, so the shortlist is Apache-2.0 strong tool-callers (clean adapter redistribution):

  | Tier | Front-runner | Mistral alternative |
  |---|---|---|
  | **24–32B** (quality / hard reasoning) | **Qwen3-32B** (or Qwen2.5-32B for ecosystem maturity) | **Mistral Small 3.2 24B** — Apache-2.0, agentic/function-calling-tuned, lighter than 32B |
  | **7–12B** (cheap / edge; route routine packs here) | **Qwen3-8B** (or Qwen2.5-7B) | **Mistral NeMo 12B** — Apache-2.0, 128k ctx |

  *Llama-3.1-70B is available as a preset but **not** shortlisted (Community licence restricts
  weight redistribution; only reach for it if 24–32B measurably falls short.)* **LoRA-SFT** (QLoRA
  for ≥24B) is the right method — full-FT/pretrain buy nothing here. The `vllm_tool_call_parser`
  must match the family (`hermes` for Qwen, `mistral` for Mistral) or tool calling silently breaks.
  Recency caveat: confirm current point releases at selection time.

## 4. Evaluation protocol — the gates

Measure before and after; train only where the measurement shows a gap.

1. **`telco-bench` (TeleQnA, held out)** — telecom knowledge retention/gain.
2. **General tool-calling regression** — e.g. BFCL (Berkeley Function-Calling Leaderboard) or
   equivalent; the tune must not regress general ability beyond a small ε.
3. **Scenario-based agentic benchmark** (working name **TeleAgentBench** — itself a novel,
   citable artifact): N held-out testbed scenarios; metrics = task success rate, invalid-tool-call
   rate, intent-validity rate, time-to-resolution, unnecessary-action count. Judging is
   **programmatic outcome checks first** (the testbed knows if the fault cleared), LLM-judge only
   for rationale quality.
4. **The honest ablation:** base vs base+RAG vs FT vs FT+RAG. If **base+RAG already meets target,
   do not train** — publish that finding instead (it's a result too).

### Go/no-go gates

| Gate | Condition to proceed |
|---|---|
| **G0 — baseline** | off-the-shelf models (e.g. Qwen2.5-7B/32B, Llama-3.1-70B, Tele-LLMs) baselined on telco-bench + agentic scenarios; a measurable gap exists that RAG alone doesn't close |
| **G1 — data** | ≥ ~5–10 k outcome-validated trajectories (heuristic), mixture assembled, contamination rules enforced |
| **G2 — quality** | tuned model beats base+RAG on held-out scenarios **without** regressing general tool-calling beyond ε |
| **G3 — publish** | licenses cleared (§5); model card written with the same hedging discipline as the blueprint |

## 5. Licensing & publication flags

| Asset | Flag |
|---|---|
| **Self-generated trajectories** | clean core asset — publishable under Apache-2.0/CC-BY. **Amarisoft caveat:** don't include proprietary API responses/config schemas verbatim in a public dataset without checking Amarisoft's terms. |
| TeleQnA | eval-only here (never trained on); license per HF card |
| Tele-Data / TSpec-LLM | contain 3GPP/ETSI-derived and Common-Crawl-derived text — **check redistribution/derivative terms before publishing weights trained on them**; internal RAG use is lower-risk |
| 5G3E | **no LICENSE file** (verified, pass #1) — contact authors before training-for-publication |
| Base model | prefer Apache-2.0 base for clean weight redistribution (§3) |

## 6. Would a *tailored* model have value?

A one-off scenario-tailored model: modest value, and it **depreciates** with every base-model
generation. The durable, differentiating asset is the **tailoring pipeline as a framework
feature** — *"point the toolkit at your network → it generates trajectories → fine-tunes a small
model → evaluates it on telco-bench/TeleAgentBench."* For an SNS JU project that is an exploitable
result and a natural work package; for GitHub it is the pitch that completes the local-first
story: **today the framework runs local models — this makes it *produce* them.**

Target headline (to be earned, not claimed): *an 8B model, tuned on your own testbed, matching
cloud-frontier models on your network's operations — running on one GPU.*

## 7. Deliverables & roadmap fit

| Deliverable | Form | Stage ([IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)) |
|---|---|---|
| Trajectory capture hooks | event-bus + agent-runtime logging (same JSONL shape as training data) | **Stage 1** (cheap to add the moment `netops-copilot` exists — capture from day one) |
| `telco-bench` baselines | score table for local models | **Stage 1** (full G0 base-vs-RAG matrix re-run in Stage 5) |
| TeleAgentBench v0 | held-out scenario suite + programmatic judges | **Stage 4** (must exist before training can be measured) |
| G0 gate + Dataset v0 + LoRA tune + ablation (G1–G2) | HF dataset + adapter weights + `training/` configs | **Stage 5** (deliberately last) |
| `corelab train` loop + model card + report (G3) | CLI + published artifacts | **Stage 5** |

Naming of the published model/dataset follows the framework-naming decision (blueprint §12).

---

*References: Tele-LLMs / Tele-Data — arXiv:2409.05314; TeleQnA — arXiv:2310.15051; 5G3E —
6GNet 2022 (HAL hal-03698732); TSpec-LLM — hf:rasoul-nikbakht/TSpec-LLM; TelecomGPT —
arXiv:2407.09424 and NetLLM — arXiv:2402.02338 (surfaced as primary sources; task-level details
not independently re-verified — cite cautiously). Intent targets: TM Forum TMF921/TIO; 3GPP
TS 28.312 v18.8.0 (Rel-18). See the blueprint appendix for the full verified-source list.*
