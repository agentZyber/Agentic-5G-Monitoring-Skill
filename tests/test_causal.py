"""Causal‑AI interop — the twin as a structural causal model (graph, do()/counterfactual, but‑for attribution)."""
from corelab.causal import (Attribution, CausalProvider, Intervention, TwinCausalModel, build_causal_registry)


def test_twin_is_a_causal_provider():
    assert issubclass(TwinCausalModel, CausalProvider)


def test_causal_graph_has_scm_structure():
    g = TwinCausalModel(turns=40).discover_graph()
    kinds = {n.id: n.kind for n in g.nodes}
    assert kinds.get("adversary") == "exogenous" and kinds.get("mission") == "outcome"
    assert kinds.get("blue") == "intervention"
    # adversary → node(hit) … node → sector … sector → mission  (a real DAG to the outcome)
    assert any(e.src == "adversary" and e.relation == "causes" for e in g.edges)
    assert any(e.dst == "mission" and e.relation == "depends_on" for e in g.edges)


def test_counterfactual_is_an_exact_do_operator():
    m = TwinCausalModel(turns=80)
    causes = [a.cause for a in m.attribute(top=5)]
    cf = m.counterfactual(Intervention(causes))
    assert cf.factual.threats_injected == 216                              # factual unchanged
    assert cf.counterfactual.threats_injected == 216 - len(causes)          # do(): exactly those removed
    assert isinstance(cf.effect_availability, float)


def test_but_for_attribution_ranks_real_causes():
    atts = TwinCausalModel(turns=80).attribute(top=8)
    assert atts and all(a.rank == i + 1 for i, a in enumerate(atts))        # ranked 1..n
    assert all(atts[i].effect >= atts[i + 1].effect for i in range(len(atts) - 1))
    assert atts[0].effect > 0                                              # at least one genuine but‑for cause
    assert " on " in atts[0].label and any(k in atts[0].label for k in
        ("jam_link", "signaling_flood", "intrude_node", "spoof_feed"))


def test_recommend_returns_only_positive_gain_targets():
    recs = TwinCausalModel(turns=80).recommend(top=3)
    assert recs and all(r.expected_gain > 0 and r.action == "apply_countermeasure" for r in recs)


def test_interop_registry_exposes_causal_tools():
    reg = build_causal_registry(TwinCausalModel(turns=40))
    assert {"causal_graph", "causal_counterfactual", "causal_attribute", "causal_recommend"} <= {t.name for t in reg.list()}
    out = reg.get("causal_counterfactual").invoke(suppress_threats=[])      # empty do() → no change
    assert out["counterfactual"]["threats_injected"] == out["factual"]["threats_injected"]
    assert "effect_availability" in out
