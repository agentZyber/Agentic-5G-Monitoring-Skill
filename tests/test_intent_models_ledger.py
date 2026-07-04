"""Intent models (validation + all three renderings) and the approval state machine."""

import json

import pytest

from corelab.intent.ledger import IntentLedger, IntentStatus, IntentTransitionError
from corelab.intent.models import (
    Expectation,
    NetworkIntent,
    render_28312_json,
    render_tio_jsonld,
    render_tio_turtle,
    validate_intent,
)


def _intent(intent_id="int-001", condition="IS_LESS_THAN", value=20, metric="latency_ms"):
    return NetworkIntent(
        intent_id=intent_id,
        name="Keep eMBB slice latency under 20ms",
        expectations=[
            Expectation(
                object_type="NETWORK_SLICE",
                object_instance="slice-embb-01",
                metric=metric,
                condition=condition,
                value=value,
            )
        ],
        context={"region": "lab-1"},
    )


# ---- validation -----------------------------------------------------------------


def test_valid_intent_passes_and_turtle_parses():
    report = validate_intent(_intent())
    assert report.valid
    assert report.errors == []
    assert report.turtle_parsed is True  # rdflib installed in this env: real parse check


def test_validation_catches_structural_errors():
    bad = _intent(condition="IS_ROUGHLY", value="fast")
    bad.expectations.append(
        Expectation(object_type="UE", object_instance="", metric="latency_ms",
                    condition="IS_WITHIN_RANGE", value=5)
    )
    bad.intent_id = ""
    report = validate_intent(bad)
    assert not report.valid
    joined = " | ".join(report.errors)
    assert "intent_id is required" in joined
    assert "IS_ROUGHLY" in joined
    assert "IS_WITHIN_RANGE requires" in joined
    assert "object_instance is required" in joined


def test_unknown_metric_warns_but_validates():
    report = validate_intent(_intent(metric="vibes_level"))
    assert report.valid
    assert any("vibes_level" in w for w in report.warnings)


# ---- renderings --------------------------------------------------------------------


def test_turtle_rendering_contains_tio_vocabulary():
    turtle = render_tio_turtle(_intent())
    assert "icm:Intent" in turtle
    assert "icm:hasExpectation" in turtle
    assert "icm:PropertyExpectation" in turtle
    assert 'icm:condition "IS_LESS_THAN"' in turtle
    assert "icm:value 20" in turtle


def test_turtle_range_rendering():
    turtle = render_tio_turtle(_intent(condition="IS_WITHIN_RANGE", value=[10, 30]))
    assert "icm:valueLow 10" in turtle
    assert "icm:valueHigh 30" in turtle
    assert validate_intent(_intent(condition="IS_WITHIN_RANGE", value=[10, 30])).valid


def test_jsonld_rendering_round_trips_as_json():
    doc = render_tio_jsonld(_intent())
    parsed = json.loads(json.dumps(doc))
    assert parsed["@type"] == "icm:Intent"
    assert parsed["icm:hasExpectation"][0]["icm:metric"] == "latency_ms"
    assert parsed["@context"]["icm"].startswith("http://tio.models.tmforum.org")


def test_28312_rendering_uses_spec_vocabulary():
    doc = render_28312_json(_intent())
    exp = doc["intentExpectations"][0]
    assert exp["expectationVerb"] == "ENSURE"
    assert exp["expectationObject"]["objectType"] == "NETWORK_SLICE"
    target = exp["expectationTargets"][0]
    assert target["targetName"] == "latency_ms"
    assert target["targetCondition"] == "IS_LESS_THAN"
    assert target["targetValueRange"] == 20
    assert exp["expectationContexts"][0]["contextAttribute"] == "region"
    assert doc["intentAdminState"] == "ACTIVATED"


# ---- ledger state machine ------------------------------------------------------------


def test_happy_path_draft_to_applied():
    ledger = IntentLedger()
    record = ledger.create(_intent())
    assert record.status is IntentStatus.DRAFT
    ledger.set_dry_run("int-001", [{"target": "amarisoft", "op": "config_set"}])
    ledger.submit("int-001")
    assert ledger.get("int-001").status is IntentStatus.AWAITING_APPROVAL
    ledger.approve("int-001", approver="akis")
    ledger.mark_applying("int-001")  # gate passes
    ledger.mark_applied("int-001", outcome={"ok": True})
    final = ledger.get("int-001")
    assert final.status is IntentStatus.APPLIED
    actions = [h["action"] for h in final.history]
    assert actions == ["created", "dry_run", "submitted", "approved", "applied"]
    assert any(h["by"] == "akis" for h in final.history)  # auditability


def test_apply_without_approval_is_blocked():
    ledger = IntentLedger()
    ledger.create(_intent())
    with pytest.raises(IntentTransitionError, match="human approval required"):
        ledger.mark_applying("int-001")  # draft
    ledger.submit("int-001")
    with pytest.raises(IntentTransitionError, match="human approval required"):
        ledger.mark_applying("int-001")  # awaiting_approval — still blocked


def test_invalid_intent_cannot_be_submitted():
    ledger = IntentLedger()
    bad = _intent()
    bad.expectations = []
    ledger.create(bad)
    with pytest.raises(IntentTransitionError, match="failed validation"):
        ledger.submit("int-001")


def test_reject_path_and_terminal_states():
    ledger = IntentLedger()
    ledger.create(_intent())
    ledger.submit("int-001")
    ledger.reject("int-001", approver="akis", reason="not in maintenance window")
    record = ledger.get("int-001")
    assert record.status is IntentStatus.REJECTED
    with pytest.raises(IntentTransitionError):
        ledger.approve("int-001", approver="akis")  # terminal: no re-approval
    with pytest.raises(IntentTransitionError):
        ledger.submit("int-001")


def test_failed_outcome_recorded():
    ledger = IntentLedger()
    ledger.create(_intent())
    ledger.submit("int-001")
    ledger.approve("int-001", approver="ops")
    ledger.mark_applying("int-001")
    ledger.mark_failed("int-001", error="amarisoft unreachable")
    record = ledger.get("int-001")
    assert record.status is IntentStatus.FAILED
    assert record.outcome["error"] == "amarisoft unreachable"


def test_duplicate_and_unknown_ids():
    ledger = IntentLedger()
    ledger.create(_intent())
    with pytest.raises(IntentTransitionError, match="already exists"):
        ledger.create(_intent())
    with pytest.raises(KeyError):
        ledger.get("ghost")
    assert ledger.list(status="draft")[0].intent.intent_id == "int-001"
    assert ledger.list(status=IntentStatus.APPLIED) == []
