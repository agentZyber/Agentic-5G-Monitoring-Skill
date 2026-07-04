"""A1 policy client — the Non-RT-RIC face (OSC A1 mediator REST, A1-P paths).

A1 is the verified O-RAN interface where *policies* flow from the Non-RT RIC (rApps) down to
the Near-RT RIC — exactly the timescale where an LLM agent belongs (research pass #2 and the
REAL/PPO finding: classical RL owns the near-RT loop; the agent supervises above it).

Paths follow the OSC A1 mediator / A1-P convention::

    GET    /a1-p/healthcheck
    GET    /a1-p/policytypes
    GET    /a1-p/policytypes/{ptid}
    GET    /a1-p/policytypes/{ptid}/policies
    PUT    /a1-p/policytypes/{ptid}/policies/{pid}     (body = policy JSON)
    GET    /a1-p/policytypes/{ptid}/policies/{pid}/status
    DELETE /a1-p/policytypes/{ptid}/policies/{pid}

**Validation status:** mock-tested; exercised against a live OSC RIC at Tier-2/3 bring-up.
Policy writes are expected to flow through the intent approval ledger, not free-form.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests

DEFAULT_BASE_URL = os.getenv("A1_BASE_URL", "http://localhost:10000")


class A1PolicyClient:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = 10,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()

    def is_available(self) -> bool:
        try:
            resp = self.session.get(f"{self.base_url}/a1-p/healthcheck", timeout=5)
            return resp.status_code in (200, 204)
        except Exception:
            return False

    def policy_types(self) -> List[Any]:
        try:
            resp = self.session.get(f"{self.base_url}/a1-p/policytypes", timeout=self.timeout)
            return resp.json() if resp.status_code == 200 else []
        except Exception:
            return []

    def policy_type(self, type_id: int) -> Optional[Dict[str, Any]]:
        try:
            resp = self.session.get(
                f"{self.base_url}/a1-p/policytypes/{type_id}", timeout=self.timeout
            )
            return resp.json() if resp.status_code == 200 else None
        except Exception:
            return None

    def policies(self, type_id: int) -> List[Any]:
        try:
            resp = self.session.get(
                f"{self.base_url}/a1-p/policytypes/{type_id}/policies", timeout=self.timeout
            )
            return resp.json() if resp.status_code == 200 else []
        except Exception:
            return []

    def put_policy(self, type_id: int, policy_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
        try:
            resp = self.session.put(
                f"{self.base_url}/a1-p/policytypes/{type_id}/policies/{policy_id}",
                json=body,
                timeout=self.timeout,
            )
            ok = resp.status_code in (200, 201, 202)
            return {"ok": ok, "status_code": resp.status_code, "policy_id": policy_id}
        except Exception as exc:
            return {"ok": False, "error": f"A1 unreachable: {exc}", "policy_id": policy_id}

    def policy_status(self, type_id: int, policy_id: str) -> Optional[Dict[str, Any]]:
        try:
            resp = self.session.get(
                f"{self.base_url}/a1-p/policytypes/{type_id}/policies/{policy_id}/status",
                timeout=self.timeout,
            )
            return resp.json() if resp.status_code == 200 else None
        except Exception:
            return None

    def delete_policy(self, type_id: int, policy_id: str) -> bool:
        try:
            resp = self.session.delete(
                f"{self.base_url}/a1-p/policytypes/{type_id}/policies/{policy_id}",
                timeout=self.timeout,
            )
            return resp.status_code in (202, 204)
        except Exception:
            return False
