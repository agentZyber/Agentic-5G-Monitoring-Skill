"""ran-opt-copilot v0 — the LLM supervises the RAN; near-RT control stays with xApps.

The verified division of labor (research passes #1–2): classical RL/xApps own the near-RT loop
(10 ms–1 s; e.g. the REAL framework's PPO slicing over E2), while the LLM agent operates at the
**rApp / Non-RT timescale** — observing KPM-ish state, explaining it, and *proposing* A1 policy
changes that flow through the intent approval ledger. This pack never bypasses the gate: its
``propose_slice_policy`` drafts an intent; apply happens via the intent-to-network flow after a
human approves.

Raw E2 termination (SCTP/E2AP) is intentionally out of scope here — that lives in the RIC; our
path to the RAN is the RIC's northbound (A1). Live OSC-RIC validation is the Tier-2/3 item.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from zortenet.agent.tools import ToolRegistry
from zortenet.connectors.a1_ric import A1PolicyClient
from zortenet.core.bus import EventStore
from zortenet.intent.ledger import IntentLedger
from zortenet.intent.models import Expectation, NetworkIntent

PACK: Dict[str, Any] = {
    "name": "ran-opt-copilot",
    "description": "LLM-supervised RAN optimization at the Non-RT/rApp timescale (A1 policies via approval flow).",
    "connectors": ["a1-ric", "prometheus", "ueransim"],
    "datasets": ["5g3e"],
    "system_prompt": (
        "You are a RAN optimization copilot operating at the Non-RT (rApp) timescale. Near-real-"
        "time control belongs to xApps/RL — you observe, explain, and propose A1 policies. Any "
        "policy change must go through the intent approval flow (a human approves); never claim "
        "you changed the RAN directly."
    ),
}


def build_registry(
    a1: Optional[A1PolicyClient] = None,
    store: Optional[EventStore] = None,
    ledger: Optional[IntentLedger] = None,
) -> ToolRegistry:
    ric = a1 or A1PolicyClient()
    events = store if store is not None else EventStore()
    book = ledger if ledger is not None else IntentLedger()
    reg = ToolRegistry()

    @reg.tool(
        name="list_policy_types",
        description="List A1 policy types registered on the Non-RT RIC (what the xApps accept).",
        tags=("oran", "a1"),
    )
    def list_policy_types() -> Dict[str, Any]:
        if not ric.is_available():
            return {
                "available": False,
                "note": f"A1/RIC unreachable at {ric.base_url} — bring up the OSC RIC (Tier-2 profile)",
            }
        types = ric.policy_types()
        return {"available": True, "policy_types": types, "count": len(types)}

    @reg.tool(
        name="get_ran_policies",
        description="List active A1 policies for a policy type, with status where available.",
        parameters={
            "type": "object",
            "properties": {"type_id": {"type": "integer", "description": "A1 policy type id"}},
            "required": ["type_id"],
        },
        tags=("oran", "a1"),
    )
    def get_ran_policies(type_id: int) -> Dict[str, Any]:
        if not ric.is_available():
            return {"available": False, "note": f"A1/RIC unreachable at {ric.base_url}"}
        policies = ric.policies(type_id)
        return {
            "available": True,
            "type_id": type_id,
            "policies": [
                {"policy_id": p, "status": ric.policy_status(type_id, str(p))} for p in policies
            ],
        }

    @reg.tool(
        name="explain_ran_state",
        description=(
            "Summarize current RAN state from the event store (ran_kpi/throughput/signaling "
            "domains): entities, alert counts, and the most recent KPI lines — the evidence base "
            "for proposing a policy."
        ),
        parameters={
            "type": "object",
            "properties": {"window": {"type": "integer", "description": "events to inspect (default 200)"}},
        },
        tags=("oran", "observability"),
    )
    def explain_ran_state(window: int = 200) -> Dict[str, Any]:
        kpi = events.recent(domain="ran_kpi", limit=window)
        throughput = events.recent(domain="throughput", limit=window)
        if not kpi and not throughput:
            return {"note": "no RAN telemetry in the store — replay 5G3E data or attach a live source"}
        return {
            "ran_kpi_events": len(kpi),
            "throughput_events": len(throughput),
            "entities": sorted(
                {e.entity_id for e in [*kpi, *throughput] if e.entity_id}
            ),
            "recent": [e.text_repr() for e in [*kpi[:8], *throughput[:4]]],
        }

    @reg.tool(
        name="propose_slice_policy",
        description=(
            "Draft a RAN slice policy proposal as an APPROVAL-GATED intent (latency or "
            "throughput target on a slice). Returns the intent id to dry-run/submit via the "
            "intent-to-network tools — this does NOT touch the RIC."
        ),
        parameters={
            "type": "object",
            "properties": {
                "slice_id": {"type": "string", "description": "e.g. slice-embb-01"},
                "metric": {"type": "string", "description": "latency_ms | throughput_dl_mbps | throughput_ul_mbps"},
                "condition": {"type": "string", "description": "e.g. IS_LESS_THAN"},
                "value": {"description": "target value"},
                "rationale": {"type": "string", "description": "why — cite explain_ran_state evidence"},
            },
            "required": ["slice_id", "metric", "condition", "value", "rationale"],
        },
        tags=("oran", "intent"),
    )
    def propose_slice_policy(
        slice_id: str, metric: str, condition: str, value: Any, rationale: str
    ) -> Dict[str, Any]:
        intent = NetworkIntent(
            intent_id=f"ran-{uuid.uuid4().hex[:8]}",
            name=f"RAN slice policy: {metric} {condition} {value} on {slice_id}",
            description=rationale,
            expectations=[
                Expectation(
                    object_type="NETWORK_SLICE",
                    object_instance=slice_id,
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
            "rationale": rationale,
            "next_steps": "dry_run_intent → submit_intent_for_approval → human approval → apply_intent",
        }

    return reg
