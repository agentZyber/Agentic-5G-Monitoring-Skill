"""MCQ benchmark runner: prompt → parse choice → score (overall + per category)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from zortenet.llm.base import LLMProvider
from zortenet.packs.telco_bench.data import MCQItem

SYSTEM_PROMPT = (
    "You are answering telecommunications multiple-choice questions. "
    "Reply with ONLY the number of the correct option. No explanation."
)

_FIRST_INT = re.compile(r"\d+")


def build_prompt(item: MCQItem) -> str:
    lines = [item.question.strip(), ""]
    lines += [f"{i + 1}. {opt}" for i, opt in enumerate(item.options)]
    lines += ["", f"Answer with the option number (1-{item.n_options}) only."]
    return "\n".join(lines)


def parse_choice(text: str, n_options: int) -> Optional[int]:
    """Extract the chosen option as a 0-based index; None if unparseable/out of range."""
    for match in _FIRST_INT.finditer(text or ""):
        value = int(match.group())
        if 1 <= value <= n_options:
            return value - 1
        return None  # a number, but not a valid option -> treat as unparseable
    return None


@dataclass
class BenchResult:
    total: int = 0
    correct: int = 0
    unparsed: int = 0
    by_category: Dict[str, Dict[str, int]] = field(default_factory=dict)
    model: str = ""
    provider: str = ""

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0

    def category_accuracy(self, category: str) -> float:
        stats = self.by_category.get(category, {})
        return stats.get("correct", 0) / stats["total"] if stats.get("total") else 0.0


def run_benchmark(
    provider: LLMProvider,
    items: List[MCQItem],
    limit: Optional[int] = None,
    progress: Optional[Callable[[int, int], None]] = None,
) -> BenchResult:
    subset = items[:limit] if limit else items
    result = BenchResult(
        model=str(getattr(provider, "model", "")),
        provider=provider.name,
    )
    for index, item in enumerate(subset, start=1):
        response = provider.chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_prompt(item)},
            ]
        )
        choice = parse_choice(response.content, item.n_options)

        result.total += 1
        category = item.category or "uncategorized"
        stats = result.by_category.setdefault(category, {"total": 0, "correct": 0})
        stats["total"] += 1
        if choice is None:
            result.unparsed += 1
        elif choice == item.answer_index:
            result.correct += 1
            stats["correct"] += 1

        if progress:
            progress(index, len(subset))
    return result


def to_markdown(result: BenchResult) -> str:
    lines = [
        f"# telco-bench — TeleQnA",
        "",
        f"- **Model:** `{result.model or 'unknown'}` (provider: {result.provider})",
        f"- **Questions:** {result.total}",
        f"- **Accuracy:** **{result.accuracy:.1%}**  (unparsed answers: {result.unparsed})",
        "",
        "| Category | Accuracy | n |",
        "|---|---|---|",
    ]
    for category in sorted(result.by_category):
        stats = result.by_category[category]
        lines.append(
            f"| {category} | {result.category_accuracy(category):.1%} | {stats['total']} |"
        )
    lines.append("")
    lines.append(
        "_TeleQnA is eval-only across this project (never used for training; "
        "see docs/MODEL_PIPELINE.md contamination rules)._"
    )
    return "\n".join(lines)
