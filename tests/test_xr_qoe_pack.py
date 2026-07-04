"""xr-qoe pack: app-vs-network QoE correlation over seeded events + graceful empty store."""

from corelab.core.bus import EventStore
from corelab.core.events import EventDomain, NetworkEvent
from corelab.packs.xr_qoe import PACK, build_registry


def _store():
    s = EventStore()
    # flowA: inside the XR budget -> good; flowB: breaches latency/jitter/loss/throughput -> degraded.
    # Exactly one of two flows degraded => correlation must be flow-specific (1/2, ratio = 0.5, not > 0.5).
    s.append(NetworkEvent(domain=EventDomain.QOS, source="qos-mon", entity_id="flowA",
                          payload={"latency_ms": 12.0, "jitter_ms": 2.0, "packet_loss": 0.002}))
    s.append(NetworkEvent(domain=EventDomain.QOS, source="qos-mon", entity_id="flowB",
                          payload={"latency_ms": 45.0, "jitter_ms": 9.0, "packet_loss": 0.05}))
    s.append(NetworkEvent(domain=EventDomain.THROUGHPUT, source="kpm", entity_id="flowA",
                          payload={"dl_mbps": 120.0}))
    s.append(NetworkEvent(domain=EventDomain.THROUGHPUT, source="kpm", entity_id="flowB",
                          payload={"dl_mbps": 18.0}))
    return s


def test_pack_metadata_and_tools():
    reg = build_registry(store=_store())
    assert PACK["name"] == "xr-qoe"
    assert set(reg.names()) == {
        "xr_qoe_overview", "assess_xr_flow", "correlate_xr_qoe", "recommend_xr_action",
    }


def test_overview_and_assessment():
    reg = build_registry(store=_store())
    ov = reg.get("xr_qoe_overview").invoke()
    assert ov["flows_reporting_qoe"] == 2 and ov["flows_breaching_budget"] == 1
    assert ov["breaching_flows"] == ["flowB"]

    good = reg.get("assess_xr_flow").invoke(entity_id="flowA")
    assert good["verdict"] == "good" and good["breached_kpis"] == [] and good["latency_ms"] == 12.0

    bad = reg.get("assess_xr_flow").invoke(entity_id="flowB")
    assert bad["verdict"] == "degraded"
    assert set(bad["breached_kpis"]) == {"latency_ms", "jitter_ms", "packet_loss", "dl_mbps"}


def test_correlation_and_recommendation():
    reg = build_registry(store=_store())
    corr = reg.get("correlate_xr_qoe").invoke()
    assert corr["degraded_flows"] == ["flowB"]
    assert "flow-specific" in corr["conclusion"]

    rec = reg.get("recommend_xr_action").invoke()
    assert rec["count"] == 1 and rec["recommendations"][0]["flow_id"] == "flowB"
    assert rec["recommendations"][0]["apply_via"] == "intent-to-network (human approval required)"


def test_degrades_without_data():
    reg = build_registry(store=None)
    assert reg.get("xr_qoe_overview").invoke()["flows_reporting_qoe"] == 0
    assert "no XR QoE data" in reg.get("correlate_xr_qoe").invoke()["conclusion"]
    assert reg.get("assess_xr_flow").invoke(entity_id="zzz")["note"]
