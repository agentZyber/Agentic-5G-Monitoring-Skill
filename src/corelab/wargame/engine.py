"""War-game engine — the red↔world↔blue turn loop.

Guardrails are code-enforced (not prompt-hoped): per-side action budgets, only registered tools may
run (LLM hallucinations are dropped, not executed), threat handles are opaque tokens, and the judge
sees only the world log — never a controller's internals. Mirrors NCSRD's red/blue bench discipline
(budgets, opaque handles, separate judge), generalised to a defence simulation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from corelab.wargame.approval import ApprovalPolicy
from corelab.wargame.arsenal import build_blue_registry, build_red_registry
from corelab.wargame.judge import TurnRecord, WarGameScore, judge_wargame
from corelab.wargame.scenario import Action, WarGameScenario, WorldState, seed_world


@dataclass
class WarGameResult:
    scenario_id: str
    red: str
    blue: str
    score: WarGameScore
    timeline: List[TurnRecord]
    approval_log: List[Dict[str, Any]]
    events: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id, "red": self.red, "blue": self.blue,
            "score": self.score.to_dict(),
            "timeline": [{"turn": t.turn, "red": t.red_action, "blue": t.blue_action,
                          "mission_healthy": t.mission_healthy, "active_threats": t.active_threats,
                          "injected": t.injected_threats, "detect": t.detect_called}
                         for t in self.timeline],
            "approval_log": self.approval_log, "events": self.events,
        }


def _observe(world: WorldState, store, role: str, budget_left: int) -> str:
    recent = store.recent(limit=8)
    lines = [f"[{e.severity.value}] {e.domain.value}/{e.event_type} {e.entity_id or ''}".rstrip()
             for e in recent]
    status = "DEGRADED" if not world.mission_healthy() else "healthy"
    head = (f"mission asset: {world.mission} | service status: {status} | "
            f"your action budget left: {budget_left}")
    return head + "\nrecent events (newest first):\n  " + "\n  ".join(lines or ["(none)"])


def _apply(registry, action: Optional[Action], budget: Dict[str, int]) -> tuple[bool, str, Any]:
    if action is None or action.tool == "__hold__":
        return False, "hold", None
    if budget["used"] >= budget["max"]:
        return False, "budget-exhausted", None
    if action.tool not in registry:                       # guardrail: only real tools run
        return False, f"invalid-action:{action.tool}", None
    try:
        result = registry.get(action.tool).invoke(**action.args)
    except Exception as exc:                              # a bad call is dropped, never crashes the game
        return False, f"tool-error:{exc}", None
    budget["used"] += 1
    return True, "applied", result


def run_wargame(scenario: WarGameScenario, red, blue,
                approval: Optional[ApprovalPolicy] = None, observer=None) -> WarGameResult:
    approval = approval or ApprovalPolicy()
    store = seed_world(scenario)
    world = WorldState(store, scenario.mission_asset)
    counter = [0]
    red_reg = build_red_registry(store, scenario, counter)
    blue_reg = build_blue_registry(store, scenario, approval)
    red_budget = {"used": 0, "max": scenario.red_budget}
    blue_budget = {"used": 0, "max": scenario.blue_budget}

    timeline: List[TurnRecord] = []
    for turn in range(1, scenario.max_turns + 1):
        rec = TurnRecord(turn=turn)

        # --- RED moves ---
        r_action = red.decide("red", _observe(world, store, "red", red_budget["max"] - red_budget["used"]),
                              red_reg, turn)
        r_ok, r_note, r_res = _apply(red_reg, r_action, red_budget)
        if r_action and r_action.tool != "__hold__":
            rec.red_action = f"{r_action.label()} [{r_note}]"
        if r_ok and isinstance(r_res, dict) and r_res.get("threat_id"):
            rec.injected_threats = [r_res["threat_id"]]

        # --- BLUE moves ---
        b_action = blue.decide("blue", _observe(world, store, "blue", blue_budget["max"] - blue_budget["used"]),
                               blue_reg, turn)
        b_ok, b_note, _ = _apply(blue_reg, b_action, blue_budget)
        if b_action and b_action.tool != "__hold__":
            rec.blue_action = f"{b_action.label()} [{b_note}]"
        rec.detect_called = bool(b_action and b_action.tool == "detect_threats" and b_ok)

        rec.mission_healthy = world.mission_healthy()
        rec.active_threats = [t.payload.get("threat_id") for t in world.active_threats()]
        timeline.append(rec)
        if observer is not None:                              # per-turn hook (guided/step-by-step demo)
            observer(turn, rec, world)

    score = judge_wargame(scenario, timeline, approval.log, world)
    return WarGameResult(
        scenario_id=scenario.scenario_id, red=getattr(red, "name", "red"),
        blue=getattr(blue, "name", "blue"), score=score, timeline=timeline,
        approval_log=approval.log, events=len(store),
    )
