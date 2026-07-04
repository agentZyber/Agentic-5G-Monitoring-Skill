"""ai-native — agentic AI-in-the-network operations (ITU-R IMT-2030 "Integrated AI and Communication").

A 6G use-case pack in the shared shape, so one generalist agent (and one fine-tuned adapter)
learns a single reusable loop across domains:

    ai_native_overview        → domain posture from the EventStore
    assess_analytics          → per-entity KPIs + a health verdict
    correlate_predictions     → cross-signal correlation → SYSTEMIC vs ENTITY-SPECIFIC conclusion
    recommend_ai_action       → a structured, read-only recommendation (actuation routes through
                                 the approval-gated `intent-to-network` pack; these packs never change state)

For AI-native ops, the correlation that matters is predicted-vs-observed: the network produces
NWDAF-style analytics (an observed KPI alongside its prediction). A single slice/NF whose
prediction is off is an entity-specific anomaly; if a strict majority of analytics are off, the
deviation is SYSTEMIC — model drift or a network-wide event. Read-only; reasons over SLICE + QOS
events whose payloads carry "observed", "predicted", and "metric".
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from corelab.agent.tools import ToolRegistry
from corelab.core.bus import EventStore
from corelab.core.events import EventDomain

PACK: Dict[str, Any] = {
    "name": "ai-native",
    "description": "Agentic AI-in-the-network ops: NWDAF-style predicted-vs-observed KPI analytics + anomaly attribution (read-only).",
    "connectors": ["nwdaf", "prometheus"],
    "datasets": ["telecomts"],
    "system_prompt": (
        "You are a 6G AI-native (Integrated AI and Communication) agent. The network produces "
        "NWDAF-style analytics: each slice or network function reports an observed KPI alongside the "
        "value its in-network model predicted. Read the per-slice/NF analytics, compute the deviation, "
        "and CORRELATE whether a prediction deviation is entity-specific or SYSTEMIC model-drift / a "
        "network-wide event, quoting the numbers. You never change the network — recommend actions that "
        "a human applies via the intent approval flow."
    ),
}

MAX_DEVIATION = 0.2      # relative deviation above which an analytics reading is anomalous (20%)


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


def _latest_metric_by_entity(events: EventStore, domain: EventDomain, window: int) -> Dict[str, str]:
    """Map entity_id -> the most recent 'metric' label (newest first)."""
    out: Dict[str, str] = {}
    for e in events.recent(domain=domain, limit=window):  # recent() is newest-first
        if not e.entity_id or e.entity_id in out:
            continue
        m = e.payload.get("metric")
        if isinstance(m, str):
            out[e.entity_id] = m
    return out


def _deviation(observed: float, predicted: float) -> float:
    """Relative error of a prediction: abs(observed - predicted) / max(abs(predicted), 1e-9)."""
    return abs(observed - predicted) / max(abs(predicted), 1e-9)


def _analytics(events: EventStore, window: int) -> Dict[str, Dict[str, Any]]:
    """Collect the latest observed/predicted/metric per analytics entity across SLICE + QOS.

    SLICE wins ties (it is read first); an entity needs both an observed and a predicted value
    to count as a usable analytics reading.
    """
    out: Dict[str, Dict[str, Any]] = {}
    for domain in (EventDomain.SLICE, EventDomain.QOS):
        observed = _latest_by_entity(events, domain, ("observed",), window)
        predicted = _latest_by_entity(events, domain, ("predicted",), window)
        metric = _latest_metric_by_entity(events, domain, window)
        for ent in set(observed) | set(predicted):
            if ent in out:
                continue
            obs, pred = observed.get(ent), predicted.get(ent)
            if obs is None or pred is None:
                continue
            dev = _deviation(obs, pred)
            out[ent] = {
                "entity_id": ent,
                "observed": obs,
                "predicted": pred,
                "metric": metric.get(ent),
                "deviation": round(dev, 4),
                "anomalous": bool(dev > MAX_DEVIATION),
            }
    return out


def build_registry(store: Optional[EventStore] = None) -> ToolRegistry:
    events = store if store is not None else EventStore()
    reg = ToolRegistry()

    @reg.tool(
        name="ai_native_overview",
        description="AI-native analytics posture: entities reporting NWDAF-style analytics (SLICE+QOS) and how many are anomalous (deviation > 20%).",
        parameters={"type": "object", "properties": {
            "window": {"type": "integer", "description": "Recent events to inspect (default 500)"}}},
        tags=("ai-native", "analytics", "overview"),
    )
    def ai_native_overview(window: int = 500) -> Dict[str, Any]:
        analytics = _analytics(events, window)
        if not analytics:
            return {"entities_with_analytics": 0, "note": "no NWDAF analytics events in the store yet"}
        anomalous = sorted(a["entity_id"] for a in analytics.values() if a["anomalous"])
        return {
            "entities_with_analytics": len(analytics),
            "anomalous_entities": anomalous,
            "anomalous_count": len(anomalous),
            "max_deviation_threshold": MAX_DEVIATION,
        }

    @reg.tool(
        name="assess_analytics",
        description="Per-entity NWDAF analytics: observed vs predicted KPI, computed relative deviation, and a verdict (on-model / anomalous).",
        parameters={"type": "object", "properties": {
            "entity_id": {"type": "string", "description": "Slice or NF id, e.g. 'slice1'"},
            "window": {"type": "integer", "description": "Recent events to inspect (default 300)"}},
            "required": ["entity_id"]},
        tags=("ai-native", "analytics"),
    )
    def assess_analytics(entity_id: str, window: int = 300) -> Dict[str, Any]:
        rec = _analytics(events, window).get(entity_id)
        if rec is None:
            return {"entity_id": entity_id, "note": "no NWDAF analytics events for this entity"}
        return {
            "entity_id": entity_id,
            "observed": rec["observed"],
            "predicted": rec["predicted"],
            "metric": rec["metric"],
            "deviation": rec["deviation"],
            "verdict": "anomalous" if rec["anomalous"] else "on-model",
        }

    @reg.tool(
        name="correlate_predictions",
        description=(
            "Correlate every analytics entity's predicted-vs-observed deviation to attribute anomalies. "
            "Concludes whether a deviation is SYSTEMIC (a strict majority of analytics are off -> model "
            "drift or a network-wide event) or entity-specific, with the per-entity evidence."
        ),
        parameters={"type": "object", "properties": {
            "window": {"type": "integer", "description": "Recent events to inspect (default 500)"}}},
        tags=("ai-native", "correlation"),
    )
    def correlate_predictions(window: int = 500) -> Dict[str, Any]:
        analytics = _analytics(events, window)
        if not analytics:
            return {"entities": [], "conclusion": "no analytics data", "note": "no NWDAF analytics events in the store"}
        entities: List[Dict[str, Any]] = []
        anomalous: List[str] = []
        for ent, rec in sorted(analytics.items()):
            if rec["anomalous"]:
                anomalous.append(ent)
            entities.append({"entity_id": ent, "observed": rec["observed"], "predicted": rec["predicted"],
                             "deviation": rec["deviation"], "anomalous": rec["anomalous"]})
        ratio = len(anomalous) / len(entities)
        conclusion = (
            f"SYSTEMIC: model drift or network-wide event ({len(anomalous)}/{len(entities)} analytics deviating)"
            if ratio > 0.5 else
            f"entity-specific: {len(anomalous)}/{len(entities)} entity(ies) deviating"
        )
        return {"entities": entities, "anomalous_entities": anomalous, "conclusion": conclusion}

    @reg.tool(
        name="recommend_ai_action",
        description=(
            "Recommend (read-only) AI-native actions for deviating analytics: scale the deviating NF, "
            "pre-emptive slice adjustment, or retrain/recalibrate the analytics model if the deviation is "
            "systemic. The operator applies these via the intent-to-network approval flow; this tool changes nothing."
        ),
        parameters={"type": "object", "properties": {
            "window": {"type": "integer", "description": "Recent events to inspect (default 500)"}}},
        tags=("ai-native", "recommendation"),
    )
    def recommend_ai_action(window: int = 500) -> Dict[str, Any]:
        corr = correlate_predictions(window=window)
        anomalous = corr.get("anomalous_entities", [])
        systemic = "SYSTEMIC" in corr.get("conclusion", "")
        recs: List[Dict[str, Any]] = []
        if systemic:
            recs.append({
                "entity_id": "*",
                "action": "retrain / recalibrate in-network analytics model (systemic drift)",
                "apply_via": "intent-to-network (human approval required)",
            })
        for ent in anomalous:
            recs.append({
                "entity_id": ent,
                "action": "scale the deviating NF / pre-emptive slice adjustment",
                "apply_via": "intent-to-network (human approval required)",
            })
        return {"recommendations": recs, "count": len(recs), "systemic": systemic,
                "note": "read-only proposal; no network change performed"}

    return reg
