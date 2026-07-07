#!/usr/bin/env python
"""Assemble the dedicated WAR-GAME defender dataset (gold blue trajectories + anti-forgetting general).

Teaches the detect_threats -> apply_countermeasure loop the base agent skips. Writes ds_wargame/
{train,val}.jsonl + a 4-bit QLoRA config (r32 + MLP, the config that worked for the 6G model).
"""
import json
from pathlib import Path

from corelab.train.configs import build_config
from corelab.train.curate import split_train_val, write_jsonl
from corelab.train.mixture import assemble_mixture
from corelab.train.synth import synth_intent_pairs, synth_wargame_trajectories

OUT = Path("ds_wargame")
OUT.mkdir(exist_ok=True)
TOTAL = 1500

wg = synth_wargame_trajectories(n_per_scenario=150)     # gold blue-defender demos (deduped)
intent = synth_intent_pairs(200)                         # a little extra tool-calling diversity
print(f"[synth] wargame(gold)={len(wg)} intent={len(intent)}", flush=True)

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
    print(f"[general] dolly fetch failed ({e}); extracting from train.jsonl", flush=True)
    if Path("train.jsonl").exists():
        for l in open("train.jsonl"):
            rec = json.loads(l)
            if rec.get("meta", {}).get("source") == "general-dolly":
                general.append(rec)

buckets = {"synth-wargame": wg, "general": general, "synth-intent": intent}
ratios = {"synth-wargame": 0.62, "general": 0.28, "synth-intent": 0.10}
mixed, rep = assemble_mixture(buckets, ratios=ratios, total=TOTAL)
train, val = split_train_val(mixed)
write_jsonl(train, OUT / "train.jsonl")
write_jsonl(val, OUT / "val.jsonl")
print("[mixture] buckets:", {k: len(v) for k, v in buckets.items()}, flush=True)
print("[mixture] report:", json.dumps(rep.to_dict(), indent=2), flush=True)
print(f"[mixture] train={len(train)} val={len(val)} -> {OUT}/", flush=True)

cfg = build_config("qwen3-8b")
cfg.update({"load_in_4bit": True, "max_seq_length": 2048,
            "per_device_train_batch_size": 1, "gradient_accumulation_steps": 16,
            "lora_r": 32, "lora_alpha": 64,
            "lora_target_modules": ["q_proj", "k_proj", "v_proj", "o_proj",
                                    "gate_proj", "up_proj", "down_proj"],
            "num_train_epochs": 3,
            "train_file": "ds_wargame/train.jsonl", "validation_file": "ds_wargame/val.jsonl",
            "output_dir": "output_wargame"})
json.dump(cfg, open("sft_config_wargame.json", "w"), indent=2)
print(f"[config] sft_config_wargame.json: r={cfg['lora_r']} epochs={cfg['num_train_epochs']} "
      f"4bit={cfg['load_in_4bit']} -> output_wargame/", flush=True)
