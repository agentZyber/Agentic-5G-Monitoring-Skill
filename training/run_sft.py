#!/usr/bin/env python
"""QLoRA SFT runner — fine-tunes a base model on the messages-format dataset per a corelab config.

Runs on the GPU host (needs torch / transformers / peft / trl / bitsandbytes / datasets).
Reads training/sft_config.json (emitted by `corelab.train config`) and train/val JSONL whose
records are ``{"messages": [...]}``. Each example is rendered to text via the tokenizer's chat
template (tool-calls normalized to the HF ``type:function`` shape), with a manual fallback so a
template quirk never aborts the run.

    python run_sft.py --config sft_config.json            # train
    python run_sft.py --config sft_config.json --dry-run  # parse config only (no CUDA needed)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _normalize_messages(messages):
    """Make assistant tool_calls HF-template-friendly (add type=function; keep dict arguments)."""
    out = []
    for m in messages:
        m = dict(m)
        if m.get("tool_calls"):
            m["tool_calls"] = [
                {"type": "function", "function": tc.get("function", tc)} for tc in m["tool_calls"]
            ]
        out.append(m)
    return out


def _manual_render(messages) -> str:
    parts = []
    for m in messages:
        role = m.get("role")
        content = m.get("content") or ""
        if m.get("tool_calls"):
            calls = "; ".join(
                f"{tc.get('function', tc).get('name')}({json.dumps(tc.get('function', tc).get('arguments', {}))})"
                for tc in m["tool_calls"]
            )
            content = (content + "\n" if content else "") + f"<tool_call> {calls}"
        name = f" name={m['name']}" if m.get("name") else ""
        parts.append(f"<|{role}|>{name}\n{content}")
    return "\n".join(parts) + "\n"


def build_render(tokenizer):
    def render(example):
        messages = _normalize_messages(example["messages"])
        try:
            text = tokenizer.apply_chat_template(messages, tokenize=False)
        except Exception:
            text = _manual_render(example["messages"])
        return {"text": text}

    return render


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = json.loads(Path(args.config).read_text())
    print(f"[config] preset={cfg['preset']} base={cfg['base_model']} "
          f"4bit={cfg['load_in_4bit']} epochs={cfg['num_train_epochs']} "
          f"train={cfg['train_file']}", flush=True)
    if args.dry_run:
        print("[dry-run] config parsed OK; no training performed.")
        return 0

    import torch
    from datasets import load_dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from trl import SFTConfig, SFTTrainer

    tokenizer = AutoTokenizer.from_pretrained(cfg["base_model"], trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    quant = None
    if cfg["load_in_4bit"]:
        quant = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True,
        )
    model = AutoModelForCausalLM.from_pretrained(
        cfg["base_model"], quantization_config=quant,
        torch_dtype=torch.bfloat16, device_map="auto", trust_remote_code=True,
    )

    render = build_render(tokenizer)
    train_ds = load_dataset("json", data_files=cfg["train_file"], split="train").map(render)
    eval_ds = load_dataset("json", data_files=cfg["validation_file"], split="train").map(render)
    print(f"[data] train={len(train_ds)} val={len(eval_ds)}; sample chars={len(train_ds[0]['text'])}", flush=True)

    peft_cfg = LoraConfig(
        r=cfg["lora_r"], lora_alpha=cfg["lora_alpha"],
        target_modules=cfg["lora_target_modules"], lora_dropout=0.05, task_type="CAUSAL_LM",
    )
    import inspect

    sft_kwargs = dict(
        output_dir=cfg["output_dir"], num_train_epochs=cfg["num_train_epochs"],
        per_device_train_batch_size=cfg["per_device_train_batch_size"],
        gradient_accumulation_steps=cfg["gradient_accumulation_steps"],
        learning_rate=cfg["learning_rate"], lr_scheduler_type=cfg["lr_scheduler_type"],
        warmup_ratio=cfg["warmup_ratio"], logging_steps=cfg["logging_steps"],
        save_strategy=cfg["save_strategy"], bf16=True, gradient_checkpointing=True,
        dataset_text_field="text", packing=False,
    )
    # TRL renamed max_seq_length -> max_length around 1.0; pick whichever this version exposes,
    # and drop any kwargs this TRL version doesn't accept (defensive against API churn).
    params = inspect.signature(SFTConfig.__init__).parameters
    if "max_seq_length" in params:
        sft_kwargs["max_seq_length"] = cfg["max_seq_length"]
    elif "max_length" in params:
        sft_kwargs["max_length"] = cfg["max_seq_length"]
    sft_kwargs = {k: v for k, v in sft_kwargs.items() if k in params}
    sft = SFTConfig(**sft_kwargs)
    trainer = SFTTrainer(
        model=model, args=sft, train_dataset=train_ds, eval_dataset=eval_ds,
        processing_class=tokenizer, peft_config=peft_cfg,
    )
    trainer.train()
    trainer.save_model(cfg["output_dir"])
    tokenizer.save_pretrained(cfg["output_dir"])
    print(f"[done] adapter saved -> {cfg['output_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
