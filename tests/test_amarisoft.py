"""Amarisoft connector + executor against a fake transport (live validation is Tier-3 scope)."""

import json

from zortenet.connectors.amarisoft import AmarisoftClient, AmarisoftExecutor, websocket_transport
from zortenet.intent.models import Expectation, NetworkIntent


class FakeTransport:
    def __init__(self, responses=None, fail=False):
        self.responses = responses or {}
        self.fail = fail
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        if self.fail:
            raise ConnectionError("ws refused")
        return self.responses.get(request["message"], {})


def test_request_shape_has_message_field():
    transport = FakeTransport({"stats": {"cells": {"1": {"dl_use": 0.4}}}})
    client = AmarisoftClient(transport=transport)
    out = client.stats()
    assert out["ok"] is True
    assert out["response"]["cells"]["1"]["dl_use"] == 0.4
    assert transport.requests[0] == {"message": "stats"}


def test_ue_list_and_control_calls():
    transport = FakeTransport({"ue_get": {"ue_list": [{"ue_id": 1, "rsrp": -90}]}})
    client = AmarisoftClient(transport=transport)
    assert client.ue_list()["response"]["ue_list"][0]["rsrp"] == -90
    assert transport.requests[0]["stats"] is True

    client.handover(ue_id=1, target_cell=2)
    assert transport.requests[-1] == {"message": "handover", "ue_id": 1, "pcell_id": 2}

    client.cell_power(cell_id=1, gain_db=-10)
    assert transport.requests[-1]["cells"]["1"]["gain"] == -10


def test_unreachable_and_api_error_degrade():
    down = AmarisoftClient(transport=FakeTransport(fail=True))
    out = down.stats()
    assert out["ok"] is False and "unreachable" in out["error"]
    assert down.is_available() is False

    erroring = AmarisoftClient(
        transport=FakeTransport({"config_set": {"error": "bad parameter"}})
    )
    result = erroring.config_set({"x": 1})
    assert result["ok"] is False and "bad parameter" in result["error"]


def _intent(metric="throughput_dl_mbps", value=100):
    return NetworkIntent(
        intent_id="int-amx",
        name="cap slice throughput",
        expectations=[
            Expectation(
                object_type="NETWORK_SLICE", object_instance="slice-embb-01",
                metric=metric, condition="IS_LESS_THAN", value=value,
            )
        ],
    )


def test_executor_plan_and_apply_real_calls():
    transport = FakeTransport({"config_set": {"status": "ok"}})
    executor = AmarisoftExecutor(AmarisoftClient(transport=transport))
    intent = _intent()
    plan = executor.plan(intent)
    assert plan[0]["executable"] is True
    assert plan[0]["params"]["rate_limit"]["dl"] == 100

    outcome = executor.apply(intent, plan)
    assert outcome["simulated"] is False
    assert outcome["ok"] is True
    assert transport.requests[0]["message"] == "config_set"
    assert transport.requests[0]["rate_limit"]["object"] == "slice-embb-01"


def test_websocket_transport_sends_origin_and_consumes_ready(monkeypatch):
    # Regression for the live first-contact fix: Amarisoft rejects the handshake without an
    # Origin header, and sends a `ready` frame that must be consumed before the command reply.
    import websockets.sync.client as wsc

    captured = {}

    class FakeWS:
        def __init__(self):
            self._frames = [
                json.dumps({"message": "ready", "name": "ENB", "type": "ENB"}),
                json.dumps({"message": "stats", "cells": {"1": {"dl_use": 0.3}}}),
            ]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def recv(self, timeout=None):
            return self._frames.pop(0)

        def send(self, data):
            captured["sent"] = json.loads(data)

    def fake_connect(url, **kw):
        captured["url"] = url
        captured["headers"] = kw.get("additional_headers") or kw.get("extra_headers")
        return FakeWS()

    monkeypatch.setattr(wsc, "connect", fake_connect)
    transport = websocket_transport("ws://10.50.101.62:9001/")
    resp = transport({"message": "stats"})

    assert captured["headers"]["Origin"] == "Test"        # the essential header
    assert captured["sent"] == {"message": "stats"}        # 'ready' consumed, then our command sent
    assert resp["cells"]["1"]["dl_use"] == 0.3             # we got the command reply, not the hello


def test_executor_unmapped_metric_is_skipped_not_executed():
    transport = FakeTransport({"config_set": {"status": "ok"}})
    executor = AmarisoftExecutor(AmarisoftClient(transport=transport))
    intent = _intent(metric="latency_ms", value=20)  # latency routes to A1, not Amarisoft
    plan = executor.plan(intent)
    assert plan[0]["executable"] is False
    outcome = executor.apply(intent, plan)
    assert outcome["actions"][0]["result"] == "skipped"
    assert transport.requests == []  # nothing was sent
