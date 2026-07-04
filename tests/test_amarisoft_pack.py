"""amarisoft pack: live-shape tools over a fake transport + graceful degradation."""

from corelab.connectors.amarisoft import AmarisoftClient
from corelab.packs.amarisoft import PACK, build_registry


class FakeTransport:
    def __init__(self, responses=None, fail=False):
        self.responses = responses or {}
        self.fail = fail

    def __call__(self, request):
        if self.fail:
            raise ConnectionError("box down")
        return self.responses.get(request["message"], {})


def _gnb(fail=False):
    return AmarisoftClient(transport=FakeTransport({
        "config_get": {"nr_cells": {"1": {"gain": 0, "rf_port": 0}}, "tx_channels": [{"gain": 89.75}]},
        "stats": {"cells": {"1": {"dl_bitrate": 1000, "ul_bitrate": 500, "n_ue": 2}},
                  "rf_ports": {"0": {}}, "cpu": {"global": 12}},
        "ue_get": {"ue_list": [{"ran_ue_id": 1, "rsrp": -95}, {"ran_ue_id": 2, "rsrp": -100}]},
    }, fail=fail))


def _core(fail=False):
    return AmarisoftClient(transport=FakeTransport({
        "config_get": {},
        "stats": {"emm_registered_ue_count": 2, "ng_connections": 1, "s1_connections": 0, "users": []},
    }, fail=fail))


def test_pack_metadata_and_tools():
    reg = build_registry(amarisoft=_gnb(), amarisoft_core=_core())
    assert PACK["name"] == "amarisoft"
    assert set(reg.names()) == {
        "amari_gnb_status", "amari_attached_ues", "amari_cell_kpis", "amari_cell_power",
        "amari_core_registration",
    }


def test_tools_return_live_shapes():
    reg = build_registry(amarisoft=_gnb(), amarisoft_core=_core())
    st = reg.get("amari_gnb_status").invoke()
    assert st["active_cells"] == ["1"] and st["num_cells"] == 1 and st["rf_ports"] == ["0"]

    ues = reg.get("amari_attached_ues").invoke()
    assert ues["attached_ue_count"] == 2 and ues["ues"][0]["rsrp"] == -95

    kpi = reg.get("amari_cell_kpis").invoke(cell_id="1")
    assert kpi["dl_bitrate"] == 1000 and kpi["n_ue"] == 2

    missing = reg.get("amari_cell_kpis").invoke(cell_id="9")
    assert "not active" in missing["error"] and missing["active_cells"] == ["1"]

    core = reg.get("amari_core_registration").invoke()
    assert core["emm_registered_ue_count"] == 2 and core["ng_connections"] == 1

    power = reg.get("amari_cell_power").invoke()
    cell = power["cells"][0]
    assert cell["cell_id"] == "1" and cell["power_offset_db"] == 0
    assert cell["status"] == "nominal" and cell["rf_abs_gain_db"] == 89.75


def test_degrades_without_clients(monkeypatch):
    monkeypatch.delenv("AMARISOFT_WS_URL", raising=False)
    monkeypatch.delenv("AMARISOFT_CORE_WS_URL", raising=False)
    reg = build_registry(amarisoft=None, amarisoft_core=None)
    assert "unavailable" in reg.get("amari_gnb_status").invoke()
    assert "AMARISOFT_WS_URL" in reg.get("amari_attached_ues").invoke()
    assert "AMARISOFT_CORE_WS_URL" in reg.get("amari_core_registration").invoke()


def test_degrades_when_box_unreachable():
    reg = build_registry(amarisoft=_gnb(fail=True), amarisoft_core=_core(fail=True))
    st = reg.get("amari_gnb_status").invoke()
    assert st["ok"] is False and "unreachable" in st["error"]
