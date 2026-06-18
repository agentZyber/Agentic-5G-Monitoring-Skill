"""The benchmark registry: axis coverage, contamination flags, and the recommended suite."""

import pytest

from zortenet.bench.registry import (
    AXES,
    RECOMMENDED_SUITE,
    REGISTRY,
    Benchmark,
    contamination_watchlist,
    get_benchmark,
    list_benchmarks,
)


def test_every_axis_has_at_least_one_benchmark():
    covered = {b.axis for b in REGISTRY.values()}
    assert covered == set(AXES)  # knowledge, tool-calling, intent-config, agentic-ops, telemetry


def test_framework_benchmarks_are_wired():
    assert get_benchmark("teleqna").status == "wired"
    assert get_benchmark("teleagentbench").status == "wired"
    # the agentic one is the only built-in with real-state outcome validation
    assert "outcome validation" in get_benchmark("teleagentbench").note


def test_gsma_open_telco_components_present():
    # The 2025 industry-standard suite's components map to our packs.
    for name in ("teleyaml", "telelogs", "telemath", "3gpp-tsg"):
        assert name in REGISTRY
    assert get_benchmark("teleyaml").axis == "intent-config"   # ~ intent-to-network
    assert get_benchmark("telelogs").axis == "agentic-ops"     # ~ self-heal diagnosis


def test_oran_and_netconf_map_to_packs():
    assert get_benchmark("oran-bench-13k").axis == "knowledge"      # O-RAN / A1 knowledge
    assert get_benchmark("netconfeval").axis == "intent-config"     # NL -> config / API calls
    assert get_benchmark("netconfeval").contamination_risk is True


def test_tool_calling_regression_axis_exists():
    tool = {b.name for b in list_benchmarks(axis="tool-calling")}
    assert any("BFCL" in n for n in tool)  # the function-calling regression anchor


def test_contamination_watchlist_covers_eval_only_sets():
    watch = contamination_watchlist()
    # knowledge/intent eval sets must be guarded; pure regression/telemetry sets need not be
    assert "TeleQnA" in watch
    assert "TeleYAML" in watch
    assert "ORAN-Bench-13K" in watch
    assert "BFCL (Berkeley Function-Calling Leaderboard)" not in watch  # regression, not eval-only


def test_recommended_suite_spans_all_axes_with_known_names():
    assert set(RECOMMENDED_SUITE) == set(AXES)
    for axis, names in RECOMMENDED_SUITE.items():
        assert names, f"{axis} has no recommended benchmark"
        for name in names:
            assert name in REGISTRY, f"{name} not in registry"
            assert REGISTRY[name].axis == axis


def test_invalid_axis_rejected_at_construction_and_query():
    with pytest.raises(ValueError):
        Benchmark("x", "not-an-axis", "mcq", "src", "lic", "external", False)
    with pytest.raises(ValueError):
        list_benchmarks(axis="bogus")
    with pytest.raises(KeyError):
        get_benchmark("nonexistent-bench")
