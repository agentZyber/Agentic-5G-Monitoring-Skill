"""Benchmark & evaluation-dataset registry — what to test the output model against.

A multi-capability agentic model needs evaluation across several axes; this catalog records the
relevant public benchmarks (verified mid-2026) plus the framework's own, tagged by axis and with
the **contamination flag** that matters for training: anything used as an eval must be excluded
from the training mixture (see zortenet.train.curate.ContaminationGuard).

Axes:
  knowledge      telecom facts / spec comprehension (MCQ, QA)
  tool-calling   function-calling + general-capability regression (did the LoRA break the base?)
  intent-config  NL → formal spec / config / API calls (maps to intent-to-network)
  agentic-ops    multi-step operation on a network (the target capability — the historical gap)
  telemetry      KPI / log / time-series datasets to replay & test diagnosis against

Status: ``wired`` = runnable in-repo today; ``external`` = recommended, needs a loader/adapter.
Licences/versions move fast — confirm at use time (the project's honesty rule).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

AXES = ("knowledge", "tool-calling", "intent-config", "agentic-ops", "telemetry")


@dataclass(frozen=True)
class Benchmark:
    name: str
    axis: str
    kind: str                 # mcq | qa | tool-call | gen-config | scenario | timeseries | suite
    source: str
    license: str
    status: str               # wired | external
    contamination_risk: bool  # if used as eval, MUST be kept out of training data
    note: str = ""

    def __post_init__(self) -> None:
        if self.axis not in AXES:
            raise ValueError(f"{self.name}: invalid axis '{self.axis}' (valid: {AXES})")


REGISTRY: Dict[str, Benchmark] = {
    # --- knowledge (telecom facts / spec comprehension) ---
    "teleqna": Benchmark(
        "TeleQnA", "knowledge", "mcq", "hf:netop/TeleQnA", "see card", "wired", True,
        "10k telecom MCQs; wired in `telco-bench`. Also a component of GSMA Open-Telco.",
    ),
    "oran-bench-13k": Benchmark(
        "ORAN-Bench-13K", "knowledge", "mcq", "github:prnshv/ORAN-Bench-13K (arXiv:2407.06245)",
        "open (see repo)", "external", True,
        "13,952 MCQs from 116 O-RAN spec docs, 3 difficulty tiers — direct fit for the O-RAN/A1 work.",
    ),
    "3gpp-tsg": Benchmark(
        "3GPP-TSG", "knowledge", "qa", "GSMA Open-Telco (Hugging Face)", "open (community)",
        "external", True, "Standards-comprehension over curated 3GPP documents.",
    ),
    "telemath": Benchmark(
        "TeleMath", "knowledge", "qa", "GSMA Open-Telco (Hugging Face)", "open (community)",
        "external", True, "Quantitative telecom-engineering reasoning / problem solving.",
    ),
    "telequad": Benchmark(
        "TeleQuAD", "knowledge", "qa", "github:EricssonResearch/TeleQuAD", "see repo",
        "external", True, "Telecom extractive QA (Ericsson Research).",
    ),
    # --- tool-calling + general-capability regression (anti-forgetting) ---
    "bfcl": Benchmark(
        "BFCL (Berkeley Function-Calling Leaderboard)", "tool-calling", "tool-call",
        "github:ShishirPatil/gorilla (BFCL)", "Apache-2.0", "external", False,
        "THE function-calling benchmark — run before/after SFT to prove tool-calling didn't regress.",
    ),
    "mcp-bench": Benchmark(
        "MCP-Bench", "tool-calling", "tool-call", "arXiv 2025 (MCP-Bench)", "see source",
        "external", False, "Tool-using agents over MCP servers — you expose MCP, so this is on-point.",
    ),
    "ifeval": Benchmark(
        "IFEval", "tool-calling", "qa", "hf:google/IFEval", "Apache-2.0", "external", False,
        "Instruction-following regression (structured-output discipline).",
    ),
    "mmlu-pro": Benchmark(
        "MMLU-Pro", "tool-calling", "mcq", "hf:TIGER-Lab/MMLU-Pro", "MIT", "external", False,
        "General-knowledge regression — catch catastrophic forgetting from domain SFT.",
    ),
    # --- intent / config generation (maps to intent-to-network) ---
    "netconfeval": Benchmark(
        "NetConfEval", "intent-config", "gen-config",
        "github:RedHatResearch/conext24-NetConfEval (hf:NetConfEval/NetConfEval)", "see repo",
        "external", True,
        "NL requirements → formal spec / API-calls / config (CoNEXT'24). Task (ii) = generate "
        "function calls from requirements — directly comparable to draft_intent.",
    ),
    "teleyaml": Benchmark(
        "TeleYAML", "intent-config", "gen-config", "GSMA Open-Telco (Hugging Face)",
        "open (community)", "external", True,
        "Operator intent → standards-aligned YAML (5GC NFs, provisioning, slicing) — a "
        "standardized cousin of intent-to-network. Strong external yardstick for that pack.",
    ),
    # --- agentic network operations (the target capability) ---
    "teleagentbench": Benchmark(
        "TeleAgentBench (built-in)", "agentic-ops", "scenario", "built-in: zortenet.bench",
        "Apache-2.0", "wired", False,
        "Our state-based scenarios (ledger/store/tool-trace judges) incl. the safety gate; the "
        "only one with REAL-state outcome validation when run on the Amarisoft testbed.",
    ),
    "telagentbench-ext": Benchmark(
        "TelAgentBench (external)", "agentic-ops", "scenario", "ACL/EMNLP 2025 (industry track)",
        "see paper", "external", False,
        "Multi-faceted telecom-agent benchmark. NOTE name collision with our built-in — cite the "
        "external one explicitly to avoid confusion.",
    ),
    "netarena": Benchmark(
        "NetArena", "agentic-ops", "scenario", "arXiv:2506.03231", "see source", "external", False,
        "Dynamic benchmarks for AI agents in network automation.",
    ),
    "wirelessbench": Benchmark(
        "WirelessBench", "agentic-ops", "scenario", "arXiv 2026 (WirelessBench)", "see source",
        "external", False, "Tolerance-aware LLM-agent benchmark for wireless network intelligence.",
    ),
    "telelogs": Benchmark(
        "TeleLogs", "agentic-ops", "qa", "GSMA Open-Telco (Hugging Face)", "open (community)",
        "external", True, "Network troubleshooting from logs — the diagnosis axis of `self-heal`.",
    ),
    # --- telemetry / time-series datasets to replay & test diagnosis against ---
    "5g3e": Benchmark(
        "5G3E", "telemetry", "timeseries", "github:cedric-cnam/5G3E-dataset", "verify (no LICENSE)",
        "external", False, "Open 5G KPI/telemetry time-series — replay → test KPI interpretation.",
    ),
    "telecomts": Benchmark(
        "TelecomTS", "telemetry", "timeseries", "hf:AliMaatouk/TelecomTS", "see card",
        "external", False, "Telecom time-series / observability for anomaly & root-cause testing.",
    ),
    "srsranbench": Benchmark(
        "srsRANBench", "telemetry", "qa", "github:prnshv/srsRANBench", "see repo", "external", False,
        "srsRAN-specific benchmark — closest open analogue to a real RAN deployment.",
    ),
}

# The curated suite to actually run on the output model (covers every axis with the
# highest-signal, mostly-Apache-2.0 options). GSMA Open-Telco is the headline external standard.
RECOMMENDED_SUITE = {
    "knowledge": ["teleqna", "oran-bench-13k", "3gpp-tsg", "telemath"],
    "tool-calling": ["bfcl", "mcp-bench", "ifeval"],
    "intent-config": ["netconfeval", "teleyaml"],
    "agentic-ops": ["teleagentbench", "telelogs", "netarena"],
    "telemetry": ["5g3e", "telecomts"],
}


def list_benchmarks(axis: Optional[str] = None, status: Optional[str] = None) -> List[Benchmark]:
    items = list(REGISTRY.values())
    if axis:
        if axis not in AXES:
            raise ValueError(f"invalid axis '{axis}' (valid: {AXES})")
        items = [b for b in items if b.axis == axis]
    if status:
        items = [b for b in items if b.status == status]
    return items


def get_benchmark(name: str) -> Benchmark:
    key = name.lower().replace(" ", "-")
    if key not in REGISTRY:
        raise KeyError(f"unknown benchmark '{name}'. Known: {', '.join(sorted(REGISTRY))}")
    return REGISTRY[key]


def contamination_watchlist() -> List[str]:
    """Benchmark names whose content must be kept OUT of training data if used as eval."""
    return [b.name for b in REGISTRY.values() if b.contamination_risk]
