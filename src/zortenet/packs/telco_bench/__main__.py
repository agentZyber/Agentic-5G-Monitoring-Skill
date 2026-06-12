"""CLI: python -m zortenet.packs.telco_bench [--data PATH] [--provider ollama] [--model M] [--limit N]"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from zortenet.llm import get_provider
from zortenet.packs.telco_bench.data import TELEQNA_URL, fetch_teleqna, load_teleqna
from zortenet.packs.telco_bench.runner import run_benchmark, to_markdown


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="telco-bench", description="Score a model on TeleQnA telecom MCQs."
    )
    parser.add_argument(
        "--data",
        default="datasets/TeleQnA.txt",
        help="Path to TeleQnA.txt (downloaded on first run if missing).",
    )
    parser.add_argument("--provider", default=None, help="ollama (default) | openai | anthropic")
    parser.add_argument("--model", default=None, help="Model name for the provider.")
    parser.add_argument("--limit", type=int, default=None, help="Question cap (default: all).")
    parser.add_argument("--out", default=None, help="Write the markdown report here.")
    parser.add_argument("--json-out", default=None, help="Write raw results JSON here.")
    args = parser.parse_args(argv)

    data_path = Path(args.data)
    if not data_path.exists():
        print(f"TeleQnA not found at {data_path}; fetching from {TELEQNA_URL} ...")
        fetch_teleqna(data_path)
    items, skipped = load_teleqna(data_path)
    print(f"Loaded {len(items)} questions ({skipped} skipped).")

    kwargs = {"model": args.model} if args.model else {}
    provider = get_provider(args.provider, **kwargs)
    if not provider.is_available():
        print(
            f"Provider '{provider.name}' is not available "
            f"(is the server running / key set?). Aborting.",
            file=sys.stderr,
        )
        return 2

    def progress(done: int, total: int) -> None:
        if done % 25 == 0 or done == total:
            print(f"  {done}/{total}", file=sys.stderr)

    result = run_benchmark(provider, items, limit=args.limit, progress=progress)
    report = to_markdown(result)
    print("\n" + report)

    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"\nreport written to {args.out}")
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(result.__dict__, indent=2, default=str), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
