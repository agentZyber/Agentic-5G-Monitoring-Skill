#!/usr/bin/env python
"""Assemble the v2.6 dataset — the FIX for the v2.5 regression (Phase D').

Root cause of v2.5: train/eval distribution gap (synth-uc ran with 4 tools; eval loads ~28). v2.6
uses `synth_uc_bench_trajectories` — the EXACT eval context (DEFAULT+UC packs, concatenated system
prompt, varied phrasing) — plus more volume and higher LoRA capacity (rank 32 + MLP modules, 4
epochs). Writes ds_v26/{train,val}.jsonl + sft_config_v26.json.
"""
import json
from pathlib import Path

from zortenet.train.configs import build_config
from zortenet.train.curate import split_train_val, write_jsonl
from zortenet.train.mixture import SIXG_RATIOS, assemble_mixture
from zortenet.train.synth import (synth_diagnosis_pairs, synth_intent_pairs,
                                   synth_uc_bench_trajectories)

OUT = Path("ds_v26")
OUT.mkdir(exist_ok=True)
TOTAL = 2800

uc = synth_uc_bench_trajectories(n_per_uc=200)   # ~1600 bench-MATCHED (the fix)
intent = synth_intent_pairs(400)
diag = synth_diagnosis_pairs(320)
print(f"[synth] uc(bench-matched)={len(uc)} intent={len(intent)} diagnosis={len(diag)}", flush=True)

general = []
try:
    from datasets import load_dataset
    ds = load_dataset("databricks/databricks-dolly-15k", split="train")
    for r in ds.select(range(min(800, len(ds)))):
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

real = []
rp = OUT / "trajectories.curated.jsonl"
if rp.exists():
    real = [json.loads(l) for l in rp.read_text().splitlines() if l.strip()]
print(f"[real] curated trajectories: {len(real)}", flush=True)

buckets = {"synth-uc": uc, "general": general, "synth-intent": intent,
           "synth-diagnosis": diag, "trajectory": real}
mixed, rep = assemble_mixture(buckets, ratios=SIXG_RATIOS, total=TOTAL)
train, val = split_train_val(mixed)
write_jsonl(train, OUT / "train.jsonl")
write_jsonl(val, OUT / "val.jsonl")
print("[mixture] buckets:", {k: len(v) for k, v in buckets.items()}, flush=True)
print("[mixture] report:", json.dumps(rep.to_dict(), indent=2), flush=True)
print(f"[mixture] train={len(train)} val={len(val)} -> {OUT}/", flush=True)

cfg = build_config("qwen3-8b")
cfg.update({
    "load_in_4bit": True, "max_seq_length": 2048,
    "per_device_train_batch_size": 1, "gradient_accumulation_steps": 16,
    "lora_r": 32, "lora_alpha": 64,
    "lora_target_modules": ["q_proj", "k_proj", "v_proj", "o_proj",
                            "gate_proj", "up_proj", "down_proj"],
    "num_train_epochs": 4,
    "train_file": "ds_v26/train.jsonl", "validation_file": "ds_v26/val.jsonl",
    "output_dir": "output_v26",
})
json.dump(cfg, open("sft_config_v26.json", "w"), indent=2)
print(f"[config] sft_config_v26.json: r={cfg['lora_r']} modules={len(cfg['lora_target_modules'])} "
      f"epochs={cfg['num_train_epochs']} 4bit={cfg['load_in_4bit']} -> output_v26/", flush=True)
