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
