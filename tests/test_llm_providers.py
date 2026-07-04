"""Unit tests for the local-first LLM provider layer (no real network calls)."""

import pytest

import corelab.llm.ollama as ollama_mod
from corelab.llm import OllamaProvider, ToolSpec, get_provider


def test_default_provider_is_ollama(monkeypatch):
    monkeypatch.delenv("CORELAB_LLM", raising=False)
    provider = get_provider()
    assert isinstance(provider, OllamaProvider)
    assert provider.name == "ollama"


def test_env_var_selects_provider(monkeypatch):
    monkeypatch.setenv("CORELAB_LLM", "ollama")
    assert get_provider().name == "ollama"


def test_unknown_provider_raises():
    with pytest.raises(ValueError):
        get_provider("does-not-exist")


def test_vllm_provider_selection_build_and_parse(monkeypatch):
    import corelab.llm.vllm as vllm_mod
    from corelab.llm.vllm import VLLMProvider

    monkeypatch.setenv("CORELAB_LLM", "vllm")
    provider = get_provider(model="Qwen/Qwen2.5-32B-Instruct", base_url="http://gpu:8000")
    assert isinstance(provider, VLLMProvider) and provider.name == "vllm"

    # request shape: OpenAI-compatible with tools rendered in the OpenAI envelope
    spec = ToolSpec(name="t", description="d")
    body = provider.build_request([{"role": "user", "content": "hi"}], tools=[spec])
    assert body["model"] == "Qwen/Qwen2.5-32B-Instruct"
    assert body["tools"][0]["type"] == "function"

    # degradation: unreachable server -> False, never raises
    def boom(*a, **k):
        raise ConnectionError("down")

    monkeypatch.setattr(vllm_mod.requests, "get", boom)
    assert provider.is_available() is False

    # chat parse: OpenAI response shape with string-encoded tool arguments
    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "model": "Qwen/Qwen2.5-32B-Instruct",
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "c1",
                                    "type": "function",
                                    "function": {"name": "t", "arguments": '{"a": 1}'},
                                }
                            ],
                        }
                    }
                ],
            }

    monkeypatch.setattr(vllm_mod.requests, "post", lambda *a, **k: FakeResp())
    resp = provider.chat([{"role": "user", "content": "go"}])
    assert resp.has_tool_calls
    from corelab.agent.runtime import parse_tool_call

    name, args = parse_tool_call(resp.tool_calls[0])  # runtime handles string arguments
    assert (name, args) == ("t", {"a": 1})


def test_vllm_model_autodiscovery(monkeypatch):
    import corelab.llm.vllm as vllm_mod
    from corelab.llm.vllm import VLLMProvider

    class ModelsResp:
        status_code = 200

        def json(self):
            return {"data": [{"id": "served-70b"}]}

    monkeypatch.setattr(vllm_mod.requests, "get", lambda *a, **k: ModelsResp())
    provider = VLLMProvider(model="")  # unset: discover from the server
    body = provider.build_request([{"role": "user", "content": "x"}])
    assert body["model"] == "served-70b"


def test_transformers_provider_tool_call_parsing():
    # Pure parsing path (no torch): Qwen-style <tool_call> blocks -> runtime tool-call shape.
    from corelab.agent.runtime import parse_tool_call
    from corelab.llm.transformers_provider import normalize_tool_calls, parse_tool_calls

    text = (
        'Let me check.\n<tool_call>{"name": "diagnose_entity", "arguments": {"entity_id": "ue-7"}}'
        '</tool_call>\n<tool_call>{"name": "audit_ue_mobility", "arguments": {"entity_id": "ue-7"}}</tool_call>'
    )
    content, calls = parse_tool_calls(text)
    assert content == "Let me check."
    assert [c["function"]["name"] for c in calls] == ["diagnose_entity", "audit_ue_mobility"]
    # the runtime parses what this provider emits
    assert parse_tool_call(calls[0]) == ("diagnose_entity", {"entity_id": "ue-7"})

    # no tool call -> plain content
    assert parse_tool_calls("just an answer") == ("just an answer", [])

    # history normalization adds the HF type=function envelope
    norm = normalize_tool_calls([{"role": "assistant", "tool_calls": [{"function": {"name": "t", "arguments": {}}}]}])
    assert norm[0]["tool_calls"][0]["type"] == "function"


