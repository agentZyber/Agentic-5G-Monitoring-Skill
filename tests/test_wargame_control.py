"""Smoke tests for the War-Game Mission Control panel (registry + page + API; no subprocesses)."""
from fastapi.testclient import TestClient

from corelab.wargame.control import build_control_app, build_registry


def test_registry_covers_every_group_and_gates_hardware():
    reg = {t.id: t for t in build_registry()}
    # a representative test from each group is present
    assert {"pytest-wargame", "scenario-tactical", "mock-9of9", "evidence-pack",
            "llm-base", "bpf-hunt-vm", "rf-live"} <= set(reg)
    # local tests always runnable; hardware tests carry a requirement tag
    assert reg["scenario-tactical"].enabled and reg["mock-9of9"].enabled
    assert reg["llm-base"].requires == "gpu"
    assert reg["rf-live"].requires == "amarisoft"
    # a locked test still exposes a copyable command + a hint
    if not reg["rf-live"].enabled:
        assert reg["rf-live"].cmd and reg["rf-live"].lock_hint


def test_index_page_and_api_render():
    client = TestClient(build_control_app())
    page = client.get("/")
    assert page.status_code == 200
    assert "War-Game Mission Control" in page.text
    assert "__TESTS__" not in page.text            # the registry was injected
    api = client.get("/api/tests").json()
    ids = {t["id"] for t in api}
    assert "mock-9of9" in ids
    assert all("argv" not in t for t in api)        # internal argv never leaks to the client


def test_unknown_test_is_404():
    client = TestClient(build_control_app())
    assert client.get("/api/run/does-not-exist").status_code == 404
