"""TeleQnA loading & parsing.

TeleQnA ships as one JSON object keyed ``"question 0" ... "question 9999"``; each entry holds
``question``, ``option 1..N``, ``answer`` (``"option 3: <text>"``), ``explanation``, ``category``.
The loader normalizes that into :class:`MCQItem` records and skips (counting) malformed entries.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

# Public dataset file on Hugging Face (see registry entry 'teleqna' for licence notes).
TELEQNA_URL = "https://huggingface.co/datasets/netop/TeleQnA/resolve/main/TeleQnA.txt"

_OPTION_KEY = re.compile(r"^option\s*(\d+)$", re.IGNORECASE)
_ANSWER_INDEX = re.compile(r"option\s*(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class MCQItem:
    qid: str
    question: str
    options: Tuple[str, ...]
    answer_index: int  # 0-based
    category: str = ""

    @property
    def n_options(self) -> int:
        return len(self.options)


def _parse_entry(qid: str, entry: Dict[str, Any]) -> Optional[MCQItem]:
    question = entry.get("question")
    answer = entry.get("answer", "")
    if not question or not isinstance(answer, str):
        return None

    numbered: List[Tuple[int, str]] = []
    for key, value in entry.items():
        m = _OPTION_KEY.match(str(key).strip())
        if m and value is not None:
            numbered.append((int(m.group(1)), str(value)))
    if len(numbered) < 2:
        return None
    numbered.sort(key=lambda pair: pair[0])
    options = tuple(text for _, text in numbered)

    m = _ANSWER_INDEX.search(answer)
    if not m:
        return None
    answer_index = int(m.group(1)) - 1
    if not 0 <= answer_index < len(options):
        return None

    return MCQItem(
        qid=qid,
        question=str(question),
        options=options,
        answer_index=answer_index,
        category=str(entry.get("category", "")),
    )


def load_teleqna_dict(data: Dict[str, Any]) -> Tuple[List[MCQItem], int]:
    """Parse the raw TeleQnA JSON object; returns (items, skipped_count)."""
    items: List[MCQItem] = []
    skipped = 0
    for qid, entry in data.items():
        if not isinstance(entry, dict):
            skipped += 1
            continue
        item = _parse_entry(str(qid), entry)
        if item is None:
            skipped += 1
        else:
            items.append(item)
    return items, skipped


def load_teleqna(path: str | Path) -> Tuple[List[MCQItem], int]:
    """Load TeleQnA from a local JSON file (the downloaded ``TeleQnA.txt``)."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return load_teleqna_dict(raw)


def fetch_teleqna(
    dest: str | Path, url: str = TELEQNA_URL, timeout: int = 60
) -> Path:
    """Download TeleQnA to ``dest`` (skipped if it already exists). Check the licence on the
    HF card before redistribution — this toolkit only fetches, never vendors."""
    dest = Path(dest)
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    return dest
