"""G2 — training configs: hardware presets → TRL-style LoRA/QLoRA SFT configurations.

Emitting configs is testbed-free; **running them is not** — the launcher needs a GPU host with
``pip install trl peft transformers datasets`` and is explicitly gate-checked (G1 must have
passed). Numbers are engineering starting points (MODEL_PIPELINE §3), not verified optima.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

# preset name -> (base model, hardware assumption, knobs)
PRESETS: Dict[str, Dict[str, Any]] = {
    "qwen2.5-7b": {
        "base_model": "Qwen/Qwen2.5-7B-Instruct",
        "hardware": "1 × 24 GB GPU",
        "load_in_4bit": False,
        "lora_r": 16,
        "lora_alpha": 32,
        "per_device_train_batch_size": 2,
        "gradient_accumulation_steps": 8,
        "learning_rate": 1.0e-4,
    },
    "qwen2.5-32b": {
        "base_model": "Qwen/Qwen2.5-32B-Instruct",
        "hardware": "4 × 24 GB GPUs (device_map/FSDP)",
        "load_in_4bit": True,
        "lora_r": 16,
        "lora_alpha": 32,
        "per_device_train_batch_size": 1,
        "gradient_accumulation_steps": 16,
        "learning_rate": 8.0e-5,
    },
    "llama-3.1-70b-qlora": {
        "base_model": "meta-llama/Llama-3.1-70B-Instruct",
        "hardware": "4 × 24 GB GPUs (QLoRA + FSDP; tight — prefer 32B unless needed)",
        "load_in_4bit": True,
        "lora_r": 8,
        "lora_alpha": 16,
        "per_device_train_batch_size": 1,
        "gradient_accumulation_steps": 32,
        "learning_rate": 5.0e-5,
    },
}

_COMMON = {
    "num_train_epochs": 2,
    "lr_scheduler_type": "cosine",
    "warmup_ratio": 0.03,
    "logging_steps": 10,
    "save_strategy": "epoch",
    "bf16": True,
    "gradient_checkpointing": True,
    "lora_target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
    "max_seq_length": 4096,
    "dataset_format": "chat+tool_calls JSONL (messages field) — the trajectory/curation shape",
    "note": (
        "Starting points, not verified optima. Base-model licences: prefer Apache-2.0 bases "
        "(Qwen) for clean adapter redistribution; Llama bases carry their own licence terms."
    ),
}


def build_config(
    preset: str,
    train_path: str = "training/dataset/train.jsonl",
    val_path: str = "training/dataset/val.jsonl",
    output_dir: str = "training/output",
) -> Dict[str, Any]:
    if preset not in PRESETS:
        raise KeyError(f"unknown preset '{preset}'. Available: {', '.join(PRESETS)}")
    return {
        "preset": preset,
        **PRESETS[preset],
        **_COMMON,
        "train_file": train_path,
        "validation_file": val_path,
        "output_dir": output_dir,
    }


def write_config(config: Dict[str, Any], path: str | Path = "training/sft_config.json") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path


LAUNCHER_NOTE = """\
# Launch (on the GPU host — NOT runnable in the light install):
#   pip install trl peft transformers datasets bitsandbytes accelerate
#   python training/run_sft.py --config training/sft_config.json
# The runner template maps this config onto trl.SFTTrainer + peft.LoraConfig.
# Gate discipline: G1 must have passed (python -m zortenet.train status).
"""
