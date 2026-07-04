#!/usr/bin/env python
"""Render the slick showcase console from a war-game results.json.

    WARGAME_RESULTS=wargame_evidence/results.json python training/wargame_dashboard.py
"""
import json
import os
from pathlib import Path

from corelab.wargame import get_scenario
from corelab.wargame.showcase import showcase_html

src = os.getenv("WARGAME_RESULTS", "wargame_evidence/results.json")
results = json.load(open(src))
sc = get_scenario(results[0]["scenario_id"])
out = Path(os.getenv("WARGAME_HTML", "wargame_evidence/console.html"))
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(showcase_html(sc.to_dict(), results))
print(f"wrote {out} ({out.stat().st_size} bytes) from {len(results)} matchups")
