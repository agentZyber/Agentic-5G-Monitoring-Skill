"""Ollama provider — the local-first default.

Talks to a local Ollama server over its HTTP API (no SDK dependency; uses ``requests`` which
is already a project dependency). If Ollama isn't running, :meth:`is_available` returns False
so callers can degrade gracefully instead of crashing — the same defensive pattern the legacy
code used for optional cloud SDKs.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests

from zortenet.llm.base import LLMProvider, LLMResponse, ToolSpec

DEFAULT_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        host: str = DEFAULT_HOST,
        timeout: int = 120,
        temperature: float = 0.0,
    ) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.temperature = temperature

    def is_available(self) -> bool:
        try:
            resp = requests.get(f"{self.host}/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def build_request(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[ToolSpec]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Construct the /api/chat request body (separated out so it is unit-testable).

        Sampling parameters belong under ``options`` (where Ollama reads them); a caller-provided
        ``options`` dict is merged over the provider default ``temperature``.
        """
        merged_options: Dict[str, Any] = {"temperature": self.temperature}
        if options:
            merged_options.update(options)
        body: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": merged_options,
        }
        if tools:
            body["tools"] = [t.to_ollama() for t in tools]
        return body

    def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[ToolSpec]] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        kwargs = dict(kwargs)
        # Route sampling params into `options` (Ollama ignores a top-level `temperature`).
        options = dict(kwargs.pop("options", {}) or {})
        if "temperature" in kwargs:
            options["temperature"] = kwargs.pop("temperature")
        body = self.build_request(messages, tools, options=options)
        # Any remaining kwargs are top-level Ollama params (e.g. `format`, `keep_alive`).
        for key, value in kwargs.items():
            body.setdefault(key, value)

        resp = requests.post(f"{self.host}/api/chat", json=body, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        message = data.get("message", {}) or {}
        return LLMResponse(
            content=message.get("content", "") or "",
            tool_calls=message.get("tool_calls", []) or [],
            model=data.get("model", self.model),
            raw=data,
        )
