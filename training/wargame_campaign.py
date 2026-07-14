"""Theater-scale campaign — headless, paced console run (~30 s). The `/map` view is the visual version.

    PYTHONPATH=src python training/wargame_campaign.py
    CAMPAIGN_PACE=0.15 CAMPAIGN_TURNS=120 PYTHONPATH=src python training/wargame_campaign.py
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from corelab.wargame.campaign import build_theater, iter_campaign, run_campaign

PACE = float(os.getenv("CAMPAIGN_PACE", "0.34"))
TURNS = int(os.getenv("CAMPAIGN_TURNS", "80"))

nodes, edges = build_theater()
print(f"THEATER EXERCISE — {len(nodes)} nodes across 3 sectors · {len(edges)} comms links · {TURNS} turns",
      flush=True)
print("sustained multi-wave assault (jam / flood / intrude / spoof) vs a doctrine blue defender\n", flush=True)

for f in iter_campaign(TURNS):
    k = f["kpi"]
    bar = "█" * int(k["availability"] * 24)
    waves = " / ".join(f["waves"]) or "consolidation"
    flag = "  ⚠ SURGE" if k["active"] >= 10 else ""
    print(f"t{f['turn']:>2}/{TURNS}  avail {k['availability']:>4.0%} {bar:<24} active {k['active']:>2} "
          f"(+{len(f['injects'])}/-{len(f['mitigations'])})  {waves}{flag}", flush=True)
    time.sleep(PACE)

s = run_campaign(TURNS)["summary"]
print(f"\n▐ CAMPAIGN COMPLETE — {'THEATER HELD ✔' if s['held'] else 'RESIDUAL THREATS ✘'}", flush=True)
print(f"  {s['threats_injected']} threats injected · {s['threats_neutralised']} neutralised · "
      f"peak {s['peak_concurrent_threats']} concurrent", flush=True)
print(f"  availability: min {s['min_availability']:.0%} → end {s['end_availability']:.0%}", flush=True)
