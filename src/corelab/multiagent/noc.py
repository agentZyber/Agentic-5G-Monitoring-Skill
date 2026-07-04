"""The NOC of agents — RAN / core / security specialists addressed over A2A.

Each specialist is a focused :class:`AgentRuntime` (a subset tool registry + a persona prompt)
fronted by its own :class:`A2ATaskManager`. The orchestrating agent reaches them **through A2A
``message/send`` envelopes** — built, dispatched, and parsed exactly as they travel on the wire.
In-process the dispatch is a direct call to each specialist's manager (cross-host deployment
sends the identical payloads over HTTP to each agent's ``/a2a`` endpoint).

Honesty note: this in-process dispatch exercises the protocol *shapes*, not network transport —
the cross-host hop and official-SDK interop are validated when multiple toolkit instances run
(Tier-2/3 live work).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from corelab.agent.runtime import AgentRuntime
from corelab.agent.tools import ToolRegistry
from corelab.core.bus import EventStore
from corelab.intent.ledger import IntentLedger
from corelab.interop.a2a_tasks import A2ATaskManager, message_text
from corelab.llm.base import LLMProvider


@dataclass
class SpecialistAgent:
    name: str
    description: str
    manager: A2ATaskManager

    def card(self) -> Dict[str, Any]:
        """Compact Agent-Card-style descriptor for discovery listings."""
        return {
            "name": self.name,
            "description": self.description,
            "skills": [
                {"id": t.name, "description": t.description}
                for t in self.manager.runtime.registry.list()
            ],
        }


class SpecialistDirectory:
    """Named specialists + the A2A envelope round-trip used to consult them."""

    def __init__(self) -> None:
        self._agents: Dict[str, SpecialistAgent] = {}

    def register(self, agent: SpecialistAgent) -> None:
        self._agents[agent.name] = agent

    def names(self) -> List[str]:
        return list(self._agents)

    def get(self, name: str) -> SpecialistAgent:
        if name not in self._agents:
            raise KeyError(f"unknown specialist '{name}'. Available: {', '.join(self._agents)}")
        return self._agents[name]

    def cards(self) -> List[Dict[str, Any]]:
        return [a.card() for a in self._agents.values()]

    def ask(self, name: str, question: str) -> Dict[str, Any]:
        """Consult one specialist via an A2A message/send envelope; returns answer + task id."""
        agent = self.get(name)
        envelope = {
            "jsonrpc": "2.0",
            "id": uuid.uuid4().hex[:8],
            "method": "message/send",
            "params": {
                "message": {
                    "kind": "message",
                    "role": "user",
                    "parts": [{"kind": "text", "text": question}],
                    "messageId": f"msg_{uuid.uuid4().hex[:12]}",
                }
            },
        }
        response = agent.manager.handle_jsonrpc(envelope)
        if "error" in response:
            return {"specialist": name, "error": response["error"]["message"]}
        task = response["result"]
        answer = ""
        for artifact in task.get("artifacts", []):
            answer = "\n".join(
                p.get("text", "") for p in artifact.get("parts", []) if p.get("kind") == "text"
            )
        return {
            "specialist": name,
            "task_id": task["id"],
            "state": task["status"]["state"],
            "answer": answer,
        }


def build_default_specialists(
    provider: LLMProvider,
    store: Optional[EventStore] = None,
    ledger: Optional[IntentLedger] = None,
) -> SpecialistDirectory:
    """The default NOC: ran-agent, core-agent, security-agent (focused registries, one provider)."""
    from corelab.packs.netops_copilot import build_registry as netops_registry
    from corelab.packs.ran_opt_copilot import build_registry as ran_registry
    from corelab.packs.security_sentinel import build_registry as security_registry
    from corelab.packs.self_heal import build_registry as selfheal_registry

    directory = SpecialistDirectory()

    def _specialist(name: str, description: str, registry: ToolRegistry, persona: str) -> None:
        runtime = AgentRuntime(provider=provider, registry=registry, system_prompt=persona)
        directory.register(
            SpecialistAgent(name=name, description=description, manager=A2ATaskManager(runtime, agent_name=name))
        )

    _specialist(
        "ran-agent",
        "RAN optimization specialist (Non-RT timescale; KPM evidence; A1 policy proposals).",
        ran_registry(store=store, ledger=ledger),
        "You are the RAN specialist in a NOC. Answer with RAN evidence (KPIs, policies) from your tools.",
    )
    _specialist(
        "core-agent",
        "5G core / observability specialist (subscriptions, UE status, KPIs, event store).",
        netops_registry(store=store),
        "You are the core-network specialist in a NOC. Ground answers in core/telemetry tool results.",
    )
    # Security specialist also carries diagnose tools — triage often needs both views.
    security_reg = security_registry(store=store)
    for tool in selfheal_registry(store=store).list():
        security_reg.register(tool)
    _specialist(
        "security-agent",
        "Security & diagnosis specialist (anomaly detection, mobility audits, playbooks).",
        security_reg,
        "You are the security specialist in a NOC. Detect anomalies, audit entities, propose playbooks.",
    )
    return directory


# ---- the pack: gives the orchestrating agent its delegation tools -----------------

PACK: Dict[str, Any] = {
    "name": "multi-agent-noc",
    "description": "Delegate to specialist agents (RAN/core/security) over A2A message/send.",
    "connectors": [],
    "datasets": [],
    "system_prompt": (
        "You are the NOC orchestrator. For incidents, consult the relevant specialists with "
        "ask_specialist (RAN, core, security perspectives), then synthesize a single incident "
        "report that attributes findings to each specialist. Consult at least the specialists "
        "whose domain the incident touches."
    ),
}


def build_registry(specialists: Optional[SpecialistDirectory] = None) -> ToolRegistry:
    directory = specialists if specialists is not None else SpecialistDirectory()
    reg = ToolRegistry()

    @reg.tool(
        name="list_specialists",
        description="List the specialist agents available for delegation (name, description, skills).",
        tags=("multi-agent", "a2a"),
    )
    def list_specialists() -> Dict[str, Any]:
        cards = directory.cards()
        if not cards:
            return {"specialists": [], "note": "no specialists registered (enable the NOC in the app)"}
        return {"specialists": cards}

    @reg.tool(
        name="ask_specialist",
        description="Delegate a question to one specialist agent over A2A; returns their answer.",
        parameters={
            "type": "object",
            "properties": {
                "specialist": {"type": "string", "description": "e.g. ran-agent | core-agent | security-agent"},
                "question": {"type": "string"},
            },
            "required": ["specialist", "question"],
        },
        tags=("multi-agent", "a2a"),
    )
    def ask_specialist(specialist: str, question: str) -> Dict[str, Any]:
        try:
            return directory.ask(specialist, question)
        except KeyError as exc:
            return {"error": str(exc)}

    return reg
