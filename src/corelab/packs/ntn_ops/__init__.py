"""ntn-ops — agentic NTN/satellite operations (ITU-R IMT-2030 "Ubiquitous Connectivity").

A 6G use-case pack following the TEMPLATE shape (see energy_agent), so one generalist agent
(and one fine-tuned adapter) reuses a single loop across domains:

    ntn_overview        → domain posture from the EventStore
    assess_<entity>     → per-terminal link KPIs + a health verdict
    correlate_ntn_link  → cross-signal correlation → SYSTEMIC vs TERMINAL-SPECIFIC conclusion
    recommend_ntn_...   → a structured, read-only recommendation (actuation routes through
                          the approval-gated `intent-to-network` pack; this pack never changes state)

For NTN, the correlation that matters is terminal-vs-beam: many terminals share a satellite beam,
so degradation that hits a STRICT majority of a beam's terminals is beam/satellite-wide (systemic),
whereas an isolated degraded terminal on an otherwise healthy beam is terminal-specific. Read-only;
reasons over RAN_KPI (propagation-delay / doppler / beam-SINR) + QOS (latency) events.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from corelab.agent.tools import ToolRegistry
from corelab.core.bus import EventStore
from corelab.core.events import EventDomain

PACK: Dict[str, Any] = {
    "name": "ntn-ops",
    "description": "Agentic NTN/satellite ops: propagation-delay, doppler & beam-SINR monitoring + terminal-vs-beam correlation (read-only).",
    "connectors": ["amarisoft", "prometheus"],
    "datasets": [],
    "system_prompt": (
        "You are a 5G/6G non-terrestrial-network (NTN/satellite) operations agent. Many terminals share "
        "each satellite beam, so read per-terminal link KPIs (propagation delay, doppler, beam-SINR, latency) "
        "and CORRELATE whether degradation is terminal-specific or beam/satellite-wide by grouping terminals "
        "under their beam_id. Quote the numbers and never change the network — recommend actions that a human "
        "applies via the intent approval flow."
    ),
}

MAX_PROP_DELAY_MS = 280.0   # one-way propagation delay above which the link is degraded
MAX_DOPPLER_HZ = 40000.0    # doppler shift above which pre-compensation is failing
MIN_SINR_DB = 0.0           # beam-SINR below which the link is degraded


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


def _latest_beam_by_entity(events: EventStore, window: int) -> Dict[str, str]:
    """Map entity_id -> its most recent beam_id (newest first); beam_id is a string label."""
    out: Dict[str, str] = {}
    for e in events.recent(domain=EventDomain.RAN_KPI, limit=window):
        if not e.entity_id or e.entity_id in out:
            continue
        beam = e.payload.get("beam_id")
        if beam is not None:
            out[e.entity_id] = str(beam)
    return out


def _breaches(prop: Optional[float], dopp: Optional[float], sinr: Optional[float]) -> List[str]:
    """Which link KPI(s) breach NTN thresholds — empty list means the link is healthy."""
    bad: List[str] = []
    if sinr is not None and sinr < MIN_SINR_DB:
        bad.append("sinr")
    if prop is not None and prop > MAX_PROP_DELAY_MS:
        bad.append("propagation_delay_ms")
    if dopp is not None and dopp > MAX_DOPPLER_HZ:
        bad.append("doppler_hz")
    return bad


def build_registry(store: Optional[EventStore] = None) -> ToolRegistry:
    events = store if store is not None else EventStore()
    reg = ToolRegistry()

    @reg.tool(
        name="ntn_overview",
        description="NTN link posture: terminals reporting, distinct satellite beams, and how many terminals breach link thresholds.",
        parameters={"type": "object", "properties": {
            "window": {"type": "integer", "description": "Recent events to inspect (default 500)"}}},
        tags=("ntn", "satellite", "overview"),
    )
    def ntn_overview(window: int = 500) -> Dict[str, Any]:
        prop = _latest_by_entity(events, EventDomain.RAN_KPI, ("propagation_delay_ms",), window)
        dopp = _latest_by_entity(events, EventDomain.RAN_KPI, ("doppler_hz",), window)
        sinr = _latest_by_entity(events, EventDomain.RAN_KPI, ("sinr",), window)
        beams = _latest_beam_by_entity(events, window)
        terminals = set(prop) | set(dopp) | set(sinr) | set(beams)
        if not terminals:
            return {"terminals_reporting": 0, "note": "no NTN link events in the store yet"}
        breaching = [t for t in terminals
                     if _breaches(prop.get(t), dopp.get(t), sinr.get(t))]
        return {
            "terminals_reporting": len(terminals),
            "distinct_beams": sorted(set(beams.values())),
            "terminals_breaching_thresholds": len(breaching),
            "breaching_terminals": sorted(breaching),
        }

    @reg.tool(
        name="assess_ntn_terminal",
        description="Per-terminal NTN link assessment: propagation delay, doppler, SINR & beam, with a verdict (ok / degraded) and which KPI(s) breached.",
        parameters={"type": "object", "properties": {
            "entity_id": {"type": "string", "description": "Terminal id, e.g. 'term1'"},
            "window": {"type": "integer", "description": "Recent events to inspect (default 300)"}},
            "required": ["entity_id"]},
        tags=("ntn", "terminal"),
    )
    def assess_ntn_terminal(entity_id: str, window: int = 300) -> Dict[str, Any]:
        prop = _latest_by_entity(events, EventDomain.RAN_KPI, ("propagation_delay_ms",), window).get(entity_id)
        dopp = _latest_by_entity(events, EventDomain.RAN_KPI, ("doppler_hz",), window).get(entity_id)
        sinr = _latest_by_entity(events, EventDomain.RAN_KPI, ("sinr",), window).get(entity_id)
        beam = _latest_beam_by_entity(events, window).get(entity_id)
        latency = _latest_by_entity(events, EventDomain.QOS, ("latency_ms",), window).get(entity_id)
        if prop is None and dopp is None and sinr is None and beam is None and latency is None:
            return {"entity_id": entity_id, "note": "no NTN link events for this terminal"}
        breached = _breaches(prop, dopp, sinr)
        verdict = "degraded" if breached else "ok"
        return {"entity_id": entity_id, "beam_id": beam, "propagation_delay_ms": prop,
                "doppler_hz": dopp, "sinr": sinr, "latency_ms": latency,
                "breached_kpis": breached, "verdict": verdict}

    @reg.tool(
        name="correlate_ntn_link",
        description=(
            "Group terminals by satellite beam and correlate per-terminal link health to decide whether "
            "degradation is SYSTEMIC (a strict majority of a beam's terminals degraded -> beam/satellite-wide) "
            "or terminal-specific, with the per-terminal evidence grouped by beam."
        ),
        parameters={"type": "object", "properties": {
            "window": {"type": "integer", "description": "Recent events to inspect (default 500)"}}},
        tags=("ntn", "correlation"),
    )
    def correlate_ntn_link(window: int = 500) -> Dict[str, Any]:
        prop = _latest_by_entity(events, EventDomain.RAN_KPI, ("propagation_delay_ms",), window)
        dopp = _latest_by_entity(events, EventDomain.RAN_KPI, ("doppler_hz",), window)
        sinr = _latest_by_entity(events, EventDomain.RAN_KPI, ("sinr",), window)
        beams = _latest_beam_by_entity(events, window)
        terminals = set(prop) | set(dopp) | set(sinr) | set(beams)
        if not terminals:
            return {"beams": {}, "conclusion": "no NTN data", "note": "no NTN link events in the store"}
        by_beam: Dict[str, List[Dict[str, Any]]] = {}
        for t in sorted(terminals):
            beam = beams.get(t, "unknown")
            breached = _breaches(prop.get(t), dopp.get(t), sinr.get(t))
            by_beam.setdefault(beam, []).append({
                "entity_id": t, "propagation_delay_ms": prop.get(t), "doppler_hz": dopp.get(t),
                "sinr": sinr.get(t), "breached_kpis": breached, "degraded": bool(breached)})
        beamwide: List[str] = []
        degraded_total = 0
        for beam, terms in by_beam.items():
            degraded = [x for x in terms if x["degraded"]]
            degraded_total += len(degraded)
            ratio = len(degraded) / len(terms)
            if ratio > 0.5:  # strict majority of THIS beam's terminals are degraded
                beamwide.append(beam)
        if beamwide:
            conclusion = f"SYSTEMIC: beam/satellite-wide degradation on beam(s) {sorted(beamwide)}"
        else:
            healthy_beams = sorted(by_beam)
            conclusion = (
                f"terminal-specific: {degraded_total} terminal(s) degraded across healthy beams"
                if degraded_total else
                f"no degradation: all terminals healthy across beams {healthy_beams}"
            )
        return {"beams": by_beam, "beamwide_degraded": sorted(beamwide),
                "degraded_terminals": degraded_total, "conclusion": conclusion}

    @reg.tool(
        name="recommend_ntn_action",
        description=(
            "Recommend (read-only) NTN remediation: beam reselection for terminal-specific issues, "
            "timing-advance / doppler pre-compensation for link-budget breaches, and beam handover for "
            "beam/satellite-wide degradation. The operator applies these via the intent-to-network "
            "approval flow; this tool changes nothing."
        ),
        parameters={"type": "object", "properties": {
            "window": {"type": "integer", "description": "Recent events to inspect (default 500)"}}},
        tags=("ntn", "recommendation"),
    )
    def recommend_ntn_action(window: int = 500) -> Dict[str, Any]:
        corr = correlate_ntn_link(window=window)
        beamwide = set(corr.get("beamwide_degraded", []))
        recs: List[Dict[str, Any]] = []
        for beam, terms in sorted(corr.get("beams", {}).items()):
            if beam in beamwide:
                recs.append({"beam_id": beam, "scope": "beam-wide",
                             "action": "beam handover / satellite reselection for the whole beam",
                             "apply_via": "intent-to-network (human approval required)"})
                continue
            for t in terms:
                if not t["degraded"]:
                    continue
                actions = ["beam reselection to a healthier beam"]
                if "propagation_delay_ms" in t["breached_kpis"]:
                    actions.append("timing-advance adjustment")
                if "doppler_hz" in t["breached_kpis"]:
                    actions.append("doppler pre-compensation")
                recs.append({"entity_id": t["entity_id"], "beam_id": beam, "scope": "terminal-specific",
                             "action": "; ".join(actions), "breached_kpis": t["breached_kpis"],
                             "apply_via": "intent-to-network (human approval required)"})
        return {"recommendations": recs, "count": len(recs), "conclusion": corr.get("conclusion"),
                "note": "read-only proposal; no network change performed"}

    return reg
