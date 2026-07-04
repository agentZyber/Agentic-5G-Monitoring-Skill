#!/usr/bin/env python
"""Run the RF red/blue episode LIVE against the real Amarisoft gNB — real cell_gain fault + real CQI.

Safety-first: ABORTS unless cell power is nominal (offset 0) AND >=1 UE with CQI is attached; the
fault window is short (only while stepping down); restore is GUARANTEED in `finally` and verified
independently. The real episode is merged into the console results so the RF run shows REAL CQI.

    AMARISOFT_WS_URL=ws://10.50.101.62:9001/ PYTHONPATH=src python training/rf_live.py
"""
import json
import os
import time
from pathlib import Path

from corelab.connectors.amarisoft import AmarisoftClient, websocket_transport
from corelab.wargame import RF_SCENARIO_ID, rf_episode

GNB = os.getenv("AMARISOFT_WS_URL", "ws://10.50.101.62:9001/")
CELL = 1
gnb = AmarisoftClient(transport=websocket_transport(GNB, timeout=8))


def set_gain(db):
    return gnb._call("cell_gain", cell_id=CELL, gain=db)


def offset():
    return gnb.config_get()["response"]["nr_cells"][str(CELL)]["gain"]


def read_cqi():
    ues = gnb._call("ue_get", stats=True).get("response", {}).get("ue_list", []) or []
    return {u.get("ran_ue_id"): (u.get("cells") or [{}])[0].get("cqi")
            for u in ues if (u.get("cells") or [{}])[0].get("cqi") is not None}


base_off = offset()
base = read_cqi()
print(f"[sanity] cell-1 power offset={base_off}  ·  UEs with CQI={base}")
if base_off != 0:
    raise SystemExit("ABORT: cell power is not nominal — refusing to stack a fault.")
if not base:
    raise SystemExit("ABORT: no UEs attached with CQI. Connect a UE to the 5G network, then re-run.")


def live_sampler(power_db: float):
    set_gain(power_db)
    time.sleep(5)                      # let the UE(s) re-measure and report CQI at the new power
    cqi = read_cqi()
    print(f"   [live] cell power {power_db:>5} dB -> CQI {cqi}", flush=True)
    return cqi


ep = None
try:
    ep = rf_episode(sampler=live_sampler)          # steps -6/-10/-14 then restores at turn 4
    ep["red"], ep["blue"] = "red:rf-power-cut(LIVE)", "blue:ran-ops(LIVE)"
finally:
    set_gain(0.0)
    time.sleep(3)
    print(f"[restore] cell-1 offset -> {offset()} (must be 0)  ·  UEs={read_cqi()}", flush=True)

out = Path("wargame_evidence/results.json")
res = [x for x in (json.load(open(out)) if out.exists() else []) if x.get("scenario_id") != RF_SCENARIO_ID]
res.append(ep)
json.dump(res, open(out, "w"), indent=2, default=str)
print(f"[done] LIVE RF episode merged into {out}. Regenerate the console:\n"
      f"       PYTHONPATH=src python training/wargame_dashboard.py")
