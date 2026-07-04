"""P4 — integration hooks so NCSRD's real assets plug into the war-game (the consortium story).

Three drop-in points, each a small, tested interface:
  1. :class:`ExternalBenchController` — wrap NCSRD's hardware-in-the-loop red/blue SCA bench (or any
     external agent) as a war-game :class:`Controller`; the engine's guardrails still sandbox it.
  2. :class:`AdaptiveRedController` — the Context Agility Manager (CAM) pattern as an adversary:
     sense the defender's state → compare → adapt aggression (escalate when it copes, hold when it hurts).
  3. :class:`HashChainAudit` — a tamper-evident, append-only audit trail for doctrine decisions, the
     local stand-in for NCSRD's Besu quantum-resistant DLT + PQC signing.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Dict, List, Optional

from corelab.wargame.scenario import Action

_ELEMENT = {"jam_link": "link-1", "signaling_flood": "cell-1",
            "intrude_node": "node-1", "spoof_feed": "feed-1"}


class ExternalBenchController:
    """Adapt an external agent/bench into a war-game Controller.

    ``decide_fn(role, observation, tool_names, turn) -> dict | None`` returns ``{"tool": str,
    "args": dict, "rationale": str}`` (or ``None`` to hold). NCSRD implements ``decide_fn`` to call
    their real red/blue bench (subprocess, REST, or in-process), map its chosen move onto the arsenal,
    and return it. The engine still enforces every guardrail (only registered tools run, budgets,
    opaque handles, separate judge) — so an external agent is sandboxed exactly like a built-in one.
    """

    def __init__(self, decide_fn: Callable[[str, str, List[str], int], Optional[Dict[str, Any]]],
                 name: str = "ncsrd-bench") -> None:
        self.decide_fn = decide_fn
        self.name = name

    def decide(self, role: str, observation: str, registry, turn: int) -> Optional[Action]:
        try:
            out = self.decide_fn(role, observation, registry.names(), turn)
        except Exception as exc:                       # an external failure must not crash the game
            return Action(tool="__hold__", args={}, rationale=f"external bench error: {exc}")
        if not out:
            return None
        return Action(tool=out.get("tool", "__hold__"), args=dict(out.get("args") or {}),
                      rationale=out.get("rationale", ""))


class AdaptiveRedController:
    """CAM-style adaptive adversary (NCSRD Context Agility Manager: sense → compare → adapt).

    Senses the mission state from the observation each turn; while the defender is *coping* (mission
    healthy), it **escalates** — launching the next attack in its tactic ladder to keep pressure on;
    once damage is active (mission degraded) it **holds**, letting the effect bite before spending the
    next move. Turns adversary difficulty into a live control loop instead of a fixed script.
    """

    def __init__(self, tactics: List[str], name: str = "red:cam-adaptive") -> None:
        self.tactics = list(tactics)
        self.name = name
        self._i = 0
        self.clean_streak = 0            # consecutive turns the defender kept the mission healthy

    def decide(self, role: str, observation: str, registry, turn: int) -> Optional[Action]:
        degraded = "degraded" in observation.lower()   # sense
        if degraded:                                    # compare + adapt: hold while it hurts
            self.clean_streak = 0
            return None
        self.clean_streak += 1                          # defender coping → escalate
        tool = self.tactics[min(self._i, len(self.tactics) - 1)]
        self._i += 1
        if tool not in registry:
            return None
        return Action(tool=tool, args={"element": _ELEMENT.get(tool, "link-1")},
                      rationale=f"CAM escalate (defender clean-streak {self.clean_streak})")


class HashChainAudit:
    """Tamper-evident, append-only audit log for doctrine decisions (DLT/PQC stand-in).

    Each entry is hash-chained to the previous (``genesis → h1 → h2 → …``); altering any past entry
    breaks :meth:`verify`. In production ``hash`` is anchored as a PQC-signed Besu ledger transaction.
    """

    def __init__(self) -> None:
        self.entries: List[Dict[str, Any]] = []
        self._prev = "genesis"

    def record(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        payload = json.dumps(decision, sort_keys=True, default=str)
        h = hashlib.sha256((self._prev + "|" + payload).encode()).hexdigest()
        entry = {**decision, "prev": self._prev, "hash": h}
        self.entries.append(entry)
        self._prev = h
        return entry

    def verify(self) -> bool:
        prev = "genesis"
        for e in self.entries:
            body = {k: v for k, v in e.items() if k not in ("prev", "hash")}
            payload = json.dumps(body, sort_keys=True, default=str)
            if e["prev"] != prev or e["hash"] != hashlib.sha256((prev + "|" + payload).encode()).hexdigest():
                return False
            prev = e["hash"]
        return True

    @classmethod
    def from_approval_log(cls, log: List[Dict[str, Any]]) -> "HashChainAudit":
        chain = cls()
        for decision in log:
            chain.record(decision)
        return chain
