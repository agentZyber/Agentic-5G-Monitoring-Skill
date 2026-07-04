"""vLLM provider — self-hosted GPU serving (the 4×24 GB / 70B-class path).

vLLM exposes an OpenAI-compatible HTTP API; this provider speaks it directly with ``requests``
(no SDK dependency, same pattern as the Ollama provider). Typical setup::

    vllm serve Qwen/Qwen2.5-32B-Instruct --tensor-parallel-size 4   # spreads across 4 GPUs
    export CORELAB_LLM=vllm VLLM_BASE_URL=http://gpu-host:8000 VLLM_MODEL=Qwen/Qwen2.5-32B-Instruct

Tool calling uses the OpenAI ``tools`` schema (vLLM needs ``--enable-auto-tool-choice`` and a
``--tool-call-parser`` matching the model family — noted here because it is the #1 live-setup
gotcha). ``function.arguments`` arrives as a JSON string; the agent runtime's parser handles it.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests

from corelab.llm.base import LLMProvider, LLMResponse, ToolSpec

DEFAULT_BASE_URL = os.getenv("VLLM_BASE_URL", "http://localhost:8000")
DEFAULT_MODEL = os.getenv("VLLM_MODEL", "")


class VLLMProvider(LLMProvider):
    name = "vllm"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        api_key: Optional[str] = None,          # vLLM can run with --api-key
        timeout: int = 120,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.getenv("VLLM_API_KEY")
        self.timeout = timeout
        self.temperature = temperature
        self.max_tokens = max_tokens

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def is_available(self) -> bool:
        try:
            resp = requests.get(
                f"{self.base_url}/v1/models", headers=self._headers(), timeout=5
            )
            return resp.status_code == 200
        except Exception:
            return False

    def served_models(self) -> List[str]:
        """Model ids the server reports (useful when ``model`` was left unset)."""
        try:
            resp = requests.get(
                f"{self.base_url}/v1/models", headers=self._headers(), timeout=5
            )
            if resp.status_code != 200:
                return []
            return [m.get("id", "") for m in resp.json().get("data", [])]
        except Exception:
            return []

    def build_request(
        self, messages: List[Dict[str, str]], tools: Optional[List[ToolSpec]] = None
    ) -> Dict[str, Any]:
        model = self.model or next(iter(self.served_models()), "")
        body: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if self.max_tokens is not None:
            body["max_tokens"] = self.max_tokens
        if tools:
            body["tools"] = [t.to_openai() for t in tools]
        return body

    def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[ToolSpec]] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        body = self.build_request(messages, tools)
        for key, value in kwargs.items():
            body.setdefault(key, value)

        resp = requests.post(
            f"{self.base_url}/v1/chat/completions",
            json=body,
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        message = (data.get("choices") or [{}])[0].get("message", {}) or {}
        return LLMResponse(
            content=message.get("content") or "",
            tool_calls=message.get("tool_calls") or [],
            model=data.get("model", body.get("model", "")),
            raw=data,
        )
