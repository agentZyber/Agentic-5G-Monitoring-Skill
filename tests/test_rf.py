"""RF red/blue episode (real-data-seeded) + its console visualisation."""

from corelab.wargame import rf_episode, rf_scenario_meta, showcase_html


def test_rf_episode_shape_and_radio():
    ep = rf_episode()
    assert ep["scenario_id"] == "rf-contested-cell" and ep["score"]["success"] is True
    assert all("radio" in t for t in ep["timeline"])
    cqi = [{u["id"]: u["cqi"] for u in t["radio"]["ues"]} for t in ep["timeline"]]
    # weak UE (154, high path-loss) is hit hard; strong UE (2) holds; both restored by the end
    assert min(c[154] for c in cqi) <= 10
    assert cqi[-1][154] == 15 and cqi[-1][2] == 15
    assert any(not t["mission_healthy"] for t in ep["timeline"])   # the mission was degraded mid-episode
    # cell power is cut then restored
    powers = [t["radio"]["cell_power_db"] for t in ep["timeline"]]
    assert min(powers) <= -14 and powers[-1] == 0


def test_live_sampler_is_honoured():
    ep = rf_episode(sampler=lambda p: {154: 3, 2: 3})   # a live gNB could return anything
    assert ep["timeline"][0]["radio"]["ues"][0]["cqi"] == 3


def test_console_renders_rf_radio_view():
    ep = rf_episode()
    html = showcase_html({rf_scenario_meta()["scenario_id"]: rf_scenario_meta()}, [ep])
    assert html.startswith("<!doctype html>")
    assert "drawRadio" in html and "cell_power_db" in html and "rf-contested-cell" in html
