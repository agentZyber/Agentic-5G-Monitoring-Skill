"""Connectors (mocked HTTP) + the netops-copilot pack's graceful degradation."""

import pytest

from zortenet.connectors.open5gs import Open5GSClient
from zortenet.connectors.prometheus import PrometheusClient
from zortenet.packs.netops_copilot import PACK, build_registry


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    """Routes (method, url-suffix) to canned responses; records requests."""

    def __init__(self, routes=None, fail=False):
        self.routes = routes or {}
        self.fail = fail
        self.requests = []

    def _respond(self, method, url, **kwargs):
        self.requests.append({"method": method, "url": url, **kwargs})
        if self.fail:
            raise ConnectionError("no route to host")
        for suffix, response in self.routes.items():
            if url.endswith(suffix) or suffix in url:
                return response
        return FakeResponse(status_code=404)

    def get(self, url, **kwargs):
        return self._respond("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self._respond("POST", url, **kwargs)


# ---- Prometheus -------------------------------------------------------------


def test_prometheus_instant_query_success():
    session = FakeSession(
        {
            "/api/v1/query": FakeResponse(
                payload={
                    "status": "success",
                    "data": {"result": [{"metric": {"job": "open5gs"}, "value": [1, "42"]}]},
                }
            )
        }
    )
    client = PrometheusClient(base_url="http://prom:9090", session=session)
    result = client.instant_query("up")
    assert result[0]["value"][1] == "42"
    assert session.requests[0]["params"]["query"] == "up"


def test_prometheus_query_error_status_raises():
    session = FakeSession(
        {"/api/v1/query": FakeResponse(payload={"status": "error", "error": "bad expr"})}
    )
    client = PrometheusClient(base_url="http://prom:9090", session=session)
    with pytest.raises(RuntimeError, match="bad expr"):
        client.instant_query("nonsense{")


def test_prometheus_targets_health_simplifies():
    session = FakeSession(
        {
            "/api/v1/targets": FakeResponse(
                payload={
                    "data": {
                        "activeTargets": [
                            {
                                "labels": {"job": "open5gs", "instance": "amf:9091"},
                                "health": "up",
                                "lastError": "",
                            },
                            {
                                "labels": {"job": "zortenet", "instance": "zortenet:5000"},
                                "health": "down",
                                "lastError": "connection refused",
                            },
                        ]
                    }
                }
            )
        }
    )
    client = PrometheusClient(base_url="http://prom:9090", session=session)
    targets = client.targets_health()
    assert {"job": "open5gs", "instance": "amf:9091", "health": "up", "last_error": None} in targets
    assert targets[1]["last_error"] == "connection refused"


def test_prometheus_is_available_never_raises():
    assert PrometheusClient(session=FakeSession(fail=True)).is_available() is False


# ---- Open5GS ----------------------------------------------------------------


def test_open5gs_token_then_authorized_list():
    session = FakeSession(
        {
            "/oauth2/token": FakeResponse(payload={"access_token": "tok123"}),
            "/namf-subscription/v1/subscriptions": FakeResponse(
                payload={"subscriptions": [{"subscriptionId": "s1", "ueId": "ue1@t"}]}
            ),
        }
    )
    client = Open5GSClient(base_url="http://core:29508", nrf_url="http://nrf:29502", session=session)
    subs = client.list_subscriptions()
    assert subs == [{"subscriptionId": "s1", "ueId": "ue1@t"}]
    list_req = next(r for r in session.requests if "namf-subscription" in r["url"])
    assert list_req["headers"]["Authorization"] == "Bearer tok123"


def test_open5gs_token_fallback_to_static_bearer():
    client = Open5GSClient(bearer_token="static-tok", session=FakeSession(fail=True))
    assert client.get_auth_token() == "static-tok"


def test_open5gs_reads_degrade_to_none_or_empty():
    client = Open5GSClient(session=FakeSession(fail=True))
    assert client.list_subscriptions() == []
    assert client.get_ue_location("ue1@t") is None
    assert client.get_ue_info("ue1@t") is None
    assert client.is_available() is False


def test_open5gs_ue_endpoints_mirror_legacy_paths():
    session = FakeSession(
        {
            "/oauth2/token": FakeResponse(payload={"access_token": "t"}),
            "/namf-loc/v1/ues/ue1@t/location": FakeResponse(payload={"cellId": "C1"}),
            "/namf-comm/v1/ues/ue1@t": FakeResponse(payload={"supi": "imsi-001"}),
        }
    )
    client = Open5GSClient(base_url="http://core:29508", nrf_url="http://nrf:29502", session=session)
    assert client.get_ue_location("ue1@t") == {"cellId": "C1"}
    assert client.get_ue_info("ue1@t") == {"supi": "imsi-001"}


# ---- netops-copilot pack ------------------------------------------------------


def _offline_clients():
    return (
        Open5GSClient(session=FakeSession(fail=True)),
        PrometheusClient(session=FakeSession(fail=True)),
    )


def test_pack_metadata_and_tools():
    core, prom = _offline_clients()
    reg = build_registry(open5gs=core, prometheus=prom)
    assert PACK["name"] == "netops-copilot"
    assert {
        "network_health_overview",
        "query_kpi",
        "list_core_subscriptions",
        "get_ue_status",
        "get_recent_events",
    } == set(reg.names())


def test_get_recent_events_degrades_without_store():
    core, prom = _offline_clients()
    reg = build_registry(open5gs=core, prometheus=prom)  # no store wired
    assert "unavailable" in reg.get("get_recent_events").invoke()


def test_get_recent_events_reads_store():
    from zortenet.core.bus import EventStore
    from zortenet.core.events import EventDomain, NetworkEvent

    store = EventStore()
    store.append(
        NetworkEvent(
            domain=EventDomain.QOS, source="t", entity_id="ue1", payload={"latency_ms": 99}
        )
    )
    core, prom = _offline_clients()
    reg = build_registry(open5gs=core, prometheus=prom, store=store)
    out = reg.get("get_recent_events").invoke(domain="qos")
    assert out["count"] == 1
    assert "latency_ms=99" in out["events"][0]
    assert out["stats"]["total"] == 1


def test_tools_degrade_gracefully_when_everything_is_down():
    core, prom = _offline_clients()
    reg = build_registry(open5gs=core, prometheus=prom)

    overview = reg.get("network_health_overview").invoke()
    assert overview == {"prometheus_reachable": False, "open5gs_reachable": False}

    assert "unavailable" in reg.get("query_kpi").invoke(promql="up")
    assert "unavailable" in reg.get("list_core_subscriptions").invoke()
    assert "unavailable" in reg.get("get_ue_status").invoke(external_id="ue1@t")


def test_query_kpi_happy_path():
    prom_session = FakeSession(
        {
            "/-/ready": FakeResponse(),
            "/api/v1/query": FakeResponse(
                payload={
                    "status": "success",
                    "data": {"result": [{"metric": {}, "value": [1, "7"]}]},
                }
            ),
        }
    )
    reg = build_registry(
        open5gs=Open5GSClient(session=FakeSession(fail=True)),
        prometheus=PrometheusClient(session=prom_session),
    )
    out = reg.get("query_kpi").invoke(promql="fivegs_amffunction_rm_registeredsubnbr")
    assert out["result_count"] == 1
    assert out["results"][0]["value"][1] == "7"


def test_get_ue_status_combines_info_and_location():
    core_session = FakeSession(
        {
            "/oauth2/token": FakeResponse(payload={"access_token": "t"}),
            "/namf-subscription/v1/subscriptions": FakeResponse(payload=[]),
            "/namf-loc/v1/ues/ue1@t/location": FakeResponse(payload={"cellId": "C1"}),
            "/namf-comm/v1/ues/ue1@t": FakeResponse(payload={"supi": "imsi-001"}),
        }
    )
    reg = build_registry(
        open5gs=Open5GSClient(session=core_session),
        prometheus=PrometheusClient(session=FakeSession(fail=True)),
    )
    out = reg.get("get_ue_status").invoke(external_id="ue1@t")
    assert out["info"]["supi"] == "imsi-001"
    assert out["location"]["cellId"] == "C1"
