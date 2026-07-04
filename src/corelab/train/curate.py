"""G1 — trajectory curation: outcome filters, dedup, contamination guard, split.

Input is what :class:`~corelab.agent.trajectory.TrajectoryLogger` (and the outcome-stamping
TeleAgentBench runner) writes. Every drop is counted by reason — no silent filtering.

Contamination rules (hard, from MODEL_PIPELINE.md §2.3): TeleQnA text and the public bench
scenarios' asks must never enter training data; the guard rejects any record whose messages
contain a forbidden text.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

_WS = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WS.sub(" ", (text or "").lower()).strip()


class ContaminationGuard:
    """Rejects records containing any forbidden text (normalized substring match)."""

    def __init__(self, forbidden_texts: Sequence[str], min_length: int = 20) -> None:
        self.forbidden = [
            _normalize(t) for t in forbidden_texts if len(_normalize(t)) >= min_length
        ]

    @classmethod
    def default(cls, teleqna_path: Optional[str | Path] = None) -> "ContaminationGuard":
        """Bench-scenario asks always; TeleQnA questions too when the local file exists."""
        from corelab.bench.teleagent import builtin_scenarios, sixg_scenarios

        forbidden: List[str] = [s.ask for s in builtin_scenarios()] + [s.ask for s in sixg_scenarios()]
        path = Path(teleqna_path) if teleqna_path else Path("datasets/TeleQnA.txt")
        if path.exists():
            try:
                from corelab.packs.telco_bench.data import load_teleqna

                items, _ = load_teleqna(path)
                forbidden.extend(item.question for item in items)
            except Exception:
                pass  # unreadable TeleQnA: guard still covers bench asks
        return cls(forbidden)

    def is_contaminated(self, record: Dict[str, Any]) -> bool:
        blob = _normalize(
            " ".join(
                str(m.get("content", "")) for m in record.get("messages", []) if isinstance(m, dict)
            )
        )
        return any(f in blob for f in self.forbidden)


def looks_non_english(text: str, threshold: float = 0.15) -> bool:
    """True if a meaningful fraction of letters are non-Latin (Thai, CJK, Cyrillic, …).

    Catches teacher language-drift (e.g. a model answering in Thai despite an English prompt) —
    a real failure mode seen in live capture that contamination/outcome filters don't flag.
    """
    letters = [c for c in (text or "") if c.isalpha()]
    if not letters:
        return False
    non_ascii = sum(1 for c in letters if ord(c) > 127)
    return non_ascii / len(letters) > threshold


@dataclass
class CurationConfig:
    require_outcome_success: bool = False  # strict mode: only judge-stamped successes
    drop_stopped_early: bool = True
    drop_tool_errors: bool = True
    require_english: bool = False          # drop trajectories whose answer drifted off-language
    guard: Optional[ContaminationGuard] = None


@dataclass
class CurationReport:
    files: int = 0
    scanned: int = 0
    kept: int = 0
    dropped: Counter = field(default_factory=Counter)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "files": self.files,
            "scanned": self.scanned,
            "kept": self.kept,
            "dropped": dict(self.dropped),
        }


def _fingerprint(record: Dict[str, Any]) -> str:
    """Dedup key: the user ask + the ordered tool-call sequence."""
    user = next(
        (m.get("content", "") for m in record.get("messages", []) if m.get("role") == "user"), ""
    )
    tools: List[str] = []
    for message in record.get("messages", []):
        for tc in message.get("tool_calls") or []:
            fn = tc.get("function") or {}
            tools.append(f"{fn.get('name')}({json.dumps(fn.get('arguments'), sort_keys=True, default=str)})")
    return hashlib.sha256(_normalize(user + "|" + ";".join(tools)).encode()).hexdigest()


def _drop_reason(record: Dict[str, Any], config: CurationConfig) -> Optional[str]:
    messages = record.get("messages")
    if not isinstance(messages, list) or len(messages) < 2:
        return "schema:no-messages"
    roles = [m.get("role") for m in messages if isinstance(m, dict)]
    if "user" not in roles:
        return "schema:no-user-message"
    if not (record.get("answer") or "").strip():
        return "empty-answer"
    if config.drop_stopped_early and record.get("stopped_early"):
        return "stopped-early"
    if config.drop_tool_errors and record.get("tool_errors", 0) > 0:
        return "tool-errors"
    outcome = record.get("outcome")
    if outcome == "failure":
        return "outcome-failure"
    if config.require_outcome_success and outcome != "success":
        return "outcome-not-stamped"  # strict mode: heuristic acceptance is off
    if config.guard and config.guard.is_contaminated(record):
        return "contaminated"
    if config.require_english and looks_non_english(record.get("answer", "")):
        return "non-english"
    return None


def curate_trajectories(
    source: str | Path | Iterable[Path],
    config: Optional[CurationConfig] = None,
) -> Tuple[List[Dict[str, Any]], CurationReport]:
    """Curate trajectory JSONL files (a directory, one path, or an iterable of paths)."""
    config = config or CurationConfig()
    if isinstance(source, (str, Path)):
        root = Path(source)
        paths = sorted(root.glob("*.jsonl")) if root.is_dir() else [root]
    else:
        paths = list(source)

    report = CurationReport(files=len(paths))
    kept: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for path in paths:
        if not Path(path).exists():
            continue
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            report.scanned += 1
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                report.dropped["schema:bad-json"] += 1
                continue
            reason = _drop_reason(record, config)
            if reason:
                report.dropped[reason] += 1
                continue
            fp = _fingerprint(record)
            if fp in seen:
                report.dropped["duplicate"] += 1
                continue
            seen.add(fp)
            kept.append(
                {
                    "messages": record["messages"],
                    "meta": {
                        **(record.get("meta") or {}),
                        "source": "trajectory",
                        "outcome": record.get("outcome"),
                        "provider": record.get("provider"),
                    },
                }
            )
            report.kept += 1
    return kept, report


def split_train_val(
    records: List[Dict[str, Any]], val_fraction: float = 0.05, seed: int = 42
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Deterministic (seeded) shuffle + split; at least one val record when any exist."""
    shuffled = list(records)
    random.Random(seed).shuffle(shuffled)
    n_val = max(1, int(len(shuffled) * val_fraction)) if shuffled else 0
    return shuffled[n_val:], shuffled[:n_val]


def write_jsonl(records: List[Dict[str, Any]], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    return path
