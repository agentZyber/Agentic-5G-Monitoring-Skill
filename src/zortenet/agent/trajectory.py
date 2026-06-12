"""Trajectory capture — log every agent run in the training-data shape.

This is the Stage-1 hook that makes Stage 5 (the model pipeline) cheap: each run is appended as
one JSONL record whose ``messages`` field is exactly the chat+tool-call format described in
docs/MODEL_PIPELINE.md §2.2, so curation later is filtering, not reformatting.

Logging is opt-in via constructor or the ``ZORTENET_TRAJECTORIES`` environment variable —
a library must not write files by surprise. The app wiring enables it by default.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

_DISABLED_VALUES = {"0", "false", "off", "disabled", "none", ""}


class TrajectoryLogger:
    """Append-only JSONL writer, one file per UTC day."""

    def __init__(self, directory: str | Path, filename_prefix: str = "trajectories") -> None:
        # The directory is created lazily on first write — constructing a logger (e.g. at app
        # import time) must not touch the filesystem.
        self.directory = Path(directory)
        self.filename_prefix = filename_prefix

    def _current_file(self) -> Path:
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        return self.directory / f"{self.filename_prefix}-{day}.jsonl"

    def log(self, record: Dict[str, Any]) -> Path:
        record = {"ts": datetime.now(timezone.utc).isoformat(), **record}
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._current_file()
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return path

    @classmethod
    def from_env(cls, default_dir: Optional[str] = None) -> Optional["TrajectoryLogger"]:
        """Build a logger from ``ZORTENET_TRAJECTORIES``.

        Unset → use ``default_dir`` (``None`` means disabled). Set to a falsy value
        (``0/false/off/disabled``) → disabled. Otherwise → treat the value as the directory.
        """
        raw = os.getenv("ZORTENET_TRAJECTORIES")
        if raw is None:
            return cls(default_dir) if default_dir else None
        if raw.strip().lower() in _DISABLED_VALUES:
            return None
        return cls(raw)
