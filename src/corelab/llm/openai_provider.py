"""OpenAI provider (optional, cloud).

The ``openai`` SDK is imported lazily inside the methods so that constructing the provider and
calling :meth:`is_available` never raise when the SDK is absent — the same graceful-degradation
contract as the Ollama provider. Install with ``pip install openai`` and set ``OPENAI_API_KEY``.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from corelab.llm.base import LLMProvider, LLMResponse, ToolSpec


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: Optional[str] = None,
        temperature: float = 0.0,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.temperature = temperature

    def is_available(self) -> bool:
        try:
            import openai  # noqa: F401
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
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - optional SDK
            raise RuntimeError(
                "The OpenAI SDK is not installed. Install it with `pip install openai`."
            ) from exc

        client = OpenAI(api_key=self.api_key)
        request: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if tools:
            request["tools"] = [t.to_openai() for t in tools]
        request.update(kwargs)

        resp = client.chat.completions.create(**request)
        message = resp.choices[0].message
        tool_calls = [tc.model_dump() for tc in (message.tool_calls or [])]
        return LLMResponse(
            content=message.content or "",
            tool_calls=tool_calls,
            model=self.model,
            raw=resp.model_dump() if hasattr(resp, "model_dump") else None,
        )
