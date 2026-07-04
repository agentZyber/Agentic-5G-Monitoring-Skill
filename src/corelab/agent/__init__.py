"""Agent runtime + the shared ToolRegistry.

The ToolRegistry is the architectural keystone of the toolkit: a tool is defined **once** and
the interop layer (corelab.interop) renders it to every protocol face — MCP, A2A, REST, and the
OpenAI/Anthropic/Ollama tool schemas. Write once, expose everywhere.
"""

from corelab.agent.runtime import AgentResult, AgentRuntime, parse_tool_call
from corelab.agent.tools import Tool, ToolRegistry, registry
from corelab.agent.trajectory import TrajectoryLogger

__all__ = [
    "AgentResult",
    "AgentRuntime",
    "parse_tool_call",
    "Tool",
    "ToolRegistry",
    "registry",
    "TrajectoryLogger",
]
