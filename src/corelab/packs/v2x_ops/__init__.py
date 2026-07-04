"""v2x-ops — agentic V2X/URLLC operations (ITU-R IMT-2030 "Hyper-Reliable Low-Latency Communication").

A 6G use-case pack for automotive/V2X, exposing the same shape as every other UC pack so one
generalist agent (and one fine-tuned adapter) learns a single reusable loop across domains:

    v2x_overview          → domain posture from the EventStore
    assess_vehicle        → per-vehicle KPIs + a health verdict
    correlate_v2x_...      → cross-signal correlation → SYSTEMIC vs VEHICLE-SPECIFIC conclusion
    recommend_v2x_action  → a structured, read-only recommendation (actuation routes through
                            the approval-gated `intent-to-network` pack; these packs never change state)

For V2X, the correlation that matters is radio-vs-congestion: when a vehicle breaches its URLLC
budget, is it the vehicle's own poor radio (low CQI/SINR) or cell-wide congestion (most vehicles
breach at once)? Read-only; reasons over QOS (latency/reliability) + RAN_KPI (cqi/sinr) events.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from corelab.agent.tools import ToolRegistry
from corelab.core.bus import EventStore
from corelab.core.events import EventDomain

PACK: Dict[str, Any] = {
    "name": "v2x-ops",
    "description": "Agentic V2X/URLLC ops: per-vehicle latency & reliability budget + radio-vs-congestion correlation (read-only).",
    "connectors": ["amarisoft", "a1-ric", "prometheus"],
    "datasets": ["5g3e"],
    "system_prompt": (
        "You are a 5G/6G V2X (URLLC) operations agent for automotive use cases. Goal: keep every "
        "vehicle inside its hyper-reliable low-latency budget. Read per-vehicle URLLC KPIs (latency, "
        "reliability) and radio (CQI, SINR), then CORRELATE whether a budget breach is the vehicle's "
        "own poor radio or cell-wide congestion, and quote the numbers. You never change the network — "
        "recommend actions that a human applies via the intent approval flow."
    ),
}

URLLC_PDB_MS = 10.0       # packet delay budget (ms): latency above this breaches URLLC
MIN_RELIABILITY = 0.999   # minimum success probability: reliability below this breaches URLLC
MIN_CQI = 7.0             # channel quality below which a vehicle's radio is considered poor


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
        name="v2x_overview",
        description="V2X URLLC posture: vehicles reporting QoS and how many breach the URLLC budget (latency or reliability).",
        parameters={"type": "object", "properties": {
            "window": {"type": "integer", "description": "Recent events to inspect (default 500)"}}},
        tags=("v2x", "urllc", "overview"),
    )
    def v2x_overview(window: int = 500) -> Dict[str, Any]:
        latency = _latest_by_entity(events, EventDomain.QOS, ("latency_ms", "value"), window)
        reliability = _latest_by_entity(events, EventDomain.QOS, ("reliability",), window)
        vehicles = sorted(set(latency) | set(reliability))
        if not vehicles:
            return {"vehicles_reporting": 0, "note": "no QoS events in the store yet"}
        breaching = [
            v for v in vehicles
            if latency.get(v, 0.0) > URLLC_PDB_MS or reliability.get(v, 1.0) < MIN_RELIABILITY
        ]
        return {
            "vehicles_reporting": len(vehicles),
            "vehicles_breaching_budget": len(breaching),
            "breaching": breaching,
            "urllc_pdb_ms": URLLC_PDB_MS,
            "min_reliability": MIN_RELIABILITY,
        }

    @reg.tool(
        name="assess_vehicle",
        description="Per-vehicle URLLC assessment: latency/reliability vs budget AND radio (cqi/sinr), with a verdict (ok / breach).",
        parameters={"type": "object", "properties": {
            "entity_id": {"type": "string", "description": "Vehicle id, e.g. 'veh1'"},
            "window": {"type": "integer", "description": "Recent events to inspect (default 300)"}},
            "required": ["entity_id"]},
        tags=("v2x", "vehicle"),
    )
    def assess_vehicle(entity_id: str, window: int = 300) -> Dict[str, Any]:
        latency = _latest_by_entity(events, EventDomain.QOS, ("latency_ms", "value"), window).get(entity_id)
        reliability = _latest_by_entity(events, EventDomain.QOS, ("reliability",), window).get(entity_id)
        cqi = _latest_by_entity(events, EventDomain.RAN_KPI, ("cqi",), window).get(entity_id)
        sinr = _latest_by_entity(events, EventDomain.RAN_KPI, ("sinr",), window).get(entity_id)
        if latency is None and reliability is None and cqi is None and sinr is None:
            return {"entity_id": entity_id, "note": "no QoS/radio events for this vehicle"}
        breached_kpis: List[str] = []
        if latency is not None and latency > URLLC_PDB_MS:
            breached_kpis.append("latency_ms")
        if reliability is not None and reliability < MIN_RELIABILITY:
            breached_kpis.append("reliability")
        radio_poor = cqi is not None and cqi < MIN_CQI
        verdict = "breach" if breached_kpis else "ok"
        return {"entity_id": entity_id, "latency_ms": latency, "reliability": reliability,
                "cqi": cqi, "sinr": sinr, "breached_kpis": breached_kpis,
                "radio_poor": radio_poor, "verdict": verdict}

    @reg.tool(
        name="correlate_v2x_reliability",
        description=(
            "Correlate every vehicle's URLLC budget breach with its radio quality. Concludes whether a "
            "breach is SYSTEMIC (a strict majority of vehicles breach -> cell-wide congestion/coverage) or "
            "vehicle-specific (check each one's radio), with the per-vehicle evidence."
        ),
        parameters={"type": "object", "properties": {
            "window": {"type": "integer", "description": "Recent events to inspect (default 500)"}}},
        tags=("v2x", "correlation"),
    )
    def correlate_v2x_reliability(window: int = 500) -> Dict[str, Any]:
        latency = _latest_by_entity(events, EventDomain.QOS, ("latency_ms", "value"), window)
        reliability = _latest_by_entity(events, EventDomain.QOS, ("reliability",), window)
        cqi = _latest_by_entity(events, EventDomain.RAN_KPI, ("cqi",), window)
        sinr = _latest_by_entity(events, EventDomain.RAN_KPI, ("sinr",), window)
        vehicles = sorted(set(latency) | set(reliability))
        if not vehicles:
            return {"vehicles": [], "conclusion": "no V2X data", "note": "no QoS events in the store"}
        per_vehicle, breached = [], []
        for v in vehicles:
            lat = latency.get(v)
            rel = reliability.get(v)
            is_breach = (lat is not None and lat > URLLC_PDB_MS) or (rel is not None and rel < MIN_RELIABILITY)
            radio_poor = v in cqi and cqi[v] < MIN_CQI
            if is_breach:
                breached.append(v)
            per_vehicle.append({"entity_id": v, "latency_ms": lat, "reliability": rel,
                                "cqi": cqi.get(v), "sinr": sinr.get(v),
                                "breach": is_breach, "radio_poor": radio_poor})
        ratio = len(breached) / len(vehicles)
        conclusion = (
            f"SYSTEMIC: cell-wide congestion/coverage ({len(breached)}/{len(vehicles)} vehicles breach)"
            if ratio > 0.5 else
            f"vehicle-specific: {len(breached)}/{len(vehicles)} vehicle(s) breach (check each one's radio)"
            if breached else
            "no URLLC breach: all reporting vehicles are within budget"
        )
        return {"vehicles": per_vehicle, "breached": breached, "conclusion": conclusion}

    @reg.tool(
        name="recommend_v2x_action",
        description=(
            "Recommend (read-only) URLLC actions per breaching vehicle: prioritise the URLLC slice, and "
            "trigger a handover when the vehicle's radio is poor. The operator applies these via the "
            "intent-to-network approval flow; this tool changes nothing."
        ),
        parameters={"type": "object", "properties": {
            "window": {"type": "integer", "description": "Recent events to inspect (default 500)"}}},
        tags=("v2x", "recommendation"),
    )
    def recommend_v2x_action(window: int = 500) -> Dict[str, Any]:
        corr = correlate_v2x_reliability(window=window)
        ev = {x["entity_id"]: x for x in corr.get("vehicles", [])}
        recs = []
        for v in corr.get("breached", []):
            radio_poor = ev.get(v, {}).get("radio_poor", False)
            action = ("trigger handover to a stronger cell, then prioritise URLLC slice"
                      if radio_poor else "prioritise URLLC slice (raise scheduling priority)")
            recs.append({"entity_id": v, "action": action, "radio_poor": radio_poor,
                         "apply_via": "intent-to-network (human approval required)"})
        return {"recommendations": recs, "count": len(recs),
                "note": "read-only proposal; no network change performed"}

    return reg
