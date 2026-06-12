"""Mixture assembly — combine data buckets by ratio, loudly honest about shortfalls.

Two non-negotiables from MODEL_PIPELINE.md:
- **No silent caps**: if a bucket can't supply its share, the report says exactly what was
  requested vs used.
- **The general-data warning**: training without a general-instruction slice is the classic
  catastrophic-forgetting mistake — its absence is a named warning, not a footnote.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_RATIOS = {
    "trajectory": 0.40,
    "synth-intent": 0.20,
    "synth-diagnosis": 0.15,
    "general": 0.25,
}


@dataclass
class MixtureReport:
    total: int = 0
    per_bucket: Dict[str, Dict[str, int]] = field(default_factory=dict)  # requested/available/used
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"total": self.total, "per_bucket": self.per_bucket, "warnings": self.warnings}


def assemble_mixture(
    buckets: Dict[str, List[Dict[str, Any]]],
    ratios: Optional[Dict[str, float]] = None,
    total: Optional[int] = None,
    seed: int = 42,
) -> Tuple[List[Dict[str, Any]], MixtureReport]:
    """Sample each bucket toward its ratio share of ``total`` (default: largest feasible)."""
    ratios = ratios or DEFAULT_RATIOS
    rng = random.Random(seed)
    report = MixtureReport()

    if abs(sum(ratios.values()) - 1.0) > 1e-6:
        report.warnings.append(f"ratios sum to {sum(ratios.values()):.3f}, not 1.0")

    # Default total: the largest mixture every non-empty bucket can support at its ratio.
    if total is None:
        feasible = [
            int(len(buckets.get(name, [])) / ratio)
            for name, ratio in ratios.items()
            if ratio > 0 and buckets.get(name)
        ]
        total = min(feasible) if feasible else 0

    mixed: List[Dict[str, Any]] = []
    for name, ratio in ratios.items():
        available = list(buckets.get(name, []))
        requested = round(total * ratio)
        used = min(requested, len(available))
        if used < requested:
            report.warnings.append(
                f"bucket '{name}': requested {requested} but only {used} available — "
                "NOT silently rebalanced; supply more data or adjust ratios"
            )
        rng.shuffle(available)
        mixed.extend(available[:used])
        report.per_bucket[name] = {
            "requested": requested,
            "available": len(buckets.get(name, [])),
            "used": used,
        }

    if not buckets.get("general"):
        report.warnings.append(
            "NO GENERAL-INSTRUCTION DATA: training on domain-only data risks catastrophic "
            "forgetting of general tool-calling (MODEL_PIPELINE §2.2). Provide a 'general' "
            "bucket (e.g. an open instruct set) before G2."
        )

    rng.shuffle(mixed)
    report.total = len(mixed)
    return mixed, report
