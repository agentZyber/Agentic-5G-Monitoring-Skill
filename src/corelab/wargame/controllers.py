"""Controllers — how a side (red/blue) chooses its move each turn.

Two interchangeable kinds behind one interface, so the engine, judge and leaderboard treat scripted
baselines and live LLM agents identically:
  - :class:`ScriptedController` — a deterministic playbook (reproducible baselines + unit tests).
  - :class:`AgentController` — a single-step LLM that, given the world observation and its arsenal,
    calls exactly one tool (sovereign local model via any :class:`~corelab.llm.base.LLMProvider`).
"""

from __future__ import annotations

from typing import List, Optional

from corelab.agent.runtime import ToolCallParseError, parse_tool_call
from corelab.agent.tools import ToolRegistry
from corelab.llm.base import LLMProvider
from corelab.wargame.scenario import Action

_ROLE_SYSTEM = {
    "red": ("You are the RED adversary in a sandboxed, non-kinetic network war-game. Each turn, "
            "choose ONE action from your tools to degrade the defender's mission service. Call a "
            "single tool."),
    "blue": ("You are the BLUE defender/mission-planner in a sandboxed network war-game. Each turn, "
             "SENSE then act: detect active threats, diagnose the live one, and apply an approved "
             "countermeasure to restore the mission service. Countermeasures require human approval. "
             "Call a single tool per turn."),
}


def default_system(role: str) -> str:
    return _ROLE_SYSTEM.get(role, "Choose the single best next action by calling one tool.")


class ScriptedController:
    """Replays a fixed list of Actions — one per turn; ``None`` (or list exhausted) means hold."""

    def __init__(self, actions: List[Optional[Action]], name: str = "scripted") -> None:
        self.actions = actions
        self.name = name

    def decide(self, role: str, observation: str, registry: ToolRegistry, turn: int) -> Optional[Action]:
        idx = turn - 1
        return self.actions[idx] if 0 <= idx < len(self.actions) else None


class ReactiveController:
    """Rule-based (non-LLM) defender baseline — the 'fixed-script' comparator.

    Senses (read-only) via its ``detect_threats`` tool, then neutralises active threats in order:
    scan first (so detection is registered), then apply an approved countermeasure to each
    outstanding threat. Deterministic and provider-free — the yardstick every agent must beat.
    """

    def __init__(self, name: str = "reactive-blue") -> None:
        self.name = name
        self._handled: set[str] = set()
        self._sensed = False

    def decide(self, role: str, observation: str, registry: ToolRegistry, turn: int) -> Optional[Action]:
        active = []
        if "detect_threats" in registry:
            active = registry.get("detect_threats").invoke().get("active_threats", [])  # read-only sense
        pending = [t.get("threat_id") for t in active
                   if t.get("threat_id") and t["threat_id"] not in self._handled]
        if not self._sensed or not pending:
            self._sensed = True
            return Action("detect_threats", rationale="sense the environment")
        tid = pending[0]
        self._handled.add(tid)
        return Action("apply_countermeasure", {"threat_id": tid, "measure": "reroute"},
                      rationale=f"neutralise {tid}")


class AgentController:
    """Single-step LLM controller: pick exactly one tool call given the observation + arsenal."""

    def __init__(self, provider: LLMProvider, name: Optional[str] = None,
                 system: Optional[str] = None) -> None:
        self.provider = provider
        self.name = name or f"agent:{getattr(provider, 'model', provider.name)}"
        self.system = system

    def decide(self, role: str, observation: str, registry: ToolRegistry, turn: int) -> Optional[Action]:
        specs = [t.to_spec() for t in registry.list()]
        messages = [
            {"role": "system", "content": self.system or default_system(role)},
            {"role": "user", "content": (
                f"Turn {turn}. Current world observation:\n{observation}\n\n"
                "Choose the single best next action by calling ONE tool. "
                "If no action is warranted, answer briefly without calling a tool.")},
        ]
        try:
            resp = self.provider.chat(messages, tools=specs or None)
        except Exception as exc:  # a provider hiccup must not crash the game — treat as hold
            return Action(tool="__hold__", args={}, rationale=f"provider error: {exc}")
        if not resp.has_tool_calls:
            return None
        try:
            name, args = parse_tool_call(resp.tool_calls[0])
        except ToolCallParseError:
            return None
        return Action(tool=name, args=args, rationale=(resp.content or "")[:200])
