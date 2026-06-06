"""Pure renderers: ToolRegistry -> each protocol's schema.

These functions are deliberately side-effect-free so they are fully unit-testable without any
SDK, server, or network. The server wrappers (mcp_server.py, a2a_server.py) build on them.
"""

from __future__ import annotations

from typing import Any, Dict, List

from zortenet.agent.tools import ToolRegistry

# --- LLM tool formats (delegate to ToolSpec so the mapping lives in one place) ---


def to_openai_tools(registry: ToolRegistry) -> List[Dict[str, Any]]:
    return [t.to_spec().to_openai() for t in registry.list()]


def to_anthropic_tools(registry: ToolRegistry) -> List[Dict[str, Any]]:
    return [t.to_spec().to_anthropic() for t in registry.list()]


def to_ollama_tools(registry: ToolRegistry) -> List[Dict[str, Any]]:
    return [t.to_spec().to_ollama() for t in registry.list()]


# --- MCP: tool descriptors use `inputSchema` (camelCase) per the MCP spec ---


def to_mcp_tools(registry: ToolRegistry) -> List[Dict[str, Any]]:
    return [
        {"name": t.name, "description": t.description, "inputSchema": t.parameters}
        for t in registry.list()
    ]


# --- A2A: an Agent Card advertised at /.well-known/agent-card.json ---


def build_agent_card(
    registry: ToolRegistry,
    name: str = "ZorteNet 5G Agent",
    description: str = "Agentic 5G/6G network operations: observe, reason, and act on the core & RAN.",
    url: str = "http://localhost:5000/a2a",
    version: str = "0.3.0",
    streaming: bool = True,
) -> Dict[str, Any]:
    """Render an A2A Agent Card. Each registered tool becomes an advertised skill.

    Field names follow the A2A v1.0 Agent Card (skills carry id/name/description/tags/examples;
    the card advertises protocol version, capabilities, and default I/O modes).
    """
    skills = [
        {
            "id": t.name,
            "name": t.name.replace("_", " ").title(),
            "description": t.description,
            "tags": list(t.tags),
            "examples": [],
        }
        for t in registry.list()
    ]
    return {
        "protocolVersion": "1.0",
        "name": name,
        "description": description,
        "url": url,
        "version": version,
        "capabilities": {"streaming": streaming, "pushNotifications": False},
        "defaultInputModes": ["text/plain", "application/json"],
        "defaultOutputModes": ["text/plain", "application/json"],
        "skills": skills,
    }
