"""massive-iot pack: cell-vs-network access-congestion correlation over seeded events + graceful empty store."""

from zortenet.core.bus import EventStore
from zortenet.core.events import EventDomain, NetworkEvent
from zortenet.packs.massive_iot import PACK, build_registry


def _store():
    s = EventStore()
    # cell 1: RACH storm + high attach-failure rate -> congested
    s.append(NetworkEvent(domain=EventDomain.SIGNALING, source="core", entity_id="1",
                          payload={"rach_attempts": 150.0, "attach_attempts": 100.0, "attach_failures": 30.0}))
    # cell 2: light access, no failures -> healthy
    s.append(NetworkEvent(domain=EventDomain.SIGNALING, source="core", entity_id="2",
                          payload={"rach_attempts": 20.0, "attach_attempts": 100.0, "attach_failures": 2.0}))
    s.append(NetworkEvent(domain=EventDomain.THROUGHPUT, source="kpm", entity_id="1", payload={"small_data_rate": 8.0}))
    s.append(NetworkEvent(domain=EventDomain.THROUGHPUT, source="kpm", entity_id="2", payload={"small_data_rate": 12.0}))
    return s


def test_pack_metadata_and_tools():
    reg = build_registry(store=_store())
    assert PACK["name"] == "massive-iot"
    assert PACK["connectors"] == ["open5gs", "amarisoft"]
    assert set(reg.names()) == {
        "massive_iot_overview", "assess_iot_cell", "correlate_iot_congestion", "recommend_iot_action",
    }


def test_overview_and_assessment():
    reg = build_registry(store=_store())
    ov = reg.get("massive_iot_overview").invoke()
    assert ov["cells_reporting_access"] == 2
    assert ov["congested_cells"] == ["1"] and ov["congested_count"] == 1

    bad = reg.get("assess_iot_cell").invoke(entity_id="1")
    assert bad["verdict"] == "congested"
    assert bad["rach_attempts"] == 150.0 and bad["failure_rate"] == 0.3
    assert "rach_storm" in bad["tripped"] and "attach_failure_rate" in bad["tripped"]

    ok = reg.get("assess_iot_cell").invoke(entity_id="2")
    assert ok["verdict"] == "healthy" and ok["tripped"] == []


def test_correlation_and_recommendation():
    reg = build_registry(store=_store())
    corr = reg.get("correlate_iot_congestion").invoke()
    assert corr["congested_cells"] == ["1"]
    assert "cell-specific" in corr["conclusion"]
    assert "1/2" in corr["conclusion"]

    rec = reg.get("recommend_iot_action").invoke()
    assert rec["count"] == 1 and rec["recommendations"][0]["cell_id"] == "1"
    assert rec["recommendations"][0]["apply_via"] == "intent-to-network (human approval required)"


def test_degrades_without_data():
    reg = build_registry(store=None)
    assert reg.get("massive_iot_overview").invoke()["cells_reporting_access"] == 0
    assert "no access data" in reg.get("correlate_iot_congestion").invoke()["conclusion"]
    assert reg.get("assess_iot_cell").invoke(entity_id="9")["note"]
    assert reg.get("recommend_iot_action").invoke()["count"] == 0
