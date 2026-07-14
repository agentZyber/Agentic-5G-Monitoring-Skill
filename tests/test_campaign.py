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
    assert {"turn", "injects", "mitigations", "active", "compromised", "kpi", "waves", "telemetry"} <= set(f)
    assert 0.0 <= f["kpi"]["availability"] <= 1.0
    for a in f["active"]:
        assert a["node"].startswith("N") and a["kind"] in kinds


def test_frames_carry_correlated_telemetry():
    # a busy turn produces packet-capture, 5G-core and gNB/eNB lines that reference the live events
    frames = list(iter_campaign(80))
    busy = max(frames, key=lambda f: len(f["injects"]) + len(f["mitigations"]))
    tel = busy["telemetry"]
    assert {"pcap", "core", "enb"} <= set(tel)
    assert tel["pcap"] and tel["core"] and tel["enb"]
    blob = " ".join(tel["pcap"] + tel["core"] + tel["enb"])
    assert any(p in blob for p in ("NGAP", "PFCP", "GTP-U", "PRACH", "HTTP2"))   # real 5G interfaces
    assert any(nf in blob for nf in ("[AMF]", "[SMF]", "[UPF]", "[NRF]"))         # core NFs
    # telemetry must not perturb the simulation (separate rng)
    assert run_campaign(80)["summary"]["threats_injected"] == 216


def test_wave_windows_exposed_for_timeline():
    w = wave_windows()
    assert len(w) == 4 and all({"s", "e", "name"} <= set(x) for x in w)
