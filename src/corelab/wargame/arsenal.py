"""Red and blue arsenals — the tools each side wields, as ordinary ToolRegistries.

Reuse over reinvention: red tools mutate the world (inject threat events); blue's *sensing* wraps
the existing ``security-sentinel`` detectors + the world's derived threat list, and blue's only
consequential move — ``apply_countermeasure`` — is routed through the doctrine (human-approval)
gate. Because these are standard ToolRegistries, an LLM controller can be handed them verbatim and
a scripted controller can name the same tools — one uniform action surface.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from corelab.agent.tools import ToolRegistry
from corelab.core.bus import EventStore
from corelab.core.events import EventDomain, NetworkEvent, Severity
from corelab.packs.security_sentinel import build_registry as security_registry
from corelab.wargame.scenario import MITIGATION, WarGameScenario, WorldState

# red tool -> (event_type, domain, human description)
_RED_SPEC = {
    "jam_link": ("JAMMING", EventDomain.RAN_KPI, "degrade a radio link serving the mission"),
    "signaling_flood": ("SIGNALING_FLOOD", EventDomain.SIGNALING, "flood the control plane"),
    "intrude_node": ("INTRUSION", EventDomain.SECURITY, "compromise a network node"),
    "spoof_feed": ("SPOOF", EventDomain.APP, "spoof/inject into a data feed"),
}


def build_red_registry(store: EventStore, scenario: WarGameScenario,
                       counter: Optional[List[int]] = None) -> ToolRegistry:
    counter = counter if counter is not None else [0]
    reg = ToolRegistry()

    def _inject(kind: str, element: str) -> Dict[str, Any]:
        etype, domain, _ = _RED_SPEC[kind]
        counter[0] += 1
        tid = f"T{counter[0]}"
        store.append(NetworkEvent(
            domain=domain, source="red", entity_id=element, severity=Severity.CRITICAL,
            event_type=etype, payload={"threat_id": tid, "target": scenario.mission_asset,
                                       "element": element, "kind": kind}))
        return {"threat_id": tid, "kind": kind, "element": element,
                "target": scenario.mission_asset}

    for tool in scenario.red_actions:
        if tool not in _RED_SPEC:
            continue
        _etype, _domain, desc = _RED_SPEC[tool]

        def _make(tool=tool):
            @reg.tool(name=tool, description=f"Adversary action: {desc} (simulated).",
                      parameters={"type": "object", "properties": {
                          "element": {"type": "string", "description": "targeted element id"}}},
                      tags=("red", "adversary"))
            def _act(element: str = "link-1") -> Dict[str, Any]:
                return _inject(tool, element)
        _make()
    return reg


def build_blue_registry(store: EventStore, scenario: WarGameScenario,
                        approval: "ApprovalPolicy") -> ToolRegistry:
    from corelab.wargame.approval import ApprovalRequest  # local import avoids cycle

    world = WorldState(store, scenario.mission_asset)
    sentinel = security_registry(store=store)
    reg = ToolRegistry()

    @reg.tool(name="detect_threats",
              description="Sensing: scan the network for active threats and signaling anomalies.",
              tags=("blue", "sensing"))
    def detect_threats() -> Dict[str, Any]:
        anomalies = sentinel.get("detect_signaling_anomalies").invoke()
        threats = [{"threat_id": t.payload.get("threat_id"), "kind": t.payload.get("kind"),
                    "element": t.entity_id, "event_type": t.event_type}
                   for t in world.active_threats()]
        return {"active_threats": threats, "threat_count": len(threats),
                "signaling_anomalies": anomalies.get("findings", [])}

    @reg.tool(name="diagnose_threat",
              description="Diagnose a specific threat by id (what it is, what it affects).",
              parameters={"type": "object", "properties": {
                  "threat_id": {"type": "string"}}, "required": ["threat_id"]},
              tags=("blue", "diagnose"))
    def diagnose_threat(threat_id: str) -> Dict[str, Any]:
        for t in world.active_threats():
            if t.payload.get("threat_id") == threat_id:
                return {"threat_id": threat_id, "kind": t.payload.get("kind"),
                        "element": t.entity_id, "target": t.payload.get("target"),
                        "severity": t.severity.value, "event_type": t.event_type}
        return {"threat_id": threat_id, "note": "no such active threat"}

    @reg.tool(name="apply_countermeasure",
              description=("Apply a countermeasure that neutralises a threat (reroute/harden/"
                           "isolate/authenticate). CONSEQUENTIAL — requires human (doctrine) approval; "
                           "does nothing unless approved."),
              parameters={"type": "object", "properties": {
                  "threat_id": {"type": "string"},
                  "measure": {"type": "string", "description": "e.g. reroute, harden, isolate"}},
                  "required": ["threat_id"]},
              tags=("blue", "control", "gated"))
    def apply_countermeasure(threat_id: str, measure: str = "reroute") -> Dict[str, Any]:
        decision = approval.request(ApprovalRequest(
            actor="blue", action="apply_countermeasure",
            args={"threat_id": threat_id, "measure": measure},
            rationale=f"neutralise {threat_id} on {scenario.mission_asset}"))
        if not decision.approved:
            return {"applied": False, "blocked": True, "reason": decision.reason,
                    "note": "doctrine gate held — no change without approval"}
        store.append(NetworkEvent(
            domain=EventDomain.SLICE, source="blue", entity_id=scenario.mission_asset,
            severity=Severity.INFO, event_type=MITIGATION,
            payload={"threat_id": threat_id, "measure": measure,
                     "approved_by": decision.approver}))
        return {"applied": True, "threat_id": threat_id, "measure": measure,
                "approved_by": decision.approver}

    return reg
