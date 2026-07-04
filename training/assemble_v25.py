#!/usr/bin/env python
"""Assemble the v2.5 MULTI-USE-CASE training set on the GPU box (Phase C).

Buckets: synth-uc (all 8 6G packs, the star) + real curated trajectories (shipped) + synth
intent/diagnosis + a general anti-forgetting slice (dolly, with a fallback to extracting the
general-dolly rows already in the v1 train.jsonl). Writes ds_v25/{train,val}.jsonl and a
v2.5 SFT config. Self-contained — does not touch the gate ledger.
"""
import json
from pathlib import Path

from corelab.train.configs import build_config
from corelab.train.curate import split_train_val, write_jsonl
from corelab.train.mixture import SIXG_RATIOS, assemble_mixture
from corelab.train.synth import synth_diagnosis_pairs, synth_intent_pairs, synth_uc_trajectories

OUT = Path("ds_v25")
OUT.mkdir(exist_ok=True)
TOTAL = 1500

# 1) synthetic
uc = synth_uc_trajectories(n_per_uc=120)          # ~960 across all 8 UCs
intent = synth_intent_pairs(300)
diag = synth_diagnosis_pairs(250)
print(f"[synth] uc={len(uc)} intent={len(intent)} diagnosis={len(diag)}", flush=True)

# 2) general anti-forgetting slice — fetch dolly, fall back to v1 extraction
general = []
try:
    from datasets import load_dataset
    ds = load_dataset("databricks/databricks-dolly-15k", split="train")
    for r in ds.select(range(min(600, len(ds)))):
        instr = r["instruction"] + (("\n\n" + r["context"]) if r.get("context") else "")
        general.append({"messages": [{"role": "user", "content": instr},
                                      {"role": "assistant", "content": r["response"]}],
                        "meta": {"source": "general-dolly"}})
    print(f"[general] fetched {len(general)} dolly samples", flush=True)
except Exception as e:
    print(f"[general] dolly fetch failed ({e}); extracting from v1 train.jsonl", flush=True)
    if Path("train.jsonl").exists():
        for l in open("train.jsonl"):
            rec = json.loads(l)
            if rec.get("meta", {}).get("source") == "general-dolly":
                general.append(rec)
    print(f"[general] extracted {len(general)} from v1", flush=True)

# 3) real curated correlation trajectories (shipped to ds_v25/)
real = []
rp = OUT / "trajectories.curated.jsonl"
if rp.exists():
    real = [json.loads(l) for l in rp.read_text().splitlines() if l.strip()]
print(f"[real] curated trajectories: {len(real)}", flush=True)

# 4) mixture (v2.5 ratios; explicit total so synth-uc is well-used and all real traj kept)
buckets = {"synth-uc": uc, "general": general, "synth-intent": intent,
           "synth-diagnosis": diag, "trajectory": real}
mixed, rep = assemble_mixture(buckets, ratios=SIXG_RATIOS, total=TOTAL)
train, val = split_train_val(mixed)
write_jsonl(train, OUT / "train.jsonl")
write_jsonl(val, OUT / "val.jsonl")
print("[mixture] buckets:", {k: len(v) for k, v in buckets.items()}, flush=True)
print("[mixture] report:", json.dumps(rep.to_dict(), indent=2), flush=True)
print(f"[mixture] train={len(train)} val={len(val)} -> {OUT}/", flush=True)

# 5) v2.5 SFT config (reuse the qwen3-8b preset; point at the new data)
cfg = build_config("qwen3-8b")
cfg.update({"train_file": "ds_v25/train.jsonl", "validation_file": "ds_v25/val.jsonl",
            "output_dir": "output_v25"})
json.dump(cfg, open("sft_config_v25.json", "w"), indent=2)
print("[config] wrote sft_config_v25.json -> output_v25/", flush=True)
