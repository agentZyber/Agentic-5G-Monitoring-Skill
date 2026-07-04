"""Intent ledger — the enforced human-approval state machine.

Lifecycle::

    draft ──submit──▶ awaiting_approval ──approve (HUMAN, REST-only)──▶ approved ──apply──▶ applied
                              │                                            │
                              └──reject (HUMAN, REST-only)──▶ rejected     └──(executor error)──▶ failed

Two deliberate security properties:
1. **Approval/rejection are not agent tools.** The pack exposes draft/dry-run/submit/apply;
   approve/reject exist only as REST endpoints a human calls (``POST /intents/{id}/approve``).
2. **Apply is gated.** ``mark_applying`` refuses any record not in ``approved`` — there is no
   code path from draft to applied that skips the human.

Every transition is recorded in the record's history for auditability.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from corelab.intent.models import NetworkIntent, ValidationReport, validate_intent


class IntentStatus(str, Enum):
    DRAFT = "draft"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    FAILED = "failed"


class IntentTransitionError(RuntimeError):
    """An operation was attempted from an illegal state."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class IntentRecord:
    intent: NetworkIntent
    status: IntentStatus = IntentStatus.DRAFT
    validation: Optional[ValidationReport] = None
    dry_run: Optional[List[Dict[str, Any]]] = None
    outcome: Optional[Dict[str, Any]] = None
    history: List[Dict[str, str]] = field(default_factory=list)

    def log(self, action: str, by: str = "agent", note: str = "") -> None:
        self.history.append({"ts": _now(), "action": action, "by": by, "note": note})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent_id": self.intent.intent_id,
            "name": self.intent.name,
            "status": self.status.value,
            "validation": self.validation.to_dict() if self.validation else None,
            "dry_run": self.dry_run,
            "outcome": self.outcome,
            "history": self.history,
        }


class IntentLedger:
    def __init__(self) -> None:
        self._records: Dict[str, IntentRecord] = {}
        self._lock = threading.Lock()

    # ---- agent-side operations ------------------------------------------

    def create(self, intent: NetworkIntent) -> IntentRecord:
        with self._lock:
            if intent.intent_id in self._records:
                raise IntentTransitionError(f"intent '{intent.intent_id}' already exists")
            record = IntentRecord(intent=intent, validation=validate_intent(intent))
            record.log("created", note="valid" if record.validation.valid else "validation errors")
            self._records[intent.intent_id] = record
            return record

    def set_dry_run(self, intent_id: str, plan: List[Dict[str, Any]]) -> IntentRecord:
        record = self.get(intent_id)
        record.dry_run = plan
        record.log("dry_run", note=f"{len(plan)} planned action(s)")
        return record

    def submit(self, intent_id: str) -> IntentRecord:
        record = self.get(intent_id)
        if record.status is not IntentStatus.DRAFT:
            raise IntentTransitionError(f"cannot submit from '{record.status.value}'")
        if not (record.validation and record.validation.valid):
            raise IntentTransitionError("cannot submit an intent that failed validation")
        record.status = IntentStatus.AWAITING_APPROVAL
        record.log("submitted")
        return record

    def mark_applying(self, intent_id: str) -> IntentRecord:
        """Gate check before execution: only an APPROVED intent may be applied."""
        record = self.get(intent_id)
        if record.status is not IntentStatus.APPROVED:
            raise IntentTransitionError(
                f"cannot apply intent in state '{record.status.value}' — human approval required"
            )
        return record

    def mark_applied(self, intent_id: str, outcome: Dict[str, Any]) -> IntentRecord:
        record = self.get(intent_id)
        record.status = IntentStatus.APPLIED
        record.outcome = outcome
        record.log("applied")
        return record

    def mark_failed(self, intent_id: str, error: str) -> IntentRecord:
        record = self.get(intent_id)
        record.status = IntentStatus.FAILED
        record.outcome = {"error": error}
        record.log("failed", note=error)
        return record

    # ---- HUMAN-side operations (REST-only; never exposed as agent tools) ----

    def approve(self, intent_id: str, approver: str) -> IntentRecord:
        record = self.get(intent_id)
        if record.status is not IntentStatus.AWAITING_APPROVAL:
            raise IntentTransitionError(f"cannot approve from '{record.status.value}'")
        record.status = IntentStatus.APPROVED
        record.log("approved", by=approver or "human")
        return record

    def reject(self, intent_id: str, approver: str, reason: str = "") -> IntentRecord:
        record = self.get(intent_id)
        if record.status is not IntentStatus.AWAITING_APPROVAL:
            raise IntentTransitionError(f"cannot reject from '{record.status.value}'")
        record.status = IntentStatus.REJECTED
        record.log("rejected", by=approver or "human", note=reason)
        return record

    # ---- queries -----------------------------------------------------------

    def get(self, intent_id: str) -> IntentRecord:
        with self._lock:
            if intent_id not in self._records:
                raise KeyError(f"unknown intent '{intent_id}'")
            return self._records[intent_id]

    def list(self, status: Optional[IntentStatus | str] = None) -> List[IntentRecord]:
        with self._lock:
            records = list(self._records.values())
        if status is not None:
            wanted = IntentStatus(status) if not isinstance(status, IntentStatus) else status
            records = [r for r in records if r.status is wanted]
        return records
