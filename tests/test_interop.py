"""Interop layer: one tool definition -> every protocol face. The architectural punchline, tested."""

import pytest

from zortenet.agent.tools import Tool, ToolRegistry
from zortenet.interop import (
    build_agent_card,
    to_anthropic_tools,
    to_mcp_tools,
    to_ollama_tools,
    to_openai_tools,
)
from zortenet.interop.mcp_server import build_mcp_tools
from zortenet.packs.location_monitor import PACK, build_registry


def test_pack_builds_registry_with_tools():
    reg = build_registry()
    assert PACK["name"] == "location-monitor"
    assert {"check_geofence_breach", "summarize_network_events"}.issubset(set(reg.names()))


def test_geofence_tool_invoces_correctly():
    reg = build_registry()
    breach = reg.get("check_geofence_breach").invoke(cell_id="UNAUTH", allowed_cells=["A", "B"])
    assert breach["breach"] is True
    assert breach["severity"] == "alert"

    ok = reg.get("check_geofence_breach").invoke(cell_id="A", allowed_cells=["A", "B"])
    assert ok["breach"] is False
    assert ok["severity"] == "info"


def test_summarize_bridges_legacy_and_new_events():
    reg = build_registry()
    out = reg.get("summarize_network_events").invoke(
        events=[
            {"externalId": "u1", "type": "alert", "locationInfo": {"cellId": "X"}},  # legacy
            {"domain": "ran_kpi", "source": "oran", "payload": {"prb_usage": 0.9}},  # new
        ]
    )
    assert out["count"] == 2
    assert out["by_domain"]["location"] == 1
    assert out["by_domain"]["ran_kpi"] == 1
    assert out["by_severity"]["alert"] == 1


def test_one_tool_renders_to_every_face():
    reg = build_registry()
    n = len(reg)

    openai = to_openai_tools(reg)
    anthropic = to_anthropic_tools(reg)
    ollama = to_ollama_tools(reg)
    mcp = to_mcp_tools(reg)

    assert len(openai) == len(anthropic) == len(ollama) == len(mcp) == n

    # OpenAI/Ollama use the nested "function" envelope...
    assert openai[0]["type"] == "function"
    assert ollama[0]["function"]["name"] in reg
    # ...Anthropic uses input_schema...
    assert "input_schema" in anthropic[0]
    # ...MCP uses inputSchema (camelCase) and a flat name/description.
    assert "inputSchema" in mcp[0]
    assert mcp[0]["name"] in reg
    assert build_mcp_tools(reg) == mcp  # the server helper matches the pure renderer


def test_agent_card_advertises_each_tool_as_a_skill():
    reg = build_registry()
    card = build_agent_card(reg, name="ZorteNet Test Agent")
    assert card["name"] == "ZorteNet Test Agent"
    assert card["protocolVersion"] == "1.0"
    assert card["capabilities"]["streaming"] is True
    assert len(card["skills"]) == len(reg)
    skill_ids = {s["id"] for s in card["skills"]}
    assert "check_geofence_breach" in skill_ids
    # geofence tool's tags propagate to the A2A skill
    geofence = next(s for s in card["skills"] if s["id"] == "check_geofence_breach")
    assert "security" in geofence["tags"]


def test_registry_decorator_and_guards():
    reg = ToolRegistry()

    @reg.tool(tags=("demo",))
    def ping() -> str:
        """Return pong."""
        return "pong"

    assert "ping" in reg
    assert reg.get("ping").invoke() == "pong"
    assert reg.get("ping").description == "Return pong."  # docstring -> description

    with pytest.raises(ValueError):  # duplicate registration
        reg.register(Tool(name="ping", description="x", handler=lambda: None))
    with pytest.raises(KeyError):  # unknown tool
        reg.get("nope")
