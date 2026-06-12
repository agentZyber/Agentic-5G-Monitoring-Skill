"""telco-bench — score any configured model on telecom knowledge (TeleQnA).

Offline benchmarking pack: no agent tools, just a loader + runner + CLI. The TeleQnA dataset
(10k telecom MCQs; arXiv:2310.15051) is **fetched on demand, never vendored** — see the dataset
registry for licence notes. TeleQnA is eval-only across the whole project: it must never enter
training data (docs/MODEL_PIPELINE.md contamination rules).

Usage:
    python -m zortenet.packs.telco_bench --data TeleQnA.txt --limit 200
    python -m zortenet.packs.telco_bench --provider ollama --model qwen2.5:7b
"""

from zortenet.packs.telco_bench.data import MCQItem, fetch_teleqna, load_teleqna
from zortenet.packs.telco_bench.runner import BenchResult, build_prompt, parse_choice, run_benchmark, to_markdown

PACK = {
    "name": "telco-bench",
    "description": "Benchmark the configured LLM on telecom knowledge (TeleQnA MCQs).",
    "connectors": [],
    "datasets": ["teleqna"],
    "system_prompt": "",  # not an agent pack; offline runner
}

__all__ = [
    "PACK",
    "MCQItem",
    "load_teleqna",
    "fetch_teleqna",
    "BenchResult",
    "build_prompt",
    "parse_choice",
    "run_benchmark",
    "to_markdown",
]
