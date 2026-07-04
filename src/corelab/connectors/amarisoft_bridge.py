"""Amarisoft → event-bus bridge: live gNB/core telemetry into NetworkEvents.

Polls the gNB UE list + cell stats and publishes NetworkEvents onto an EventBus, so the
store-backed packs (self-heal / security-sentinel / netops-copilot) reason over **real** UE
telemetry — turning the live network into agent-visible state (and into real, outcome-validated
trajectories). Single-shot ``poll_once`` for seed-then-reason; ``run`` for continuous monitoring.
"""

from __future__ import annotations

import time
from typing import List, Optional

from corelab.connectors.amarisoft import AmarisoftClient
from corelab.core.bus import EventBus
from corelab.core.events import EventDomain, NetworkEvent, Severity


def radio_severity(cqi, snr, path_loss) -> Severity:
    """Map NR radio quality to a severity so detectors can flag degraded UEs."""
    if cqi is None:
        return Severity.INFO
    if cqi < 6 or (snr is not None and snr < 0) or (path_loss is not None and path_loss > 120):
        return Severity.ALERT
    if cqi < 10 or (snr is not None and snr < 5) or (path_loss is not None and path_loss > 110):
        return Severity.WARNING
    return Severity.INFO


def amarisoft_ue_events(gnb: AmarisoftClient) -> List[NetworkEvent]:
    """One RAN_KPI (radio) + one LOCATION (cell association) event per attached UE."""
    events: List[NetworkEvent] = []
    resp = gnb.ue_list().get("response") or {}
    for u in resp.get("ue_list") or []:
        if not isinstance(u, dict):
            continue
        ue_id = f"ue-{u.get('ran_ue_id', u.get('rnti', 'unknown'))}"
        for c in u.get("cells") or []:
            if not isinstance(c, dict):
                continue
            cqi, snr, pl = c.get("cqi"), c.get("pusch_snr"), c.get("ul_path_loss")
            events.append(NetworkEvent(
                domain=EventDomain.RAN_KPI, source="amarisoft", entity_id=ue_id,
                severity=radio_severity(cqi, snr, pl), event_type="UE_RADIO",
                payload={k: v for k, v in {
                    "cell_id": c.get("cell_id"), "cqi": cqi, "pusch_snr": snr, "ul_path_loss": pl,
                    "dl_mcs": c.get("dl_mcs"), "ul_mcs": c.get("ul_mcs"),
                    "dl_bitrate": c.get("dl_bitrate"), "ul_bitrate": c.get("ul_bitrate"),
                    "dl_retx": c.get("dl_retx"), "ul_retx": c.get("ul_retx"),
                }.items() if v is not None},
            ))
            if c.get("cell_id") is not None:
                events.append(NetworkEvent(
                    domain=EventDomain.LOCATION, source="amarisoft", entity_id=ue_id,
                    event_type="CELL_ASSOC", payload={"cell_id": str(c.get("cell_id"))},
                ))
    return events


def amarisoft_cell_events(gnb: AmarisoftClient) -> List[NetworkEvent]:
    """One THROUGHPUT event per active cell (load + aggregate rates)."""
    events: List[NetworkEvent] = []
    st = gnb.stats().get("response") or {}
    for cid, c in (st.get("cells") or {}).items():
        if not isinstance(c, dict):
            continue
        events.append(NetworkEvent(
            domain=EventDomain.THROUGHPUT, source="amarisoft", entity_id=f"cell-{cid}",
            event_type="CELL_STATS",
            payload={k: v for k, v in {
                "dl_bitrate": c.get("dl_bitrate"), "ul_bitrate": c.get("ul_bitrate"),
                "ue_count": c.get("ue_count_max"), "dl_use_avg": c.get("dl_use_avg"),
                "ul_use_avg": c.get("ul_use_avg"),
            }.items() if v is not None},
        ))
    return events


class AmarisoftBridge:
    def __init__(self, gnb: AmarisoftClient, core: Optional[AmarisoftClient] = None) -> None:
        self.gnb = gnb
        self.core = core

    def poll_once(self, bus: EventBus) -> int:
        """Publish one snapshot of live UE + cell telemetry; returns the event count."""
        return bus.publish_all(amarisoft_ue_events(self.gnb) + amarisoft_cell_events(self.gnb))

    def run(self, bus: EventBus, interval: float = 5.0, iterations: Optional[int] = None,
            sleeper=time.sleep) -> int:
        """Poll repeatedly (continuous monitoring); returns the number of polls performed."""
        polls = 0
        while iterations is None or polls < iterations:
            self.poll_once(bus)
            polls += 1
            if iterations is not None and polls >= iterations:
                break
            sleeper(interval)
        return polls
