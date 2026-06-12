"""LLM provider layer — local-first (Ollama default), cloud optional.

Select a provider with :func:`get_provider`. The default is read from the ``ZORTENET_LLM``
environment variable and falls back to ``"ollama"`` so the toolkit runs with **no API keys**.
OpenAI/Anthropic providers are imported lazily so their SDKs remain optional.
"""

from __future__ import annotations

import os
from typing import Any

from zortenet.llm.base import LLMProvider, LLMResponse, ToolSpec
from zortenet.llm.ollama import OllamaProvider

__all__ = ["LLMProvider", "LLMResponse", "ToolSpec", "OllamaProvider", "get_provider", "available_providers"]


def available_providers() -> list[str]:
    return ["ollama", "vllm", "openai", "anthropic"]


def get_provider(name: str | None = None, **kwargs: Any) -> LLMProvider:
    """Return an LLM provider instance.

    Args:
        name: ``"ollama"`` (default), ``"vllm"`` (self-hosted GPU serving), ``"openai"``, or
            ``"anthropic"``. If omitted, reads ``ZORTENET_LLM`` and defaults to ``"ollama"``.
        **kwargs: forwarded to the provider constructor (e.g. ``model=``, ``host=``).
    """
    name = (name or os.getenv("ZORTENET_LLM", "ollama")).lower()

    if name == "ollama":
        return OllamaProvider(**kwargs)
    if name == "vllm":
        from zortenet.llm.vllm import VLLMProvider  # local-first sibling: requests-only

        return VLLMProvider(**kwargs)
    if name == "openai":
        from zortenet.llm.openai_provider import OpenAIProvider  # lazy, optional

        return OpenAIProvider(**kwargs)
    if name == "anthropic":
        from zortenet.llm.anthropic_provider import AnthropicProvider  # lazy, optional

        return AnthropicProvider(**kwargs)

    raise ValueError(
        f"Unknown LLM provider '{name}'. Available: {', '.join(available_providers())}"
    )
