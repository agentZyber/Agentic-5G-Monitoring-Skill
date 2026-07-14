#!/usr/bin/env python
"""G2 war-game eval — does the fine-tuned defender actually WIN the war-game?

Runs the war-game (every scenario × adversary profile) with the LLM agent as BLUE, base vs
base+adapter, via the same TransformersProvider. Reference: the scripted reactive policy wins 100%.
The question: does fine-tuning move the agent from ~0% toward that gold line? Saves g2_wargame.json.
"""
import gc
import json
import os

import torch

from corelab.llm.transformers_provider import TransformersProvider
from corelab.wargame import (SCENARIOS, AgentController, ApprovalPolicy, get_scenario, run_wargame)
from corelab.wargame.benchmark import scripted_reds

BASE = "Qwen/Qwen3-8B"
ADAPTER = os.getenv("ZT_ADAPTER", "/home/localadmin/zt/output_wargame")


def winrate(label, **kw):
    print(f"\n[load] {label}", flush=True)
    prov = TransformersProvider(model=BASE, load_in_4bit=True, max_new_tokens=256, **kw)
    wins = tot = avail = 0
    detail = {}
    for sid in SCENARIOS:
        sc = get_scenario(sid)
        for rk, rf in scripted_reds(sc).items():
            res = run_wargame(sc, rf(), AgentController(prov, name="blue:agent"),
                              ApprovalPolicy(mode="auto-approve"))
            wins += int(res.score.success)
            avail += res.score.availability
            tot += 1
            detail[f"{sid}:{rk}"] = {"held": res.score.success,
                                     "availability": round(res.score.availability, 2)}
            print(f"   {sid:28} vs {rk:14} {'HELD' if res.score.success else 'lost'}", flush=True)
    print(f"[done] {label}: {wins}/{tot} held · mean availability {avail / tot:.0%}", flush=True)
    del prov
    gc.collect()
    torch.cuda.empty_cache()
    return {"wins": wins, "total": tot, "win_rate": wins / tot,
            "mean_availability": round(avail / tot, 3), "detail": detail}


base = winrate("BASE qwen3:8b agent")
ft = winrate("FINE-TUNED wargame agent", adapter=ADAPTER)
improved = ft["win_rate"] > base["win_rate"]
print("\n========== G2 WAR-GAME — base vs fine-tuned BLUE agent ==========", flush=True)
print(f"  base   win-rate {base['win_rate']:.0%}  (availability {base['mean_availability']:.0%})", flush=True)
print(f"  ft     win-rate {ft['win_rate']:.0%}  (availability {ft['mean_availability']:.0%})", flush=True)
print(f"  gold (reactive) 100%  ·  improved={improved}", flush=True)
json.dump({"base": base, "fine_tuned": ft, "reactive_gold": 1.0, "improved": improved},
          open(os.getenv("ZT_G2_OUT", "/home/localadmin/zt/g2_wargame.json"), "w"), indent=2, default=str)
print("[saved] g2_wargame.json", flush=True)
