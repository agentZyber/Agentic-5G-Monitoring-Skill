"""Tool + ToolRegistry — define a network capability once, expose it through every face."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from corelab.llm.base import ToolSpec

EMPTY_SCHEMA: Dict[str, Any] = {"type": "object", "properties": {}}


@dataclass
class Tool:
    """A callable network capability with a JSON-Schema parameter spec.

    Attributes:
        name: unique tool name (snake_case).
        description: what it does — surfaced to LLMs and in MCP/A2A descriptors.
        parameters: JSON Schema for the arguments (``inputSchema`` in MCP terms).
        handler: the Python callable invoked with the validated arguments.
        tags: free-form tags (used as A2A skill tags).
    """

    name: str
    description: str
    handler: Callable[..., Any]
    parameters: Dict[str, Any] = field(default_factory=lambda: dict(EMPTY_SCHEMA))
    tags: Tuple[str, ...] = ()

    def to_spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, parameters=self.parameters)

    def invoke(self, **kwargs: Any) -> Any:
        return self.handler(**kwargs)


class ToolRegistry:
    """An ordered collection of Tools with a decorator for ergonomic registration."""

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")
        self._tools[tool.name] = tool
        return tool

    def tool(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        tags: Tuple[str, ...] = (),
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator: register the wrapped function as a Tool, returning the original function."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self.register(
                Tool(
                    name=name or func.__name__,
                    description=description or (func.__doc__ or "").strip() or func.__name__,
                    handler=func,
                    parameters=parameters or dict(EMPTY_SCHEMA),
                    tags=tags,
                )
            )
            return func

        return decorator

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"Unknown tool '{name}'. Known: {', '.join(sorted(self._tools))}")
        return self._tools[name]

    def list(self) -> List[Tool]:
        return list(self._tools.values())

    def names(self) -> List[str]:
        return list(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: object) -> bool:
        return name in self._tools


# A process-wide default registry that capability packs populate.
registry = ToolRegistry()
