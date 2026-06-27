"""uav-ops — agentic UAV/aerial connectivity operations (ITU-R IMT-2030 "Ubiquitous Connectivity").

A 6G use-case pack mirroring the energy-agent TEMPLATE shape, so one generalist agent (and one
fine-tuned adapter) reuses a single loop across domains:

    <uc>_overview      → domain posture from the EventStore
    assess_<entity>    → per-entity KPIs + a health verdict
    correlate_<uc>     → cross-signal correlation → SYSTEMIC vs ENTITY-SPECIFIC conclusion
    recommend_<uc>_... → a structured, read-only recommendation (actuation routes through
                          the approval-gated `intent-to-network` pack; these packs never change state)

For aerial UEs, the correlation that matters is UE-specific vs cell-wide interference: drones fly
into line-of-sight of many cells, so they both *see* and *cause* strong uplink interference and tend
to thrash between cells. A single bad aerial UE is a UE-specific problem; a strict majority of aerial
UEs degraded points to cell-wide aerial interference (line-of-sight) needing a coverage fix.
Read-only; reasons over RAN_KPI + LOCATION events.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from zortenet.agent.tools import ToolRegistry
from zortenet.core.bus import EventStore
from zortenet.core.events import EventDomain

PACK: Dict[str, Any] = {
    "name": "uav-ops",
    "description": "Agentic UAV/aerial ops: aerial-UE uplink interference & handover-thrash detection + UE-vs-cell correlation (read-only).",
    "connectors": ["amarisoft", "prometheus"],
    "datasets": ["5g3e"],
    "system_prompt": (
        "You are a 5G/6G UAV/aerial connectivity agent. Aerial UEs (drones) fly into line-of-sight "
        "of many cells, so they both see and cause strong uplink interference and tend to thrash "
        "between cells via repeated handovers. Read each aerial UE's radio and mobility with the "
        "tools, then CORRELATE whether degradation is UE-specific or cell-wide aerial interference "
        "(line-of-sight), and always quote the numbers. You never change the network — recommend "
        "actions that a human applies via the intent approval flow."
    ),
}

HIGH_UL_INTERFERENCE_DB = -100.0   # ul_interference_db >= this is high uplink interference
AERIAL_ALT_M = 50.0                # altitude_m above which a UE is "aerial"
HANDOVER_THRASH_CELLS = 4          # distinct cells in window => handover thrashing


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


def _distinct_cells(events: EventStore, entity_id: str, window: int) -> List[str]:
    """Distinct cells a UE visited, from its LOCATION events (newest first), order-preserving."""
    history = events.recent(domain=EventDomain.LOCATION, entity_id=entity_id, limit=window)
    cells = [e.payload.get("cell_id") for e in history if e.payload.get("cell_id")]
    return list(dict.fromkeys(cells))


def build_registry(store: Optional[EventStore] = None) -> ToolRegistry:
    events = store if store is not None else EventStore()
    reg = ToolRegistry()

    @reg.tool(
        name="uav_overview",
        description="Aerial posture: count aerial UEs (by altitude) and how many show high uplink interference or handover thrash.",
        parameters={"type": "object", "properties": {
            "window": {"type": "integer", "description": "Recent events to inspect (default 500)"}}},
        tags=("uav", "aerial", "overview"),
    )
    def uav_overview(window: int = 500) -> Dict[str, Any]:
        alt = _latest_by_entity(events, EventDomain.RAN_KPI, ("altitude_m",), window)
        aerial = [u for u, a in alt.items() if a >= AERIAL_ALT_M]
        if not aerial:
            return {"aerial_ues": 0, "note": "no aerial-UE RAN_KPI events in the store yet"}
        interf = _latest_by_entity(events, EventDomain.RAN_KPI, ("ul_interference_db",), window)
        high_interf = [u for u in aerial if interf.get(u, float("-inf")) >= HIGH_UL_INTERFERENCE_DB]
        thrash = [u for u in aerial if len(_distinct_cells(events, u, window)) >= HANDOVER_THRASH_CELLS]
        return {
            "aerial_ues": len(aerial),
            "aerial_ue_ids": sorted(aerial),
            "high_ul_interference": sorted(high_interf),
            "handover_thrash": sorted(thrash),
        }

    @reg.tool(
        name="assess_aerial_ue",
        description="Per-UE aerial assessment: latest uplink interference / SINR / CQI / altitude, distinct cells visited, handover-thrash flag and a verdict (nominal / degraded).",
        parameters={"type": "object", "properties": {
            "entity_id": {"type": "string", "description": "Aerial UE external id, e.g. 'uav1'"},
            "window": {"type": "integer", "description": "Recent events to inspect (default 300)"}},
            "required": ["entity_id"]},
        tags=("uav", "aerial"),
    )
    def assess_aerial_ue(entity_id: str, window: int = 300) -> Dict[str, Any]:
        interf = _latest_by_entity(events, EventDomain.RAN_KPI, ("ul_interference_db",), window).get(entity_id)
        sinr = _latest_by_entity(events, EventDomain.RAN_KPI, ("sinr",), window).get(entity_id)
        cqi = _latest_by_entity(events, EventDomain.RAN_KPI, ("cqi",), window).get(entity_id)
        altitude = _latest_by_entity(events, EventDomain.RAN_KPI, ("altitude_m",), window).get(entity_id)
        cells = _distinct_cells(events, entity_id, window)
        if interf is None and sinr is None and cqi is None and altitude is None and not cells:
            return {"entity_id": entity_id, "note": "no aerial/radio events for this UE"}
        thrash = len(cells) >= HANDOVER_THRASH_CELLS
        high_interf = interf is not None and interf >= HIGH_UL_INTERFERENCE_DB
        verdict = "degraded" if (high_interf or thrash) else "nominal"
        return {
            "entity_id": entity_id,
            "ul_interference_db": interf,
            "sinr": sinr,
            "cqi": cqi,
            "altitude_m": altitude,
            "aerial": altitude is not None and altitude >= AERIAL_ALT_M,
            "cells_visited": cells,
            "distinct_cells": len(cells),
            "handover_thrash": thrash,
            "high_ul_interference": high_interf,
            "verdict": verdict,
        }

    @reg.tool(
        name="correlate_uav_coverage",
        description=(
            "Correlate uplink interference across aerial UEs. Concludes whether degradation is SYSTEMIC "
            "(a strict majority of aerial UEs see high uplink interference -> cell-wide aerial interference "
            "from line-of-sight) or UE-specific, with the per-UE evidence."
        ),
        parameters={"type": "object", "properties": {
            "window": {"type": "integer", "description": "Recent events to inspect (default 500)"}}},
        tags=("uav", "correlation"),
    )
    def correlate_uav_coverage(window: int = 500) -> Dict[str, Any]:
        alt = _latest_by_entity(events, EventDomain.RAN_KPI, ("altitude_m",), window)
        aerial = sorted(u for u, a in alt.items() if a >= AERIAL_ALT_M)
        if not aerial:
            return {"ues": [], "conclusion": "no aerial-UE data", "note": "no aerial RAN_KPI events in the store"}
        interf = _latest_by_entity(events, EventDomain.RAN_KPI, ("ul_interference_db",), window)
        ues, degraded = [], []
        for u in aerial:
            ui = interf.get(u)
            cells = _distinct_cells(events, u, window)
            thrash = len(cells) >= HANDOVER_THRASH_CELLS
            high_interf = ui is not None and ui >= HIGH_UL_INTERFERENCE_DB
            is_degraded = bool(high_interf or thrash)
            if is_degraded:
                degraded.append(u)
            ues.append({"entity_id": u, "ul_interference_db": ui, "distinct_cells": len(cells),
                        "handover_thrash": thrash, "high_ul_interference": high_interf,
                        "degraded": is_degraded})
        high_count = sum(1 for x in ues if x["high_ul_interference"])
        ratio = high_count / len(ues)
        conclusion = (
            f"SYSTEMIC: cell-wide aerial interference (line-of-sight) — {high_count}/{len(ues)} aerial UEs see high uplink interference"
            if ratio > 0.5 else
            f"UE-specific: {len(degraded)}/{len(ues)} aerial UE(s) degraded"
        )
        return {"ues": ues, "degraded": degraded, "conclusion": conclusion}

    @reg.tool(
        name="recommend_uav_action",
        description=(
            "Recommend (read-only) aerial-connectivity actions: antenna down-tilt or a dedicated aerial "
            "cell/beam for cell-wide interference, and mobility-robustness tuning for thrashing UEs. The "
            "operator applies these via the intent-to-network approval flow; this tool changes nothing."
        ),
        parameters={"type": "object", "properties": {
            "window": {"type": "integer", "description": "Recent events to inspect (default 500)"}}},
        tags=("uav", "recommendation"),
    )
    def recommend_uav_action(window: int = 500) -> Dict[str, Any]:
        corr = correlate_uav_coverage(window=window)
        recs: List[Dict[str, Any]] = []
        if "SYSTEMIC" in corr.get("conclusion", ""):
            recs.append({
                "scope": "cell",
                "action": "apply antenna down-tilt and/or provision a dedicated aerial cell/beam",
                "reason": "cell-wide aerial uplink interference (line-of-sight)",
                "apply_via": "intent-to-network (human approval required)",
            })
        for u in corr.get("ues", []):
            if u["handover_thrash"]:
                recs.append({
                    "scope": "ue",
                    "entity_id": u["entity_id"],
                    "action": "tune mobility robustness (hysteresis / time-to-trigger) to stop handover thrashing",
                    "reason": f"{u['distinct_cells']} distinct cells in window",
                    "apply_via": "intent-to-network (human approval required)",
                })
        return {"recommendations": recs, "count": len(recs),
                "note": "read-only proposal; no network change performed"}

    return reg
