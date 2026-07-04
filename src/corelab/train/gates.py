"""The G0→G3 gate ledger — enforced order, persisted evidence, no skipping.

Same philosophy as the intent approval ledger: the pipeline cannot proceed to a stage whose
prerequisite gate hasn't passed, and every gate records its evidence for the model card.
State persists to ``training/gates.json`` so the CLI is resumable across sessions.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

GATE_ORDER = ["G0", "G1", "G2", "G3"]

GATE_MEANINGS = {
    "G0": "baseline measured; a gap exists that RAG alone doesn't close",
    "G1": "outcome-validated dataset assembled; contamination rules enforced",
    "G2": "tuned model beats base+RAG on held-out scenarios without general regression",
    "G3": "licences cleared; hedged model card written; artifacts published",
}


class GateError(RuntimeError):
    """A stage was attempted before its prerequisite gate passed."""


class TrainingGates:
    def __init__(self, path: str | Path = "training/gates.json") -> None:
        self.path = Path(path)
        self.state: Dict[str, Dict[str, Any]] = {}
        if self.path.exists():
            try:
                self.state = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self.state = {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.state, indent=2, default=str), encoding="utf-8")

    # ---- recording -----------------------------------------------------------

    def record(self, gate: str, passed: bool, evidence: Optional[Dict[str, Any]] = None) -> None:
        if gate not in GATE_ORDER:
            raise ValueError(f"unknown gate '{gate}' (valid: {GATE_ORDER})")
        self.state[gate] = {
            "passed": passed,
            "ts": datetime.now(timezone.utc).isoformat(),
            "meaning": GATE_MEANINGS[gate],
            "evidence": evidence or {},
        }
        self._save()

    # ---- enforcement ------------------------------------------------------------

    def passed(self, gate: str) -> bool:
        return bool(self.state.get(gate, {}).get("passed"))

    def require(self, gate: str) -> None:
        """Raise unless every gate STRICTLY BEFORE ``gate`` has passed."""
        if gate not in GATE_ORDER:
            raise ValueError(f"unknown gate '{gate}'")
        for prior in GATE_ORDER[: GATE_ORDER.index(gate)]:
            if not self.passed(prior):
                raise GateError(
                    f"cannot proceed to {gate}: prerequisite {prior} has not passed "
                    f"({GATE_MEANINGS[prior]})"
                )

    def status(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for gate in GATE_ORDER:
            entry = self.state.get(gate)
            out[gate] = {
                "passed": bool(entry and entry.get("passed")),
                "meaning": GATE_MEANINGS[gate],
                **({"ts": entry["ts"]} if entry else {}),
            }
        return out
