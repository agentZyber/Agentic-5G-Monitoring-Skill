"""massive-iot — agentic massive-IoT / mMTC operations (ITU-R IMT-2030 "Massive Communication").

A 6G use-case pack that mirrors the template shape so one generalist agent (and one fine-tuned
adapter) learns a single reusable loop across domains:

    massive_iot_overview     → domain posture from the EventStore
    assess_iot_cell          → per-cell access KPIs + a health verdict
    correlate_iot_congestion → cross-cell correlation → SYSTEMIC vs CELL-SPECIFIC conclusion
    recommend_iot_action     → a structured, read-only recommendation (actuation routes through
                                the approval-gated `intent-to-network` pack; this pack never
                                changes state)

For massive IoT, the correlation that matters is cell-vs-network: bursts of devices cause
random-access (RACH) storms and attach-failure congestion. A storm confined to one cell points to
a localized device cluster, whereas congestion across a strict majority of cells points to a
network-wide signaling/RACH storm. Read-only; reasons over SIGNALING (RACH/attach) + optional
THROUGHPUT (small-data) events.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from corelab.agent.tools import ToolRegistry
from corelab.core.bus import EventStore
from corelab.core.events import EventDomain

PACK: Dict[str, Any] = {
    "name": "massive-iot",
    "description": "Agentic massive-IoT (mMTC) ops: RACH/attach-storm & access-congestion detection + cell-vs-network correlation (read-only).",
    "connectors": ["open5gs", "amarisoft"],
    "datasets": ["5g3e"],
    "system_prompt": (
        "You are a 5G/6G massive-IoT (mMTC) agent. Massive IoT bursts cause random-access (RACH) "
        "storms and attach-failure congestion that overwhelm a cell's signaling capacity. Gather "
        "evidence with the tools by reading each cell's access KPIs, then CORRELATE whether "
        "congestion is confined to one cell (a localized device cluster) or spread network-wide (a "
        "systemic signaling/RACH storm), and quote the numbers. You never change the network — "
        "recommend actions that a human applies via the intent approval flow."
    ),
}

RACH_STORM = 100.0          # rach_attempts >= this is a random-access storm
MAX_ATTACH_FAIL_RATE = 0.1  # attach_failures / attach_attempts above which a cell is congested


def _latest_by_entity(events: EventStore, domain: EventDomain, keys, window: int) -> Dict[str, float]:
    """Map entity_id -> the most recent numeric value for the first present key (newest first)."""
    out: Dict[str, float] = {}
    for e in events.recent(domain=domain, limit=window):  # recent() is newest-first
        if not e.entity_id or e.entity_id in out:
            continue
        for k in keys:
            v = e.payload.get(k)
            if isinstance(v, (int, float)):
                out[e.entity_id] = float(v)
                break
    return out


def _fail_rate(failures: Optional[float], attempts: Optional[float]) -> Optional[float]:
    """Attach failure ratio; None when attach attempts are unknown/zero."""
    if attempts is None or attempts <= 0:
        return None
    return (failures or 0.0) / attempts


def build_registry(store: Optional[EventStore] = None) -> ToolRegistry:
    events = store if store is not None else EventStore()
    reg = ToolRegistry()

    @reg.tool(
        name="massive_iot_overview",
        description="Massive-IoT access posture: cells reporting access KPIs and how many are congested (RACH storm or high attach-failure rate).",
        parameters={"type": "object", "properties": {
            "window": {"type": "integer", "description": "Recent events to inspect (default 500)"}}},
        tags=("massive-iot", "mmtc", "overview"),
    )
    def massive_iot_overview(window: int = 500) -> Dict[str, Any]:
        rach = _latest_by_entity(events, EventDomain.SIGNALING, ("rach_attempts",), window)
        attempts = _latest_by_entity(events, EventDomain.SIGNALING, ("attach_attempts",), window)
        failures = _latest_by_entity(events, EventDomain.SIGNALING, ("attach_failures",), window)
        cells = set(rach) | set(attempts) | set(failures)
        if not cells:
            return {"cells_reporting_access": 0, "note": "no massive-IoT access events in the store yet"}
        congested = []
        for c in cells:
            rate = _fail_rate(failures.get(c), attempts.get(c))
            if rach.get(c, 0.0) >= RACH_STORM or (rate is not None and rate > MAX_ATTACH_FAIL_RATE):
                congested.append(c)
        return {
            "cells_reporting_access": len(cells),
            "congested_cells": sorted(congested),
            "congested_count": len(congested),
        }

    @reg.tool(
        name="assess_iot_cell",
        description="Per-cell massive-IoT assessment: RACH attempts, attach attempts/failures and computed failure rate, with a health verdict (healthy / congested).",
        parameters={"type": "object", "properties": {
            "entity_id": {"type": "string", "description": "Cell id, e.g. '1'"},
            "window": {"type": "integer", "description": "Recent events to inspect (default 300)"}},
            "required": ["entity_id"]},
        tags=("massive-iot", "cell"),
    )
    def assess_iot_cell(entity_id: str, window: int = 300) -> Dict[str, Any]:
        rach = _latest_by_entity(events, EventDomain.SIGNALING, ("rach_attempts",), window).get(entity_id)
        attempts = _latest_by_entity(events, EventDomain.SIGNALING, ("attach_attempts",), window).get(entity_id)
        failures = _latest_by_entity(events, EventDomain.SIGNALING, ("attach_failures",), window).get(entity_id)
        if rach is None and attempts is None and failures is None:
            return {"entity_id": entity_id, "note": "no massive-IoT access events for this cell"}
        rate = _fail_rate(failures, attempts)
        tripped: List[str] = []
        if rach is not None and rach >= RACH_STORM:
            tripped.append("rach_storm")
        if rate is not None and rate > MAX_ATTACH_FAIL_RATE:
            tripped.append("attach_failure_rate")
        verdict = "congested" if tripped else "healthy"
        return {"entity_id": entity_id, "rach_attempts": rach, "attach_attempts": attempts,
                "attach_failures": failures, "failure_rate": round(rate, 4) if rate is not None else None,
                "verdict": verdict, "tripped": tripped}

    @reg.tool(
        name="correlate_iot_congestion",
        description=(
            "Correlate access congestion across every cell to tell a localized device cluster from a "
            "network-wide storm. Concludes SYSTEMIC (a strict majority of cells congested -> network-wide "
            "signaling/RACH storm) or cell-specific, with the per-cell evidence."
        ),
        parameters={"type": "object", "properties": {
            "window": {"type": "integer", "description": "Recent events to inspect (default 500)"}}},
        tags=("massive-iot", "correlation"),
    )
    def correlate_iot_congestion(window: int = 500) -> Dict[str, Any]:
        rach = _latest_by_entity(events, EventDomain.SIGNALING, ("rach_attempts",), window)
        attempts = _latest_by_entity(events, EventDomain.SIGNALING, ("attach_attempts",), window)
        failures = _latest_by_entity(events, EventDomain.SIGNALING, ("attach_failures",), window)
        names = set(rach) | set(attempts) | set(failures)
        if not names:
            return {"cells": [], "conclusion": "no access data", "note": "no massive-IoT access events in the store"}
        cells, congested = [], []
        for c in sorted(names):
            rate = _fail_rate(failures.get(c), attempts.get(c))
            r = rach.get(c, 0.0)
            is_congested = bool(r >= RACH_STORM or (rate is not None and rate > MAX_ATTACH_FAIL_RATE))
            if is_congested:
                congested.append(c)
            cells.append({"cell_id": c, "rach_attempts": r,
                          "failure_rate": round(rate, 4) if rate is not None else None,
                          "congested": is_congested})
        ratio = len(congested) / len(cells)
        conclusion = (
            f"SYSTEMIC: network-wide signaling/RACH storm ({len(congested)}/{len(cells)} cells congested)"
            if ratio > 0.5 else
            f"cell-specific: {len(congested)}/{len(cells)} cell(s) congested (localized device cluster)"
        )
        return {"cells": cells, "congested_cells": congested, "conclusion": conclusion}

    @reg.tool(
        name="recommend_iot_action",
        description=(
            "Recommend (read-only) access-congestion mitigations for congested cells: RACH backoff tuning, "
            "access-class barring, and a dedicated NB-IoT/RedCap carrier. The operator applies these via the "
            "intent-to-network approval flow; this tool changes nothing."
        ),
        parameters={"type": "object", "properties": {
            "window": {"type": "integer", "description": "Recent events to inspect (default 500)"}}},
        tags=("massive-iot", "recommendation"),
    )
    def recommend_iot_action(window: int = 500) -> Dict[str, Any]:
        corr = correlate_iot_congestion(window=window)
        recs = [
            {"cell_id": c,
             "actions": ["tune RACH backoff (extend backoff window)",
                         "enable access-class barring (ACB) for IoT classes",
                         "offload to a dedicated NB-IoT/RedCap carrier"],
             "apply_via": "intent-to-network (human approval required)"}
            for c in corr.get("congested_cells", [])
        ]
        return {"recommendations": recs, "count": len(recs),
                "note": "read-only proposal; no network change performed"}

    return reg
