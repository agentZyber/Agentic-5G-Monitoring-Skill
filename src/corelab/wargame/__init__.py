"""wargame — a sovereign, scored, human-in-the-loop red/blue adversarial simulation.

Generalises NCSRD's red/blue side-channel bench + this toolkit's multi-agent framework into a
domain-agnostic war-game: a scenario from the benchmark DB is played out by a Red controller and a
Blue controller over an auditable event-log world; a programmatic judge scores mission outcomes;
consequential actions pass a human-approval (doctrine) gate; results rank on a leaderboard vs
scripted and human baselines. Runs on local (sovereign) LLMs. Simulation + decision-support only.
"""

from corelab.wargame.approval import ApprovalPolicy, ApprovalRequest
from corelab.wargame.arsenal import build_blue_registry, build_red_registry
from corelab.wargame.benchmark import blue_configs, leaderboard, run_matchups, scripted_reds
from corelab.wargame.controllers import AgentController, ReactiveController, ScriptedController
from corelab.wargame.engine import WarGameResult, run_wargame
from corelab.wargame.judge import Check, TurnRecord, WarGameScore, judge_wargame
from corelab.wargame.report import dashboard_html, result_markdown
from corelab.wargame.showcase import showcase_html
from corelab.wargame.scenario import (SCENARIOS, Action, WarGameScenario, WorldState,
                                       get_scenario, seed_world)

__all__ = [
    "Action", "WarGameScenario", "WorldState", "SCENARIOS", "get_scenario", "seed_world",
    "ApprovalPolicy", "ApprovalRequest", "ScriptedController", "ReactiveController", "AgentController",
    "run_wargame", "WarGameResult", "judge_wargame", "WarGameScore", "Check", "TurnRecord",
    "build_red_registry", "build_blue_registry",
    "scripted_reds", "blue_configs", "run_matchups", "leaderboard",
    "dashboard_html", "result_markdown", "showcase_html",
]
