"""TeleAgentBench — scenario-based evaluation of *network agency* (not knowledge).

TeleQnA measures what a model knows about telecom; **nothing public measures whether an agent
can act on a network**. TeleAgentBench fills that gap (MODEL_PIPELINE.md §4): each scenario
seeds a network situation (events, intents), poses an operator ask, and judges the outcome
**programmatically on state** — did the right tools run, does the ledger hold a valid intent,
did the safety gate hold — never on answer "vibes" alone.

This v0 ships five public *dev* scenarios. Held-out scenarios for Stage-5 evaluation follow the
same `Scenario` contract and live outside the repo until evaluation time (contamination rule).
"""

from zortenet.bench.registry import (
    AXES,
    Benchmark,
    RECOMMENDED_SUITE,
    REGISTRY,
    contamination_watchlist,
    get_benchmark,
    list_benchmarks,
)
from zortenet.bench.teleagent import (
    BenchRun,
    Scenario,
    ScenarioReport,
    builtin_scenarios,
    run_teleagent_bench,
    to_markdown,
)

__all__ = [
    "AXES",
    "Benchmark",
    "REGISTRY",
    "RECOMMENDED_SUITE",
    "list_benchmarks",
    "get_benchmark",
    "contamination_watchlist",
    "BenchRun",
    "Scenario",
    "ScenarioReport",
    "builtin_scenarios",
    "run_teleagent_bench",
    "to_markdown",
]
