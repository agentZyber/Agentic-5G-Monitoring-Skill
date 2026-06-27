"""energy-agent pack: power-vs-load correlation over seeded events + graceful empty store."""

from zortenet.core.bus import EventStore
from zortenet.core.events import EventDomain, NetworkEvent
from zortenet.packs.energy_agent import PACK, build_registry


def _store():
    s = EventStore()
    # cell 1: powered but idle -> energy-saving candidate; cell 2: powered and busy -> justified
    s.append(NetworkEvent(domain=EventDomain.ENERGY, source="meter", entity_id="1", payload={"power_w": 35.0}))
    s.append(NetworkEvent(domain=EventDomain.ENERGY, source="meter", entity_id="2", payload={"power_w": 40.0}))
    s.append(NetworkEvent(domain=EventDomain.THROUGHPUT, source="kpm", entity_id="1", payload={"prb_util": 4.0, "dl_mbps": 1.0}))
    s.append(NetworkEvent(domain=EventDomain.THROUGHPUT, source="kpm", entity_id="2", payload={"prb_util": 85.0, "dl_mbps": 220.0}))
    return s


def test_pack_metadata_and_tools():
    reg = build_registry(store=_store())
    assert PACK["name"] == "energy-agent"
    assert set(reg.names()) == {
        "energy_overview", "assess_cell_energy", "correlate_energy_load", "recommend_energy_saving",
    }


def test_overview_and_assessment():
    reg = build_registry(store=_store())
    ov = reg.get("energy_overview").invoke()
    assert ov["cells_reporting_power"] == 2 and ov["total_power_w"] == 75.0
    assert ov["under_utilised_cells"] == ["1"]

    waste = reg.get("assess_cell_energy").invoke(cell_id="1")
    assert waste["verdict"] == "wasteful" and waste["low_load"] is True and waste["power_w"] == 35.0

    busy = reg.get("assess_cell_energy").invoke(cell_id="2")
    assert busy["verdict"] == "overloaded" and busy["low_load"] is False


def test_correlation_and_recommendation():
    reg = build_registry(store=_store())
    corr = reg.get("correlate_energy_load").invoke()
    assert corr["energy_saving_candidates"] == ["1"]
    assert "cell-specific" in corr["conclusion"]

    rec = reg.get("recommend_energy_saving").invoke()
    assert rec["count"] == 1 and rec["recommendations"][0]["cell_id"] == "1"
    assert rec["recommendations"][0]["expected_saving_w"] == 35.0


def test_degrades_without_data():
    reg = build_registry(store=None)
    assert reg.get("energy_overview").invoke()["cells_reporting_power"] == 0
    assert "no energy" in reg.get("correlate_energy_load").invoke()["conclusion"]
    assert reg.get("assess_cell_energy").invoke(cell_id="9")["note"]
