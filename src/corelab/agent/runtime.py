"""Provider-agnostic agent runtime — the observe → reason → act loop.

A deliberately small ReAct-style tool-calling loop over the :mod:`corelab.llm` provider
abstraction and a :class:`~corelab.agent.tools.ToolRegistry`. It is the execution engine behind
``POST /agent/ask``, the MCP/A2A faces, and (later) the capability-pack demos.

Design choices:
- **Provider-agnostic tool-call parsing** — accepts the Ollama/OpenAI ``function`` envelope
  (arguments as dict *or* JSON string) and the Anthropic ``tool_use`` block shape.
- **Errors are data** — an unknown tool or a tool exception becomes a tool-result message the
  model can read and recover from, never a crash.
- **Bounded** — ``max_iterations`` caps the loop; exhaustion is reported, not hidden.
- **Observable** — every run can be captured by a :class:`~corelab.agent.trajectory.TrajectoryLogger`
  in the training-data shape (Stage-5 fuel).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from corelab.agent.tools import ToolRegistry
from corelab.agent.trajectory import TrajectoryLogger
from corelab.llm.base import LLMProvider

DEFAULT_SYSTEM_PROMPT = (
    "You are a 5G/6G network operations agent. Use the provided tools to gather facts about the "
    "network before answering. Ground every claim in tool results — never invent network state. "
    "If a tool fails or data is unavailable, say so plainly and suggest what access is missing."
)


class ToolCallParseError(ValueError):
    """A tool call could not be parsed into (name, arguments)."""


def parse_tool_call(tc: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Normalize a provider tool call into ``(name, arguments_dict)``.

    Accepts: Ollama/OpenAI ``{"function": {"name", "arguments"}}`` (arguments dict or JSON
    string), Anthropic ``{"type": "tool_use", "name", "input"}``, and the flat
    ``{"name", "arguments"}`` shape.
    """
    if not isinstance(tc, dict):
        raise ToolCallParseError(f"tool call is not an object: {tc!r}")

    if isinstance(tc.get("function"), dict):
        name = tc["function"].get("name")
        args: Any = tc["function"].get("arguments")
    elif tc.get("type") == "tool_use":
        name = tc.get("name")
        args = tc.get("input")
    else:
        name = tc.get("name")
        args = tc.get("arguments")

    if not name:
        raise ToolCallParseError(f"tool call has no name: {tc!r}")

    if args is None:
        args = {}
    elif isinstance(args, str):
        try:
            args = json.loads(args) if args.strip() else {}
        except json.JSONDecodeError as exc:
            raise ToolCallParseError(f"arguments are not valid JSON: {args!r}") from exc
    if not isinstance(args, dict):
        raise ToolCallParseError(f"arguments are not an object: {args!r}")
    return str(name), args


def _serialize_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, ensure_ascii=False, default=str)
    except TypeError:
        return str(result)


@dataclass
class AgentResult:
    answer: str
    messages: List[Dict[str, Any]] = field(default_factory=list)
    iterations: int = 0
    tool_calls_made: int = 0
    tool_errors: int = 0
    stopped_early: bool = False


class AgentRuntime:
    def __init__(
        self,
        provider: LLMProvider,
        registry: ToolRegistry,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        max_iterations: int = 8,
        trajectory: Optional[TrajectoryLogger] = None,
    ) -> None:
        self.provider = provider
        self.registry = registry
        self.system_prompt = system_prompt
        self.max_iterations = max_iterations
        self.trajectory = trajectory

    def _execute_tool_call(self, tc: Dict[str, Any]) -> Tuple[str, str, bool]:
        """Run one tool call; returns (tool_name, result_text, is_error)."""
        try:
            name, args = parse_tool_call(tc)
        except ToolCallParseError as exc:
            return "unknown", f"ERROR: {exc}", True
        try:
            tool = self.registry.get(name)
        except KeyError:
            available = ", ".join(self.registry.names()) or "(none)"
            return name, f"ERROR: unknown tool '{name}'. Available tools: {available}", True
        try:
            return name, _serialize_result(tool.invoke(**args)), False
        except Exception as exc:  # tool bugs must not kill the loop
            return name, f"ERROR: tool '{name}' failed: {exc}", True

    def run(self, user_message: str, meta: Optional[Dict[str, Any]] = None) -> AgentResult:
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_message},
        ]
        specs = [t.to_spec() for t in self.registry.list()]
        result = AgentResult(answer="", messages=messages)

        for iteration in range(1, self.max_iterations + 1):
            result.iterations = iteration
            response = self.provider.chat(messages, tools=specs or None)

            if not response.has_tool_calls:
                messages.append({"role": "assistant", "content": response.content})
                result.answer = response.content
                break

            messages.append(
                {
                    "role": "assistant",
                    "content": response.content or "",
                    "tool_calls": response.tool_calls,
                }
            )
            for tc in response.tool_calls:
                name, text, is_error = self._execute_tool_call(tc)
                result.tool_calls_made += 1
                result.tool_errors += int(is_error)
                messages.append({"role": "tool", "name": name, "content": text})
        else:
            result.stopped_early = True
            result.answer = (
                f"(stopped after {self.max_iterations} iterations without a final answer; "
                f"{result.tool_calls_made} tool calls made)"
            )

        if self.trajectory is not None:
            self.trajectory.log(
                {
                    "provider": self.provider.name,
                    "model": getattr(self.provider, "model", None),
                    "messages": messages,
                    "answer": result.answer,
                    "iterations": result.iterations,
                    "tool_calls_made": result.tool_calls_made,
                    "tool_errors": result.tool_errors,
                    "stopped_early": result.stopped_early,
                    "meta": meta or {},
                    "outcome": None,  # filled by curation/judges in the model pipeline (Stage 5)
                }
            )
        return result
