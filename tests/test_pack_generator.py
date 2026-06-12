"""The pack generator must produce packs that honor the house contract, loadable as written."""

import importlib.util
import sys

import pytest

from zortenet.packs.new import generate


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_generated_pack_honors_the_contract(tmp_path):
    result = generate("energy-agent", "Energy-efficiency capability.", tmp_path)

    module = _load_module(result["pack_file"], "generated_energy_agent")
    # PACK metadata contract
    assert module.PACK["name"] == "energy-agent"
    assert module.PACK["description"] == "Energy-efficiency capability."
    # build_registry contract: works standalone (graceful degradation)…
    reg = module.build_registry()
    out = reg.get("energy_agent_status").invoke()
    assert "standalone" in out["store"]
    # …and opts into the shared store by parameter name
    from zortenet.core.bus import EventStore

    store = EventStore()
    reg2 = module.build_registry(store=store)
    assert reg2.get("energy_agent_status").invoke()["events_visible"] == 0

    # registration line is copy-pasteable
    assert result["registration"].strip() == '"energy-agent": "zortenet.packs.energy_agent",'
    # a test file was scaffolded too
    assert "test_energy_agent.py" in result["test_file"]


def test_generator_rejects_bad_names_and_duplicates(tmp_path):
    with pytest.raises(SystemExit, match="kebab-case"):
        generate("Bad_Name", "x", tmp_path)
    generate("twice", "x", tmp_path)
    with pytest.raises(SystemExit, match="already exists"):
        generate("twice", "x", tmp_path)
