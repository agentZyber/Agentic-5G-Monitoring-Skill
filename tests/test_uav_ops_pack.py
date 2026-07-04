"""uav-ops pack: aerial UE-vs-cell interference correlation over seeded events + graceful empty store."""

from corelab.core.bus import EventStore
from corelab.core.events import EventDomain, NetworkEvent
from corelab.packs.uav_ops import PACK, build_registry


def _store():
    s = EventStore()
    # uav1: aerial + handover thrash across 5 cells + high uplink interference -> degraded
    s.append(NetworkEvent(domain=EventDomain.RAN_KPI, source="kpm", entity_id="uav1",
                          payload={"ul_interference_db": -92.0, "sinr": 2.0, "cqi": 4, "altitude_m": 120.0}))
    for cell in ("1", "2", "3", "4", "5"):
        s.append(NetworkEvent(domain=EventDomain.LOCATION, source="amarisoft", entity_id="uav1",
                              payload={"cell_id": cell}))
    # uav2: aerial but healthy -> low uplink interference, no thrash (stays on one cell)
    s.append(NetworkEvent(domain=EventDomain.RAN_KPI, source="kpm", entity_id="uav2",
                          payload={"ul_interference_db": -118.0, "sinr": 18.0, "cqi": 14, "altitude_m": 80.0}))
    s.append(NetworkEvent(domain=EventDomain.LOCATION, source="amarisoft", entity_id="uav2",
                          payload={"cell_id": "7"}))
    return s


def test_pack_metadata_and_tools():
    reg = build_registry(store=_store())
    assert PACK["name"] == "uav-ops"
    assert set(reg.names()) == {
        "uav_overview", "assess_aerial_ue", "correlate_uav_coverage", "recommend_uav_action",
    }


def test_overview_and_assessment():
    reg = build_registry(store=_store())
    ov = reg.get("uav_overview").invoke()
    assert ov["aerial_ues"] == 2
    assert ov["aerial_ue_ids"] == ["uav1", "uav2"]
    assert ov["high_ul_interference"] == ["uav1"]
    assert ov["handover_thrash"] == ["uav1"]

    bad = reg.get("assess_aerial_ue").invoke(entity_id="uav1")
    assert bad["verdict"] == "degraded"
    assert bad["handover_thrash"] is True and bad["distinct_cells"] == 5
    assert bad["high_ul_interference"] is True and bad["ul_interference_db"] == -92.0

    good = reg.get("assess_aerial_ue").invoke(entity_id="uav2")
    assert good["verdict"] == "nominal"
    assert good["handover_thrash"] is False and good["high_ul_interference"] is False


def test_correlation_and_recommendation():
    reg = build_registry(store=_store())
    corr = reg.get("correlate_uav_coverage").invoke()
    assert corr["degraded"] == ["uav1"]
    # exactly one of two aerial UEs sees high interference -> NOT a strict majority -> UE-specific
    assert "UE-specific" in corr["conclusion"]
    assert "1/2" in corr["conclusion"]

    rec = reg.get("recommend_uav_action").invoke()
    assert rec["count"] == 1
    only = rec["recommendations"][0]
    assert only["scope"] == "ue" and only["entity_id"] == "uav1"
    assert only["apply_via"] == "intent-to-network (human approval required)"


def test_degrades_without_data():
    reg = build_registry(store=None)
    assert reg.get("uav_overview").invoke()["aerial_ues"] == 0
    assert "no aerial-UE data" in reg.get("correlate_uav_coverage").invoke()["conclusion"]
    assert reg.get("assess_aerial_ue").invoke(entity_id="nope")["note"]
    assert reg.get("recommend_uav_action").invoke()["count"] == 0
