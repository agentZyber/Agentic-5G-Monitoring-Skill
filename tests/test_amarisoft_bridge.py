"""Amarisoft->bus bridge: live telemetry -> NetworkEvents with health severity."""

from corelab.connectors.amarisoft import AmarisoftClient
from corelab.connectors.amarisoft_bridge import AmarisoftBridge, radio_severity
from corelab.core.bus import EventBus
from corelab.core.events import EventDomain, Severity


class FakeTransport:
    def __init__(self, responses):
        self.responses = responses

    def __call__(self, request):
        return self.responses.get(request["message"], {})


def _gnb(ue_list, cells):
    return AmarisoftClient(transport=FakeTransport({
        "ue_get": {"ue_list": ue_list},
        "stats": {"cells": cells},
    }))


def test_radio_severity_thresholds():
    assert radio_severity(15, 30, 60) is Severity.INFO
    assert radio_severity(8, 4, 112) is Severity.WARNING
    assert radio_severity(3, -2, 130) is Severity.ALERT
    assert radio_severity(None, None, None) is Severity.INFO


def test_bridge_emits_ue_and_cell_events():
    gnb = _gnb(
        ue_list=[
            {"ran_ue_id": 154, "cells": [{"cell_id": 1, "cqi": 15, "pusch_snr": 33, "ul_path_loss": 60, "dl_bitrate": 2000}]},
            {"ran_ue_id": 2, "cells": [{"cell_id": 1, "cqi": 4, "pusch_snr": -1, "ul_path_loss": 125, "dl_bitrate": 50}]},
        ],
        cells={"1": {"dl_bitrate": 2050, "ul_bitrate": 0, "ue_count_max": 2, "dl_use_avg": 0.2}},
    )
    bus = EventBus()
    n = AmarisoftBridge(gnb).poll_once(bus)
    # 2 UEs x (RAN_KPI + LOCATION) + 1 cell THROUGHPUT = 5
    assert n == 5
    ran = bus.store.recent(domain=EventDomain.RAN_KPI, limit=10)
    assert {e.entity_id for e in ran} == {"ue-154", "ue-2"}
    # the weak UE is flagged ALERT by the severity rule; the strong one INFO
    sev = {e.entity_id: e.severity for e in ran}
    assert sev["ue-154"] is Severity.INFO
    assert sev["ue-2"] is Severity.ALERT
    # radio payload carries real metrics
    weak = next(e for e in ran if e.entity_id == "ue-2")
    assert weak.payload["cqi"] == 4 and weak.payload["pusch_snr"] == -1
    # location (cell assoc) events present for mobility/geofence tools
    assert {e.entity_id for e in bus.store.recent(domain=EventDomain.LOCATION, limit=10)} == {"ue-154", "ue-2"}
    # cell throughput event
    cell = bus.store.recent(domain=EventDomain.THROUGHPUT, limit=5)
    assert cell[0].entity_id == "cell-1" and cell[0].payload["ue_count"] == 2


def test_bridge_run_loops_without_sleeping():
    gnb = _gnb(ue_list=[{"ran_ue_id": 1, "cells": [{"cell_id": 1, "cqi": 15}]}], cells={})
    bus = EventBus()
    polls = AmarisoftBridge(gnb).run(bus, iterations=3, sleeper=lambda s: None)
    assert polls == 3
    assert len(bus.store) == 6  # per poll: 1 RAN_KPI + 1 LOCATION for the UE; x3 polls


def test_bridge_empty_network():
    gnb = _gnb(ue_list=[], cells={})
    bus = EventBus()
    assert AmarisoftBridge(gnb).poll_once(bus) == 0
