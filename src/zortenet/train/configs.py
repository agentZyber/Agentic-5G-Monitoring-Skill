"""G2 — training configs: hardware presets → TRL-style LoRA/QLoRA SFT configurations.

Emitting configs is testbed-free; **running them is not** — the launcher needs a GPU host with
``pip install trl peft transformers datasets`` and is explicitly gate-checked (G1 must have
passed). Numbers are engineering starting points (MODEL_PIPELINE §3), not verified optima.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

# preset name -> (base model, hardware assumption, knobs).
# Model IDs/versions move fast — confirm at selection time. The BASE IS CHOSEN BY G0's bake-off
# (run base vs base+RAG on the real agentic scenarios), not asserted: see G0_SHORTLIST below.
PRESETS: Dict[str, Dict[str, Any]] = {
    # --- 7-8B tier: 1 × 24 GB LoRA; the cheap/edge variant (route routine packs here) ---
    "qwen3-8b": {  # current-gen front-runner for tool calling, Apache-2.0
        "base_model": "Qwen/Qwen3-8B",
        "license": "Apache-2.0",
        "vllm_tool_call_parser": "hermes",
        "hardware": "1 × 24 GB GPU",
        "load_in_4bit": False,
        "lora_r": 16,
        "lora_alpha": 32,
        "per_device_train_batch_size": 2,
        "gradient_accumulation_steps": 8,
        "learning_rate": 1.0e-4,
    },
    "qwen2.5-7b": {  # mature ecosystem / quant + tooling coverage
        "base_model": "Qwen/Qwen2.5-7B-Instruct",
        "license": "Apache-2.0",
        "vllm_tool_call_parser": "hermes",
        "hardware": "1 × 24 GB GPU",
        "load_in_4bit": False,
        "lora_r": 16,
        "lora_alpha": 32,
        "per_device_train_batch_size": 2,
        "gradient_accumulation_steps": 8,
        "learning_rate": 1.0e-4,
    },
    "mistral-nemo-12b": {  # the Mistral mid-size; Apache-2.0, 128k ctx, function-calling-trained
        "base_model": "mistralai/Mistral-Nemo-Instruct-2407",
        "license": "Apache-2.0",
        "vllm_tool_call_parser": "mistral",
        "hardware": "1 × 24 GB GPU (4-bit) or 2 × 24 GB (bf16)",
        "load_in_4bit": True,
        "lora_r": 16,
        "lora_alpha": 32,
        "per_device_train_batch_size": 1,
        "gradient_accumulation_steps": 16,
        "learning_rate": 9.0e-5,
    },
    # --- 24-32B tier: 2-4 × 24 GB QLoRA; the quality variant (hard reasoning / orchestration) ---
    "qwen3-32b": {  # current-gen Qwen, Apache-2.0
        "base_model": "Qwen/Qwen3-32B",
        "license": "Apache-2.0",
        "vllm_tool_call_parser": "hermes",
        "hardware": "2-4 × 24 GB GPUs (QLoRA + FSDP)",
        "load_in_4bit": True,
        "lora_r": 16,
        "lora_alpha": 32,
        "per_device_train_batch_size": 1,
        "gradient_accumulation_steps": 16,
        "learning_rate": 8.0e-5,
    },
    "qwen2.5-32b": {  # mature ecosystem alternative to qwen3-32b
        "base_model": "Qwen/Qwen2.5-32B-Instruct",
        "license": "Apache-2.0",
        "vllm_tool_call_parser": "hermes",
        "hardware": "2-4 × 24 GB GPUs (QLoRA + FSDP)",
        "load_in_4bit": True,
        "lora_r": 16,
        "lora_alpha": 32,
        "per_device_train_batch_size": 1,
        "gradient_accumulation_steps": 16,
        "learning_rate": 8.0e-5,
    },
    "mistral-small-24b": {  # THE Mistral alternative to Qwen-32B: Apache-2.0, agentic/function-calling
        "base_model": "mistralai/Mistral-Small-3.2-24B-Instruct-2506",  # or 3.1-2503
        "license": "Apache-2.0",
        "vllm_tool_call_parser": "mistral",
        "hardware": "2 × 24 GB GPUs (QLoRA) — lighter than 32B",
        "load_in_4bit": True,
        "lora_r": 16,
        "lora_alpha": 32,
        "per_device_train_batch_size": 1,
        "gradient_accumulation_steps": 16,
        "learning_rate": 8.0e-5,
    },
    # --- 70B: all 4 GPUs, serialize with serving; only if 24-32B measurably falls short ---
    "llama-3.1-70b-qlora": {
        "base_model": "meta-llama/Llama-3.1-70B-Instruct",
        "license": "Llama-3.1 Community (NOT Apache-2.0 — restricts weight redistribution)",
        "vllm_tool_call_parser": "llama3_json",
        "hardware": "4 × 24 GB GPUs (QLoRA + FSDP; tight — prefer 24-32B unless needed)",
        "load_in_4bit": True,
        "lora_r": 8,
        "lora_alpha": 16,
        "per_device_train_batch_size": 1,
        "gradient_accumulation_steps": 32,
        "learning_rate": 5.0e-5,
    },
}

# The recommended G0 base-model bake-off (Apache-2.0 strong tool-callers; run base vs base+RAG
# on the real agentic scenarios, then LoRA-SFT the winner). Quality tier leads; 7-8B is the
# cheap/edge variant you can ROUTE routine packs to (the provider abstraction supports per-call
# model choice). Recency caveat: confirm current point releases at selection time.
G0_SHORTLIST = ["qwen3-32b", "mistral-small-24b", "qwen3-8b", "mistral-nemo-12b"]

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
        "Starting points, not verified optima. The base is chosen by G0's bake-off, not asserted "
        "(see G0_SHORTLIST). Prefer Apache-2.0 bases (Qwen2.5/Qwen3, Mistral NeMo/Small) for clean "
        "adapter redistribution; Llama bases carry their own licence terms. vllm_tool_call_parser "
        "must match the base family or tool calling silently breaks."
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
