"""A2A task lifecycle + the multi-agent NOC exit-gate scenario (≥3 agents over A2A)."""

import json

from corelab.agent.runtime import AgentRuntime
from corelab.agent.tools import ToolRegistry
from corelab.core.bus import EventStore
from corelab.core.events import EventDomain, NetworkEvent, Severity
from corelab.interop.a2a_tasks import A2ATaskManager
from corelab.llm.base import LLMProvider, LLMResponse
from corelab.multiagent.noc import build_default_specialists, build_registry as noc_registry


class ScriptedProvider(LLMProvider):
    name = "scripted"
    model = "fake"

    def __init__(self, responses):
        self.responses = list(responses)

    def is_available(self):
        return True

    def chat(self, messages, tools=None, **kwargs):
        if not self.responses:
            return LLMResponse(content="(no further reply scripted)")
        return self.responses.pop(0)


class RoutedProvider(LLMProvider):
    """Routes by the user question content — lets ONE provider serve all specialists."""

    name = "routed"
    model = "fake"

    def __init__(self, routes):
        self.routes = routes  # substring -> LLMResponse list (consumed in order)
        self.fallback = LLMResponse(content="no data")

    def is_available(self):
        return True

    def chat(self, messages, tools=None, **kwargs):
        text = " ".join(m.get("content", "") or "" for m in messages)
        for key, responses in self.routes.items():
            if key in text and responses:
                return responses.pop(0)
        return self.fallback


def _tc(name, args):
    return {"function": {"name": name, "arguments": args}}


def _manager(responses, registry=None):
    runtime = AgentRuntime(ScriptedProvider(responses), registry or ToolRegistry())
    return A2ATaskManager(runtime, agent_name="test-agent")


# ---- task lifecycle -------------------------------------------------------------


def test_message_send_completes_task_with_artifact():
    manager = _manager([LLMResponse(content="All cells nominal.")])
    response = manager.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "message/send",
            "params": {
                "message": {
                    "kind": "message",
                    "role": "user",
                    "parts": [{"kind": "text", "text": "status?"}],
                    "messageId": "m1",
                }
            },
        }
    )
    task = response["result"]
    assert task["kind"] == "task"
    assert task["status"]["state"] == "completed"
    assert task["artifacts"][0]["parts"][0]["text"] == "All cells nominal."
    roles = [m["role"] for m in task["history"]]
    assert roles == ["user", "agent"]
    assert task["history"][0]["taskId"] == task["id"]


def test_tasks_get_and_cancel_and_errors():
    manager = _manager([LLMResponse(content="ok")])
    task = manager.send_message(
        {"role": "user", "parts": [{"kind": "text", "text": "q"}], "messageId": "m1"}
    )
    fetched = manager.handle_jsonrpc(
        {"jsonrpc": "2.0", "id": 2, "method": "tasks/get", "params": {"id": task["id"]}}
    )
    assert fetched["result"]["id"] == task["id"]

    # cancel on a terminal task is a no-op state-wise (stays completed)
    canceled = manager.handle_jsonrpc(
        {"jsonrpc": "2.0", "id": 3, "method": "tasks/cancel", "params": {"id": task["id"]}}
    )
    assert canceled["result"]["status"]["state"] == "completed"

    unknown = manager.handle_jsonrpc(
        {"jsonrpc": "2.0", "id": 4, "method": "tasks/get", "params": {"id": "ghost"}}
    )
    assert unknown["error"]["code"] == -32001

    bad_method = manager.handle_jsonrpc({"jsonrpc": "2.0", "id": 5, "method": "nope"})
    assert bad_method["error"]["code"] == -32601

    empty = manager.handle_jsonrpc(
        {"jsonrpc": "2.0", "id": 6, "method": "message/send", "params": {"message": {"parts": []}}}
    )
    assert empty["error"]["code"] == -32602


def test_runtime_failure_yields_failed_task():
    class ExplodingProvider(LLMProvider):
        name = "boom"

        def is_available(self):
            return True

        def chat(self, *a, **k):
            raise ConnectionError("provider down")

    manager = A2ATaskManager(AgentRuntime(ExplodingProvider(), ToolRegistry()))
    task = manager.send_message(
        {"role": "user", "parts": [{"kind": "text", "text": "q"}], "messageId": "m1"}
    )
    assert task["status"]["state"] == "failed"
    assert "provider down" in task["history"][-1]["parts"][0]["text"]


