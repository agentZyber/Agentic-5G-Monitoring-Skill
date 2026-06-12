"""AG-UI stream + Stage-2 integration: ingest/query endpoints and the cross-domain scenario.

The cross-domain test is the mock version of the Stage-2 exit gate: replayed multi-domain
events → store-backed tools → agent correlates QoS degradation with mobility. The live version
runs at testbed bring-up.
"""

import json

from fastapi.testclient import TestClient

from zortenet.agent.runtime import AgentResult
from zortenet.app import create_app
from zortenet.core.events import EventDomain, NetworkEvent, Severity
from zortenet.interop.agui import agui_events
from zortenet.llm.base import LLMProvider, LLMResponse


class ScriptedProvider(LLMProvider):
    name = "scripted"
    model = "fake-model"

    def __init__(self, responses):
        self.responses = list(responses)

    def is_available(self):
        return True

    def chat(self, messages, tools=None, **kwargs):
        return self.responses.pop(0)


def _tc(name, args):
    return {"function": {"name": name, "arguments": args}}


# ---- AG-UI event derivation (pure) -----------------------------------------------


def test_agui_event_sequence_for_tool_run():
    result = AgentResult(
        answer="All good.",
        messages=[
            {"role": "system", "content": "s"},
            {"role": "user", "content": "q"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [_tc("network_health_overview", {})],
            },
            {"role": "tool", "name": "network_health_overview", "content": '{"ok": true}'},
            {"role": "assistant", "content": "All good."},
        ],
        iterations=2,
        tool_calls_made=1,
    )
    events = list(agui_events(result, thread_id="t1", run_id="r1"))
    types = [e["type"] for e in events]
    assert types == [
        "RUN_STARTED",
        "TOOL_CALL_START",
        "TOOL_CALL_ARGS",
        "TOOL_CALL_END",
        "TOOL_CALL_RESULT",
        "TEXT_MESSAGE_START",
        "TEXT_MESSAGE_CONTENT",
        "TEXT_MESSAGE_END",
        "RUN_FINISHED",
    ]
    start = events[1]
    assert start["toolCallName"] == "network_health_overview"
    result_event = events[4]
    assert result_event["toolCallId"] == start["toolCallId"]
    assert json.loads(result_event["content"])["ok"] is True
    assert events[6]["delta"] == "All good."
    assert events[0]["threadId"] == "t1" and events[-1]["runId"] == "r1"


def test_agui_no_tools_run_is_minimal():
    result = AgentResult(answer="hi", messages=[{"role": "assistant", "content": "hi"}])
    types = [e["type"] for e in agui_events(result)]
    assert types == [
        "RUN_STARTED",
        "TEXT_MESSAGE_START",
        "TEXT_MESSAGE_CONTENT",
        "TEXT_MESSAGE_END",
        "RUN_FINISHED",
    ]


# ---- AG-UI over SSE through the app -------------------------------------------------


def test_agui_run_streams_sse():
    provider = ScriptedProvider([LLMResponse(content="Network looks healthy.")])
    app = create_app(provider=provider, trajectory=None)
    with TestClient(app) as client:
        resp = client.post("/agui/run", json={"message": "status?", "thread_id": "t-9"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    payloads = [
        json.loads(line[len("data: ") :])
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]
    types = [p["type"] for p in payloads]
    assert types[0] == "RUN_STARTED" and types[-1] == "RUN_FINISHED"
    assert payloads[0]["threadId"] == "t-9"
    content = next(p for p in payloads if p["type"] == "TEXT_MESSAGE_CONTENT")
    assert content["delta"] == "Network looks healthy."


# ---- event ingest/query endpoints ----------------------------------------------------


def test_events_ingest_query_and_stats():
    provider = ScriptedProvider([])
    app = create_app(provider=provider, trajectory=None)
    with TestClient(app) as client:
        # NetworkEvent shape
        r1 = client.post(
            "/events",
            json={
                "domain": "qos",
                "source": "probe",
                "entity_id": "ue7",
                "payload": {"latency_ms": 250},
                "severity": "warning",
            },
        )
        assert r1.status_code == 200
        # legacy callback shape
        r2 = client.post(
            "/events",
            json={"externalId": "ue7", "type": "alert", "locationInfo": {"cellId": "C9"}},
        )
        assert r2.json()["domain"] == "location"
        # garbage shape rejected
        assert client.post("/events", json={"foo": 1}).status_code == 422

        recent = client.get("/events/recent", params={"entity_id": "ue7"}).json()
        assert recent["count"] == 2
        stats = client.get("/events/stats").json()
        assert stats["total"] == 2
        assert stats["by_domain"] == {"qos": 1, "location": 1}

        connectors = client.get("/connectors").json()
        assert {c["name"] for c in connectors} == {
            "prometheus", "open5gs", "ueransim", "nwdaf", "amarisoft", "a1-ric",
        }


# ---- the cross-domain scenario (mock exit gate) ----------------------------------------


def test_cross_domain_correlation_scenario():
    """QoS degradation + mobility events for one UE → agent correlates via store-backed tools."""
    provider = ScriptedProvider(
        [
            LLMResponse(content="", tool_calls=[_tc("diagnose_entity", {"entity_id": "ue42"})]),
            LLMResponse(content="", tool_calls=[_tc("audit_ue_mobility", {"entity_id": "ue42"})]),
            LLMResponse(
                content=(
                    "ue42's latency spiked to 300ms right after it moved C1→C2→C3→C4→C5; "
                    "the QoS degradation correlates with its mobility (suspected qos-degradation)."
                )
            ),
        ]
    )
    app = create_app(provider=provider, trajectory=None)

    # Seed the app's bus with a multi-domain story (what replay does from recorded data).
    bus = app.state.bus
    for cell in ["C1", "C2", "C3", "C4", "C5"]:
        bus.publish(
            NetworkEvent(
                domain=EventDomain.LOCATION, source="replay", entity_id="ue42",
                payload={"cell_id": cell},
            )
        )
    bus.publish(
        NetworkEvent(
            domain=EventDomain.QOS, source="replay", entity_id="ue42",
            severity=Severity.ALERT, event_type="QOS_MONITORING",
            payload={"latency_ms": 300},
        )
    )

    with TestClient(app) as client:
        body = client.post(
            "/agent/ask",
            json={"message": "why is ue42 slow?", "include_messages": True},
        ).json()

    assert "correlates with its mobility" in body["answer"]
    assert body["tool_calls_made"] == 2 and body["tool_errors"] == 0
    tool_msgs = [m for m in body["messages"] if m["role"] == "tool"]
    diag = json.loads(tool_msgs[0]["content"])
    assert "qos-degradation" in diag["suspected_issues"]  # evidence, not vibes
    audit = json.loads(tool_msgs[1]["content"])
    assert audit["distinct_cells"] == 5 and audit["cell_hopping"] is True
