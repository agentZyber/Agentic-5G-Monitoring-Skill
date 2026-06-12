"""Intent data model + renderers (TIO Turtle / JSON-LD, TS 28.312 JSON) + validation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# Conditions follow the TS 28.312 targetCondition vocabulary.
VALID_CONDITIONS = (
    "IS_EQUAL_TO",
    "IS_LESS_THAN",
    "IS_GREATER_THAN",
    "IS_WITHIN_RANGE",
)
VALID_VERBS = ("ENSURE", "DELIVER")

# Known target metrics the dry-run mapper understands (extensible; unknown metrics still
# validate — they just won't map to an executor action).
KNOWN_METRICS = ("latency_ms", "throughput_dl_mbps", "throughput_ul_mbps", "reliability_pct", "energy_kwh")

_TIO_PREFIXES = (
    "@prefix icm: <http://tio.models.tmforum.org/tio/v3.6.0/IntentCommonModel#> .\n"
    "@prefix znet: <https://zortenet.example.org/intents#> .\n"
    "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
)


@dataclass
class Expectation:
    """One expectation: a measurable target on an object (slice / UE / cell / NF)."""

    object_type: str            # e.g. "NETWORK_SLICE", "UE", "CELL", "RAN_SUBNETWORK"
    object_instance: str        # e.g. "slice-embb-01", "ue42"
    metric: str                 # e.g. "latency_ms"
    condition: str              # one of VALID_CONDITIONS
    value: Any                  # number or [low, high] for IS_WITHIN_RANGE
    verb: str = "ENSURE"        # ENSURE | DELIVER (TS 28.312 expectationVerb)


@dataclass
class NetworkIntent:
    intent_id: str
    name: str
    expectations: List[Expectation] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)   # e.g. {"validity": "...", "scope": "..."}
    description: str = ""


@dataclass
class ValidationReport:
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    turtle_parsed: Optional[bool] = None  # None = rdflib not installed / not attempted

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "turtle_parsed": self.turtle_parsed,
        }


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_") or "x"


# ---- validation ---------------------------------------------------------------


def validate_intent(intent: NetworkIntent, parse_turtle: bool = True) -> ValidationReport:
    """Structural validation everywhere; optional rdflib parse of the rendered Turtle."""
    errors: List[str] = []
    warnings: List[str] = []

    if not intent.intent_id:
        errors.append("intent_id is required")
    if not intent.name:
        errors.append("name is required")
    if not intent.expectations:
        errors.append("at least one expectation is required")

    for i, exp in enumerate(intent.expectations):
        where = f"expectation[{i}]"
        if exp.verb not in VALID_VERBS:
            errors.append(f"{where}: verb '{exp.verb}' not in {VALID_VERBS}")
        if exp.condition not in VALID_CONDITIONS:
            errors.append(f"{where}: condition '{exp.condition}' not in {VALID_CONDITIONS}")
        if not exp.object_instance:
            errors.append(f"{where}: object_instance is required")
        if exp.condition == "IS_WITHIN_RANGE":
            if not (isinstance(exp.value, (list, tuple)) and len(exp.value) == 2):
                errors.append(f"{where}: IS_WITHIN_RANGE requires a [low, high] value")
        elif not isinstance(exp.value, (int, float)):
            errors.append(f"{where}: value must be numeric for {exp.condition}")
        if exp.metric not in KNOWN_METRICS:
            warnings.append(
                f"{where}: metric '{exp.metric}' is not in the known set {KNOWN_METRICS} — "
                "it validates but has no dry-run executor mapping"
            )

    turtle_parsed: Optional[bool] = None
    if not errors and parse_turtle:
        try:
            import rdflib  # optional: real syntax check of what we generate

            graph = rdflib.Graph()
            graph.parse(data=render_tio_turtle(intent), format="turtle")
            turtle_parsed = len(graph) > 0
            if not turtle_parsed:
                errors.append("rendered Turtle parsed to an empty graph")
        except ImportError:
            turtle_parsed = None  # rdflib absent: structural validation only
        except Exception as exc:
            turtle_parsed = False
            errors.append(f"rendered Turtle failed to parse: {exc}")

    return ValidationReport(valid=not errors, errors=errors, warnings=warnings, turtle_parsed=turtle_parsed)


# ---- renderers ------------------------------------------------------------------


def render_tio_turtle(intent: NetworkIntent) -> str:
    """TIO-style Turtle (icm: vocabulary as used in published TIO examples)."""
    iid = _slug(intent.intent_id)
    lines = [_TIO_PREFIXES]
    exp_refs = " , ".join(f"znet:{iid}_exp{i}" for i in range(len(intent.expectations)))
    lines.append(f"znet:{iid} a icm:Intent ;")
    lines.append(f'    icm:intentOwner "zortenet" ;')
    lines.append(f'    icm:description "{intent.name}" ;')
    lines.append(f"    icm:hasExpectation {exp_refs} .")
    for i, exp in enumerate(intent.expectations):
        low, high = (exp.value if exp.condition == "IS_WITHIN_RANGE" else (exp.value, exp.value))
        lines.append("")
        lines.append(f"znet:{iid}_exp{i} a icm:PropertyExpectation ;")
        lines.append(f"    icm:target znet:{_slug(exp.object_instance)} ;")
        lines.append(f'    icm:targetDescription "{exp.object_type}" ;')
        lines.append(f'    icm:expectationVerb "{exp.verb}" ;')
        lines.append(f'    icm:metric "{exp.metric}" ;')
        lines.append(f'    icm:condition "{exp.condition}" ;')
        if exp.condition == "IS_WITHIN_RANGE":
            lines.append(f"    icm:valueLow {json.dumps(low)} ;")
            lines.append(f"    icm:valueHigh {json.dumps(high)} .")
        else:
            lines.append(f"    icm:value {json.dumps(exp.value)} .")
    return "\n".join(lines) + "\n"


def render_tio_jsonld(intent: NetworkIntent) -> Dict[str, Any]:
    """TIO-style JSON-LD (same vocabulary as the Turtle rendering)."""
    iid = _slug(intent.intent_id)
    return {
        "@context": {
            "icm": "http://tio.models.tmforum.org/tio/v3.6.0/IntentCommonModel#",
            "znet": "https://zortenet.example.org/intents#",
        },
        "@id": f"znet:{iid}",
        "@type": "icm:Intent",
        "icm:intentOwner": "zortenet",
        "icm:description": intent.name,
        "icm:hasExpectation": [
            {
                "@id": f"znet:{iid}_exp{i}",
                "@type": "icm:PropertyExpectation",
                "icm:target": {"@id": f"znet:{_slug(exp.object_instance)}"},
                "icm:targetDescription": exp.object_type,
                "icm:expectationVerb": exp.verb,
                "icm:metric": exp.metric,
                "icm:condition": exp.condition,
                "icm:value": exp.value,
            }
            for i, exp in enumerate(intent.expectations)
        ],
    }


def render_28312_json(intent: NetworkIntent) -> Dict[str, Any]:
    """TS 28.312-style intent (intentExpectations information-model vocabulary, Rel-18)."""
    return {
        "id": intent.intent_id,
        "userLabel": intent.name,
        "intentAdminState": "ACTIVATED",
        "intentExpectations": [
            {
                "expectationId": f"{intent.intent_id}-exp-{i}",
                "expectationVerb": exp.verb,
                "expectationObject": {
                    "objectType": exp.object_type,
                    "objectInstance": exp.object_instance,
                },
                "expectationTargets": [
                    {
                        "targetName": exp.metric,
                        "targetCondition": exp.condition,
                        "targetValueRange": exp.value,
                    }
                ],
                "expectationContexts": [
                    {"contextAttribute": k, "contextCondition": "IS_EQUAL_TO", "contextValueRange": v}
                    for k, v in intent.context.items()
                ],
            }
            for i, exp in enumerate(intent.expectations)
        ],
    }
