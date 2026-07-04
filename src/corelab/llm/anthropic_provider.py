"""Anthropic provider (optional, cloud).

The ``anthropic`` SDK is imported lazily so constructing the provider and calling
:meth:`is_available` never raise when the SDK is absent. Install with ``pip install anthropic``
and set ``ANTHROPIC_API_KEY``.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from corelab.llm.base import LLMProvider, LLMResponse, ToolSpec


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        api_key: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.max_tokens = max_tokens
        self.temperature = temperature

    def is_available(self) -> bool:
        try:
            import anthropic  # noqa: F401
        except Exception:
            return False
        return bool(self.api_key)

    def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[ToolSpec]] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        try:
            from anthropic import Anthropic
        except ImportError as exc:  # pragma: no cover - optional SDK
            raise RuntimeError(
                "The Anthropic SDK is not installed. Install it with `pip install anthropic`."
            ) from exc

        client = Anthropic(api_key=self.api_key)

        # Anthropic takes the system prompt separately from the message list.
        system: Optional[str] = None
        chat_messages: List[Dict[str, Any]] = []
        for m in messages:
            if m.get("role") == "system":
                system = m.get("content")
            else:
                chat_messages.append(m)

        request: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": chat_messages,
        }
        if system:
            request["system"] = system
        if tools:
            request["tools"] = [t.to_anthropic() for t in tools]
        request.update(kwargs)

        resp = client.messages.create(**request)
        text = "".join(
            block.text for block in resp.content if getattr(block, "type", None) == "text"
        )
        tool_calls = [
            block.model_dump()
            for block in resp.content
            if getattr(block, "type", None) == "tool_use"
        ]
        return LLMResponse(content=text, tool_calls=tool_calls, model=self.model)
