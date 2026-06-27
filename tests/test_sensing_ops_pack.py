"""sensing-ops pack: detection-quality-vs-comms-load correlation over seeded events + graceful empty store."""

from zortenet.core.bus import EventStore
from zortenet.core.events import EventDomain, NetworkEvent
from zortenet.packs.sensing_ops import PACK, build_registry


def _store():
    s = EventStore()
    # tgt1: weak sensing (low SNR) but LOW comms load -> target/clutter-specific (no contention)
    s.append(NetworkEvent(domain=EventDomain.SENSING, source="isac", entity_id="tgt1",
                          payload={"sensing_snr_db": 6.0, "detections": 1, "range_m": 120.0, "velocity_mps": 3.0}))
    # tgt2: reliable sensing (high SNR)
    s.append(NetworkEvent(domain=EventDomain.SENSING, source="isac", entity_id="tgt2",
                          payload={"sensing_snr_db": 18.0, "detections": 4, "range_m": 80.0, "velocity_mps": 12.0}))
    # comms load on the same cells: weak cell tgt1 is NOT congested, tgt2 is busy
    s.append(NetworkEvent(domain=EventDomain.THROUGHPUT, source="kpm", entity_id="tgt1", payload={"prb_util": 20.0}))
    s.append(NetworkEvent(domain=EventDomain.THROUGHPUT, source="kpm", entity_id="tgt2", payload={"prb_util": 85.0}))
    return s


def test_pack_metadata_and_tools():
    reg = build_registry(store=_store())
    assert PACK["name"] == "sensing-ops"
    assert PACK["connectors"] == ["amarisoft", "prometheus"]
    assert set(reg.names()) == {
        "sensing_overview", "assess_sensing_cell", "correlate_sensing_comms", "recommend_sensing_action",
    }


def test_overview_and_assessment():
    reg = build_registry(store=_store())
    ov = reg.get("sensing_overview").invoke()
    assert ov["sensing_cells_reporting"] == 2 and ov["total_detections"] == 5
    assert ov["weak_sensing_cells"] == ["tgt1"] and ov["weak_count"] == 1

    weak = reg.get("assess_sensing_cell").invoke(entity_id="tgt1")
    assert weak["verdict"] == "weak" and weak["sensing_snr_db"] == 6.0 and weak["prb_util"] == 20.0

    good = reg.get("assess_sensing_cell").invoke(entity_id="tgt2")
    assert good["verdict"] == "reliable" and good["detections"] == 4.0


def test_correlation_and_recommendation():
    reg = build_registry(store=_store())
    corr = reg.get("correlate_sensing_comms").invoke()
    # exactly one weak cell, and it has LOW prb -> target/clutter-specific
    assert corr["contended_cells"] == []
    assert "target/clutter-specific" in corr["conclusion"]
    assert len(corr["cells"]) == 1
    assert corr["cells"][0]["entity_id"] == "tgt1" and corr["cells"][0]["comms_contention"] is False

    rec = reg.get("recommend_sensing_action").invoke()
    assert rec["count"] == 1 and rec["recommendations"][0]["entity_id"] == "tgt1"
    assert rec["recommendations"][0]["action"] == "investigate clutter/target scene"
    assert rec["recommendations"][0]["apply_via"] == "intent-to-network (human approval required)"


def test_degrades_without_data():
    reg = build_registry(store=None)
    assert reg.get("sensing_overview").invoke()["sensing_cells_reporting"] == 0
    assert "no sensing" in reg.get("correlate_sensing_comms").invoke()["conclusion"]
    assert reg.get("assess_sensing_cell").invoke(entity_id="x9")["note"]
    assert reg.get("recommend_sensing_action").invoke()["count"] == 0
