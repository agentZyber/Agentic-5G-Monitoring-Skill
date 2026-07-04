"""intent-to-network pack: the full draft→dry-run→submit→(human)→apply flow, gates included."""

from corelab.intent.ledger import IntentLedger
from corelab.packs.intent_to_network import PACK, SimulatedExecutor, build_registry


def _draft(reg, **overrides):
    args = dict(
        name="Slice latency under 20ms",
        object_type="NETWORK_SLICE",
        object_instance="slice-embb-01",
        metric="latency_ms",
        condition="IS_LESS_THAN",
        value=20,
    )
    args.update(overrides)
    return reg.get("draft_intent").invoke(**args)


def test_pack_has_no_approval_tool():
    reg = build_registry()
    names = set(reg.names())
    assert names == {
        "draft_intent",
        "dry_run_intent",
        "submit_intent_for_approval",
        "apply_intent",
        "list_intents",
    }
    # The security property: approval is not in the agent's vocabulary at all.
    assert not any("approve" in n or "reject" in n for n in names)
    assert "cannot approve" in PACK["system_prompt"].lower() or "CANNOT approve" in PACK["system_prompt"]


def test_draft_returns_all_three_renderings_and_validation():
    reg = build_registry()
    out = _draft(reg)
    assert out["status"] == "draft"
    assert out["validation"]["valid"] is True
    assert "icm:Intent" in out["renderings"]["tio_turtle"]
    assert out["renderings"]["tio_jsonld"]["@type"] == "icm:Intent"
    assert out["renderings"]["ts28312"]["intentExpectations"][0]["expectationVerb"] == "ENSURE"


def test_dry_run_routes_metrics_to_targets():
    reg = build_registry()
    intent_id = _draft(reg)["intent_id"]
    plan = reg.get("dry_run_intent").invoke(intent_id=intent_id)
    assert plan["executor"] == "simulated"
    action = plan["plan"][0]
    assert action["executable"] is True
    assert action["target"] == "a1-ric"  # latency routes to the RIC policy path
    assert action["params"]["value"] == 20

    unmapped = _draft(reg, metric="vibes_level")["intent_id"]
    plan2 = reg.get("dry_run_intent").invoke(intent_id=unmapped)
    assert plan2["plan"][0]["executable"] is False
    assert "no executor route" in plan2["plan"][0]["reason"]


def test_apply_blocked_until_human_approves():
    ledger = IntentLedger()
    reg = build_registry(ledger=ledger)
    intent_id = _draft(reg)["intent_id"]
    reg.get("dry_run_intent").invoke(intent_id=intent_id)

    # Apply on a draft: blocked.
    blocked = reg.get("apply_intent").invoke(intent_id=intent_id)
    assert "human approval required" in blocked["error"]

    submitted = reg.get("submit_intent_for_approval").invoke(intent_id=intent_id)
    assert submitted["status"] == "awaiting_approval"
    assert "/intents/" in submitted["next_step"]  # points the human at the REST gate

    # Still blocked while awaiting approval.
    still_blocked = reg.get("apply_intent").invoke(intent_id=intent_id)
    assert "human approval required" in still_blocked["error"]

    # The HUMAN approves out-of-band (REST path drives this same ledger call).
    ledger.approve(intent_id, approver="akis")

    applied = reg.get("apply_intent").invoke(intent_id=intent_id)
    assert applied["status"] == "applied"
    assert applied["outcome"]["simulated"] is True  # honest executor
    assert applied["outcome"]["executed_actions"][0]["target"] == "a1-ric"

    record = ledger.get(intent_id)
    assert [h["action"] for h in record.history] == [
        "created", "dry_run", "submitted", "approved", "applied",
    ]


def test_invalid_draft_cannot_be_submitted():
    reg = build_registry()
    out = _draft(reg, condition="IS_ROUGHLY")
    assert out["validation"]["valid"] is False
    submit = reg.get("submit_intent_for_approval").invoke(intent_id=out["intent_id"])
    assert "failed validation" in submit["error"]


def test_executor_failure_marks_failed():
    class ExplodingExecutor(SimulatedExecutor):
        name = "exploding"

        def apply(self, intent, plan):
            raise RuntimeError("amarisoft unreachable")

    ledger = IntentLedger()
    reg = build_registry(ledger=ledger, executor=ExplodingExecutor())
    intent_id = _draft(reg)["intent_id"]
    reg.get("submit_intent_for_approval").invoke(intent_id=intent_id)
    ledger.approve(intent_id, approver="ops")

    out = reg.get("apply_intent").invoke(intent_id=intent_id)
    assert out["status"] == "failed"
    assert "amarisoft unreachable" in out["error"]
    assert ledger.get(intent_id).status.value == "failed"


def test_list_intents_with_filter():
    reg = build_registry()
    _draft(reg)
    listing = reg.get("list_intents").invoke(status="draft")
    assert listing["count"] == 1
    assert listing["intents"][0]["status"] == "draft"
    assert reg.get("list_intents").invoke(status="applied")["count"] == 0
    assert reg.get("dry_run_intent").invoke(intent_id="ghost")["error"]
