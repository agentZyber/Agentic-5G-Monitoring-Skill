"""ntn-ops pack: terminal-vs-beam correlation over seeded events + graceful empty store."""

from zortenet.core.bus import EventStore
from zortenet.core.events import EventDomain, NetworkEvent
from zortenet.packs.ntn_ops import PACK, build_registry


def _store():
    s = EventStore()
    # beam B1 has two terminals: term1 is degraded (low SINR), term2 is healthy ->
    # NOT a strict majority degraded => the beam is fine => terminal-specific.
    s.append(NetworkEvent(domain=EventDomain.RAN_KPI, source="ntn", entity_id="term1",
                          payload={"propagation_delay_ms": 250.0, "doppler_hz": 12000.0, "sinr": -3.0, "beam_id": "B1"}))
    s.append(NetworkEvent(domain=EventDomain.RAN_KPI, source="ntn", entity_id="term2",
                          payload={"propagation_delay_ms": 240.0, "doppler_hz": 11000.0, "sinr": 9.0, "beam_id": "B1"}))
    s.append(NetworkEvent(domain=EventDomain.QOS, source="ntn", entity_id="term1", payload={"latency_ms": 620.0}))
    s.append(NetworkEvent(domain=EventDomain.QOS, source="ntn", entity_id="term2", payload={"latency_ms": 540.0}))
    return s


def test_pack_metadata_and_tools():
    reg = build_registry(store=_store())
    assert PACK["name"] == "ntn-ops"
    assert PACK["connectors"] == ["amarisoft", "prometheus"]
    assert set(reg.names()) == {
        "ntn_overview", "assess_ntn_terminal", "correlate_ntn_link", "recommend_ntn_action",
    }


def test_overview_and_assessment():
    reg = build_registry(store=_store())
    ov = reg.get("ntn_overview").invoke()
    assert ov["terminals_reporting"] == 2
    assert ov["distinct_beams"] == ["B1"]
    assert ov["terminals_breaching_thresholds"] == 1
    assert ov["breaching_terminals"] == ["term1"]

    bad = reg.get("assess_ntn_terminal").invoke(entity_id="term1")
    assert bad["verdict"] == "degraded" and bad["breached_kpis"] == ["sinr"]
    assert bad["beam_id"] == "B1" and bad["sinr"] == -3.0 and bad["latency_ms"] == 620.0

    good = reg.get("assess_ntn_terminal").invoke(entity_id="term2")
    assert good["verdict"] == "ok" and good["breached_kpis"] == [] and good["beam_id"] == "B1"


def test_correlation_terminal_specific():
    reg = build_registry(store=_store())
    corr = reg.get("correlate_ntn_link").invoke()
    # one of two terminals on B1 degraded -> ratio 0.5, NOT a strict majority -> beam is healthy.
    assert corr["beamwide_degraded"] == []
    assert corr["degraded_terminals"] == 1
    assert "terminal-specific" in corr["conclusion"]
    b1 = {x["entity_id"]: x for x in corr["beams"]["B1"]}
    assert b1["term1"]["degraded"] is True and b1["term2"]["degraded"] is False


def test_recommendation():
    reg = build_registry(store=_store())
    rec = reg.get("recommend_ntn_action").invoke()
    assert rec["count"] == 1
    r = rec["recommendations"][0]
    assert r["entity_id"] == "term1" and r["scope"] == "terminal-specific" and r["beam_id"] == "B1"
    assert "beam reselection" in r["action"]
    assert r["apply_via"] == "intent-to-network (human approval required)"


def test_degrades_without_data():
    reg = build_registry(store=None)
    assert reg.get("ntn_overview").invoke()["terminals_reporting"] == 0
    assert "no NTN data" in reg.get("correlate_ntn_link").invoke()["conclusion"]
    assert reg.get("assess_ntn_terminal").invoke(entity_id="ghost")["note"]
    assert reg.get("recommend_ntn_action").invoke()["count"] == 0
