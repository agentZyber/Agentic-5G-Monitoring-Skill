"""Reference :class:`~corelab.causal.interfaces.CausalProvider` — the digital twin AS a structural causal model.

The twin is deterministic, seeded and intervention‑based, so counterfactuals are computed **exactly** by
re‑running the campaign with a do()/suppress set — no surrogate model, no identifiability assumptions. That is
the whole point of a digital‑twin war‑game for causal reasoning: the simulator *is* the SCM, and "what if this
attack had never happened?" is a real re‑run, not an estimate.

:func:`build_causal_registry` wraps the provider as a tool registry so any external causal‑AI engine (or an
agent) can call ``causal_graph`` / ``causal_counterfactual`` / ``causal_attribute`` / ``causal_recommend`` over
the platform's MCP/A2A fabric.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from corelab.agent.tools import ToolRegistry
from corelab.causal.interfaces import (Attribution, CausalEdge, CausalGraph, CausalNode, CausalOutcome,
                                       CausalProvider, CausalRecommendation, Counterfactual, Intervention)
from corelab.wargame.campaign import run_campaign


class TwinCausalModel(CausalProvider):
    """Compute causal graph, counterfactuals, attribution and recommendations from the deterministic twin."""

    name = "twin-causal"

    def __init__(self, turns: int = 80, seed: int = 11) -> None:
        self.turns, self.seed = turns, seed
        self._factual = run_campaign(turns, seed)
        self._nodes = self._factual["nodes"]
        self._by_id = {n["id"]: n for n in self._nodes}

    # --- helpers -------------------------------------------------------------------------------------
    @staticmethod
    def _outcome(run: Dict[str, Any]) -> CausalOutcome:
        frames, s = run["frames"], run["summary"]
        mean = sum(f["kpi"]["availability"] for f in frames) / max(1, len(frames))
        return CausalOutcome(min_availability=s["min_availability"], mean_availability=round(mean, 4),
                             end_availability=s["end_availability"], peak_concurrent=s["peak_concurrent_threats"],
                             held=s["held"], threats_injected=s["threats_injected"])

    def _threat_label(self, threat_id: str) -> str:
        for f in self._factual["frames"]:
            for a in f["active"]:
                if a["threat_id"] == threat_id:
                    return f"{a['kind']} on {self._by_id.get(a['node'], {}).get('label', a['node'])}"
        return threat_id

    def _worst_actives(self) -> List[str]:
        worst = min(self._factual["frames"], key=lambda f: f["kpi"]["availability"])
        return [a["threat_id"] for a in worst["active"]]

    # --- CausalProvider ------------------------------------------------------------------------------
    def discover_graph(self) -> CausalGraph:
        """adversary → node(hit) → sector → mission, with blue as an intervention variable on each node."""
        hit: Dict[str, int] = {}
        for f in self._factual["frames"]:
            for inj in f["injects"]:
                hit[inj["node"]] = hit.get(inj["node"], 0) + 1
        nodes = [CausalNode("adversary", "exogenous", "Adversary"),
                 CausalNode("blue", "intervention", "Blue doctrine (countermeasures)"),
                 CausalNode("mission", "outcome", "Mission availability")]
        edges: List[CausalEdge] = []
        for sector in sorted({n["sector"] for n in self._nodes}):
            nodes.append(CausalNode(f"sector:{sector}", "mechanism", f"{sector} sector"))
            edges.append(CausalEdge(f"sector:{sector}", "mission", "depends_on"))
        for nd in self._nodes:
            nid = f"node:{nd['id']}"
            nodes.append(CausalNode(nid, "mechanism", f"{nd['label']} · {nd['domain']}"))
            edges.append(CausalEdge(nid, f"sector:{nd['sector']}", "depends_on"))
            if hit.get(nd["id"]):
                edges.append(CausalEdge("adversary", nid, "causes", weight=float(hit[nd["id"]])))
                edges.append(CausalEdge("blue", nid, "mitigates"))
        return CausalGraph(nodes, edges)

    def counterfactual(self, intervention: Intervention) -> Counterfactual:
        cf = run_campaign(self.turns, self.seed, suppress=frozenset(intervention.suppress_threats))
        factual, counter = self._outcome(self._factual), self._outcome(cf)
        return Counterfactual(intervention, factual, counter,
                              round(counter.mean_availability - factual.mean_availability, 4))

    def attribute(self, candidates: Optional[List[str]] = None, top: int = 8) -> List[Attribution]:
        cands = candidates if candidates is not None else self._worst_actives()
        base = self._outcome(self._factual).mean_availability
        out: List[Attribution] = []
        for cid in cands:
            co = self._outcome(run_campaign(self.turns, self.seed, suppress=frozenset({cid})))
            out.append(Attribution(cid, self._threat_label(cid), round(co.mean_availability - base, 5)))
        out.sort(key=lambda a: a.effect, reverse=True)
        for i, a in enumerate(out):
            a.rank = i + 1
        return out[:top]

    def recommend(self, top: int = 3) -> List[CausalRecommendation]:
        recs: List[CausalRecommendation] = []
        for a in self.attribute(top=top):
            if a.effect <= 0:
                continue
            recs.append(CausalRecommendation(
                target=a.label, action="apply_countermeasure", expected_gain=a.effect,
                rationale=f"but‑for {a.cause}, mean mission availability rises by {a.effect:+.1%}"))
        return recs


def build_causal_registry(provider: CausalProvider) -> ToolRegistry:
    """Expose a causal provider as tools — so external causal‑AI or agents call it over MCP/A2A."""
    reg = ToolRegistry()

    @reg.tool(name="causal_graph", tags=("causal", "interop"),
              description="Structural causal graph relating adversary actions, assets/sectors and the mission.")
    def causal_graph() -> Dict[str, Any]:
        return provider.discover_graph().to_dict()

    @reg.tool(name="causal_counterfactual", tags=("causal", "interop"),
              description="do(): re‑run the twin with the given threat‑ids suppressed; return the availability effect.",
              parameters={"type": "object", "properties": {
                  "suppress_threats": {"type": "array", "items": {"type": "string"}}},
                  "required": ["suppress_threats"]})
    def causal_counterfactual(suppress_threats: List[str]) -> Dict[str, Any]:
        return provider.counterfactual(Intervention(list(suppress_threats))).to_dict()

    @reg.tool(name="causal_attribute", tags=("causal", "interop"),
              description="But‑for attribution: rank causes of mission‑availability loss (leave‑one‑out).",
              parameters={"type": "object", "properties": {
                  "candidates": {"type": "array", "items": {"type": "string"}},
                  "top": {"type": "integer"}}})
    def causal_attribute(candidates: Optional[List[str]] = None, top: int = 8) -> List[Dict[str, Any]]:
        return [a.to_dict() for a in provider.attribute(candidates, top)]

    @reg.tool(name="causal_recommend", tags=("causal", "interop"),
              description="Recommend mitigation targets ranked by estimated causal effect.",
              parameters={"type": "object", "properties": {"top": {"type": "integer"}}})
    def causal_recommend(top: int = 3) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in provider.recommend(top)]

    return reg
