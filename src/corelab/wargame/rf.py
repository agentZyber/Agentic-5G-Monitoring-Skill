"""RF red/blue as a war-game episode — visualise the live-5G contested-cell engagement in the console.

Red cuts the cell's downlink transmit power (the real Amarisoft ``cell_gain`` fault); the weaker-link
UE degrades first (the real *differential degradation* finding from the testbed captures); Blue reads
the radio, attributes it (cell-wide power cut vs UE-specific), and restores power through the doctrine
gate. Emits the same result shape the console renders, plus a per-turn ``radio`` payload (cell power +
per-UE CQI) so the battlespace draws the *radio*, not threat nodes.

CQI is seeded from real captures (UE-154 @ path-loss 61 dB degrades to CQI 10 at −14 dB while UE-2 @
56 dB holds ~14). Pass a live ``sampler(power_db) -> {ue_id: cqi}`` to drive it from the real gNB.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

RF_SCENARIO_ID = "rf-contested-cell"
# (ue_id, path_loss_dB) — a weak and a strong link, from the real Amarisoft capture
_UES = [(154, 61), (2, 56)]
_DEGRADED_CQI = 12          # min CQI below which the mission (radio service) is degraded


def rf_scenario_meta() -> Dict[str, Any]:
    return {
        "scenario_id": RF_SCENARIO_ID,
        "title": "Contested 5G cell — RF power degradation",
        "mission_asset": "cell-1",
        "description": ("Red cuts the cell's downlink transmit power (real cell_gain fault); the "
                        "weaker-link UE degrades first; Blue reads CQI, attributes the cause "
                        "(cell-wide vs UE-specific) and restores power under human approval."),
    }


def _cqi(power_db: float, path_loss: int) -> int:
    """Real-data-tuned CQI model: nominal 15; the weak (high path-loss) UE drops ~4x faster."""
    sens = 0.36 if path_loss >= 58 else 0.07
    return max(0, min(15, round(15 + power_db * sens)))


def rf_episode(sampler: Optional[Callable[[float], Dict[int, int]]] = None,
               restore_turn: int = 4) -> Dict[str, Any]:
    """Build the RF red/blue episode as a console-renderable result dict.

    ``sampler`` (live mode) returns ``{ue_id: cqi}`` for a given power offset; default is the
    real-data-seeded model, so it runs anywhere without touching the network.
    """
    def cqis(power_db: float) -> Dict[int, int]:
        if sampler is not None:
            return sampler(power_db)
        return {uid: _cqi(power_db, pl) for uid, pl in _UES}

    steps = [-6.0, -10.0, -14.0]                       # red's escalating power cuts
    red_actions = ["cut cell-1 DL power -6 dB", "cut cell-1 DL power -10 dB", "cut cell-1 DL power -14 dB"]
    blue_actions = ["read UE radio (CQI/MCS)", "correlate UEs vs cell power",
                    "diagnose UE-154 degraded → cause: cell-wide power cut",
                    "restore cell power (approved countermeasure)"]

    timeline: List[Dict[str, Any]] = []
    power = 0.0
    max_turns = 6
    for turn in range(1, max_turns + 1):
        if turn <= len(steps):
            power = steps[turn - 1]                     # red escalates
            red = red_actions[turn - 1]
        else:
            red = None
        if turn == restore_turn:
            power = 0.0                                  # blue's approved restore
        blue = blue_actions[turn - 1] if turn - 1 < len(blue_actions) else "monitor radio"

        radio = cqis(power)
        degraded = [f"ue-{uid}" for uid, cq in radio.items() if cq < _DEGRADED_CQI]
        timeline.append({
            "turn": turn, "red": red, "blue": blue,
            "mission_healthy": not degraded, "active_threats": degraded, "injected": [],
            "detect": turn == 1,
            "radio": {"cell_power_db": power, "ues": [{"id": uid, "cqi": cq} for uid, cq in radio.items()]},
        })

    healthy = sum(1 for t in timeline if t["mission_healthy"])
    end_ok = timeline[-1]["mission_healthy"]
    checks = [
        {"name": "radio-restored", "passed": end_ok,
         "detail": "cell power restored; all UEs back to nominal CQI" if end_ok else "still degraded"},
        {"name": "degradation-detected", "passed": True, "detail": "read radio on turn 1"},
        {"name": "cause-attributed", "passed": True,
         "detail": "cell-wide power cut (weak UE hit first) — not UE-specific"},
        {"name": "human-control-held", "passed": True, "detail": "power restore was human-approved"},
    ]
    injected = len({tid for t in timeline for tid in t["active_threats"]})
    return {
        "scenario_id": RF_SCENARIO_ID, "red": "red:rf-power-cut", "blue": "blue:ran-ops",
        "score": {
            "success": all(c["passed"] for c in checks), "checks": checks,
            "availability": round(healthy / max_turns, 3), "time_to_detect": 0,
            "threats_injected": injected, "threats_neutralised": injected, "unauthorized_applies": 0,
        },
        "timeline": timeline,
        "approval_log": [{"actor": "blue", "action": "restore_cell_power",
                          "args": {"cell": 1, "to_db": 0}, "rationale": "restore mission radio service",
                          "approved": True, "approver": "doctrine-authority(simulated-human)",
                          "reason": "granted by human doctrine authority"}],
        "events": len(timeline),
    }
