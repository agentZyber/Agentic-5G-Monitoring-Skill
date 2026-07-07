"""Theater campaign — the large-scale, dynamic engagement behind the live map."""
from corelab.wargame.campaign import build_theater, iter_campaign, run_campaign, wave_windows


def test_theater_layout_and_mesh_are_deterministic():
    nodes, edges = build_theater()
    assert len(nodes) == 28
    assert all({"id", "kind", "x", "y", "sector", "crit"} <= set(n) for n in nodes)
    assert len(edges) >= 24 and all(len(e) == 2 for e in edges)
    assert {n["sector"] for n in nodes} == {"Rear", "Main", "Forward"}
    assert build_theater()[0][0]["x"] == nodes[0]["x"]           # seeded → stable


def test_campaign_is_large_dynamic_and_recovers():
    r = run_campaign(80)
    s = r["summary"]
    assert len(r["frames"]) == 80
    assert s["threats_injected"] > 120                            # large scale, not a toy fixture
    assert s["peak_concurrent_threats"] >= 8                      # visibly stressed under the surge
    assert s["min_availability"] < 0.9                            # availability genuinely dips
    assert s["held"] and s["residual_active"] == 0                # blue clears the theater by the end


def test_every_frame_is_map_ready():
    kinds = {"jam_link", "signaling_flood", "intrude_node", "spoof_feed"}
    f = list(iter_campaign(30))[15]
    assert {"turn", "injects", "mitigations", "active", "compromised", "kpi", "waves"} <= set(f)
    assert 0.0 <= f["kpi"]["availability"] <= 1.0
    for a in f["active"]:
        assert a["node"].startswith("N") and a["kind"] in kinds


def test_wave_windows_exposed_for_timeline():
    w = wave_windows()
    assert len(w) == 4 and all({"s", "e", "name"} <= set(x) for x in w)
