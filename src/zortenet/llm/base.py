"""Provider-agnostic LLM interface.

The legacy ZorteNet wired OpenAI/Anthropic directly into the agent (cloud-only, API key
required to do anything). This abstraction makes the toolkit **local-first**: the default
provider is Ollama, and a tool defined once is converted to every provider's tool schema
(Ollama / OpenAI / Anthropic) — the same "write once, expose everywhere" principle the interop
layer applies to agent protocols.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolSpec:
    """A tool the model may call, defined once and rendered to each provider's schema."""

    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})

    def to_openai(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def to_ollama(self) -> Dict[str, Any]:
        # Ollama's /api/chat uses the same OpenAI-style "function" tool shape.
        return self.to_openai()

    def to_anthropic(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }


@dataclass
class LLMResponse:
    """Normalized response across providers."""

    content: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    model: str = ""
    raw: Optional[Dict[str, Any]] = None

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


class LLMProvider(ABC):
    """Minimal chat interface every provider implements."""

    name: str = "base"

    @abstractmethod
    def is_available(self) -> bool:
        """Cheap reachability/credential check; never raises."""

    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[ToolSpec]] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Single-turn chat completion with optional tool specs."""
