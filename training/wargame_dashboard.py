#!/usr/bin/env python
"""Render the slick showcase console (multi-scenario, incl. RF) from a war-game results.json.

    WARGAME_RESULTS=wargame_evidence/results.json python training/wargame_dashboard.py
"""
import json
import os
from pathlib import Path

from corelab.wargame import RF_SCENARIO_ID, SCENARIOS, get_scenario, rf_scenario_meta
from corelab.wargame.showcase import showcase_html

src = os.getenv("WARGAME_RESULTS", "wargame_evidence/results.json")
results = json.load(open(src))


def _meta(sid):
    if sid in SCENARIOS:
        return get_scenario(sid).to_dict()
    if sid == RF_SCENARIO_ID:
        return rf_scenario_meta()
    return {"scenario_id": sid, "title": sid, "mission_asset": sid, "description": ""}


scenarios = {sid: _meta(sid) for sid in {r["scenario_id"] for r in results}}
out = Path(os.getenv("WARGAME_HTML", "wargame_evidence/console.html"))
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(showcase_html(scenarios, results))
print(f"wrote {out} ({out.stat().st_size} bytes) from {len(results)} matchups "
      f"across {len(scenarios)} scenario(s)")
