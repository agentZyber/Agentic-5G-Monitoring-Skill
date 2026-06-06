"""Interop layer — one capability core, many protocol faces.

Renders a :class:`~zortenet.agent.tools.ToolRegistry` into each agent-interop protocol's
schema, so a tool written once is reachable over MCP, A2A, REST, and the cloud/local LLM tool
formats. See docs/AGENTIC_TOOLKIT_BLUEPRINT.md §5 for the verified protocol landscape.
"""

from zortenet.interop.schemas import (
    build_agent_card,
    to_anthropic_tools,
    to_mcp_tools,
    to_ollama_tools,
    to_openai_tools,
)

__all__ = [
    "build_agent_card",
    "to_mcp_tools",
    "to_openai_tools",
    "to_anthropic_tools",
    "to_ollama_tools",
]
