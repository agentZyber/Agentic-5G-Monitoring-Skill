"""Synthetic supervision generators — every sample machine-validated before it exists.

Two generators (MODEL_PIPELINE.md §2.1 sources #2 and #3):
- **NL → intent pairs**: paraphrase templates over object/metric/condition/value pools; the
  assistant turn is a correct ``draft_intent`` tool call. Each sample is validated through the
  real :func:`validate_intent` — invalid samples cannot be generated.
- **Diagnosis pairs**: synthetic evidence summaries → structured diagnosis whose
  ``suspected_issue`` must be a real playbook key.

Seeded RNG throughout: the same seed reproduces the same dataset (reproducibility > novelty).
"""

from __future__ import annotations

import json
import random
from typing import Any, Dict, List

from zortenet.intent.models import Expectation, NetworkIntent, validate_intent
from zortenet.packs.self_heal import PLAYBOOKS

_OBJECTS = [
    ("NETWORK_SLICE", "slice-embb-{n:02d}"),
    ("NETWORK_SLICE", "slice-urllc-{n:02d}"),
    ("UE", "ue-{n}"),
    ("CELL", "cell-{n}"),
    ("RAN_SUBNETWORK", "ran-sub-{n}"),
]

_METRICS = {
    "latency_ms": ("latency", "ms", "IS_LESS_THAN", (5, 100)),
    "throughput_dl_mbps": ("downlink throughput", "Mbps", "IS_GREATER_THAN", (10, 1000)),
    "throughput_ul_mbps": ("uplink throughput", "Mbps", "IS_GREATER_THAN", (5, 500)),
    "reliability_pct": ("reliability", "%", "IS_GREATER_THAN", (90, 99)),
}

_NL_TEMPLATES = [
    "Keep the {metric_h} of {obj} {direction} {value} {unit}.",
    "Ensure {obj} maintains {metric_h} {direction} {value} {unit}.",
    "I need {obj} to have {metric_h} {direction} {value} {unit} — set that up.",
    "Please guarantee {direction_alt} {value} {unit} {metric_h} for {obj}.",
    "Operations requirement: {obj} must stay {direction} {value} {unit} {metric_h}.",
]

_INTENT_SYSTEM = (
    "You translate operator goals into standards-shaped network intents using the draft_intent tool."
)

_DIAG_TEMPLATES = {
    "ue-connectivity-loss": (
        "Entity {entity}: {n} signaling events in the last window, including "
        "LOSS_OF_CONNECTIVITY and deregistration; last PDU session dropped.",
    ),
    "qos-degradation": (
        "Entity {entity}: QoS alerts with latency {latency} ms (baseline 20 ms); "
        "{n} mobility events across cells in the same window.",
    ),
    "signaling-storm": (
        "Network-wide: {n} registration/attach events in the last window across many entities; "
        "AMF load climbing.",
    ),
    "geofence-breach": (
        "Entity {entity}: location alert — current cell {cell} is outside the allowed policy "
        "set; {n} prior compliant reports.",
    ),
}

_DIAG_SYSTEM = (
    "You are a 5G diagnosis assistant. Given evidence, name the most likely issue as a playbook "
    "key and justify it from the evidence. Respond as JSON: "
    '{"suspected_issue": "...", "rationale": "..."}'
)


def synth_intent_pairs(n: int = 100, seed: int = 42) -> List[Dict[str, Any]]:
    """Generate NL→draft_intent tool-call training pairs; 100% validated by construction."""
    rng = random.Random(seed)
    pairs: List[Dict[str, Any]] = []
    while len(pairs) < n:
        object_type, instance_template = rng.choice(_OBJECTS)
        instance = instance_template.format(n=rng.randint(1, 99))
        metric, (metric_h, unit, condition, (low, high)) = rng.choice(list(_METRICS.items()))
        value = rng.randint(low, high)
        direction = "under" if condition == "IS_LESS_THAN" else "above"
        nl = rng.choice(_NL_TEMPLATES).format(
            metric_h=metric_h, obj=instance, direction=direction,
            direction_alt=("at most" if direction == "under" else "at least"),
            value=value, unit=unit,
        )
        args = {
            "name": f"{metric_h} target for {instance}",
            "object_type": object_type,
            "object_instance": instance,
            "metric": metric,
            "condition": condition,
            "value": value,
        }
        # The generator must be incapable of emitting an invalid sample.
        intent = NetworkIntent(
            intent_id="synth-check",
            name=args["name"],
            expectations=[
                Expectation(
                    object_type=object_type, object_instance=instance,
                    metric=metric, condition=condition, value=value,
                )
            ],
        )
        if not validate_intent(intent, parse_turtle=False).valid:
            continue  # defensive: pools should never produce this
        pairs.append(
            {
                "messages": [
                    {"role": "system", "content": _INTENT_SYSTEM},
                    {"role": "user", "content": nl},
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [{"function": {"name": "draft_intent", "arguments": args}}],
                    },
                ],
                "meta": {"source": "synth-intent", "seed": seed},
            }
        )
    return pairs


