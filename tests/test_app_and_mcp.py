"""The wired app: REST + A2A faces, pack merging, and the MCP server (handlers + real HTTP)."""

import json

import pytest
from fastapi.testclient import TestClient

import mcp.types as mcp_types
from zortenet.app import create_app
from zortenet.interop.mcp_server import create_server
from zortenet.llm.base import LLMProvider, LLMResponse
from zortenet.packs import available_packs, load_packs
from zortenet.packs.location_monitor import build_registry as build_location_registry


class ScriptedProvider(LLMProvider):
    name = "scripted"
    model = "fake-model"

    def __init__(self, responses=None, fail=False):
        self.responses = list(responses or [])
        self.fail = fail

    def is_available(self):
        return not self.fail

    def chat(self, messages, tools=None, **kwargs):
        if self.fail:
            raise ConnectionError("provider down")
        return self.responses.pop(0)


# ---- pack loading -----------------------------------------------------------


def test_load_packs_merges_without_collisions():
    registry, metas = load_packs(available_packs())
    names = registry.names()
    assert "check_geofence_breach" in names  # location-monitor
    assert "network_health_overview" in names  # netops-copilot
    assert "detect_signaling_anomalies" in names  # security-sentinel
    assert "propose_remediation" in names  # self-heal
    assert "search_specs" in names  # spec-kb
    assert "draft_intent" in names  # intent-to-network
    assert "propose_slice_policy" in names  # ran-opt-copilot
    assert "ask_specialist" in names  # multi-agent-noc
    assert "amari_gnb_status" in names  # amarisoft (opt-in, but enumerable via available_packs)
    assert len(names) == len(set(names))
    assert [m["name"] for m in metas] == [
        "location-monitor",
        "netops-copilot",
        "security-sentinel",
        "self-heal",
        "spec-kb",
        "intent-to-network",
        "ran-opt-copilot",
        "multi-agent-noc",
        "amarisoft",
    ]


def test_load_packs_unknown_name():
    with pytest.raises(KeyError, match="Unknown pack"):
        load_packs(["does-not-exist"])


# ---- the app: REST + A2A faces ------------------------------------------------


def _make_client(provider=None, **kwargs):
    app = create_app(provider=provider or ScriptedProvider(), trajectory=None, **kwargs)
    return TestClient(app)


def test_health_reports_wiring():
    with _make_client() as client:
        body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["provider"] == "scripted"
    assert body["packs"] == [
        "location-monitor",
        "netops-copilot",
        "security-sentinel",
        "self-heal",
        "spec-kb",
        "intent-to-network",
        "ran-opt-copilot",
        "multi-agent-noc",
    ]
    assert body["tools"] >= 22  # all eight default packs merged
    assert body["executor"] == "simulated"  # honest default: no real network touched
    assert body["specialists"] == ["ran-agent", "core-agent", "security-agent"]
    assert "a2a-tasks" in body["faces"] and "acp" in body["faces"]
    assert body["mcp_http"] is True  # mcp SDK installed in this env
    assert body["trajectories"] is None  # explicitly disabled for tests


def test_packs_subset_via_config():
    # The Stage-2 exit-gate requirement: packs enable/disable cleanly via config.
    with _make_client(packs=["location-monitor"]) as client:
        body = client.get("/health").json()
    assert body["packs"] == ["location-monitor"]
    assert body["tools"] == 2  # only the legacy pack's tools


def test_tools_endpoint_serves_mcp_descriptors():
    with _make_client() as client:
        tools = client.get("/tools").json()
    by_name = {t["name"]: t for t in tools}
    assert "inputSchema" in by_name["check_geofence_breach"]


