"""Agent runtime + the shared ToolRegistry.

The ToolRegistry is the architectural keystone of the toolkit: a tool is defined **once** and
the interop layer (zortenet.interop) renders it to every protocol face — MCP, A2A, REST, and the
OpenAI/Anthropic/Ollama tool schemas. Write once, expose everywhere.
"""

from zortenet.agent.runtime import AgentResult, AgentRuntime, parse_tool_call
from zortenet.agent.tools import Tool, ToolRegistry, registry
from zortenet.agent.trajectory import TrajectoryLogger

__all__ = [
    "AgentResult",
    "AgentRuntime",
    "parse_tool_call",
    "Tool",
    "ToolRegistry",
    "registry",
    "TrajectoryLogger",
]
