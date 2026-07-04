#!/usr/bin/env python
"""G2 multi-UC eval — base vs v2.5 fine-tuned on the 8 per-UC correlation scenarios.

Both run via the SAME TransformersProvider (fair, same decoding) over sixg_scenarios, each with
DEFAULT_PACKS + the matching UC pack. The decisive question: does the v2.5 adapter make the model
perform the full assess→correlate loop on the use cases the base skipped (xr, massive-iot,
ai-native, sensing)? Saves /home/localadmin/zt/g2_sixg.json.
"""
import gc
import json
import os

import torch

from corelab.bench.teleagent import SIXG_SCENARIO_PACKS, run_teleagent_bench, sixg_scenarios
from corelab.llm.transformers_provider import TransformersProvider
from corelab.packs import DEFAULT_PACKS

BASE = "Qwen/Qwen3-8B"
ADAPTER = os.getenv("ZT_ADAPTER", "/home/localadmin/zt/output_v25")
OUT = os.getenv("ZT_G2_OUT", "/home/localadmin/zt/g2_sixg.json")


def evaluate(label, **kw):
    print(f"\n[load] {label}", flush=True)
    prov = TransformersProvider(model=BASE, load_in_4bit=True, max_new_tokens=512, **kw)
    res = {}
    for s in sixg_scenarios():
        pack = SIXG_SCENARIO_PACKS[s.scenario_id]
        run = run_teleagent_bench(prov, scenarios=[s], packs=list(DEFAULT_PACKS) + [pack])
        r = run.reports[0]
        res[s.scenario_id] = {"success": r.success, "checks": {c.name: c.passed for c in r.checks}}
        print(f"   {s.scenario_id:28} {'PASS' if r.success else 'fail'}", flush=True)
    res["_passed"] = sum(1 for k, v in res.items() if not k.startswith("_") and v["success"])
    res["_total"] = len(SIXG_SCENARIO_PACKS)
    print(f"[done] {label}: {res['_passed']}/{res['_total']} use-case scenarios passed", flush=True)
    del prov
    gc.collect()
    torch.cuda.empty_cache()
    return res


base = evaluate("BASE qwen3:8b")
ft = evaluate("FINE-TUNED v2.5 (qwen3:8b + multi-UC adapter)", adapter=ADAPTER)

print("\n========== G2 multi-UC — base vs v2.5 fine-tuned ==========", flush=True)
for s in [k for k in base if not k.startswith("_")]:
    print(f"  {s:28} base={'PASS' if base[s]['success'] else 'fail':4}  "
          f"ft={'PASS' if ft[s]['success'] else 'fail':4}", flush=True)
print(f"  {'TOTAL passed':28} base={base['_passed']}/{base['_total']}      ft={ft['_passed']}/{ft['_total']}", flush=True)

improved = ft["_passed"] > base["_passed"]
allpass = ft["_passed"] == ft["_total"]
json.dump({"base": base, "fine_tuned": ft, "improved": improved, "all_pass": allpass, "adapter": ADAPTER},
          open(OUT, "w"), indent=2, default=str)
print(f"[saved] {OUT} | improved={improved} all_pass={allpass}", flush=True)