def synth_correlation_trajectories(n: int = 40, seed: int = 42) -> List[Dict[str, Any]]:
    """Gold multi-step demonstrations for the G0-identified gap: cross-domain correlation.

    Each trajectory seeds a real EventStore (a UE with a QoS alert + mobility across cells), then
    executes the *ideal* tool sequence against the REAL pack tools — ``diagnose_entity`` then
    ``audit_ue_mobility`` — capturing genuine tool outputs, and emits a final answer that
    correlates them. This teaches the exact habit the bake-off models missed (diagnose → audit
    mobility → conclude UE-specific vs network-wide). Grounded, not fabricated: the tool results
    are real, and the trajectory passes the TeleAgentBench qos-mobility judge by construction.
    """
    from zortenet.agent.tools import ToolRegistry
    from zortenet.core.bus import EventStore
    from zortenet.core.events import EventDomain, NetworkEvent, Severity
    from zortenet.packs.security_sentinel import build_registry as security_registry
    from zortenet.packs.self_heal import build_registry as selfheal_registry

    rng = random.Random(seed)
    system = (
        "You are a 5G network operations agent. Diagnose issues by gathering evidence with tools; "
        "when a UE reports QoS problems, ALWAYS correlate with its mobility before concluding "
        "whether the issue is UE-specific or network-wide."
    )
    out: List[Dict[str, Any]] = []
    for _ in range(n):
        ue = f"ue-{rng.randint(1, 250)}"
        latency = rng.randint(150, 400)
        # sample WITHOUT replacement so every demo is a clean cell-hopping case (>= threshold)
        cells = rng.sample([f"C{i}" for i in range(1, 10)], k=rng.randint(4, 6))

        store = EventStore()
        for cell in cells:
            store.append(NetworkEvent(domain=EventDomain.LOCATION, source="synth", entity_id=ue,
                                      event_type="LOCATION_REPORTING", payload={"cell_id": cell}))
        store.append(NetworkEvent(domain=EventDomain.QOS, source="synth", entity_id=ue,
                                   severity=Severity.ALERT, event_type="QOS_MONITORING",
                                   payload={"latency_ms": latency}))

        reg = ToolRegistry()
        for t in selfheal_registry(store=store).list() + security_registry(store=store).list():
            if t.name not in reg:
                reg.register(t)

        diag = reg.get("diagnose_entity").invoke(entity_id=ue)        # real tool output
        audit = reg.get("audit_ue_mobility").invoke(entity_id=ue)     # real tool output

        final = (
            f"{ue}'s latency is elevated (~{latency} ms vs a ~20 ms baseline) and it has moved "
            f"across {audit['distinct_cells']} cells "
            f"({'cell-hopping detected' if audit['cell_hopping'] else 'normal mobility'}). "
            f"The degradation is UE-specific and correlates with its mobility — investigate "
            f"handover/coverage for {ue} rather than a network-wide fault."
        )
        out.append({
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content":
                    f"{ue} reports poor latency. Diagnose why — is it UE-specific or network-wide?"},
                {"role": "assistant", "content": "",
                 "tool_calls": [{"function": {"name": "diagnose_entity", "arguments": {"entity_id": ue}}}]},
                {"role": "tool", "name": "diagnose_entity", "content": json.dumps(diag, default=str)},
                {"role": "assistant", "content": "",
                 "tool_calls": [{"function": {"name": "audit_ue_mobility", "arguments": {"entity_id": ue}}}]},
                {"role": "tool", "name": "audit_ue_mobility", "content": json.dumps(audit, default=str)},
                {"role": "assistant", "content": final},
            ],
            "meta": {"source": "synth-correlation", "ue": ue, "seed": seed},
        })
    return out


def synth_diagnosis_pairs(n: int = 100, seed: int = 42) -> List[Dict[str, Any]]:
    """Generate evidence→diagnosis pairs; suspected_issue always a real playbook key."""
    rng = random.Random(seed)
    issues = sorted(_DIAG_TEMPLATES)
    pairs: List[Dict[str, Any]] = []
    for i in range(n):
        issue = issues[i % len(issues)]
        template = _DIAG_TEMPLATES[issue][0]
        evidence = template.format(
            entity=f"ue-{rng.randint(1, 99)}",
            n=rng.randint(3, 40),
            latency=rng.randint(150, 500),
            cell=f"CELL-{rng.randint(100, 999)}",
        )
        assert issue in PLAYBOOKS  # the generator's validity contract
        answer = json.dumps(
            {
                "suspected_issue": issue,
                "rationale": f"The evidence pattern matches the {issue} playbook: {evidence}",
            }
        )
        pairs.append(
            {
                "messages": [
                    {"role": "system", "content": _DIAG_SYSTEM},
                    {"role": "user", "content": f"Evidence:\n{evidence}\n\nDiagnose."},
                    {"role": "assistant", "content": answer},
                ],
                "meta": {"source": "synth-diagnosis", "issue": issue, "seed": seed},
            }
        )
    return pairs
