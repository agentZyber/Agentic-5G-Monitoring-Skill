"""xr-qoe — agentic XR / immersive QoE operations (ITU-R IMT-2030 "Immersive Communication").

A 6G use-case pack that follows the shared shape so one generalist agent (and one fine-tuned
adapter) learns a single reusable loop across domains:

    <uc>_overview      → domain posture from the EventStore
    assess_<entity>    → per-entity KPIs + a health verdict
    correlate_<uc>     → cross-signal correlation → SYSTEMIC vs ENTITY-SPECIFIC conclusion
    recommend_<uc>_... → a structured, read-only recommendation (actuation routes through
                          the approval-gated `intent-to-network` pack; these packs never change state)

For XR/holographic flows the correlation that matters is app-vs-network: if a STRICT majority of
flows breach the immersive QoE budget the cause is network-wide (congestion / radio degradation);
if only a minority breach it is flow-specific (likely app or edge). Read-only; reasons over
QOS + THROUGHPUT events.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from corelab.agent.tools import ToolRegistry
from corelab.core.bus import EventStore
from corelab.core.events import EventDomain

PACK: Dict[str, Any] = {
    "name": "xr-qoe",
    "description": "Agentic XR/immersive QoE ops: per-flow latency/jitter/throughput vs XR budget + app-vs-network correlation (read-only).",
    "connectors": ["prometheus", "nwdaf", "amarisoft"],
    "datasets": ["5g3e"],
    "system_prompt": (
        "You are a 5G/6G XR/immersive QoE agent. Goal: keep holographic and XR flows inside the "
        "motion-to-photon budget. Read each flow's latency/jitter/loss/throughput with the tools, then "
        "CORRELATE whether breaches are flow/app-specific or network-wide (a strict majority breaching "
        "means systemic congestion or radio degradation). Always quote the numbers. You never change the "
        "network — recommend actions that a human applies via the intent approval flow."
    ),
}

MOTION_TO_PHOTON_MS = 20.0   # max end-to-end latency for immersive XR
MAX_JITTER_MS = 5.0          # max jitter before motion artefacts appear
MIN_MBPS = 50.0              # min DL throughput for an XR/holographic flow
MAX_LOSS = 0.01              # max packet loss ratio (1%)


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


def _breaches(latency: Optional[float], jitter: Optional[float], loss: Optional[float],
              mbps: Optional[float]) -> List[str]:
    """Return the list of XR KPIs that breach the immersive budget."""
    breached: List[str] = []
    if latency is not None and latency > MOTION_TO_PHOTON_MS:
        breached.append("latency_ms")
    if jitter is not None and jitter > MAX_JITTER_MS:
        breached.append("jitter_ms")
    if loss is not None and loss > MAX_LOSS:
        breached.append("packet_loss")
    if mbps is not None and mbps < MIN_MBPS:
        breached.append("dl_mbps")
    return breached


def build_registry(store: Optional[EventStore] = None) -> ToolRegistry:
    events = store if store is not None else EventStore()
    reg = ToolRegistry()

    @reg.tool(
        name="xr_qoe_overview",
        description="XR/immersive QoE posture: flows reporting QoE and how many breach the motion-to-photon budget.",
        parameters={"type": "object", "properties": {
            "window": {"type": "integer", "description": "Recent events to inspect (default 500)"}}},
        tags=("xr", "qoe", "immersive", "overview"),
    )
    def xr_qoe_overview(window: int = 500) -> Dict[str, Any]:
        latency = _latest_by_entity(events, EventDomain.QOS, ("latency_ms", "value"), window)
        jitter = _latest_by_entity(events, EventDomain.QOS, ("jitter_ms",), window)
        loss = _latest_by_entity(events, EventDomain.QOS, ("packet_loss",), window)
        mbps = _latest_by_entity(events, EventDomain.THROUGHPUT, ("dl_mbps", "value"), window)
        flows = sorted(set(latency) | set(jitter) | set(loss) | set(mbps))
        if not flows:
            return {"flows_reporting_qoe": 0, "note": "no XR QoE events in the store yet"}
        breaching = [
            f for f in flows
            if _breaches(latency.get(f), jitter.get(f), loss.get(f), mbps.get(f))
        ]
        return {
            "flows_reporting_qoe": len(flows),
            "flows_breaching_budget": len(breaching),
            "breaching_flows": breaching,
        }

    @reg.tool(
        name="assess_xr_flow",
        description="Per-flow XR assessment: latency/jitter/loss/throughput vs the immersive budget, with a verdict (good / degraded).",
        parameters={"type": "object", "properties": {
            "entity_id": {"type": "string", "description": "Flow id, e.g. 'flowA'"},
            "window": {"type": "integer", "description": "Recent events to inspect (default 300)"}},
            "required": ["entity_id"]},
        tags=("xr", "qoe", "flow"),
    )
    def assess_xr_flow(entity_id: str, window: int = 300) -> Dict[str, Any]:
        latency = _latest_by_entity(events, EventDomain.QOS, ("latency_ms", "value"), window).get(entity_id)
        jitter = _latest_by_entity(events, EventDomain.QOS, ("jitter_ms",), window).get(entity_id)
        loss = _latest_by_entity(events, EventDomain.QOS, ("packet_loss",), window).get(entity_id)
        mbps = _latest_by_entity(events, EventDomain.THROUGHPUT, ("dl_mbps", "value"), window).get(entity_id)
        if latency is None and jitter is None and loss is None and mbps is None:
            return {"entity_id": entity_id, "note": "no XR QoE events for this flow"}
        breached = _breaches(latency, jitter, loss, mbps)
        verdict = "degraded" if breached else "good"
        return {"entity_id": entity_id, "latency_ms": latency, "jitter_ms": jitter,
                "packet_loss": loss, "dl_mbps": mbps, "breached_kpis": breached, "verdict": verdict}

    @reg.tool(
        name="correlate_xr_qoe",
        description=(
            "Correlate every flow's QoE against the immersive budget to localise breaches. Concludes "
            "whether degradation is SYSTEMIC (a strict majority of flows breach -> network-wide congestion / "
            "radio degradation) or flow-specific (likely app/edge), with the per-flow evidence."
        ),
        parameters={"type": "object", "properties": {
            "window": {"type": "integer", "description": "Recent events to inspect (default 500)"}}},
        tags=("xr", "qoe", "correlation"),
    )
    def correlate_xr_qoe(window: int = 500) -> Dict[str, Any]:
        latency = _latest_by_entity(events, EventDomain.QOS, ("latency_ms", "value"), window)
        jitter = _latest_by_entity(events, EventDomain.QOS, ("jitter_ms",), window)
        loss = _latest_by_entity(events, EventDomain.QOS, ("packet_loss",), window)
        mbps = _latest_by_entity(events, EventDomain.THROUGHPUT, ("dl_mbps", "value"), window)
        flows_ids = sorted(set(latency) | set(jitter) | set(loss) | set(mbps))
        if not flows_ids:
            return {"flows": [], "conclusion": "no XR QoE data", "note": "no XR QoE events in the store"}
        flows, degraded = [], []
        for f in flows_ids:
            breached = _breaches(latency.get(f), jitter.get(f), loss.get(f), mbps.get(f))
            is_degraded = bool(breached)
            if is_degraded:
                degraded.append(f)
            flows.append({"flow_id": f, "latency_ms": latency.get(f), "jitter_ms": jitter.get(f),
                          "packet_loss": loss.get(f), "dl_mbps": mbps.get(f),
                          "breached_kpis": breached, "degraded": is_degraded})
        ratio = len(degraded) / len(flows)
        conclusion = (
            f"SYSTEMIC: network-wide congestion/radio degradation ({len(degraded)}/{len(flows)} flows breach)"
            if ratio > 0.5 else
            f"flow-specific: {len(degraded)}/{len(flows)} flow(s) degraded (likely app/edge)"
        )
        return {"flows": flows, "degraded_flows": degraded, "conclusion": conclusion}

    @reg.tool(
        name="recommend_xr_action",
        description=(
            "Recommend (read-only) remediation for degraded XR flows: raise XR slice priority / add radio "
            "resources. The operator applies these via the intent-to-network approval flow; this tool changes nothing."
        ),
        parameters={"type": "object", "properties": {
            "window": {"type": "integer", "description": "Recent events to inspect (default 500)"}}},
        tags=("xr", "qoe", "recommendation"),
    )
    def recommend_xr_action(window: int = 500) -> Dict[str, Any]:
        corr = correlate_xr_qoe(window=window)
        systemic = corr.get("conclusion", "").startswith("SYSTEMIC")
        action = "add radio resources / scale XR slice capacity" if systemic else "raise XR slice priority"
        recs = [
            {"flow_id": f, "action": action,
             "breached_kpis": next((x["breached_kpis"] for x in corr.get("flows", []) if x["flow_id"] == f), []),
             "apply_via": "intent-to-network (human approval required)"}
            for f in corr.get("degraded_flows", [])
        ]
        return {"recommendations": recs, "count": len(recs),
                "note": "read-only proposal; no network change performed"}

    return reg
