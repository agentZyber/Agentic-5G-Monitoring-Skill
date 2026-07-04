"""intent-to-network — NL goal → standards-shaped intent → human approval → applied change.

The agent's tools cover **draft → validate → dry-run → submit → apply**; the approve/reject
steps are deliberately *missing* from this registry — they exist only as human-facing REST
endpoints (``POST /intents/{id}/approve``). The ledger enforces the gate: ``apply_intent`` on
anything not human-approved raises and the agent is told so.

Execution goes through an injected **executor** mapping intent expectations to concrete actions
(Amarisoft ``config_set``, A1 policy PUT, UERANSIM ops). The default ``SimulatedExecutor`` makes
the full flow runnable with zero hardware and labels every outcome ``"simulated": true`` —
real executors are selected at live bring-up.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from corelab.agent.tools import ToolRegistry
from corelab.intent.ledger import IntentLedger, IntentTransitionError
from corelab.intent.models import (
    Expectation,
    NetworkIntent,
    VALID_CONDITIONS,
    render_28312_json,
    render_tio_jsonld,
    render_tio_turtle,
)

PACK: Dict[str, Any] = {
    "name": "intent-to-network",
    "description": "NL → TMF921/TIO + TS 28.312 intents with dry-run, human approval, and gated apply.",
    "connectors": ["amarisoft", "a1-ric", "ueransim"],
    "datasets": [],
    "system_prompt": (
        "You translate operator goals into standards-shaped network intents. Workflow: "
        "draft_intent → review the validation report → dry_run_intent → submit_intent_for_approval. "
        "You CANNOT approve intents — a human must, via the /intents API. Only after approval can "
        "apply_intent succeed. Always show the operator the dry-run plan before submitting."
    ),
}


class SimulatedExecutor:
    """Plans and 'applies' intent actions without touching any network. Honest by construction:
    every result carries ``simulated: True``."""

    name = "simulated"

    # expectation metric -> (target system, operation)
    ROUTES = {
        "latency_ms": ("a1-ric", "put_policy:qos-latency"),
        "throughput_dl_mbps": ("amarisoft", "config_set:dl-rate-limit"),
        "throughput_ul_mbps": ("amarisoft", "config_set:ul-rate-limit"),
        "reliability_pct": ("a1-ric", "put_policy:reliability"),
        "energy_kwh": ("amarisoft", "config_set:tx-power-profile"),
    }

    def plan(self, intent: NetworkIntent) -> List[Dict[str, Any]]:
        actions: List[Dict[str, Any]] = []
        for exp in intent.expectations:
            route = self.ROUTES.get(exp.metric)
            if route is None:
                actions.append(
                    {
                        "target": None,
                        "op": None,
                        "executable": False,
                        "reason": f"no executor route for metric '{exp.metric}'",
                    }
                )
                continue
            target, op = route
            actions.append(
                {
                    "target": target,
                    "op": op,
                    "executable": True,
                    "object": exp.object_instance,
                    "params": {"metric": exp.metric, "condition": exp.condition, "value": exp.value},
                }
            )
        return actions

    def apply(self, intent: NetworkIntent, plan: List[Dict[str, Any]]) -> Dict[str, Any]:
        executed = [a for a in plan if a.get("executable")]
        return {
            "simulated": True,
            "executed_actions": executed,
            "skipped_actions": [a for a in plan if not a.get("executable")],
            "note": "SimulatedExecutor: no real network was modified",
        }


def build_registry(
    ledger: Optional[IntentLedger] = None,
    executor: Optional[Any] = None,
) -> ToolRegistry:
    book = ledger if ledger is not None else IntentLedger()
    runner = executor if executor is not None else SimulatedExecutor()
    reg = ToolRegistry()

    @reg.tool(
        name="draft_intent",
        description=(
            "Draft a standards-shaped network intent from a goal. Returns the validation report "
            "plus TIO Turtle / JSON-LD (TMF921-style) and TS 28.312 JSON renderings. "
            f"Conditions: {', '.join(VALID_CONDITIONS)}."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Human-readable goal"},
                "object_type": {"type": "string", "description": "NETWORK_SLICE | UE | CELL | RAN_SUBNETWORK"},
                "object_instance": {"type": "string", "description": "e.g. slice-embb-01, ue42"},
                "metric": {"type": "string", "description": "e.g. latency_ms, throughput_dl_mbps"},
                "condition": {"type": "string", "description": "e.g. IS_LESS_THAN"},
                "value": {"description": "number, or [low, high] for IS_WITHIN_RANGE"},
            },
            "required": ["name", "object_type", "object_instance", "metric", "condition", "value"],
        },
        tags=("intent", "standards"),
    )
    def draft_intent(
        name: str, object_type: str, object_instance: str, metric: str, condition: str, value: Any
    ) -> Dict[str, Any]:
        intent = NetworkIntent(
            intent_id=f"int-{uuid.uuid4().hex[:8]}",
            name=name,
            expectations=[
                Expectation(
                    object_type=object_type,
                    object_instance=object_instance,
                    metric=metric,
                    condition=condition,
                    value=value,
                )
            ],
        )
        record = book.create(intent)
        return {
            "intent_id": intent.intent_id,
            "status": record.status.value,
            "validation": record.validation.to_dict(),
            "renderings": {
                "tio_turtle": render_tio_turtle(intent),
                "tio_jsonld": render_tio_jsonld(intent),
                "ts28312": render_28312_json(intent),
            },
        }

    @reg.tool(
        name="dry_run_intent",
        description="Map a drafted intent to the concrete actions that WOULD be executed (no changes).",
        parameters={
            "type": "object",
            "properties": {"intent_id": {"type": "string"}},
            "required": ["intent_id"],
        },
        tags=("intent",),
    )
    def dry_run_intent(intent_id: str) -> Dict[str, Any]:
        try:
            record = book.get(intent_id)
        except KeyError as exc:
            return {"error": str(exc)}
        plan = runner.plan(record.intent)
        book.set_dry_run(intent_id, plan)
        return {"intent_id": intent_id, "executor": getattr(runner, "name", "unknown"), "plan": plan}

    @reg.tool(
        name="submit_intent_for_approval",
        description=(
            "Submit a valid drafted intent for HUMAN approval. Approval happens outside the "
            "agent via POST /intents/{id}/approve — you cannot approve it yourself."
        ),
        parameters={
            "type": "object",
            "properties": {"intent_id": {"type": "string"}},
            "required": ["intent_id"],
        },
        tags=("intent", "approval"),
    )
    def submit_intent_for_approval(intent_id: str) -> Dict[str, Any]:
        try:
            record = book.submit(intent_id)
        except (KeyError, IntentTransitionError) as exc:
            return {"error": str(exc)}
        return {
            "intent_id": intent_id,
            "status": record.status.value,
            "next_step": f"a human must POST /intents/{intent_id}/approve (or /reject)",
        }

    @reg.tool(
        name="apply_intent",
        description="Execute a HUMAN-APPROVED intent via the configured executor. Fails on anything unapproved.",
        parameters={
            "type": "object",
            "properties": {"intent_id": {"type": "string"}},
            "required": ["intent_id"],
        },
        tags=("intent", "apply"),
    )
    def apply_intent(intent_id: str) -> Dict[str, Any]:
        try:
            record = book.mark_applying(intent_id)  # raises unless status == approved
        except (KeyError, IntentTransitionError) as exc:
            return {"error": str(exc)}
        plan = record.dry_run if record.dry_run is not None else runner.plan(record.intent)
        try:
            outcome = runner.apply(record.intent, plan)
        except Exception as exc:
            book.mark_failed(intent_id, error=str(exc))
            return {"intent_id": intent_id, "status": "failed", "error": str(exc)}
        book.mark_applied(intent_id, outcome=outcome)
        return {"intent_id": intent_id, "status": "applied", "outcome": outcome}

    @reg.tool(
        name="list_intents",
        description="List intents in the ledger with status and audit history.",
        parameters={
            "type": "object",
            "properties": {"status": {"type": "string", "description": "Optional status filter"}},
        },
        tags=("intent",),
    )
    def list_intents(status: Optional[str] = None) -> Dict[str, Any]:
        try:
            records = book.list(status=status)
        except ValueError:
            return {"error": f"unknown status '{status}'"}
        return {"count": len(records), "intents": [r.to_dict() for r in records]}

    return reg
