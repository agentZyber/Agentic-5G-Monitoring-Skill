"""UERANSIM controller (mocked runner) + NWDAF stub + connector catalog."""

import pytest

from zortenet.connectors.base import CONNECTOR_CATALOG, catalog
from zortenet.connectors.nwdaf import NWDAFClient
from zortenet.connectors.ueransim import RunResult, UERANSIMController


class FakeRunner:
    def __init__(self, responses=None, fail=False):
        self.responses = responses or {}
        self.fail = fail
        self.calls = []

    def __call__(self, argv):
        self.calls.append(argv)
        if self.fail:
            return RunResult(1, "", "docker: no such container")
        key = " ".join(argv)
        for fragment, result in self.responses.items():
            if fragment in key:
                return result
        return RunResult(0, "OK")


def _controller(runner):
    return UERANSIMController(container="ueransim-ue", runner=runner)


# ---- UERANSIM ----------------------------------------------------------------


def test_argv_shape_uses_docker_exec_and_nr_cli():
    runner = FakeRunner()
    _controller(runner).ue_status("imsi-001010000000001")
    argv = runner.calls[0]
    assert argv[:3] == ["docker", "exec", "ueransim-ue"]
    assert argv[3].endswith("nr-cli")
    assert argv[4:] == ["imsi-001010000000001", "-e", "status"]


def test_list_nodes_parses_lines():
    runner = FakeRunner({"-d": RunResult(0, "UERANSIM-gnb-1-1-1\nimsi-001010000000001\n")})
    nodes = _controller(runner).list_nodes()
    assert nodes == ["UERANSIM-gnb-1-1-1", "imsi-001010000000001"]


def test_deregister_modes_validated():
    runner = FakeRunner()
    ctl = _controller(runner)
    out = ctl.deregister("imsi-001", mode="switch-off")
    assert out["ok"] and out["command"] == "deregister switch-off"
    with pytest.raises(ValueError):
        ctl.deregister("imsi-001", mode="yank-cable")


def test_session_commands():
    runner = FakeRunner()
    ctl = _controller(runner)
    assert ctl.ps_establish("imsi-001")["command"] == "ps-establish IPv4 --sst 1"
    assert ctl.ps_release("imsi-001", ps_id=2)["command"] == "ps-release 2"
    assert ctl.ps_list("imsi-001")["command"] == "ps-list"
    assert ctl.gnb_ue_list("UERANSIM-gnb-1")["command"] == "ue-list"


def test_failure_surfaces_output_and_is_available():
    down = FakeRunner(fail=True)
    ctl = _controller(down)
    out = ctl.ue_status("imsi-001")
    assert out["ok"] is False
    assert "no such container" in out["output"]
    assert ctl.is_available() is False

    up = FakeRunner({"-d": RunResult(0, "imsi-001\n")})
    assert _controller(up).is_available() is True


def test_no_docker_mode():
    runner = FakeRunner()
    UERANSIMController(runner=runner, use_docker=False, nr_cli="nr-cli").ue_status("imsi-1")
    assert runner.calls[0][0] == "nr-cli"  # no docker exec prefix


# ---- NWDAF stub -----------------------------------------------------------------


class FakeSession:
    def __init__(self, status_code=200, payload=None, fail=False):
        self.status_code = status_code
        self.payload = payload or {}
        self.fail = fail
        self.requests = []

    def get(self, url, **kwargs):
        self.requests.append({"url": url, **kwargs})
        if self.fail:
            raise ConnectionError("refused")

        class R:
            status_code = self.status_code

            def json(inner):
                return self.payload

        return R()


def test_nwdaf_analytics_happy_path():
    session = FakeSession(payload={"loadLevelInformation": 3})
    client = NWDAFClient(base_url="http://nwdaf:29520", session=session)
    out = client.analytics("LOAD_LEVEL_INFORMATION")
    assert out["available"] is True
    assert out["analytics"]["loadLevelInformation"] == 3
    assert session.requests[0]["params"]["event-id"] == "LOAD_LEVEL_INFORMATION"


def test_nwdaf_unknown_event_id_rejected_locally():
    out = NWDAFClient(session=FakeSession()).analytics("NOT_A_THING")
    assert out["available"] is False
    assert "unknown event-id" in out["error"]


def test_nwdaf_degrades_with_hint():
    out = NWDAFClient(session=FakeSession(fail=True)).analytics("NF_LOAD")
    assert out["available"] is False
    assert "free5GC" in out["hint"]  # honest: default testbed ships no NWDAF


# ---- catalog ---------------------------------------------------------------------


def test_connector_catalog_marks_stub_and_fault_injection():
    entries = {e["name"]: e for e in catalog()}
    assert entries["nwdaf"]["status"] == "stub"
    assert "fault-injection" in entries["ueransim"]["capabilities"]
    assert set(CONNECTOR_CATALOG) == {
        "prometheus", "open5gs", "ueransim", "nwdaf", "amarisoft", "a1-ric",
    }
    # honesty markers: hardware-facing connectors are explicitly live-pending until Tier-2/3
    assert entries["amarisoft"]["status"] == "live-pending"
    assert entries["a1-ric"]["status"] == "live-pending"
    assert "control" in entries["amarisoft"]["capabilities"]
