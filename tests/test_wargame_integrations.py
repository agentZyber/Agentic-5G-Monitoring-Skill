"""P4 integration hooks — external-bench adapter, CAM adaptive red, tamper-evident audit."""

from corelab.wargame import (Action, AdaptiveRedController, ApprovalPolicy, ExternalBenchController,
                             HashChainAudit, ReactiveController, ScriptedController, get_scenario,
                             run_wargame)


def test_external_bench_controller_drives_red():
    sc = get_scenario("contested-tactical-network")
    seen = []

    def bench(role, obs, tools, turn):
        seen.append((role, turn))
        return {"tool": "jam_link", "args": {"element": "link-1"}} if turn == 1 else None

    res = run_wargame(sc, ExternalBenchController(bench, name="ncsrd-bench"),
                      ReactiveController(), ApprovalPolicy(mode="auto-approve"))
    assert res.red == "ncsrd-bench" and res.score.threats_injected == 1
    assert ("red", 1) in seen  # the external bench was consulted for red's move


def test_external_bench_error_is_contained():
    sc = get_scenario("contested-tactical-network")

    def boom(role, obs, tools, turn):
        raise RuntimeError("bench offline")

    res = run_wargame(sc, ExternalBenchController(boom), ReactiveController())
    assert res.score.threats_injected == 0  # the error was held; the game did not crash


def test_adaptive_red_escalates_while_defender_copes():
    sc = get_scenario("contested-tactical-network")
    red = AdaptiveRedController(["jam_link", "signaling_flood", "intrude_node"])
    res = run_wargame(sc, red, ReactiveController(), ApprovalPolicy(mode="auto-approve"))
    # CAM launches a fresh attack every time the defender restores the mission → sustained pressure
    assert res.score.threats_injected >= 2 and red.clean_streak >= 1


def test_hash_chain_audit_detects_tampering():
    chain = HashChainAudit()
    for tid in ("T1", "T2", "T3"):
        chain.record({"action": "apply_countermeasure", "threat_id": tid, "approved": True})
    assert chain.verify() is True
    chain.entries[1]["approved"] = False        # tamper with a past decision
    assert chain.verify() is False


def test_audit_from_approval_log_verifies():
    sc = get_scenario("contested-tactical-network")
    res = run_wargame(sc, ScriptedController([Action("jam_link", {"element": "link-1"})]),
                      ScriptedController([Action("detect_threats"),
                                          Action("apply_countermeasure", {"threat_id": "T1"})]),
                      ApprovalPolicy(mode="auto-approve"))
    chain = HashChainAudit.from_approval_log(res.approval_log)
    assert chain.verify() and len(chain.entries) == len(res.approval_log) >= 1
