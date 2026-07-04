"""synth_uc_trajectories: outcome-grounded diagnose→correlate demos across all 6G use-case packs."""

from corelab.packs import SIXG_PACKS
from corelab.train.synth import synth_uc_bench_trajectories, synth_uc_trajectories


def test_covers_every_uc_with_grounded_conclusions():
    recs = synth_uc_trajectories(n_per_uc=2)
    assert len(recs) == 2 * len(SIXG_PACKS)            # one generator -> data for every UC
    assert {r["meta"]["uc"] for r in recs} == set(SIXG_PACKS)

    for r in recs:
        assert r["meta"]["source"] == "synth-uc"
        roles = [m["role"] for m in r["messages"]]
        # system, user, assistant(assess call), tool, assistant(correlate call), tool, assistant(final)
        assert roles == ["system", "user", "assistant", "tool", "assistant", "tool", "assistant"]
        tool_calls = [m for m in r["messages"] if m.get("tool_calls")]
        assert len(tool_calls) == 2  # assess then correlate
        final = r["messages"][-1]["content"].lower()
        # the seeded scenario plants exactly ONE degraded entity among peers -> entity-specific,
        # never SYSTEMIC. The conclusion is the REAL correlate-tool output (grounded, not fabricated).
        assert "specific" in final and "systemic" not in final


def test_seed_is_deterministic():
    a = synth_uc_trajectories(n_per_uc=1, seed=7)
    b = synth_uc_trajectories(n_per_uc=1, seed=7)
    assert [m["content"] for r in a for m in r["messages"]] == [m["content"] for r in b for m in r["messages"]]


def test_use_case_filter():
    recs = synth_uc_trajectories(n_per_uc=3, use_cases=["energy-agent", "xr-qoe"])
    assert {r["meta"]["uc"] for r in recs} == {"energy-agent", "xr-qoe"}
    assert len(recs) == 6


def test_bench_matched_trajectories_match_eval_context():
    """v2.6: trajectories must use the realistic eval context (DEFAULT+UC packs, concatenated
    prompt) and still chain assess→correlate with real, error-free tool outputs."""
    recs = synth_uc_bench_trajectories(n_per_uc=1)
    assert len(recs) == 8 and {r["meta"]["uc"] for r in recs} == set(SIXG_PACKS)
    for r in recs:
        assert len(r["messages"][0]["content"]) > 800  # multi-pack system prompt, not the 4-tool toy
        tcs = [tc["function"]["name"] for m in r["messages"] for tc in (m.get("tool_calls") or [])]
        assert any(t.startswith("assess_") for t in tcs) and any(t.startswith("correlate_") for t in tcs)
        assert not any("ERROR" in str(m.get("content", "")) for m in r["messages"] if m.get("role") == "tool")
        final = r["messages"][-1]["content"].lower()
        assert "specific" in final and "systemic" not in final
