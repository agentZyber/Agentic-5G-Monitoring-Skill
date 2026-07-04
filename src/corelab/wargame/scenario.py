"""War-game scenarios + world state — the contested-environment simulation substrate.

The "world" is a :class:`~corelab.core.bus.EventStore`: red actions inject hostile events
(threats) about a mission asset; blue actions mitigate them (MITIGATION events resolving a
threat_id). :class:`WorldState` derives active threats and mission health from that event log —
so the judge and the controllers reason over the SAME auditable substrate the rest of the toolkit
uses. Fully sandboxed and non-kinetic: everything is simulated telemetry, decision-support only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from corelab.core.bus import EventStore
from corelab.core.events import EventDomain, NetworkEvent, Severity

MITIGATION = "MITIGATION"  # blue event_type that resolves a threat_id


@dataclass
class Action:
    """One move by a red or blue controller: a tool name + args + a short rationale."""

    tool: str
    args: Dict[str, Any] = field(default_factory=dict)
    rationale: str = ""

    def label(self) -> str:
        arg = ", ".join(f"{k}={v}" for k, v in self.args.items())
        return f"{self.tool}({arg})"


@dataclass
class WarGameScenario:
    """A reproducible contested-environment scenario (init state + objectives + arsenals)."""

    scenario_id: str
    title: str
    description: str
    mission_asset: str                                  # entity whose service must be protected
    max_turns: int = 6
    detect_deadline: int = 2                            # turns within which blue must detect a live threat
    red_actions: List[str] = field(default_factory=list)
    blue_actions: List[str] = field(default_factory=list)
    seed_events: List[Dict[str, Any]] = field(default_factory=list)
    red_budget: int = 6
    blue_budget: int = 10

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id, "title": self.title, "description": self.description,
            "mission_asset": self.mission_asset, "max_turns": self.max_turns,
            "detect_deadline": self.detect_deadline, "red_actions": self.red_actions,
            "blue_actions": self.blue_actions, "red_budget": self.red_budget,
            "blue_budget": self.blue_budget,
        }


def seed_world(scenario: WarGameScenario) -> EventStore:
    """Materialise a scenario's initial world state into a fresh EventStore."""
    store = EventStore()
    for e in scenario.seed_events:
        store.append(NetworkEvent(
            domain=e.get("domain", EventDomain.APP), source="scenario",
            entity_id=e.get("entity_id"), severity=e.get("severity", Severity.INFO),
            event_type=e.get("event_type", "SEED"), payload=dict(e.get("payload", {})),
        ))
    return store


class WorldState:
    """Derives active threats + mission health from the event log (single source of truth)."""

    def __init__(self, store: EventStore, mission_asset: str) -> None:
        self.store = store
        self.mission = mission_asset

    def _ordered(self) -> List[NetworkEvent]:
        return list(reversed(self.store.recent(limit=5000)))  # oldest → newest

    def active_threats(self) -> List[NetworkEvent]:
        """Red-injected threats (by threat_id) with no subsequent MITIGATION."""
        injected: Dict[str, NetworkEvent] = {}
        mitigated: set[str] = set()
        for e in self._ordered():
            tid = e.payload.get("threat_id")
            if not tid:
                continue
            if e.source == "red":
                injected[tid] = e
            elif e.event_type == MITIGATION:
                mitigated.add(tid)
        return [e for tid, e in injected.items() if tid not in mitigated]

    def threats_on_mission(self) -> List[NetworkEvent]:
        return [t for t in self.active_threats()
                if t.entity_id == self.mission or t.payload.get("target") == self.mission]

    def mission_healthy(self) -> bool:
        return not self.threats_on_mission()


# ---- built-in scenarios ----------------------------------------------------------------

def _tactical_network_scenario() -> WarGameScenario:
    return WarGameScenario(
        scenario_id="contested-tactical-network",
        title="Contested tactical network — link degradation & intrusion",
        description=(
            "A mission-critical tactical service slice must stay available while an adversary "
            "degrades the network (jamming, signaling flood, node intrusion). Blue must detect the "
            "live threat and apply an approved countermeasure to restore service. Non-kinetic, "
            "human-in-the-loop: countermeasures require doctrine (human) approval."
        ),
        mission_asset="mission-slice",
        max_turns=6,
        detect_deadline=2,
        red_actions=["jam_link", "signaling_flood", "intrude_node"],
        blue_actions=["detect_threats", "diagnose_threat", "apply_countermeasure"],
        seed_events=[
            {"domain": EventDomain.SLICE, "entity_id": "mission-slice", "event_type": "SLA_OK",
             "payload": {"sla": "nominal", "service": "C2-voice+data"}},
            {"domain": EventDomain.RAN_KPI, "entity_id": "link-1", "event_type": "KPI",
             "payload": {"cqi": 14, "target": "mission-slice"}},
        ],
        red_budget=5,
        blue_budget=10,
    )


def _isr_tasking_scenario() -> WarGameScenario:
    return WarGameScenario(
        scenario_id="isr-sensor-contested",
        title="ISR sensor feed under contested backhaul",
        description=(
            "An ISR sensor feed rides a backhaul the adversary tries to disrupt/spoof. Blue must "
            "keep the feed trustworthy and available, detecting spoofing/flooding and applying an "
            "approved reroute/authentication countermeasure. Simulation + decision-support only."
        ),
        mission_asset="isr-feed",
        max_turns=6,
        detect_deadline=2,
        red_actions=["jam_link", "spoof_feed", "signaling_flood"],
        blue_actions=["detect_threats", "diagnose_threat", "apply_countermeasure"],
        seed_events=[
            {"domain": EventDomain.APP, "entity_id": "isr-feed", "event_type": "FEED_OK",
             "payload": {"integrity": "verified", "target": "isr-feed"}},
        ],
        red_budget=5,
        blue_budget=10,
    )


SCENARIOS: Dict[str, WarGameScenario] = {
    s.scenario_id: s for s in (_tactical_network_scenario(), _isr_tasking_scenario())
}


def get_scenario(scenario_id: str) -> WarGameScenario:
    if scenario_id not in SCENARIOS:
        raise KeyError(f"unknown scenario '{scenario_id}'. Available: {list(SCENARIOS)}")
    return SCENARIOS[scenario_id]
