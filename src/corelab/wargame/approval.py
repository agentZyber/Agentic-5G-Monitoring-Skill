"""Doctrine gate — meaningful human control over consequential actions, with a full audit trail.

Every consequential blue action (a countermeasure) must pass through an :class:`ApprovalPolicy`.
The policy decides (auto-approve = simulated human authority, deny, or a supplied callback for a
real operator / rules-of-engagement policy) and LOGS every decision. That log is the EU-AI-Act /
ethics-by-design evidence the audit needs: the AI proposes, a human disposes, and it is recorded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ApprovalRequest:
    actor: str
    action: str
    args: Dict[str, Any] = field(default_factory=dict)
    rationale: str = ""


@dataclass
class ApprovalDecision:
    approved: bool
    approver: str = ""
    reason: str = ""


class ApprovalPolicy:
    """Gate + audit log for consequential actions.

    mode: ``"auto-approve"`` (a simulated human authority grants it — the default for reproducible
    runs), ``"deny"`` (verify the gate actually holds), or supply ``callback(req) -> bool`` for a
    real operator prompt or a rules-of-engagement policy.
    """

    def __init__(self, mode: str = "auto-approve",
                 approver: str = "doctrine-authority(simulated-human)",
                 callback: Optional[Callable[[ApprovalRequest], bool]] = None) -> None:
        self.mode = mode
        self.approver = approver
        self.callback = callback
        self.log: List[Dict[str, Any]] = []

    def request(self, req: ApprovalRequest) -> ApprovalDecision:
        if self.callback is not None:
            approved = bool(self.callback(req))
        elif self.mode == "deny":
            approved = False
        else:
            approved = True
        decision = ApprovalDecision(
            approved=approved,
            approver=self.approver if approved else "",
            reason="granted by human doctrine authority" if approved else "denied by policy/ROE",
        )
        self.log.append({
            "actor": req.actor, "action": req.action, "args": dict(req.args),
            "rationale": req.rationale, "approved": approved,
            "approver": decision.approver, "reason": decision.reason,
        })
        return decision

    @property
    def approvals(self) -> int:
        return sum(1 for e in self.log if e["approved"])

    @property
    def denials(self) -> int:
        return sum(1 for e in self.log if not e["approved"])
