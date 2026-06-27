"""ai-native pack: predicted-vs-observed analytics correlation over seeded events + graceful empty store."""

from zortenet.core.bus import EventStore
from zortenet.core.events import EventDomain, NetworkEvent
from zortenet.packs.ai_native import PACK, build_registry


def _store():
    s = EventStore()
    # slice1: observed close to predicted -> on-model; slice2: observed far off -> anomalous (>20%)
    s.append(NetworkEvent(domain=EventDomain.SLICE, source="nwdaf", entity_id="slice1",
                          payload={"observed": 102.0, "predicted": 100.0, "metric": "dl_throughput_mbps"}))
    s.append(NetworkEvent(domain=EventDomain.QOS, source="nwdaf", entity_id="slice2",
                          payload={"observed": 50.0, "predicted": 100.0, "metric": "latency_ms"}))
    return s


def test_pack_metadata_and_tools():
    reg = build_registry(store=_store())
    assert PACK["name"] == "ai-native"
    assert PACK["connectors"] == ["nwdaf", "prometheus"]
    assert set(reg.names()) == {
        "ai_native_overview", "assess_analytics", "correlate_predictions", "recommend_ai_action",
    }


def test_overview_and_assessment():
    reg = build_registry(store=_store())
    ov = reg.get("ai_native_overview").invoke()
    assert ov["entities_with_analytics"] == 2
    assert ov["anomalous_entities"] == ["slice2"]
    assert ov["anomalous_count"] == 1

    on_model = reg.get("assess_analytics").invoke(entity_id="slice1")
    assert on_model["verdict"] == "on-model"
    assert on_model["observed"] == 102.0 and on_model["predicted"] == 100.0
    assert on_model["metric"] == "dl_throughput_mbps"
    assert on_model["deviation"] < 0.2

    anomalous = reg.get("assess_analytics").invoke(entity_id="slice2")
    assert anomalous["verdict"] == "anomalous"
    assert anomalous["deviation"] == 0.5


def test_correlation_and_recommendation():
    reg = build_registry(store=_store())
    corr = reg.get("correlate_predictions").invoke()
    assert corr["anomalous_entities"] == ["slice2"]
    assert "entity-specific" in corr["conclusion"]
    assert "1/2" in corr["conclusion"]
    evidence = {e["entity_id"]: e for e in corr["entities"]}
    assert evidence["slice1"]["anomalous"] is False
    assert evidence["slice2"]["anomalous"] is True

    rec = reg.get("recommend_ai_action").invoke()
    assert rec["systemic"] is False
    assert rec["count"] == 1
    assert rec["recommendations"][0]["entity_id"] == "slice2"
    assert rec["recommendations"][0]["apply_via"] == "intent-to-network (human approval required)"


def test_degrades_without_data():
    reg = build_registry(store=None)
    assert reg.get("ai_native_overview").invoke()["entities_with_analytics"] == 0
    assert "no analytics data" in reg.get("correlate_predictions").invoke()["conclusion"]
    assert reg.get("assess_analytics").invoke(entity_id="nope")["note"]
    assert reg.get("recommend_ai_action").invoke()["count"] == 0
