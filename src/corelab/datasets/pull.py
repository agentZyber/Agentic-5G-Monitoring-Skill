"""Registry-driven dataset acquisition.

Strategy per dataset, honest by design:
- **auto**: small/public files are downloaded directly (TeleQnA).
- **guide**: oversized or licence-sensitive datasets (Tele-Data 12 GB, 5G3E ~1.1 TB with no
  LICENSE file, HF-hosted corpora) are NOT blind-downloaded — ``pull`` prints the source,
  the licence flag from the registry, and the exact command/URL to fetch what you need.

Nothing is ever vendored into the repo; licences stay with their sources.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from corelab.datasets.registry import Dataset, get_dataset

DEFAULT_ROOT = "datasets"


def _guide_for(ds: Dataset) -> str:
    lines = [
        f"{ds.name}: manual/selective fetch (size: {ds.size}; licence: {ds.license}).",
        f"  source: {ds.source}",
    ]
    if ds.source.startswith("hf:"):
        repo = ds.source[3:]
        lines += [
            f"  browse:   https://huggingface.co/datasets/{repo}",
            f"  CLI:      huggingface-cli download {repo} --repo-type dataset --local-dir <dest>",
            "  tip:      pull only the subset you need; put KB extracts under datasets/kb/",
        ]
    else:
        lines += [f"  visit:    {ds.source}"]
    if ds.note:
        lines += [f"  ⚠ note:   {ds.note}"]
    return "\n".join(lines)


def pull(name: str, root: str | Path = DEFAULT_ROOT) -> Dict[str, str]:
    """Acquire (or explain how to acquire) a dataset; returns a status dict."""
    ds = get_dataset(name)
    root = Path(root)

    if ds.name == "TeleQnA":
        from corelab.packs.telco_bench.data import fetch_teleqna

        dest = root / "TeleQnA.txt"
        path = fetch_teleqna(dest)
        return {
            "dataset": ds.name,
            "action": "downloaded" if path.exists() else "failed",
            "path": str(path),
            "license": ds.license,
            "reminder": "TeleQnA is eval-only project-wide (never train on it).",
        }

    return {
        "dataset": ds.name,
        "action": "guide",
        "license": ds.license,
        "guide": _guide_for(ds),
    }
