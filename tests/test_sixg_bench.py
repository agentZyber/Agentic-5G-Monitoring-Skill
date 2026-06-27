"""sixg_scenarios: per-use-case correlation scenarios are well-formed, entity-specific, and judged right."""

from zortenet.agent.runtime import AgentResult
from zortenet.bench.teleagent import SIXG_SCENARIO_PACKS, ScenarioContext, sixg_scenarios
from zortenet.core.bus import EventBus
from zortenet.intent.ledger import IntentLedger
from zortenet.packs import load_packs


def test_scenarios_well_formed_and_ground_truth_entity_specific():
    scen = sixg_scenarios()
    assert {s.scenario_id for s in scen} == set(SIXG_SCENARIO_PACKS)
    for s in scen:
        ctx = ScenarioContext(bus=EventBus(), ledger=IntentLedger())
        s.setup(ctx)
        assert len(ctx.bus.store) > 0  # the scenario actually seeded events
        # the matching pack's correlate tool, run on the seeded store, must conclude entity-specific
        pack = SIXG_SCENARIO_PACKS[s.scenario_id]
        reg, _ = load_packs([pack], context={"store": ctx.bus.store})
        corr = next(n for n in reg.names() if n.startswith("correlate_"))
        conclusion = (reg.get(corr).invoke().get("conclusion", "")).lower()
        assert "specific" in conclusion and "systemic" not in conclusion, (s.scenario_id, conclusion)


def test_judge_rewards_assess_then_correlate():
    s = next(x for x in sixg_scenarios() if x.scenario_id == "energy-saving-correlation")
    ctx = ScenarioContext(bus=EventBus(), ledger=IntentLedger())
    s.setup(ctx)
    good = AgentResult(
        answer="cell-7 is the energy-saving candidate; the inefficiency is cell-specific.",
        messages=[{"role": "tool", "name": "assess_cell_energy"},
                  {"role": "tool", "name": "correlate_energy_load"}],
    )
    bad = AgentResult(answer="the network looks fine", messages=[])
    assert all(c.passed for c in s.judge(good, ctx))
    assert not all(c.passed for c in s.judge(bad, ctx))
