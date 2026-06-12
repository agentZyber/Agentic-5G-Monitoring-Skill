"""Connector catalog — what can source/control which event domains.

A lightweight, queryable description of the south-bound surface (shown at ``/connectors`` and
used by docs/packs to reason about coverage). Connectors stay plain classes; this catalog is
metadata, not a framework.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class ConnectorInfo:
    name: str
    description: str
    domains: Tuple[str, ...]          # EventDomain values this connector can source
    capabilities: Tuple[str, ...]     # "read" | "control" | "fault-injection"
    module: str
    status: str = "implemented"       # implemented | stub

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "domains": list(self.domains),
            "capabilities": list(self.capabilities),
            "module": self.module,
            "status": self.status,
        }


CONNECTOR_CATALOG: Dict[str, ConnectorInfo] = {
    "prometheus": ConnectorInfo(
        name="prometheus",
        description="PromQL telemetry (Open5GS NF metrics, toolkit metrics).",
        domains=("ran_kpi", "throughput", "energy"),
        capabilities=("read",),
        module="zortenet.connectors.prometheus",
    ),
    "open5gs": ConnectorInfo(
        name="open5gs",
        description="Open5GS core API: subscriptions, UE info/location (legacy-mirrored endpoints).",
        domains=("location", "signaling"),
        capabilities=("read",),
        module="zortenet.connectors.open5gs",
    ),
    "ueransim": ConnectorInfo(
        name="ueransim",
        description="UERANSIM nr-cli control: UE/gNB status, deregister, PDU sessions — the fault-injection primitive.",
        domains=("signaling",),
        capabilities=("read", "control", "fault-injection"),
        module="zortenet.connectors.ueransim",
    ),
    "nwdaf": ConnectorInfo(
        name="nwdaf",
        description="3GPP NWDAF analytics (Nnwdaf_AnalyticsInfo shape).",
        domains=("qos", "slice"),
        capabilities=("read",),
        module="zortenet.connectors.nwdaf",
        status="stub",  # no NWDAF in the default Open5GS testbed; free5GC profile later
    ),
    "amarisoft": ConnectorInfo(
        name="amarisoft",
        description="Amarisoft callbox remote API (WebSocket-JSON): stats, UE list, config_set, "
        "handover, channel-sim fault injection. Control flows through the intent approval ledger.",
        domains=("ran_kpi", "signaling", "qos", "throughput"),
        capabilities=("read", "control", "fault-injection"),
        module="zortenet.connectors.amarisoft",
        status="live-pending",  # mock-tested; validated against the real callbox at Tier-3 bring-up
    ),
    "a1-ric": ConnectorInfo(
        name="a1-ric",
        description="O-RAN A1 policy interface (OSC A1 mediator REST): policy types + policies — "
        "the Non-RT/rApp control path the LLM supervises.",
        domains=("ran_kpi", "slice"),
        capabilities=("read", "control"),
        module="zortenet.connectors.a1_ric",
        status="live-pending",  # mock-tested; validated against a live OSC RIC at Tier-2/3 bring-up
    ),
}


def catalog() -> List[Dict[str, object]]:
    return [info.to_dict() for info in CONNECTOR_CATALOG.values()]
