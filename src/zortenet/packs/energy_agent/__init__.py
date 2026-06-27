"""energy-agent — agentic energy & sustainability operations (ITU-R IMT-2030 overarching aspect).

The TEMPLATE pack for 6G use-case operations: every UC pack exposes the same shape so one
generalist agent (and one fine-tuned adapter) learns a single reusable loop across domains:

    <uc>_overview      → domain posture from the EventStore
    assess_<entity>    → per-entity KPIs + a health verdict
    correlate_<uc>     → cross-signal correlation → SYSTEMIC vs ENTITY-SPECIFIC conclusion
    recommend_<uc>_... → a structured, read-only recommendation (actuation routes through
                          the approval-gated `intent-to-network` pack; these packs never change state)

For energy, the correlation that matters is power-vs-load: a cell drawing power while carrying
little traffic is an energy-saving (sleep / carrier-shutdown) candidate, whereas a high-load cell's
draw is justified. Read-only; reasons over ENERGY + THROUGHPUT/RAN_KPI events.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from zortenet.agent.tools import ToolRegistry
from zortenet.core.bus import EventStore
from zortenet.core.events import EventDomain

PACK: Dict[str, Any] = {
    "name": "energy-agent",
    "description": "Agentic energy/sustainability ops: power-vs-load correlation + sleep-candidate detection (read-only).",
    "connectors": ["prometheus", "nwdaf", "amarisoft"],
    "datasets": ["5g3e"],
    "system_prompt": (
        "You are a 5G/6G energy-efficiency agent. Goal: cut network energy without hurting service. "
        "Gather evidence with the tools, then CORRELATE each cell's power draw with its traffic load: "
        "a cell with low load but non-trivial power is an energy-saving candidate; a high-load cell's "
        "draw is justified. Decide whether inefficiency is SYSTEMIC (over-provisioned network) or "
        "cell-specific, and quote the numbers. You never change the network — recommend actions that a "
        "human applies via the intent approval flow."
    ),
}

LOW_LOAD_PRB = 15.0      # % PRB utilisation below which a cell is under-utilised
LOW_LOAD_MBPS = 5.0      # DL Mbps below which a cell is under-utilised (fallback when no PRB)
IDLE_POWER_W = 20.0      # power draw above which an under-utilised cell is "wasting" energy


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


def build_registry(store: Optional[EventStore] = None) -> ToolRegistry:
    events = store if store is not None else EventStore()
    reg = ToolRegistry()

    @reg.tool(
        name="energy_overview",
        description="Network energy posture: cells reporting power, total/mean power draw, and how many cells are under-utilised.",
        parameters={"type": "object", "properties": {
            "window": {"type": "integer", "description": "Recent events to inspect (default 500)"}}},
        tags=("energy", "sustainability", "overview"),
    )
    def energy_overview(window: int = 500) -> Dict[str, Any]:
        power = _latest_by_entity(events, EventDomain.ENERGY, ("power_w", "power", "value"), window)
        if not power:
            return {"cells_reporting_power": 0, "note": "no energy events in the store yet"}
        load = _latest_by_entity(events, EventDomain.THROUGHPUT, ("prb_util", "dl_mbps", "value"), window)
        under = [c for c in power if load.get(c, 0.0) < LOW_LOAD_MBPS]
        total = sum(power.values())
        return {
            "cells_reporting_power": len(power),
            "total_power_w": round(total, 2),
            "mean_power_w": round(total / len(power), 2),
            "under_utilised_cells": sorted(under),
        }

    @reg.tool(
        name="assess_cell_energy",
        description="Per-cell energy assessment: power draw vs load, with an efficiency verdict (efficient / wasteful / overloaded).",
        parameters={"type": "object", "properties": {
            "cell_id": {"type": "string", "description": "Cell id, e.g. '1'"},
            "window": {"type": "integer", "description": "Recent events to inspect (default 300)"}},
            "required": ["cell_id"]},
        tags=("energy", "cell"),
    )
    def assess_cell_energy(cell_id: str, window: int = 300) -> Dict[str, Any]:
        power = _latest_by_entity(events, EventDomain.ENERGY, ("power_w", "power", "value"), window).get(cell_id)
        prb = _latest_by_entity(events, EventDomain.THROUGHPUT, ("prb_util",), window).get(cell_id)
        mbps = _latest_by_entity(events, EventDomain.THROUGHPUT, ("dl_mbps", "value"), window).get(cell_id)
        if power is None and prb is None and mbps is None:
            return {"cell_id": cell_id, "note": "no energy/load events for this cell"}
        low_load = (prb is not None and prb < LOW_LOAD_PRB) or (prb is None and (mbps or 0.0) < LOW_LOAD_MBPS)
        if power and low_load:
            verdict = "wasteful"  # drawing power while idle -> energy-saving candidate
        elif prb is not None and prb >= 80:
            verdict = "overloaded"
        else:
            verdict = "efficient"
        return {"cell_id": cell_id, "power_w": power, "prb_util": prb, "dl_mbps": mbps,
                "low_load": low_load, "verdict": verdict}

    @reg.tool(
        name="correlate_energy_load",
        description=(
            "Correlate every cell's power draw with its traffic load to find energy-saving candidates. "
            "Concludes whether energy inefficiency is SYSTEMIC (many under-utilised cells drawing power -> "
            "over-provisioned network) or cell-specific, with the per-cell evidence."
        ),
        parameters={"type": "object", "properties": {
            "window": {"type": "integer", "description": "Recent events to inspect (default 500)"}}},
        tags=("energy", "correlation"),
    )
    def correlate_energy_load(window: int = 500) -> Dict[str, Any]:
        power = _latest_by_entity(events, EventDomain.ENERGY, ("power_w", "power", "value"), window)
        if not power:
            return {"cells": [], "conclusion": "no energy data", "note": "no energy events in the store"}
        prb = _latest_by_entity(events, EventDomain.THROUGHPUT, ("prb_util",), window)
        mbps = _latest_by_entity(events, EventDomain.THROUGHPUT, ("dl_mbps", "value"), window)
        cells, candidates = [], []
        for c, p in sorted(power.items()):
            load = prb.get(c, mbps.get(c, 0.0))
            metric = "prb_util" if c in prb else "dl_mbps"
            low = (prb.get(c, 100.0) < LOW_LOAD_PRB) if c in prb else (mbps.get(c, 100.0) < LOW_LOAD_MBPS)
            saveable = bool(low and p >= IDLE_POWER_W)
            if saveable:
                candidates.append(c)
            cells.append({"cell_id": c, "power_w": p, "load": load, "load_metric": metric,
                          "energy_saving_candidate": saveable})
        ratio = len(candidates) / len(cells)
        conclusion = (
            f"SYSTEMIC over-provisioning: {len(candidates)}/{len(cells)} cells draw power at low load"
            if ratio > 0.5 else
            f"cell-specific: {len(candidates)}/{len(cells)} cell(s) are energy-saving candidates"
            if candidates else
            "no energy-saving opportunity: all powered cells are adequately loaded"
        )
        return {"cells": cells, "energy_saving_candidates": candidates, "conclusion": conclusion}

    @reg.tool(
        name="recommend_energy_saving",
        description=(
            "Recommend (read-only) energy-saving actions for under-utilised cells: carrier shutdown / cell "
            "sleep. The operator applies these via the intent-to-network approval flow; this tool changes nothing."
        ),
        parameters={"type": "object", "properties": {
            "window": {"type": "integer", "description": "Recent events to inspect (default 500)"}}},
        tags=("energy", "recommendation"),
    )
    def recommend_energy_saving(window: int = 500) -> Dict[str, Any]:
        corr = correlate_energy_load(window=window)
        recs = [
            {"cell_id": c, "action": "enable cell sleep / carrier shutdown",
             "expected_saving_w": next((x["power_w"] for x in corr.get("cells", []) if x["cell_id"] == c), None),
             "apply_via": "intent-to-network (human approval required)"}
            for c in corr.get("energy_saving_candidates", [])
        ]
        return {"recommendations": recs, "count": len(recs),
                "note": "read-only proposal; no network change performed"}

    return reg
