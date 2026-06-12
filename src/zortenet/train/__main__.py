"""CLI: python -m zortenet.train {status|g0|curate|synth|mixture|config|card}

The gate ledger is enforced at every step — e.g. `config` refuses until G1 has passed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from zortenet.train.card import generate_model_card
from zortenet.train.configs import LAUNCHER_NOTE, build_config, write_config
from zortenet.train.curate import (
    ContaminationGuard,
    CurationConfig,
    curate_trajectories,
    split_train_val,
    write_jsonl,
)
from zortenet.train.g0 import run_g0
from zortenet.train.gates import GateError, TrainingGates
from zortenet.train.mixture import assemble_mixture
from zortenet.train.synth import synth_diagnosis_pairs, synth_intent_pairs


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="zortenet-train", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show the G0→G3 gate ledger.")

    g0_parser = sub.add_parser("g0", help="Run the baseline matrix (needs a live provider).")
    g0_parser.add_argument("--provider", default=None)
    g0_parser.add_argument("--model", default=None)
    g0_parser.add_argument("--target", type=float, default=0.9)
    g0_parser.add_argument("--teleqna", default="datasets/TeleQnA.txt")
    g0_parser.add_argument("--limit", type=int, default=100)
    g0_parser.add_argument("--kb-dir", default="datasets/kb")

    curate_parser = sub.add_parser("curate", help="Curate trajectory JSONL into a dataset.")
    curate_parser.add_argument("--in", dest="source", default="trajectories")
    curate_parser.add_argument("--out", default="training/dataset")
    curate_parser.add_argument("--strict", action="store_true",
                               help="Keep only judge-stamped successes (outcome == success).")

    synth_parser = sub.add_parser("synth", help="Generate machine-validated synthetic pairs.")
    synth_parser.add_argument("--intents", type=int, default=200)
    synth_parser.add_argument("--diagnosis", type=int, default=150)
    synth_parser.add_argument("--seed", type=int, default=42)
    synth_parser.add_argument("--out", default="training/dataset")

    mix_parser = sub.add_parser("mixture", help="Assemble the training mixture (marks G1).")
    mix_parser.add_argument("--dataset-dir", default="training/dataset")
    mix_parser.add_argument("--general", default=None,
                            help="Path to a general-instruction JSONL (strongly recommended).")

    config_parser = sub.add_parser("config", help="Emit a LoRA-SFT config (requires G1 passed).")
    config_parser.add_argument("--preset", default="qwen2.5-7b")

    card_parser = sub.add_parser("card", help="Generate the (draft) hedged model card.")
    card_parser.add_argument("--name", default="zortenet-netops-lora")
    card_parser.add_argument("--base", default="(base model)")

    args = parser.parse_args(argv)
    gates = TrainingGates()

    if args.command == "status":
        for gate, entry in gates.status().items():
            mark = "✅" if entry["passed"] else "—"
            print(f"{mark} {gate}: {entry['meaning']}")
        return 0

    if args.command == "g0":
        from zortenet.llm import get_provider
        from zortenet.memory.knowledge_base import KnowledgeBase

        kwargs = {"model": args.model} if args.model else {}
        provider = get_provider(args.provider, **kwargs)
        if not provider.is_available():
            print(f"provider '{provider.name}' unavailable — start it first.", file=sys.stderr)
            return 2
        items = None
        if Path(args.teleqna).exists():
            from zortenet.packs.telco_bench.data import load_teleqna

            items, _ = load_teleqna(args.teleqna)
        kb = KnowledgeBase()
        kb.ingest_dir(args.kb_dir)
        label = f"{provider.name}:{getattr(provider, 'model', '')}"
        report = run_g0([(label, provider)], kb=kb, teleqna_items=items,
                        teleqna_limit=args.limit, target_success=args.target)
        print(report.to_markdown())
        gap, verdict = report.decide_gap()
        gates.record("G0", passed=gap, evidence={"verdict": verdict,
                                                 "rows": [r.to_dict() for r in report.rows]})
        return 0

    if args.command == "curate":
        config = CurationConfig(
            require_outcome_success=args.strict, guard=ContaminationGuard.default()
        )
        records, report = curate_trajectories(args.source, config)
        out = Path(args.out)
        write_jsonl(records, out / "trajectories.curated.jsonl")
        print(json.dumps(report.to_dict(), indent=2))
        if report.kept == 0:
            print("0 trajectories kept — run the agent/bench with trajectory logging first.",
                  file=sys.stderr)
        return 0

    if args.command == "synth":
        out = Path(args.out)
        intents = synth_intent_pairs(args.intents, seed=args.seed)
        diagnosis = synth_diagnosis_pairs(args.diagnosis, seed=args.seed)
        write_jsonl(intents, out / "synth-intent.jsonl")
        write_jsonl(diagnosis, out / "synth-diagnosis.jsonl")
        print(f"wrote {len(intents)} intent pairs, {len(diagnosis)} diagnosis pairs → {out}/")
        return 0

    if args.command == "mixture":
        dataset_dir = Path(args.dataset_dir)

        def _load(name: str):
            path = dataset_dir / name
            if not path.exists():
                return []
            return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]

        buckets = {
            "trajectory": _load("trajectories.curated.jsonl"),
            "synth-intent": _load("synth-intent.jsonl"),
            "synth-diagnosis": _load("synth-diagnosis.jsonl"),
            "general": (
                [json.loads(l) for l in Path(args.general).read_text().splitlines() if l.strip()]
                if args.general and Path(args.general).exists()
                else []
            ),
        }
        mixed, report = assemble_mixture(buckets)
        train, val = split_train_val(mixed)
        write_jsonl(train, dataset_dir / "train.jsonl")
        write_jsonl(val, dataset_dir / "val.jsonl")
        print(json.dumps(report.to_dict(), indent=2))
        ready = report.total > 0 and not any("NO GENERAL" in w for w in report.warnings)
        gates.record(
            "G1",
            passed=ready,
            evidence={"mixture": report.to_dict(), "train": len(train), "val": len(val)},
        )
        if not ready:
            print("G1 NOT passed (see warnings above).", file=sys.stderr)
        return 0

    if args.command == "config":
        try:
            gates.require("G2")  # everything before G2 (G0, G1) must have passed
        except GateError as exc:
            print(f"blocked: {exc}", file=sys.stderr)
            return 3
        config = build_config(args.preset)
        path = write_config(config)
        print(f"wrote {path}")
        print(LAUNCHER_NOTE)
        return 0

    if args.command == "card":
        print(generate_model_card(gates, model_name=args.name, base_model=args.base))
        return 0

    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
