"""Intent layer — standards-bridged intent objects + the human-approval ledger.

Two verified intent targets (research pass #2):
- **TM Forum TMF921/TMF921A** on the RDF-based TM Forum Intent Ontology (TIO) — rendered here
  as TIO-style Turtle and JSON-LD.
- **3GPP TS 28.312** Intent Driven Management Service (IDMS, an MnS in SBMA; verified at
  v18.8.0/Rel-18) — rendered as the intentExpectations JSON information model.

Conformance honesty: property vocabularies follow the published TIO examples (``icm:``
namespace) and the TS 28.312 v18 information-model terms (expectationVerb / expectationObject /
expectationTargets, ENSURE/DELIVER, IS_LESS_THAN/…). Strict conformance — SHACL against the
official TIO release and the 28.312 stage-3 schema — is a standards-validation item tracked for
the live/Stage-4 pass; structural validation plus optional rdflib Turtle parsing run everywhere.
"""

from zortenet.intent.ledger import IntentLedger, IntentRecord, IntentStatus
from zortenet.intent.models import (
    Expectation,
    NetworkIntent,
    ValidationReport,
    render_28312_json,
    render_tio_jsonld,
    render_tio_turtle,
    validate_intent,
)

__all__ = [
    "Expectation",
    "NetworkIntent",
    "ValidationReport",
    "render_28312_json",
    "render_tio_jsonld",
    "render_tio_turtle",
    "validate_intent",
    "IntentLedger",
    "IntentRecord",
    "IntentStatus",
]