# ---- the NOC: ≥3 specialists cooperating over A2A (exit-gate mock) ---------------------


def _seeded_store():
    store = EventStore()
    for cell in ["C1", "C2", "C3", "C4"]:
        store.append(
            NetworkEvent(domain=EventDomain.LOCATION, source="replay", entity_id="ue7",
                         payload={"cell_id": cell})
        )
    store.append(
        NetworkEvent(domain=EventDomain.RAN_KPI, source="replay", entity_id="cell-3",
                     payload={"prb_usage": 0.95})
    )
    for _ in range(3):
        store.append(
            NetworkEvent(domain=EventDomain.SIGNALING, source="replay", entity_id="ue7",
                         severity=Severity.ALERT, event_type="AUTH_FAILURE")
        )
    return store


def test_noc_three_specialists_solve_incident_over_a2a():
    store = _seeded_store()

    # One routed provider serves all three specialists: each consults a REAL tool first,
    # then answers from its evidence.
    specialist_provider = RoutedProvider(
        {
            "RAN specialist": [
                LLMResponse(content="", tool_calls=[_tc("explain_ran_state", {})]),
                LLMResponse(content="RAN: cell-3 PRB usage at 0.95 — congestion likely."),
            ],
            "core-network specialist": [
                LLMResponse(content="", tool_calls=[_tc("get_recent_events", {"entity_id": "ue7"})]),
                LLMResponse(content="Core: ue7 shows repeated auth failures and rapid cell changes."),
            ],
            "security specialist": [
                LLMResponse(content="", tool_calls=[_tc("detect_signaling_anomalies", {})]),
                LLMResponse(content="Security: failure burst confirmed for ue7 (3 alert events)."),
            ],
        }
    )
    directory = build_default_specialists(specialist_provider, store=store)
    assert set(directory.names()) == {"ran-agent", "core-agent", "security-agent"}

    # The orchestrator consults all three over A2A envelopes, then synthesizes.
    orchestrator_provider = ScriptedProvider(
        [
            LLMResponse(content="", tool_calls=[
                _tc("ask_specialist", {"specialist": "ran-agent",
                                       "question": "Any RAN-side issues around ue7?"})]),
            LLMResponse(content="", tool_calls=[
                _tc("ask_specialist", {"specialist": "core-agent",
                                       "question": "What does the core see for ue7?"})]),
            LLMResponse(content="", tool_calls=[
                _tc("ask_specialist", {"specialist": "security-agent",
                                       "question": "Is ue7 behaving suspiciously?"})]),
            LLMResponse(content=(
                "Incident report: RAN reports cell-3 congestion (PRB 0.95); core sees ue7 auth "
                "failures with rapid cell changes; security confirms a failure burst. Likely a "
                "misbehaving/rogue UE aggravating congestion — recommend security playbook review."
            )),
        ]
    )
    orchestrator = AgentRuntime(
        orchestrator_provider, noc_registry(specialists=directory),
        system_prompt="NOC orchestrator",
    )
    result = orchestrator.run("ue7 is misbehaving and users near cell-3 report slowness — investigate.")

    # ≥3 agents cooperated…
    assert result.tool_calls_made == 3 and result.tool_errors == 0
    # …each over a real A2A task (completed), with their evidence in the orchestrator's context.
    tool_payloads = [json.loads(m["content"]) for m in result.messages if m["role"] == "tool"]
    assert {p["specialist"] for p in tool_payloads} == {"ran-agent", "core-agent", "security-agent"}
    assert all(p["state"] == "completed" and p["task_id"].startswith("task_") for p in tool_payloads)
    assert "PRB usage at 0.95" in tool_payloads[0]["answer"]
    # …and the final report synthesizes all three perspectives.
    for fragment in ("RAN", "core", "security"):
        assert fragment.lower() in result.answer.lower()


def test_noc_tools_degrade_without_specialists():
    reg = noc_registry()
    assert reg.get("list_specialists").invoke()["specialists"] == []
    out = reg.get("ask_specialist").invoke(specialist="ran-agent", question="hi")
    assert "unknown specialist" in out["error"]
