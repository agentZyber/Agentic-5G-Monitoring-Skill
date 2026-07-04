"""LLM provider layer — local-first (Ollama default), cloud optional.

Select a provider with :func:`get_provider`. The default is read from the ``CORELAB_LLM``
environment variable and falls back to ``"ollama"`` so the toolkit runs with **no API keys**.
OpenAI/Anthropic providers are imported lazily so their SDKs remain optional.
"""

from __future__ import annotations

import os
from typing import Any

from corelab.llm.base import LLMProvider, LLMResponse, ToolSpec
from corelab.llm.ollama import OllamaProvider

__all__ = ["LLMProvider", "LLMResponse", "ToolSpec", "OllamaProvider", "get_provider", "available_providers"]


def available_providers() -> list[str]:
    return ["ollama", "vllm", "transformers", "openai", "anthropic"]


def get_provider(name: str | None = None, **kwargs: Any) -> LLMProvider:
    """Return an LLM provider instance.

    Args:
        name: ``"ollama"`` (default), ``"vllm"`` (self-hosted GPU serving), ``"openai"``, or
            ``"anthropic"``. If omitted, reads ``CORELAB_LLM`` and defaults to ``"ollama"``.
        **kwargs: forwarded to the provider constructor (e.g. ``model=``, ``host=``).
    """
    name = (name or os.getenv("CORELAB_LLM", "ollama")).lower()

    if name == "ollama":
        return OllamaProvider(**kwargs)
    if name == "vllm":
        from corelab.llm.vllm import VLLMProvider  # local-first sibling: requests-only

        return VLLMProvider(**kwargs)
    if name == "transformers":
        from corelab.llm.transformers_provider import TransformersProvider  # serverless local + adapters

        return TransformersProvider(**kwargs)
    if name == "openai":
        from corelab.llm.openai_provider import OpenAIProvider  # lazy, optional

        return OpenAIProvider(**kwargs)
    if name == "anthropic":
        from corelab.llm.anthropic_provider import AnthropicProvider  # lazy, optional

        return AnthropicProvider(**kwargs)

    raise ValueError(
        f"Unknown LLM provider '{name}'. Available: {', '.join(available_providers())}"
    )
