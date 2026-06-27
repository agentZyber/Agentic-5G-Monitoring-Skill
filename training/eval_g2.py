#!/usr/bin/env python
"""G2 eval — TeleAgentBench head-to-head: base qwen3:8b vs base+LoRA-adapter, on the GPU host.

Runs both via TransformersProvider (transformers + PEFT, no serving). The decisive question:
does the fine-tuned model now PASS qos-mobility-correlation (the gap all base models failed)?
"""

import gc
import json

import torch

from zortenet.bench.teleagent import run_teleagent_bench
from zortenet.llm.transformers_provider import TransformersProvider

BASE = "Qwen/Qwen3-8B"
ADAPTER = "/home/localadmin/zt/output"


def evaluate(label, **kw):
    print(f"\n[load] {label}", flush=True)
    provider = TransformersProvider(model=BASE, load_in_4bit=True, max_new_tokens=512, **kw)
    run = run_teleagent_bench(
        provider, progress=lambda sid, ok: print(f"   {sid:30} {'PASS' if ok else 'fail'}", flush=True)
    )
    res = {r.scenario_id: r.success for r in run.reports}
    res["_success_rate"] = run.success_rate
    res["_invalid"] = run.invalid_call_rate
    print(f"[done] {label}: success={run.success_rate:.0%} invalid_calls={run.invalid_call_rate:.1%}", flush=True)
    del provider
    gc.collect()
    torch.cuda.empty_cache()
    return res


base = evaluate("BASE qwen3:8b")
ft = evaluate("FINE-TUNED qwen3:8b + adapter", adapter=ADAPTER)

print("\n================ G2 EVAL — TeleAgentBench: base vs fine-tuned ================", flush=True)
for s in [k for k in base if not k.startswith("_")]:
    tag = "   <== TARGET GAP" if s == "qos-mobility-correlation" else ""
    print(f"  {s:30} base={'PASS' if base[s] else 'fail':4}  ft={'PASS' if ft[s] else 'fail':4}{tag}", flush=True)
print(f"  {'OVERALL success rate':30} base={base['_success_rate']:.0%}      ft={ft['_success_rate']:.0%}", flush=True)

json.dump({"base": base, "fine_tuned": ft}, open("/home/localadmin/zt/g2_eval.json", "w"), indent=2, default=str)
print("[saved] /home/localadmin/zt/g2_eval.json", flush=True)
