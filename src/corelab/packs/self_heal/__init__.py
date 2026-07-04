"""self-heal v0 — diagnose-only: structured diagnosis + human-approved playbooks.

v0 scope is deliberate (IMPLEMENTATION_PLAN Stage 2): the tools *gather and structure* evidence
(per-entity event history, suspected issues from explainable rules) and *look up* remediation
playbooks — they never apply changes. Apply actions arrive in Stage 3 behind the
intent-to-network approval flow; every playbook says so explicitly. Framed as the observe/orient
half of an ETSI-ZSM-style closed loop, with the human as the decide/act gate.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from corelab.agent.tools import ToolRegistry
from corelab.core.bus import EventStore
from corelab.core.events import EventDomain, Severity

PACK: Dict[str, Any] = {
    "name": "self-heal",
    "description": "Diagnosis + remediation playbooks (diagnose-only; apply actions are Stage 3).",
    "connectors": ["open5gs", "prometheus", "ueransim"],
    "datasets": [],
    "system_prompt": (
        "You are a 5G self-healing assistant in DIAGNOSE-ONLY mode. Gather evidence with the "
        "diagnosis tools, identify the most likely issue, and propose the matching playbook. "
        "Always state that remediation steps require human approval — you cannot apply changes."
    ),
}

APPROVAL_NOTE = "human approval required — apply actions land in Stage 3 (intent-to-network)"

PLAYBOOKS: Dict[str, Dict[str, Any]] = {
    "ue-connectivity-loss": {
        "description": "A UE lost connectivity (deregistration, radio loss, or core-side drop).",
        "diagnosis_steps": [
            "Check UE status on the core (get_ue_status) and RAN (ueransim ue_status).",
            "Inspect recent signaling events for the entity (diagnose_entity).",
            "Check AMF registered-subscriber KPI for a wider outage (query_kpi).",
        ],
        "remediation_steps": [
            "Re-establish the PDU session (ueransim ps-establish).",
            "If core-side: verify AMF/SMF health and subscriber provisioning.",
            "If recurring: audit the UE's mobility pattern for coverage gaps.",
        ],
    },
    "qos-degradation": {
        "description": "Latency/jitter/throughput degraded for a UE, slice, or flow.",
        "diagnosis_steps": [
            "Pull recent QoS events for the entity (diagnose_entity).",
            "Compare slice load KPIs before/after onset (query_kpi).",
            "Check whether degradation correlates with mobility (audit_ue_mobility).",
        ],
        "remediation_steps": [
            "Adjust QoS policy / slice allocation via intent (Stage 3).",
            "Steer the UE to a less-loaded cell where supported.",
        ],
    },
    "signaling-storm": {
        "description": "Abnormal signaling volume (attach storms, registration loops).",
        "diagnosis_steps": [
            "Confirm with detect_signaling_anomalies and identify top entities.",
            "Check AMF load KPIs (query_kpi).",
        ],
        "remediation_steps": [
            "Rate-limit or quarantine offending UEs (policy action, Stage 3).",
            "Scale the affected NF if load-driven.",
        ],
    },
    "geofence-breach": {
        "description": "A UE entered a cell outside its allowed policy set.",
        "diagnosis_steps": [
            "Verify with check_geofence_breach and audit_ue_mobility.",
            "Review the entity's alert history (diagnose_entity).",
        ],
        "remediation_steps": [
            "Notify the operator; optionally restrict service via policy (Stage 3).",
        ],
    },
}


def _suspect_issues(by_domain: Dict[str, int], alerts: int, event_types: List[str]) -> List[str]:
    suspected: List[str] = []
    types_lower = " ".join(event_types).lower()
    if "loss_of_connectivity" in types_lower or "deregister" in types_lower:
        suspected.append("ue-connectivity-loss")
    if by_domain.get("qos", 0) > 0 and alerts > 0:
        suspected.append("qos-degradation")
    if by_domain.get("signaling", 0) >= 10:
        suspected.append("signaling-storm")
    if by_domain.get("location", 0) > 0 and alerts > 0:
        suspected.append("geofence-breach")
    return suspected


def build_registry(store: Optional[EventStore] = None) -> ToolRegistry:
    events = store if store is not None else EventStore()
    reg = ToolRegistry()

    @reg.tool(
        name="diagnose_entity",
        description=(
            "Structured diagnosis for one entity (UE/cell/NF): event counts by domain & severity, "
            "recent event lines, and suspected issues (explainable rules) mapped to playbooks."
        ),
        parameters={
            "type": "object",
            "properties": {
                "entity_id": {"type": "string"},
                "window": {"type": "integer", "description": "Recent events to inspect (default 200)"},
            },
            "required": ["entity_id"],
        },
        tags=("diagnosis",),
    )
    def diagnose_entity(entity_id: str, window: int = 200) -> Dict[str, Any]:
        history = events.recent(entity_id=entity_id, limit=window)
        if not history:
            return {"entity_id": entity_id, "note": "no events for this entity"}
        by_domain: Dict[str, int] = {}
        by_severity: Dict[str, int] = {}
        event_types: List[str] = []
        for e in history:
            by_domain[e.domain.value] = by_domain.get(e.domain.value, 0) + 1
            by_severity[e.severity.value] = by_severity.get(e.severity.value, 0) + 1
            if e.event_type:
                event_types.append(e.event_type)
        alerts = by_severity.get("alert", 0) + by_severity.get("critical", 0)
        return {
            "entity_id": entity_id,
            "events": len(history),
            "by_domain": by_domain,
            "by_severity": by_severity,
            "suspected_issues": _suspect_issues(by_domain, alerts, event_types),
            "recent": [e.text_repr() for e in history[:10]],
            "note": APPROVAL_NOTE,
        }

    @reg.tool(
        name="list_playbooks",
        description="List available remediation playbooks (all diagnose-only / human-approved).",
        tags=("playbooks",),
    )
    def list_playbooks() -> Dict[str, Any]:
        return {
            "playbooks": {k: v["description"] for k, v in PLAYBOOKS.items()},
            "note": APPROVAL_NOTE,
        }

    @reg.tool(
        name="propose_remediation",
        description="Fetch the playbook for a suspected issue: diagnosis steps + human-approved remediation steps.",
        parameters={
            "type": "object",
            "properties": {"issue": {"type": "string", "description": "Playbook key, e.g. 'qos-degradation'"}},
            "required": ["issue"],
        },
        tags=("playbooks",),
    )
    def propose_remediation(issue: str) -> Dict[str, Any]:
        key = issue.strip().lower()
        if key not in PLAYBOOKS:
            return {
                "error": f"no playbook '{issue}'",
                "available": sorted(PLAYBOOKS),
            }
        return {"issue": key, **PLAYBOOKS[key], "note": APPROVAL_NOTE}

    return reg
