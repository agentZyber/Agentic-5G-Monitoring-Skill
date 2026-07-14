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
    "blue": ("You are BLUE, the defender in a sandboxed network war-game. Keep the mission service "
             "available by clearing EVERY active threat. Follow this doctrine exactly, one tool per "
             "turn:\n"
             "1. On turn 1 (before you have sensed), call detect_threats.\n"
             "2. On later turns, if the observation's 'active threats' line lists one or more threats, "
             "call apply_countermeasure with threat_id set to the FIRST listed id and measure=reroute. "
             "One countermeasure clears one threat, so repeat this every turn until the list is empty.\n"
             "3. If no active threats are listed, call detect_threats.\n"
             "Never call any other tool. Countermeasures take effect only after human (doctrine) "
             "approval."),
}


def default_system(role: str) -> str:
    return _ROLE_SYSTEM.get(role, "Choose the single best next action by calling one tool.")


def render_agent_messages(role: str, observation: str, turn: int,
                          system: Optional[str] = None) -> List[dict]:
    """The exact chat prompt an LLM controller sees for one turn.

    Single source of truth for the agent's turn prompt, shared by :class:`AgentController` (eval) and
    the gold-trajectory synthesiser (train) so the two never drift — a train/eval prompt mismatch is
    what silently sinks a fine-tune. The observation already carries the active-threat id list, so a
    single-step policy can ground ``apply_countermeasure(threat_id=...)`` without extra tool round-trips.
    """
    return [
        {"role": "system", "content": system or default_system(role)},
        {"role": "user", "content": (
            f"Turn {turn}. Current world observation:\n{observation}\n\n"
            "Choose the single best next action by calling ONE tool. "
            "If no action is warranted, answer briefly without calling a tool.")},
    ]


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
        messages = render_agent_messages(role, observation, turn, system=self.system)
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
