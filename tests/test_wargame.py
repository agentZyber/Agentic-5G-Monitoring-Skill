"""wargame: deterministic (scripted) end-to-end — scoring, doctrine gate, guardrails, leaderboard."""

from corelab.wargame import (Action, ApprovalPolicy, ReactiveController, ScriptedController,
                              blue_configs, dashboard_html, get_scenario, leaderboard,
                              result_markdown, run_matchups, run_wargame, scripted_reds)


def test_approved_countermeasure_restores_mission():
    sc = get_scenario("contested-tactical-network")
    red = ScriptedController([Action("jam_link", {"element": "link-1"})])
    blue = ScriptedController([Action("detect_threats"),
                              Action("apply_countermeasure", {"threat_id": "T1"})])
    res = run_wargame(sc, red, blue, ApprovalPolicy(mode="auto-approve"))
    assert res.score.success is True
    assert res.score.threats_neutralised == 1 and res.score.time_to_detect == 0
    assert {c.name: c.passed for c in res.score.checks} == {
        "mission-available": True, "threat-detected-in-time": True,
        "threats-neutralised": True, "human-control-held": True}
    assert res.approval_log and res.approval_log[0]["approved"] is True


def test_doctrine_gate_holds_when_denied():
    sc = get_scenario("contested-tactical-network")
    red = ScriptedController([Action("jam_link", {"element": "link-1"})])
    blue = ScriptedController([Action("detect_threats"),
                              Action("apply_countermeasure", {"threat_id": "T1"})])
    res = run_wargame(sc, red, blue, ApprovalPolicy(mode="deny"))
    assert res.score.success is False                 # mission lost — countermeasure was blocked
    assert res.score.unauthorized_applies == 0        # ...but nothing ran without approval
    checks = {c.name: c.passed for c in res.score.checks}
    assert checks["human-control-held"] is True and checks["mission-available"] is False
    assert res.approval_log[0]["approved"] is False


def test_guardrail_drops_invalid_and_over_budget_actions():
    sc = get_scenario("contested-tactical-network")
    red = ScriptedController([Action("no_such_weapon", {"element": "x"})])  # hallucinated tool
    blue = ScriptedController([Action("detect_threats")])
    res = run_wargame(sc, red, blue)
    assert "invalid-action" in (res.timeline[0].red_action or "")
    assert res.score.threats_injected == 0            # nothing was injected


def test_reactive_beats_passive_on_leaderboard():
    sc = get_scenario("contested-tactical-network")
    results = run_matchups(sc, scripted_reds(sc), blue_configs(sc))
    board = {row["blue"]: row for row in leaderboard(results)}
    assert board["blue:reactive-heuristic"]["win_rate"] == 1.0
    assert board["blue:passive"]["win_rate"] == 0.0
    assert (board["blue:reactive-heuristic"]["mean_availability"]
            > board["blue:passive"]["mean_availability"])


def test_reactive_handles_multi_vector_red():
    sc = get_scenario("contested-tactical-network")
    red = ScriptedController([Action("jam_link", {"element": "link-1"}),
                              Action("signaling_flood", {"element": "cell-1"}),
                              Action("intrude_node", {"element": "node-1"})])
    res = run_wargame(sc, red, ReactiveController(), ApprovalPolicy(mode="auto-approve"))
    assert res.score.threats_injected == 3 and res.score.threats_neutralised == 3
    assert res.score.success is True


def test_observer_hook_fires_each_turn():
    """The step-by-step guided demo relies on the per-turn observer being called every turn."""
    sc = get_scenario("contested-tactical-network")
    seen = []
    run_wargame(sc, ScriptedController([Action("jam_link", {"element": "link-1"})]),
                ReactiveController(), ApprovalPolicy(mode="auto-approve"),
                observer=lambda t, rec, w: seen.append((t, rec.mission_healthy)))
    assert [t for t, _ in seen] == list(range(1, sc.max_turns + 1))


def test_evidence_artifacts_render():
    sc = get_scenario("contested-tactical-network")
    results = run_matchups(sc, scripted_reds(sc), blue_configs(sc))
    md = result_markdown(results[-1])
    assert "War-game" in md and "Human-control" in md and "Timeline" in md
    html = dashboard_html(sc, results, leaderboard(results))
    assert html.startswith("<!doctype html>") and "leaderboard" in html.lower()
    assert "human-in-the-loop" in html and "doctrine" in html.lower()
