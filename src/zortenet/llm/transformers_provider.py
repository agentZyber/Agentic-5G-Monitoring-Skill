"""Transformers provider — run an agent on a local HF model (+ optional LoRA adapter), no server.

Its job in this project is the **G2 evaluation**: load the fine-tuned adapter directly via
``transformers`` (PEFT) and run TeleAgentBench against it vs. the base — no Ollama/vLLM serving
needed. It's also a reusable serverless local provider.

Tool calls are parsed from the model's chat-template output (Qwen-style
``<tool_call>{...}</tool_call>`` blocks) into the runtime's tool-call shape, so the existing
AgentRuntime drives it unchanged. Heavy deps (torch/transformers/peft) are imported lazily, so
importing this module on a machine without them is safe (the tool-call parsing is unit-tested
without a GPU).
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from zortenet.llm.base import LLMProvider, LLMResponse, ToolSpec

_TOOL_CALL = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)


def normalize_tool_calls(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Add the HF ``type: function`` envelope so chat templates render history tool calls."""
    out = []
    for m in messages:
        m = dict(m)
        if m.get("tool_calls"):
            m["tool_calls"] = [
                {"type": "function", "function": tc.get("function", tc)} for tc in m["tool_calls"]
            ]
        out.append(m)
    return out


def parse_tool_calls(text: str) -> tuple[str, List[Dict[str, Any]]]:
    """Extract ``<tool_call>{json}</tool_call>`` blocks → runtime tool-call shape; return (content, calls)."""
    calls: List[Dict[str, Any]] = []
    for match in _TOOL_CALL.finditer(text):
        try:
            d = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if d.get("name"):
            calls.append({"function": {"name": d["name"], "arguments": d.get("arguments", {})}})
    content = _TOOL_CALL.sub("", text).strip()
    return content, calls


class TransformersProvider(LLMProvider):
    name = "transformers"

    def __init__(
        self,
        model: str,
        adapter: Optional[str] = None,
        load_in_4bit: bool = True,
        max_new_tokens: int = 512,
        temperature: float = 0.0,
        enable_thinking: bool = False,
    ) -> None:
        self.model_id = model
        self.adapter = adapter
        self.load_in_4bit = load_in_4bit
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        # Qwen3 etc. default to emitting <think>…</think>; off keeps outputs tool-call-focused and
        # matches our training data (which has direct tool calls). Harmless for non-thinking models.
        self.enable_thinking = enable_thinking
        self.model = model + (f"+adapter({adapter})" if adapter else "")  # display label
        self._tok = None
        self._model = None

    def is_available(self) -> bool:
        try:
            import torch  # noqa: F401
            import transformers  # noqa: F401
        except Exception:
            return False
        return True

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        self._tok = AutoTokenizer.from_pretrained(self.model_id, trust_remote_code=True)
        quant = None
        if self.load_in_4bit:
            quant = BitsAndBytesConfig(
                load_in_4bit=True, bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True,
            )
        model = AutoModelForCausalLM.from_pretrained(
            self.model_id, quantization_config=quant,
            torch_dtype=torch.bfloat16, device_map="auto", trust_remote_code=True,
        )
        if self.adapter:
            from peft import PeftModel

            model = PeftModel.from_pretrained(model, self.adapter)
        model.eval()
        self._model = model

    def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[ToolSpec]] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        import torch

        self._ensure_loaded()
        tool_schemas = [t.to_openai() for t in tools] if tools else None
        norm = normalize_tool_calls(messages)

        def _encode(use_tools: bool):
            kw = dict(
                add_generation_prompt=True, return_tensors="pt", return_dict=True,
                tokenize=True, enable_thinking=self.enable_thinking,
            )
            if use_tools:
                kw["tools"] = tool_schemas
            return self._tok.apply_chat_template(norm, **kw)

        try:
            enc = _encode(bool(tool_schemas))
        except Exception:
            # fallback: some templates choke on tool history — render without the tools kwarg
            enc = _encode(False)
        enc = {k: v.to(self._model.device) for k, v in enc.items()}
        input_len = enc["input_ids"].shape[1]
        with torch.no_grad():
            generated = self._model.generate(
                **enc, max_new_tokens=self.max_new_tokens,
                do_sample=self.temperature > 0,
                temperature=self.temperature if self.temperature > 0 else None,
                pad_token_id=self._tok.eos_token_id,
            )
        text = self._tok.decode(generated[0][input_len:], skip_special_tokens=True)
        content, tool_calls = parse_tool_calls(text)
        return LLMResponse(content=content, tool_calls=tool_calls, model=self.model)