def test_transformers_provider_selectable_and_lazy(monkeypatch):
    monkeypatch.setenv("CORELAB_LLM", "transformers")
    p = get_provider(model="Qwen/Qwen3-8B")
    assert p.name == "transformers" and p.model == "Qwen/Qwen3-8B"  # construct w/o loading torch


def test_get_provider_openai_and_anthropic_construct_and_degrade(monkeypatch):
    # Regression for the review's HIGH finding: these must not raise ModuleNotFoundError, and
    # must degrade gracefully (is_available False) when the optional SDK/key is absent.
    from corelab.llm.anthropic_provider import AnthropicProvider
    from corelab.llm.openai_provider import OpenAIProvider

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    op = get_provider("openai")
    assert isinstance(op, OpenAIProvider) and op.name == "openai"
    assert op.is_available() is False  # no key/SDK -> False, never raises

    ap = get_provider("anthropic")
    assert isinstance(ap, AnthropicProvider) and ap.name == "anthropic"
    assert ap.is_available() is False


def test_toolspec_renders_each_provider_schema():
    spec = ToolSpec(
        name="get_slice_load",
        description="Return load for a slice",
        parameters={"type": "object", "properties": {"snssai": {"type": "string"}}},
    )
    # The "write a tool once, expose it everywhere" guarantee at the model layer.
    assert spec.to_openai()["function"]["name"] == "get_slice_load"
    assert spec.to_ollama()["function"]["name"] == "get_slice_load"
    anthropic = spec.to_anthropic()
    assert anthropic["name"] == "get_slice_load"
    assert anthropic["input_schema"]["properties"]["snssai"]["type"] == "string"


def test_ollama_build_request_includes_tools():
    provider = OllamaProvider(model="qwen2.5:7b")
    spec = ToolSpec(name="t", description="d")
    body = provider.build_request([{"role": "user", "content": "hi"}], tools=[spec])
    assert body["model"] == "qwen2.5:7b"
    assert body["stream"] is False
    assert body["tools"][0]["function"]["name"] == "t"


def test_ollama_build_request_merges_caller_options():
    body = OllamaProvider(model="m").build_request(
        [{"role": "user", "content": "x"}], options={"temperature": 0.7, "num_ctx": 2048}
    )
    assert body["options"]["temperature"] == 0.7  # caller overrides provider default
    assert body["options"]["num_ctx"] == 2048


def test_ollama_chat_routes_sampling_params_into_options(monkeypatch):
    # Regression for the review's options-nesting finding.
    captured = {}

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"model": "m", "message": {"content": "ok"}}

    def fake_post(url, json=None, timeout=None):
        captured["body"] = json
        return FakeResp()

    monkeypatch.setattr(ollama_mod.requests, "post", fake_post)
    OllamaProvider(model="m").chat(
        [{"role": "user", "content": "hi"}],
        temperature=0.9,
        options={"num_ctx": 4096},
        format="json",
    )
    body = captured["body"]
    assert body["options"]["temperature"] == 0.9  # not dropped, not top-level
    assert body["options"]["num_ctx"] == 4096  # caller options merged, not discarded
    assert body["format"] == "json"  # non-sampling kwargs stay top-level
    assert "temperature" not in body  # never leaks to the top level


def test_ollama_is_available_false_when_unreachable(monkeypatch):
    def boom(*args, **kwargs):
        raise ConnectionError("no server")

    monkeypatch.setattr(ollama_mod.requests, "get", boom)
    # Must degrade gracefully, never raise.
    assert OllamaProvider().is_available() is False


def test_ollama_chat_parses_response(monkeypatch):
    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "model": "llama3.1:8b",
                "message": {"role": "assistant", "content": "PRBs look healthy.", "tool_calls": []},
            }

    monkeypatch.setattr(ollama_mod.requests, "post", lambda *a, **k: FakeResp())
    resp = OllamaProvider().chat([{"role": "user", "content": "status?"}])
    assert resp.content == "PRBs look healthy."
    assert resp.has_tool_calls is False
    assert resp.model == "llama3.1:8b"
