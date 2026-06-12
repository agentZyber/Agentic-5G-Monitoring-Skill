"""CLI: python -m zortenet.bench [--provider ollama] [--model M] [--out report.md]"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from zortenet.bench.teleagent import builtin_scenarios, run_teleagent_bench, to_markdown
from zortenet.llm import get_provider


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="teleagent-bench",
        description="Scenario-based agentic-telecom benchmark (programmatic, state-based judges).",
    )
    parser.add_argument("--provider", default=None, help="ollama (default) | vllm | openai | anthropic")
    parser.add_argument("--model", default=None)
    parser.add_argument("--out", default=None, help="Write the markdown report here.")
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args(argv)

    kwargs = {"model": args.model} if args.model else {}
    provider = get_provider(args.provider, **kwargs)
    if not provider.is_available():
        print(
            f"Provider '{provider.name}' is not available (server running / key set?). Aborting.",
            file=sys.stderr,
        )
        return 2

    def progress(scenario_id: str, ok: bool) -> None:
        print(f"  {'✅' if ok else '❌'} {scenario_id}", file=sys.stderr)

    run = run_teleagent_bench(provider, scenarios=builtin_scenarios(), progress=progress)
    report = to_markdown(run)
    print("\n" + report)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps([r.to_dict() for r in run.reports], indent=2), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
