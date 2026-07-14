"""Causal‑AI interoperability contract for CORE‑DT.

Two directions of interop:
  1. The platform exposes its digital twin as a *structural causal model* — a do()/counterfactual oracle an
     external causal‑AI engine can query (via :func:`~corelab.causal.twin.build_causal_registry`, served over
     MCP/A2A like any tool registry).
  2. An external causal engine plugs INTO the platform by implementing :class:`CausalProvider`, so its causal
     graph, attributions and recommendations feed the war‑game agents, the judge, and the operator picture.

All types are plain dataclasses with ``to_dict`` so they serialise cleanly across the interop fabric.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CausalNode:
    id: str
    kind: str = "mechanism"            # "exogenous" | "mechanism" | "outcome" | "intervention"
    label: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "label": self.label}


@dataclass
class CausalEdge:
    src: str
    dst: str
    relation: str = "causes"           # "causes" | "mitigates" | "depends_on"
    weight: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {"src": self.src, "dst": self.dst, "relation": self.relation, "weight": round(self.weight, 3)}


@dataclass
class CausalGraph:
    nodes: List[CausalNode] = field(default_factory=list)
    edges: List[CausalEdge] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"nodes": [n.to_dict() for n in self.nodes], "edges": [e.to_dict() for e in self.edges]}


@dataclass
class Intervention:
    """A do() operator over the twin: treat these threat‑ids as never injected (but‑for)."""

    suppress_threats: List[str] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"suppress_threats": list(self.suppress_threats), "note": self.note}


@dataclass
class CausalOutcome:
    min_availability: float
    mean_availability: float
    end_availability: float
    peak_concurrent: int
    held: bool
    threats_injected: int

    def to_dict(self) -> Dict[str, Any]:
        return {"min_availability": self.min_availability, "mean_availability": self.mean_availability,
                "end_availability": self.end_availability, "peak_concurrent": self.peak_concurrent,
                "held": self.held, "threats_injected": self.threats_injected}


@dataclass
class Counterfactual:
    intervention: Intervention
    factual: CausalOutcome
    counterfactual: CausalOutcome
    effect_availability: float          # mean‑availability delta (counterfactual − factual)

    def to_dict(self) -> Dict[str, Any]:
        return {"intervention": self.intervention.to_dict(), "factual": self.factual.to_dict(),
                "counterfactual": self.counterfactual.to_dict(), "effect_availability": self.effect_availability}


@dataclass
class Attribution:
    cause: str                          # threat‑id (the exogenous adversary action)
    label: str                          # human label, e.g. "jam_link on gNB‑16"
    effect: float                       # but‑for effect on mean mission availability
    rank: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {"cause": self.cause, "label": self.label, "effect": self.effect, "rank": self.rank}


@dataclass
class CausalRecommendation:
    target: str
    action: str
    expected_gain: float
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"target": self.target, "action": self.action,
                "expected_gain": self.expected_gain, "rationale": self.rationale}


class CausalProvider(ABC):
    """The interop contract for a causal‑AI engine (the twin ships a reference implementation).

    An engine that implements these four methods can be onboarded as a first‑class causal reasoner: its graph
    explains the battlespace, its counterfactuals answer "what if", its attributions assign blame, and its
    recommendations propose interventions — all consumable by agents/judge/operator via ``to_dict``.
    """

    name: str = "causal"

    @abstractmethod
    def discover_graph(self) -> CausalGraph:
        """Return the structural causal graph relating adversary actions, assets and the mission outcome."""

    @abstractmethod
    def counterfactual(self, intervention: Intervention) -> Counterfactual:
        """Answer a do()/but‑for query: outcome had the given threats never been injected."""

    @abstractmethod
    def attribute(self, candidates: Optional[List[str]] = None, top: int = 8) -> List[Attribution]:
        """Rank the causes of mission‑availability loss (leave‑one‑out but‑for attribution)."""

    def recommend(self, top: int = 3) -> List[CausalRecommendation]:
        """Propose interventions by estimated causal effect. Optional; default derives from ``attribute``."""
        raise NotImplementedError
