"""Benchmark harness — run red×blue matchups and rank defenders on a leaderboard.

The scenario/benchmark DB (PoC-2): reproducible adversary profiles + defender configs, played
head-to-head, scored by the judge, and ranked. Any defender — a fixed-script heuristic, a human
baseline, or a sovereign LLM agent — is measured on the same axis (mission success, availability,
time-to-detect), so improvement is evidence, not assertion.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from corelab.llm.base import LLMProvider
from corelab.wargame.approval import ApprovalPolicy
from corelab.wargame.controllers import AgentController, ReactiveController, ScriptedController
from corelab.wargame.engine import WarGameResult, run_wargame
from corelab.wargame.scenario import Action, WarGameScenario

# controller factories (fresh instance per matchup — stateful controllers must not leak between runs)
Factory = Callable[[], Any]


def scripted_reds(scenario: WarGameScenario) -> Dict[str, Factory]:
    """Reproducible adversary profiles for a scenario."""
    acts = scenario.red_actions
    elements = ["link-1", "cell-1", "node-1", "feed-1"]
    reds: Dict[str, Factory] = {
        "single-jam": lambda: ScriptedController(
            [Action(acts[0], {"element": "link-1"})], name="red:single-jam"),
        "multi-vector": lambda: ScriptedController(
            [Action(a, {"element": e}) for a, e in zip(acts, elements)], name="red:multi-vector"),
        "persistent": lambda: ScriptedController(
            [Action(acts[0], {"element": "link-1"})] * 3, name="red:persistent"),
    }
    return reds


def blue_configs(scenario: WarGameScenario,
                 provider: Optional[LLMProvider] = None) -> Dict[str, Factory]:
    """Defender configs: a do-nothing floor, the fixed-script heuristic, and (optionally) an LLM agent."""
    cfgs: Dict[str, Factory] = {
        "passive": lambda: ScriptedController([], name="blue:passive"),
        "reactive-heuristic": lambda: ReactiveController(name="blue:reactive-heuristic"),
    }
    if provider is not None:
        cfgs["agent"] = lambda: AgentController(provider, name="blue:agent")
    return cfgs


def run_matchups(scenario: WarGameScenario, reds: Dict[str, Factory], blues: Dict[str, Factory],
                 approval_mode: str = "auto-approve") -> List[WarGameResult]:
    results: List[WarGameResult] = []
    for _rname, red_factory in reds.items():
        for _bname, blue_factory in blues.items():
            results.append(run_wargame(scenario, red_factory(), blue_factory(),
                                       ApprovalPolicy(mode=approval_mode)))
    return results


def leaderboard(results: List[WarGameResult]) -> List[Dict[str, Any]]:
    """Aggregate per defender across all adversary profiles, ranked by wins then availability."""
    agg: Dict[str, Dict[str, Any]] = {}
    for r in results:
        row = agg.setdefault(r.blue, {"blue": r.blue, "matchups": 0, "wins": 0,
                                      "avail_sum": 0.0, "ttd": []})
        row["matchups"] += 1
        row["wins"] += int(r.score.success)
        row["avail_sum"] += r.score.availability
        if r.score.time_to_detect is not None:
            row["ttd"].append(r.score.time_to_detect)
    board = []
    for row in agg.values():
        n = max(1, row["matchups"])
        board.append({
            "blue": row["blue"], "matchups": row["matchups"],
            "win_rate": round(row["wins"] / n, 3),
            "mean_availability": round(row["avail_sum"] / n, 3),
            "mean_time_to_detect": round(sum(row["ttd"]) / len(row["ttd"]), 2) if row["ttd"] else None,
        })
    board.sort(key=lambda x: (x["win_rate"], x["mean_availability"]), reverse=True)
    return board
