"""security-sentinel detections + self-heal diagnosis/playbooks over a seeded EventStore."""

from corelab.core.bus import EventStore
from corelab.core.events import EventDomain, NetworkEvent, Severity
from corelab.packs.security_sentinel import build_registry as build_security
from corelab.packs.self_heal import PLAYBOOKS, build_registry as build_selfheal


def _ev(domain, entity, severity=Severity.INFO, event_type="", **payload):
    return NetworkEvent(
        domain=domain,
        source="test",
        entity_id=entity,
        severity=severity,
        event_type=event_type,
        payload=payload,
    )


def _seeded_store():
    store = EventStore()
    # ue-bad: failure burst (4 alert-severity signaling/security events)
    for _ in range(4):
        store.append(_ev(EventDomain.SIGNALING, "ue-bad", Severity.ALERT, "AUTH_FAILURE"))
    # ue-roam: cell hopping across 5 cells, one geofence alert
    for i, cell in enumerate(["C1", "C2", "C3", "C4", "C5"]):
        sev = Severity.ALERT if i == 4 else Severity.INFO
        store.append(_ev(EventDomain.LOCATION, "ue-roam", sev, "LOCATION_REPORTING", cell_id=cell))
    # ue-ok: quiet UE
    store.append(_ev(EventDomain.LOCATION, "ue-ok", cell_id="C1"))
    return store


# ---- security-sentinel ----------------------------------------------------------


def test_failure_burst_detected_with_counts():
    reg = build_security(store=_seeded_store())
    out = reg.get("detect_signaling_anomalies").invoke()
    bursts = [f for f in out["findings"] if f["type"] == "failure_burst"]
    assert len(bursts) == 1
    assert bursts[0]["entity_id"] == "ue-bad"
    assert bursts[0]["count"] == 4
    assert out["inspected"] == 10


def test_signaling_storm_detected_at_threshold():
    store = EventStore()
    for i in range(20):
        store.append(_ev(EventDomain.SIGNALING, f"ue{i}", event_type="REGISTRATION"))
    out = build_security(store=store).get("detect_signaling_anomalies").invoke()
    assert any(f["type"] == "signaling_storm" and f["count"] == 20 for f in out["findings"])


def test_no_anomalies_on_quiet_store():
    store = EventStore()
    store.append(_ev(EventDomain.LOCATION, "ue1", cell_id="C1"))
    out = build_security(store=store).get("detect_signaling_anomalies").invoke()
    assert out["findings"] == []


def test_empty_store_reports_honestly():
    out = build_security().get("detect_signaling_anomalies").invoke()
    assert out["inspected"] == 0
    assert "empty" in out["note"]


def test_mobility_audit_flags_cell_hopping():
    reg = build_security(store=_seeded_store())
    audit = reg.get("audit_ue_mobility").invoke(entity_id="ue-roam")
    assert audit["distinct_cells"] == 5
    assert audit["cell_hopping"] is True
    assert audit["geofence_alerts"] == 1
    assert audit["cells_visited"][0] in {"C1", "C5"}  # order preserved, most-recent-first source

    quiet = reg.get("audit_ue_mobility").invoke(entity_id="ue-ok")
    assert quiet["cell_hopping"] is False

    unknown = reg.get("audit_ue_mobility").invoke(entity_id="ghost")
    assert "no location events" in unknown["note"]


def test_security_posture_lists_alerting_entities():
    out = build_security(store=_seeded_store()).get("security_posture").invoke()
    assert out["total"] == 10
    assert set(out["entities_with_alerts"]) == {"ue-bad", "ue-roam"}


# ---- self-heal --------------------------------------------------------------------


def test_diagnose_entity_structures_evidence_and_suspects():
    store = _seeded_store()
    # add QoS trouble for ue-bad so multiple suspicions fire
    store.append(_ev(EventDomain.QOS, "ue-bad", Severity.WARNING, "QOS_MONITORING", latency_ms=300))
    store.append(_ev(EventDomain.SIGNALING, "ue-bad", Severity.ALERT, "LOSS_OF_CONNECTIVITY"))

    reg = build_selfheal(store=store)
    diag = reg.get("diagnose_entity").invoke(entity_id="ue-bad")
    assert diag["events"] == 6
    assert diag["by_domain"]["signaling"] == 5
    assert "ue-connectivity-loss" in diag["suspected_issues"]  # LOSS_OF_CONNECTIVITY seen
    assert "qos-degradation" in diag["suspected_issues"]
    assert any("[signaling]" in line for line in diag["recent"])
    assert "human approval" in diag["note"]


def test_diagnose_unknown_entity():
    out = build_selfheal().get("diagnose_entity").invoke(entity_id="ghost")
    assert "no events" in out["note"]


def test_playbooks_lookup_and_approval_note():
    reg = build_selfheal()
    listing = reg.get("list_playbooks").invoke()
    assert set(listing["playbooks"]) == set(PLAYBOOKS)

    pb = reg.get("propose_remediation").invoke(issue="qos-degradation")
    assert pb["remediation_steps"]
    assert "human approval" in pb["note"]
    assert "Stage 3" in pb["note"]

    missing = reg.get("propose_remediation").invoke(issue="nonsense")
    assert "no playbook" in missing["error"]
    assert "qos-degradation" in missing["available"]
