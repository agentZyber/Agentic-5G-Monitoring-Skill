"""location-monitor — the legacy ZorteNet capability, repackaged as the first capability pack.

This is the proof that the original single-purpose NetApp becomes *one pack among many*: its
geofence/mobility logic is now a set of registered tools that the interop layer can expose over
MCP, A2A, REST, and the LLM tool formats.
"""

from __future__ import annotations

from typing import Any, Dict, List

from zortenet.agent.tools import ToolRegistry
from zortenet.core.events import NetworkEvent, Severity

PACK: Dict[str, Any] = {
    "name": "location-monitor",
    "description": "UE location/mobility monitoring and geofence policy (legacy ZorteNet capability).",
    "connectors": ["nef", "open5gs", "free5gc"],
    "datasets": [],
    "system_prompt": (
        "You are a 5G location-monitoring agent. Track UE mobility, detect geofence policy "
        "breaches, and summarize network events for an operator."
    ),
}


def build_registry() -> ToolRegistry:
    reg = ToolRegistry()

    @reg.tool(
        name="check_geofence_breach",
        description="Check whether a UE currently in a given cell has breached its allowed-cell policy.",
        parameters={
            "type": "object",
            "properties": {
                "cell_id": {"type": "string", "description": "The cell the UE is currently in"},
                "allowed_cells": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Cells the UE is permitted to be in",
                },
            },
            "required": ["cell_id", "allowed_cells"],
        },
        tags=("location", "security"),
    )
    def check_geofence_breach(cell_id: str, allowed_cells: List[str]) -> Dict[str, Any]:
        breach = cell_id not in allowed_cells
        return {
            "cell_id": cell_id,
            "breach": breach,
            "severity": (Severity.ALERT if breach else Severity.INFO).value,
        }

    @reg.tool(
        name="summarize_network_events",
        description="Summarize a batch of network events by domain and severity.",
        parameters={
            "type": "object",
            "properties": {
                "events": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Events as dicts (legacy location shape or NetworkEvent dicts)",
                }
            },
            "required": ["events"],
        },
        tags=("observability",),
    )
    def summarize_network_events(events: List[Dict[str, Any]]) -> Dict[str, Any]:
        parsed = [
            NetworkEvent.from_dict(e) if "domain" in e else NetworkEvent.from_location_event(e)
            for e in events
        ]
        by_domain: Dict[str, int] = {}
        by_severity: Dict[str, int] = {}
        for ev in parsed:
            by_domain[ev.domain.value] = by_domain.get(ev.domain.value, 0) + 1
            by_severity[ev.severity.value] = by_severity.get(ev.severity.value, 0) + 1
        return {"count": len(parsed), "by_domain": by_domain, "by_severity": by_severity}

    return reg
