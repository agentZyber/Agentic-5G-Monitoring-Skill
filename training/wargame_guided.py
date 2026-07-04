#!/usr/bin/env python
"""Guided, step-by-step war-game walkthrough — for the audit demo.

Narrates each scenario turn-by-turn (red move → blue move → doctrine gate → mission status),
pausing between steps, then prints the verdict + scorecard, and a campaign summary across scenarios.

    python training/wargame_guided.py                 # all scenarios, interactive (Enter to advance)
    python training/wargame_guided.py --auto          # no pauses (CI / quick run)
    python training/wargame_guided.py --live-approval  # YOU approve/deny each countermeasure
    python training/wargame_guided.py contested-tactical-network   # a specific scenario
"""
import sys

from corelab.wargame import (SCENARIOS, ApprovalPolicy, ReactiveController, get_scenario,
                             run_wargame)
from corelab.wargame.benchmark import scripted_reds

C = {"r": "\033[0m", "b": "\033[1m", "dim": "\033[2m", "cy": "\033[36m", "rd": "\033[31m",
     "gn": "\033[32m", "am": "\033[33m", "bl": "\033[94m", "gy": "\033[90m"}
def c(s, col): return f"{C[col]}{s}{C['r']}"

ARGS = sys.argv[1:]
INTERACTIVE = "--auto" not in ARGS
LIVE_APPROVAL = "--live-approval" in ARGS


def pause(msg="   ↵ Enter to advance"):
    if INTERACTIVE:
        try:
            input(c(msg, "gy"))
        except EOFError:
            pass


def banner():
    print(c("\n  ████  CORE LAB · NCSRD — ADVERSARIAL WAR-GAME  ████", "cy"))
    print(c("  sovereign  ·  human-in-the-loop  ·  non-kinetic simulation", "gy"))


def briefing(sc):
    print(c(f"\n▌ SCENARIO — {sc.scenario_id}", "b"))
    print(f"  {c(sc.title, 'am')}")
    print(c(f"  {sc.description}", "dim"))
    print(f"  mission asset : {c(sc.mission_asset, 'cy')}")
    print(f"  red arsenal   : {c(', '.join(sc.red_actions), 'rd')}")
    print(f"  blue arsenal  : {c(', '.join(sc.blue_actions), 'bl')}")
    print(f"  win condition : hold the mission service · detect within {c(sc.detect_deadline, 'am')} "
          f"turn(s) · {c('zero', 'am')} unauthorized actions")


def observer(turn, rec, world, sc):
    print(c(f"\n  ── TURN {turn}/{sc.max_turns} " + "─" * 34, "gy"))
    print(f"   {c('RED ', 'rd')}  {rec.red_action or c('holds', 'dim')}")
    print(f"   {c('BLUE', 'bl')}  {rec.blue_action or c('holds', 'dim')}")
    status = c("● MISSION HEALTHY", "gn") if rec.mission_healthy else c("● MISSION DEGRADED", "rd")
    threats = c(f"   active threats: {rec.active_threats}", "dim") if rec.active_threats else ""
    print(f"   {status}{threats}")
    pause()


def live_approval_cb(req):
    print(c("\n   ⚠  DOCTRINE GATE — operator decision required", "am"))
    print(f"      proposed: {c(req.action + '(' + str(req.args) + ')', 'b')}")
    print(f"      rationale: {c(req.rationale, 'dim')}")
    try:
        ans = input(c("      approve this countermeasure? [Y/n] ", "am")).strip().lower()
    except EOFError:
        ans = "y"
    ok = ans in ("", "y", "yes")
    print(c("      → " + ("APPROVED" if ok else "DENIED"), "gn" if ok else "rd"))
    return ok


def run_one(sc):
    briefing(sc)
    pause("   ↵ Enter to begin the engagement")
    approval = (ApprovalPolicy(callback=live_approval_cb) if LIVE_APPROVAL
                else ApprovalPolicy(mode="auto-approve"))
    red = scripted_reds(sc)["multi-vector"]()          # multi-threat adversary → shows the full loop
    blue = ReactiveController(name="blue:doctrine-defender")
    res = run_wargame(sc, red, blue, approval, observer=lambda t, rec, w: observer(t, rec, w, sc))
    s = res.score
    print(c(f"\n  ▐ VERDICT — {'MISSION HELD ✔' if s.success else 'MISSION LOST ✘'}",
            "gn" if s.success else "rd"))
    print(f"    availability {c(f'{s.availability:.0%}', 'cy')}  ·  detect "
          f"{c(s.time_to_detect, 'cy')} turn(s)  ·  neutralised "
          f"{c(f'{s.threats_neutralised}/{s.threats_injected}', 'cy')}  ·  unauthorized "
          f"{c(s.unauthorized_applies, 'gn' if not s.unauthorized_applies else 'rd')}")
    for ck in s.checks:
        print(f"      {c('✔', 'gn') if ck.passed else c('✘', 'rd')} {ck.name} "
              f"{c('— ' + ck.detail, 'dim')}")
    if res.approval_log:
        print(c("    doctrine decisions:", "gy"))
        for e in res.approval_log:
            print(f"      {c('APPROVED', 'gn') if e['approved'] else c('DENIED', 'rd')}  "
                  f"{e['action']}({e['args']})  ·  {c(e['approver'] or e['reason'], 'dim')}")
    return res


def main():
    banner()
    chosen = [a for a in ARGS if a in SCENARIOS] or list(SCENARIOS)
    print(c(f"  campaign: {len(chosen)} scenario(s) — {', '.join(chosen)}", "gy"))
    results = []
    for sid in chosen:
        results.append(run_one(get_scenario(sid)))
        pause("\n   ↵ Enter for the next scenario")
    print(c("\n  ═══════  CAMPAIGN SUMMARY  ═══════", "cy"))
    for r in results:
        print(f"   {r.scenario_id:30} "
              f"{c('HELD', 'gn') if r.score.success else c('LOST', 'rd')}  ·  "
              f"availability {r.score.availability:.0%}  ·  "
              f"{r.score.threats_neutralised}/{r.score.threats_injected} neutralised  ·  "
              f"{c('0 unauthorized', 'gn')}")
    print(c("\n  full leaderboard + interactive console → http://127.0.0.1:8799/console.html\n", "gy"))


if __name__ == "__main__":
    main()
