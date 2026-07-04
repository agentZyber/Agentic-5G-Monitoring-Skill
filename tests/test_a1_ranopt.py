"""A1 client (mocked REST) + ran-opt-copilot: supervision without bypassing the gate."""

from corelab.connectors.a1_ric import A1PolicyClient
from corelab.core.bus import EventStore
from corelab.core.events import EventDomain, NetworkEvent
from corelab.intent.ledger import IntentLedger
from corelab.packs.ran_opt_copilot import build_registry


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, routes=None, fail=False):
        self.routes = routes or {}
        self.fail = fail
        self.requests = []

    def _respond(self, method, url, **kwargs):
        self.requests.append({"method": method, "url": url, **kwargs})
        if self.fail:
            raise ConnectionError("refused")
        for suffix, resp in self.routes.items():
            if url.endswith(suffix):
                return resp
        return FakeResponse(404, None)

    def get(self, url, **kw):
        return self._respond("GET", url, **kw)

    def put(self, url, **kw):
        return self._respond("PUT", url, **kw)

    def delete(self, url, **kw):
        return self._respond("DELETE", url, **kw)


# ---- A1 client -------------------------------------------------------------------


def test_a1_paths_and_crud():
    session = FakeSession(
        {
            "/a1-p/healthcheck": FakeResponse(200, {}),
            "/a1-p/policytypes": FakeResponse(200, [20008]),
            "/a1-p/policytypes/20008/policies": FakeResponse(200, ["p1"]),
            "/a1-p/policytypes/20008/policies/p1/status": FakeResponse(200, {"enforced": True}),
            "/a1-p/policytypes/20008/policies/p1": FakeResponse(202, {}),
        }
    )
    client = A1PolicyClient(base_url="http://ric:10000", session=session)
    assert client.is_available() is True
    assert client.policy_types() == [20008]
    assert client.policies(20008) == ["p1"]
    assert client.policy_status(20008, "p1")["enforced"] is True

    put = client.put_policy(20008, "p1", {"sliceTarget": {"throughput": 50}})
    assert put["ok"] is True and put["status_code"] == 202
    put_req = [r for r in session.requests if r["method"] == "PUT"][0]
    assert put_req["url"].endswith("/a1-p/policytypes/20008/policies/p1")
    assert put_req["json"]["sliceTarget"]["throughput"] == 50

    assert client.delete_policy(20008, "p1") is True


def test_a1_degrades_when_ric_down():
    client = A1PolicyClient(session=FakeSession(fail=True))
    assert client.is_available() is False
    assert client.policy_types() == []
    assert client.put_policy(1, "p", {})["ok"] is False


# ---- ran-opt-copilot ----------------------------------------------------------------


def _seeded_store():
    store = EventStore()
    for i in range(3):
        store.append(
            NetworkEvent(
                domain=EventDomain.RAN_KPI, source="replay", entity_id="cell-1",
                payload={"prb_usage": 0.7 + i / 10},
            )
        )
    store.append(
        NetworkEvent(
            domain=EventDomain.THROUGHPUT, source="replay", entity_id="slice-embb-01",
            payload={"dl_mbps": 42.0},
        )
    )
    return store


def test_explain_ran_state_uses_store_evidence():
    reg = build_registry(a1=A1PolicyClient(session=FakeSession(fail=True)), store=_seeded_store())
    out = reg.get("explain_ran_state").invoke()
    assert out["ran_kpi_events"] == 3
    assert out["throughput_events"] == 1
    assert "cell-1" in out["entities"] and "slice-embb-01" in out["entities"]
    assert any("prb_usage" in line for line in out["recent"])

    empty = build_registry(a1=A1PolicyClient(session=FakeSession(fail=True)))
    assert "no RAN telemetry" in empty.get("explain_ran_state").invoke()["note"]


def test_policy_tools_degrade_without_ric():
    reg = build_registry(a1=A1PolicyClient(session=FakeSession(fail=True)))
    out = reg.get("list_policy_types").invoke()
    assert out["available"] is False
    assert "Tier-2" in out["note"]  # points at the testbed profile


def test_policy_tools_read_ric():
    session = FakeSession(
        {
            "/a1-p/healthcheck": FakeResponse(200, {}),
            "/a1-p/policytypes": FakeResponse(200, [20008]),
            "/a1-p/policytypes/20008/policies": FakeResponse(200, ["p1"]),
            "/a1-p/policytypes/20008/policies/p1/status": FakeResponse(200, {"enforced": True}),
        }
    )
    reg = build_registry(a1=A1PolicyClient(session=session))
    types = reg.get("list_policy_types").invoke()
    assert types["policy_types"] == [20008]
    policies = reg.get("get_ran_policies").invoke(type_id=20008)
    assert policies["policies"][0]["status"]["enforced"] is True


def test_propose_slice_policy_goes_through_the_ledger_not_the_ric():
    session = FakeSession({"/a1-p/healthcheck": FakeResponse(200, {})})
    ledger = IntentLedger()
    reg = build_registry(a1=A1PolicyClient(session=session), ledger=ledger)

    out = reg.get("propose_slice_policy").invoke(
        slice_id="slice-embb-01",
        metric="latency_ms",
        condition="IS_LESS_THAN",
        value=15,
        rationale="PRB usage trending to 0.9 on cell-1 while slice latency target is at risk",
    )
    assert out["status"] == "draft"
    assert out["validation"]["valid"] is True
    assert "human approval" in out["next_steps"] or "approval" in out["next_steps"]

    # The proposal exists in the shared ledger…
    record = ledger.get(out["intent_id"])
    assert record.intent.expectations[0].object_instance == "slice-embb-01"
    # …and the RIC was never written to (no PUTs — supervision, not bypass).
    assert [r for r in session.requests if r["method"] == "PUT"] == []
