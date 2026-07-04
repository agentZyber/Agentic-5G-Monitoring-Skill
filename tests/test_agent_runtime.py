"""Agent runtime: the tool-calling loop, error recovery, bounds, and trajectory capture."""

import json

import pytest

from corelab.agent.runtime import (
    AgentRuntime,
    ToolCallParseError,
    parse_tool_call,
)
from corelab.agent.tools import ToolRegistry
from corelab.agent.trajectory import TrajectoryLogger
from corelab.llm.base import LLMProvider, LLMResponse


class ScriptedProvider(LLMProvider):
    """Returns canned responses in order; records what it was called with."""

    name = "scripted"
    model = "fake-model"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def is_available(self):
        return True

    def chat(self, messages, tools=None, **kwargs):
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools})
        return self.responses.pop(0)


def _registry_with_spy():
    reg = ToolRegistry()
    seen = {}

    @reg.tool(
        name="get_slice_load",
        description="Slice load",
        parameters={"type": "object", "properties": {"snssai": {"type": "string"}}},
    )
    def get_slice_load(snssai: str):
        seen["snssai"] = snssai
        return {"snssai": snssai, "load_pct": 73}

    return reg, seen


# ---- parse_tool_call: every provider shape --------------------------------


def test_parse_ollama_dict_arguments():
    name, args = parse_tool_call({"function": {"name": "t", "arguments": {"a": 1}}})
    assert (name, args) == ("t", {"a": 1})


def test_parse_openai_json_string_arguments():
    name, args = parse_tool_call({"function": {"name": "t", "arguments": '{"a": 1}'}})
    assert (name, args) == ("t", {"a": 1})


def test_parse_anthropic_tool_use_block():
    name, args = parse_tool_call({"type": "tool_use", "name": "t", "input": {"a": 1}})
    assert (name, args) == ("t", {"a": 1})


def test_parse_flat_shape_and_empty_arguments():
    assert parse_tool_call({"name": "t"}) == ("t", {})
    assert parse_tool_call({"function": {"name": "t", "arguments": ""}}) == ("t", {})


def test_parse_rejects_garbage():
    with pytest.raises(ToolCallParseError):
        parse_tool_call({"function": {"name": "t", "arguments": "{not json"}})
    with pytest.raises(ToolCallParseError):
        parse_tool_call({"function": {"arguments": "{}"}})  # no name


# ---- the loop --------------------------------------------------------------


def test_happy_path_tool_call_then_answer():
    reg, seen = _registry_with_spy()
    provider = ScriptedProvider(
        [
            LLMResponse(
                content="",
                tool_calls=[{"function": {"name": "get_slice_load", "arguments": {"snssai": "B"}}}],
            ),
            LLMResponse(content="Slice B is at 73% load."),
        ]
    )
    result = AgentRuntime(provider, reg).run("how loaded is slice B?")

    assert result.answer == "Slice B is at 73% load."
    assert seen["snssai"] == "B"  # the tool actually executed
    assert result.iterations == 2
    assert result.tool_calls_made == 1
    assert result.tool_errors == 0
    assert not result.stopped_early

    # The second provider call saw the tool result message.
    second_call_messages = provider.calls[1]["messages"]
    tool_msgs = [m for m in second_call_messages if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    assert json.loads(tool_msgs[0]["content"])["load_pct"] == 73
    # Tools were advertised as ToolSpecs.
    assert provider.calls[0]["tools"][0].name == "get_slice_load"


def test_unknown_tool_is_recoverable():
    reg, _ = _registry_with_spy()
    provider = ScriptedProvider(
        [
            LLMResponse(content="", tool_calls=[{"function": {"name": "nope", "arguments": {}}}]),
            LLMResponse(content="I don't have that tool."),
        ]
    )
    result = AgentRuntime(provider, reg).run("q")
    assert result.tool_errors == 1
    assert result.answer == "I don't have that tool."
    tool_msg = next(m for m in result.messages if m["role"] == "tool")
    assert "unknown tool 'nope'" in tool_msg["content"]
    assert "get_slice_load" in tool_msg["content"]  # tells the model what IS available


def test_tool_exception_is_recoverable():
    reg = ToolRegistry()

    @reg.tool(name="boom", description="explodes")
    def boom():
        raise RuntimeError("kaput")

    provider = ScriptedProvider(
        [
            LLMResponse(content="", tool_calls=[{"function": {"name": "boom", "arguments": {}}}]),
            LLMResponse(content="The boom tool is failing."),
        ]
    )
    result = AgentRuntime(provider, reg).run("q")
    assert result.tool_errors == 1
    tool_msg = next(m for m in result.messages if m["role"] == "tool")
    assert "kaput" in tool_msg["content"]
    assert result.answer == "The boom tool is failing."


def test_max_iterations_bound():
    reg, _ = _registry_with_spy()
    looping = LLMResponse(
        content="",
        tool_calls=[{"function": {"name": "get_slice_load", "arguments": {"snssai": "A"}}}],
    )
    provider = ScriptedProvider([looping] * 3)
    result = AgentRuntime(provider, reg, max_iterations=3).run("q")
    assert result.stopped_early
    assert result.iterations == 3
    assert result.tool_calls_made == 3
    assert "stopped after 3 iterations" in result.answer


def test_empty_registry_passes_no_tools():
    provider = ScriptedProvider([LLMResponse(content="hi")])
    result = AgentRuntime(provider, ToolRegistry()).run("hello")
    assert result.answer == "hi"
    assert provider.calls[0]["tools"] is None


# ---- trajectory capture -----------------------------------------------------


def test_trajectory_logged_in_training_shape(tmp_path):
    reg, _ = _registry_with_spy()
    provider = ScriptedProvider(
        [
            LLMResponse(
                content="",
                tool_calls=[{"function": {"name": "get_slice_load", "arguments": {"snssai": "B"}}}],
            ),
            LLMResponse(content="73%."),
        ]
    )
    logger = TrajectoryLogger(tmp_path)
    AgentRuntime(provider, reg, trajectory=logger).run("q", meta={"pack": "netops-copilot"})

    files = list(tmp_path.glob("trajectories-*.jsonl"))
    assert len(files) == 1
    record = json.loads(files[0].read_text().strip())
    assert record["provider"] == "scripted"
    assert record["model"] == "fake-model"
    assert record["meta"]["pack"] == "netops-copilot"
    assert record["answer"] == "73%."
    assert record["outcome"] is None  # filled later by Stage-5 curation
    roles = [m["role"] for m in record["messages"]]
    assert roles[0] == "system" and "tool" in roles  # the training-data chat shape


def test_trajectory_from_env(tmp_path, monkeypatch):
    monkeypatch.delenv("CORELAB_TRAJECTORIES", raising=False)
    assert TrajectoryLogger.from_env() is None  # unset + no default -> disabled
    assert TrajectoryLogger.from_env(str(tmp_path)) is not None  # default dir

    monkeypatch.setenv("CORELAB_TRAJECTORIES", "off")
    assert TrajectoryLogger.from_env(str(tmp_path)) is None  # explicit opt-out wins

    monkeypatch.setenv("CORELAB_TRAJECTORIES", str(tmp_path / "custom"))
    logger = TrajectoryLogger.from_env()
    assert logger is not None
    assert logger.directory == tmp_path / "custom"
