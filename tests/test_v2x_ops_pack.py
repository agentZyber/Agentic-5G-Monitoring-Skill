"""v2x-ops pack: radio-vs-congestion correlation over seeded events + graceful empty store."""

from corelab.core.bus import EventStore
from corelab.core.events import EventDomain, NetworkEvent
from corelab.packs.v2x_ops import PACK, build_registry


def _store():
    s = EventStore()
    # veh1: breaches latency AND has poor radio (low CQI) -> vehicle-specific, radio-driven.
    # veh2: well within URLLC budget with good radio -> ok.
    s.append(NetworkEvent(domain=EventDomain.QOS, source="qos-mon", entity_id="veh1", payload={"latency_ms": 22.0, "reliability": 0.995}))
    s.append(NetworkEvent(domain=EventDomain.QOS, source="qos-mon", entity_id="veh2", payload={"latency_ms": 4.0, "reliability": 0.9999}))
    s.append(NetworkEvent(domain=EventDomain.RAN_KPI, source="kpm", entity_id="veh1", payload={"cqi": 3.0, "sinr": 1.5}))
    s.append(NetworkEvent(domain=EventDomain.RAN_KPI, source="kpm", entity_id="veh2", payload={"cqi": 13.0, "sinr": 22.0}))
    return s


def test_pack_metadata_and_tools():
    reg = build_registry(store=_store())
    assert PACK["name"] == "v2x-ops"
    assert set(reg.names()) == {
        "v2x_overview", "assess_vehicle", "correlate_v2x_reliability", "recommend_v2x_action",
    }


def test_overview_and_assessment():
    reg = build_registry(store=_store())
    ov = reg.get("v2x_overview").invoke()
    assert ov["vehicles_reporting"] == 2 and ov["vehicles_breaching_budget"] == 1
    assert ov["breaching"] == ["veh1"]

    bad = reg.get("assess_vehicle").invoke(entity_id="veh1")
    assert bad["verdict"] == "breach" and bad["radio_poor"] is True
    assert "latency_ms" in bad["breached_kpis"] and bad["latency_ms"] == 22.0

    good = reg.get("assess_vehicle").invoke(entity_id="veh2")
    assert good["verdict"] == "ok" and good["radio_poor"] is False and good["breached_kpis"] == []


def test_correlation_and_recommendation():
    reg = build_registry(store=_store())
    corr = reg.get("correlate_v2x_reliability").invoke()
    assert corr["breached"] == ["veh1"]
    assert "vehicle-specific" in corr["conclusion"]
    veh1 = next(x for x in corr["vehicles"] if x["entity_id"] == "veh1")
    assert veh1["radio_poor"] is True and veh1["cqi"] == 3.0

    rec = reg.get("recommend_v2x_action").invoke()
    assert rec["count"] == 1 and rec["recommendations"][0]["entity_id"] == "veh1"
    assert rec["recommendations"][0]["radio_poor"] is True
    assert "handover" in rec["recommendations"][0]["action"]
    assert rec["recommendations"][0]["apply_via"] == "intent-to-network (human approval required)"


def test_degrades_without_data():
    reg = build_registry(store=None)
    assert reg.get("v2x_overview").invoke()["vehicles_reporting"] == 0
    assert "no V2X data" in reg.get("correlate_v2x_reliability").invoke()["conclusion"]
    assert reg.get("assess_vehicle").invoke(entity_id="veh9")["note"]