def test_agent_ask_runs_the_loop():
    provider = ScriptedProvider(
        [
            LLMResponse(
                content="",
                tool_calls=[
                    {
                        "function": {
                            "name": "check_geofence_breach",
                            "arguments": {"cell_id": "X", "allowed_cells": ["A"]},
                        }
                    }
                ],
            ),
            LLMResponse(content="UE breached its geofence: cell X is not allowed."),
        ]
    )
    with _make_client(provider) as client:
        body = client.post(
            "/agent/ask", json={"message": "is the UE in an allowed cell?"}
        ).json()
    assert body["answer"].startswith("UE breached")
    assert body["tool_calls_made"] == 1
    assert body["tool_errors"] == 0
    assert "messages" not in body  # opt-in only


def test_agent_ask_provider_down_returns_503():
    with _make_client(ScriptedProvider(fail=True)) as client:
        resp = client.post("/agent/ask", json={"message": "hi"})
    assert resp.status_code == 503
    assert "ollama serve" in resp.json()["detail"] or "failed" in resp.json()["detail"]


def test_a2a_agent_card_served_at_well_known():
    with _make_client() as client:
        card = client.get("/.well-known/agent-card.json").json()
    assert card["protocolVersion"] == "1.0"
    skill_ids = {s["id"] for s in card["skills"]}
    assert {"check_geofence_breach", "network_health_overview"}.issubset(skill_ids)


def test_a2a_skill_invocation():
    with _make_client() as client:
        resp = client.post(
            "/a2a/skills/check_geofence_breach",
            json={"cell_id": "BAD", "allowed_cells": ["A", "B"]},
        )
    assert resp.status_code == 200
    assert resp.json()["result"]["breach"] is True


# ---- MCP: protocol handlers, no transport ------------------------------------


@pytest.mark.asyncio
async def test_mcp_list_tools_handler_preserves_schemas():
    server = create_server(build_location_registry())
    handler = server.request_handlers[mcp_types.ListToolsRequest]
    result = await handler(mcp_types.ListToolsRequest(method="tools/list"))
    tools = {t.name: t for t in result.root.tools}
    assert "check_geofence_breach" in tools
    schema = tools["check_geofence_breach"].inputSchema
    assert schema["required"] == ["cell_id", "allowed_cells"]  # exact schema, not re-derived


@pytest.mark.asyncio
async def test_mcp_call_tool_handler_executes():
    server = create_server(build_location_registry())
    handler = server.request_handlers[mcp_types.CallToolRequest]
    request = mcp_types.CallToolRequest(
        method="tools/call",
        params=mcp_types.CallToolRequestParams(
            name="check_geofence_breach",
            arguments={"cell_id": "X", "allowed_cells": ["A"]},
        ),
    )
    result = await handler(request)
    assert not result.root.isError
    assert "'breach': True" in result.root.content[0].text


# ---- MCP: over real Streamable HTTP through the mounted app --------------------


MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


def _rpc(method, params=None, id_=1):
    body = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None:
        body["params"] = params
    return body


def test_mcp_streamable_http_initialize_and_list_tools():
    with _make_client() as client:
        init = client.post(
            "/mcp",
            json=_rpc(
                "initialize",
                {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "pytest", "version": "0"},
                },
            ),
            headers=MCP_HEADERS,
        )
        assert init.status_code == 200, init.text
        assert init.json()["result"]["serverInfo"]["name"] == "zortenet-5g"

        listed = client.post(
            "/mcp", json=_rpc("tools/list", {}, id_=2), headers=MCP_HEADERS
        )
        assert listed.status_code == 200, listed.text
        tool_names = {t["name"] for t in listed.json()["result"]["tools"]}
        assert "check_geofence_breach" in tool_names
        assert "network_health_overview" in tool_names


def test_mcp_streamable_http_tool_call_roundtrip():
    with _make_client() as client:
        resp = client.post(
            "/mcp",
            json=_rpc(
                "tools/call",
                {
                    "name": "check_geofence_breach",
                    "arguments": {"cell_id": "ROGUE", "allowed_cells": ["A1"]},
                },
                id_=3,
            ),
            headers=MCP_HEADERS,
        )
    assert resp.status_code == 200, resp.text
    result = resp.json()["result"]
    assert result.get("isError") is not True
    assert "'breach': True" in result["content"][0]["text"]
