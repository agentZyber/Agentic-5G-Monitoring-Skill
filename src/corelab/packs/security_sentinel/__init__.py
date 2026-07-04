"""security-sentinel — signaling/behavioral anomaly detection over the event store.

Evolves the legacy geofence idea into rule-based detectors the agent drives: failure bursts,
attach/signaling storms, and cell-hopping (mobility-pattern) audits. Rules are deliberately
simple and explainable (counts + thresholds over the EventStore) — the *agent* contextualizes
and triages; ML-based detectors can join in a later stage. Detection only: remediation goes
through `self-heal` playbooks with a human in the loop.

``build_registry(store=...)`` receives the shared EventStore from the app context; standalone
construction gets an empty store and reports honestly that there is no data yet.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional

from corelab.agent.tools import ToolRegistry
from corelab.core.bus import EventStore
from corelab.core.events import EventDomain, Severity

PACK: Dict[str, Any] = {
    "name": "security-sentinel",
    "description": "Rule-based signaling/behavioral anomaly detection + mobility audits (detection only).",
    "connectors": ["open5gs", "ueransim"],
    "datasets": ["5g3e"],
    "system_prompt": (
        "You are a 5G security sentinel. Use the detection tools to find anomalies, then explain "
        "each finding with the underlying counts and affected entities. You only detect and "
        "triage — remediation is proposed via self-heal playbooks and requires human approval."
    ),
}

# Tunable rule thresholds (kept visible: explainability is the point)
FAILURE_BURST_THRESHOLD = 3      # >= alert-severity security/signaling events per entity
SIGNALING_STORM_THRESHOLD = 20   # signaling events in the inspected window (any entity)
CELL_HOP_THRESHOLD = 4           # distinct cells per entity in the inspected window


def build_registry(store: Optional[EventStore] = None) -> ToolRegistry:
    events = store if store is not None else EventStore()
    reg = ToolRegistry()

    @reg.tool(
        name="detect_signaling_anomalies",
        description=(
            "Scan recent events for security-relevant anomalies: per-entity failure bursts "
            "(alert+ severity) and global signaling storms. Returns explainable findings with counts."
        ),
        parameters={
            "type": "object",
            "properties": {
                "window": {
                    "type": "integer",
                    "description": "How many recent events to inspect (default 500)",
                }
            },
        },
        tags=("security", "anomaly"),
    )
    def detect_signaling_anomalies(window: int = 500) -> Dict[str, Any]:
        recent = events.recent(limit=window)
        if not recent:
            return {"findings": [], "inspected": 0, "note": "event store is empty"}

        findings: List[Dict[str, Any]] = []

        alert_counts: Counter = Counter(
            e.entity_id
            for e in recent
            if e.entity_id
            and e.domain in (EventDomain.SECURITY, EventDomain.SIGNALING)
            and e.severity in (Severity.ALERT, Severity.CRITICAL)
        )
        for entity, count in alert_counts.items():
            if count >= FAILURE_BURST_THRESHOLD:
                findings.append(
                    {
                        "type": "failure_burst",
                        "entity_id": entity,
                        "count": count,
                        "threshold": FAILURE_BURST_THRESHOLD,
                        "detail": f"{count} alert+ security/signaling events for {entity}",
                    }
                )

        signaling_total = sum(1 for e in recent if e.domain is EventDomain.SIGNALING)
        if signaling_total >= SIGNALING_STORM_THRESHOLD:
            findings.append(
                {
                    "type": "signaling_storm",
                    "count": signaling_total,
                    "threshold": SIGNALING_STORM_THRESHOLD,
                    "detail": f"{signaling_total} signaling events in the last {len(recent)} events",
                }
            )

        return {"findings": findings, "inspected": len(recent)}

    @reg.tool(
        name="audit_ue_mobility",
        description=(
            "Audit a UE's mobility pattern from location events: cells visited, geofence alerts, "
            "and a cell-hopping flag when distinct-cell count exceeds the threshold."
        ),
        parameters={
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "UE external id"},
                "window": {"type": "integer", "description": "Recent events to inspect (default 200)"},
            },
            "required": ["entity_id"],
        },
        tags=("security", "mobility"),
    )
    def audit_ue_mobility(entity_id: str, window: int = 200) -> Dict[str, Any]:
        history = events.recent(domain=EventDomain.LOCATION, entity_id=entity_id, limit=window)
        if not history:
            return {"entity_id": entity_id, "note": "no location events for this entity"}
        cells = [e.payload.get("cell_id") for e in history if e.payload.get("cell_id")]
        distinct = list(dict.fromkeys(cells))
        alerts = sum(
            1 for e in history if e.severity in (Severity.ALERT, Severity.CRITICAL)
        )
        return {
            "entity_id": entity_id,
            "events": len(history),
            "cells_visited": distinct,
            "distinct_cells": len(distinct),
            "geofence_alerts": alerts,
            "cell_hopping": len(distinct) >= CELL_HOP_THRESHOLD,
            "threshold": CELL_HOP_THRESHOLD,
        }

    @reg.tool(
        name="security_posture",
        description="Store-wide security posture: event totals by domain/severity and entities with alerts.",
        tags=("security",),
    )
    def security_posture() -> Dict[str, Any]:
        stats = events.stats()
        alerting = sorted(
            {
                e.entity_id
                for e in events.recent(min_severity="alert", limit=1000)
                if e.entity_id
            }
        )
        return {**stats, "entities_with_alerts": alerting}

    return reg
