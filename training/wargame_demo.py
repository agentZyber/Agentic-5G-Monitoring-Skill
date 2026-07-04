#!/usr/bin/env python
"""Flagship war-game demo — run the red/blue adversarial simulation and write the audit evidence pack.

Plays every adversary profile against the defender configs (passive floor, fixed-script heuristic,
and — when a sovereign local model is reachable — an LLM agent), ranks them on a leaderboard, and
emits dashboard.html + run_report.md + results.json. Runs offline; the agent uses a local Ollama
model (sovereign, air-gappable). Non-kinetic simulation + decision-support only.

    OLLAMA_MODEL=qwen2.5:14b python training/wargame_demo.py
"""
import json
import os
from pathlib import Path

from corelab.wargame import (blue_configs, dashboard_html, get_scenario, leaderboard,
                              result_markdown, run_matchups, scripted_reds)

OUT = Path(os.getenv("WARGAME_OUT", "wargame_evidence"))
OUT.mkdir(exist_ok=True)
sc = get_scenario(os.getenv("WARGAME_SCENARIO", "contested-tactical-network"))
print(f"[demo] scenario: {sc.title}")

provider = None
try:
    from corelab.llm import get_provider
    p = get_provider("ollama", model=os.getenv("OLLAMA_MODEL", "qwen2.5:14b"),
                     host=os.getenv("OLLAMA_HOST", "http://localhost:11434"))
    if p.is_available():
        provider = p
        print(f"[demo] sovereign agent defender enabled: {p.model}")
    else:
        print("[demo] Ollama not reachable — running scripted baselines only")
except Exception as exc:
    print(f"[demo] no LLM provider ({exc}) — scripted baselines only")

results = run_matchups(sc, scripted_reds(sc), blue_configs(sc, provider))
board = leaderboard(results)
print("\n[demo] DEFENDER LEADERBOARD (vs adversary profiles):")
for r in board:
    print(f"   {r['blue']:26} win={r['win_rate']:.0%} availability={r['mean_availability']:.0%} "
          f"t-to-detect={r['mean_time_to_detect']}")

featured = next((r for r in results if "agent" in r.blue), results[-1])
(OUT / "dashboard.html").write_text(
    dashboard_html(sc, results, board, featured, model=(provider.model if provider else "scripted")))
(OUT / "run_report.md").write_text(result_markdown(featured))
(OUT / "results.json").write_text(json.dumps([r.to_dict() for r in results], indent=2, default=str))
print(f"\n[demo] evidence pack -> {OUT}/  (dashboard.html, run_report.md, results.json)")
