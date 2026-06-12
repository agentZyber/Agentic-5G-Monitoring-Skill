"""Telemetry replay — drive the event bus from recorded data, no live core required.

Turns CSV (5G3E-style time-series: one timestamp column + N metric columns) or JSONL
(NetworkEvent dicts / arbitrary records) into :class:`NetworkEvent`s published on an
:class:`~zortenet.core.bus.EventBus`. This is how the anomaly-detection demo and Stage-4/5
scenario generation run on a laptop: replayed traffic instead of a live testbed.

``speed`` controls pacing: 0 = as fast as possible (default, right for tests/batch),
1.0 = real time (sleeps between rows per the timestamp column), 10.0 = 10× compressed.
"""

from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from zortenet.core.bus import EventBus
from zortenet.core.events import EventDomain, NetworkEvent, Severity, _utcnow_iso


@dataclass
class ReplayReport:
    published: int = 0
    skipped: int = 0
    source: str = ""


def _row_to_event(
    row: Dict[str, str],
    source: str,
    domain: EventDomain,
    entity_col: Optional[str],
    ts_col: Optional[str],
    value_cols: Optional[Sequence[str]],
) -> Optional[NetworkEvent]:
    payload: Dict[str, Any] = {}
    columns = value_cols if value_cols else [c for c in row if c not in {entity_col, ts_col}]
    for col in columns:
        raw = row.get(col)
        if raw is None or raw == "":
            continue
        try:
            payload[col] = float(raw)
        except ValueError:
            payload[col] = raw
    if not payload:
        return None
    timestamp = (row.get(ts_col) if ts_col else None) or _utcnow_iso()
    return NetworkEvent(
        domain=domain,
        source=source,
        entity_id=row.get(entity_col) if entity_col else None,
        timestamp=timestamp,
        payload=payload,
        severity=Severity.INFO,
        event_type="replay",
    )


def replay_csv(
    bus: EventBus,
    path: str | Path,
    domain: EventDomain | str = EventDomain.RAN_KPI,
    entity_col: Optional[str] = None,
    ts_col: Optional[str] = None,
    value_cols: Optional[Sequence[str]] = None,
    speed: float = 0.0,
    max_events: Optional[int] = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> ReplayReport:
    """Replay a CSV of telemetry rows (5G3E-shaped) onto the bus."""
    path = Path(path)
    dom = EventDomain.coerce(domain)
    report = ReplayReport(source=path.name)
    previous_ts: Optional[float] = None

    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if max_events is not None and report.published >= max_events:
                break
            event = _row_to_event(row, path.name, dom, entity_col, ts_col, value_cols)
            if event is None:
                report.skipped += 1
                continue
            if speed > 0 and ts_col:
                try:
                    current = float(row.get(ts_col, ""))
                    if previous_ts is not None and current > previous_ts:
                        sleeper((current - previous_ts) / speed)
                    previous_ts = current
                except ValueError:
                    pass  # non-numeric timestamps: no pacing
            bus.publish(event)
            report.published += 1
    return report


def replay_jsonl(
    bus: EventBus,
    path: str | Path,
    max_events: Optional[int] = None,
) -> ReplayReport:
    """Replay JSONL of NetworkEvent dicts (or legacy location callbacks) onto the bus."""
    path = Path(path)
    report = ReplayReport(source=path.name)
    for line in path.read_text(encoding="utf-8").splitlines():
        if max_events is not None and report.published >= max_events:
            break
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            report.skipped += 1
            continue
        if "domain" in record:
            event = NetworkEvent.from_dict(record)
        elif "externalId" in record or "locationInfo" in record:
            event = NetworkEvent.from_location_event(record, source=path.name)
        else:
            report.skipped += 1
            continue
        bus.publish(event)
        report.published += 1
    return report
