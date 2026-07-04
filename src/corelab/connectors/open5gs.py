"""Minimal Open5GS client — mirrors the legacy adapter's endpoint map, toolkit-side.

Endpoints (as used by the existing ``src/adapters/open5gs_adapter.py``):
- OAuth2 client-credentials token: ``{nrf_url}/oauth2/token``
- Subscriptions:                   ``{base_url}/namf-subscription/v1/subscriptions``
- UE location:                     ``{base_url}/namf-loc/v1/ues/{id}/location``
- UE info:                         ``{base_url}/namf-comm/v1/ues/{id}``

Read-only here (the legacy adapter keeps subscription write paths); plain-dict returns; the
graceful-degradation contract of the package applies.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests

DEFAULT_BASE_URL = os.getenv("OPEN5GS_BASE_URL", "http://localhost:29508")
DEFAULT_NRF_URL = os.getenv("OPEN5GS_NRF_URL", "http://localhost:29502")


class Open5GSClient:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        nrf_url: str = DEFAULT_NRF_URL,
        client_id: str = "netapp",
        client_secret: str = "secret",
        bearer_token: str = "",
        timeout: int = 10,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.nrf_url = nrf_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.bearer_token = bearer_token
        self.timeout = timeout
        self.session = session or requests.Session()

    # ---- auth ----------------------------------------------------------

    def get_auth_token(self) -> str:
        """OAuth2 client-credentials at the NRF; falls back to a configured static token."""
        try:
            resp = self.session.post(
                f"{self.nrf_url}/oauth2/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                return resp.json().get("access_token", "") or self.bearer_token
        except Exception:
            pass
        return self.bearer_token

    def _headers(self) -> Dict[str, str]:
        token = self.get_auth_token()
        return {"Authorization": f"Bearer {token}"} if token else {}

    def is_available(self) -> bool:
        try:
            resp = self.session.get(
                f"{self.base_url}/namf-subscription/v1/subscriptions",
                headers=self._headers(),
                params={"limit": 1},
                timeout=5,
            )
            return resp.status_code < 500
        except Exception:
            return False

    # ---- reads -----------------------------------------------------------

    def list_subscriptions(self, offset: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        try:
            resp = self.session.get(
                f"{self.base_url}/namf-subscription/v1/subscriptions",
                headers=self._headers(),
                params={"offset": offset, "limit": limit},
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            subs = data.get("subscriptions", data) if isinstance(data, dict) else data
            return subs if isinstance(subs, list) else []
        except Exception:
            return []

    def get_ue_location(self, external_id: str) -> Optional[Dict[str, Any]]:
        try:
            resp = self.session.get(
                f"{self.base_url}/namf-loc/v1/ues/{external_id}/location",
                headers=self._headers(),
                timeout=self.timeout,
            )
            return resp.json() if resp.status_code == 200 else None
        except Exception:
            return None

    def get_ue_info(self, external_id: str) -> Optional[Dict[str, Any]]:
        try:
            resp = self.session.get(
                f"{self.base_url}/namf-comm/v1/ues/{external_id}",
                headers=self._headers(),
                timeout=self.timeout,
            )
            return resp.json() if resp.status_code == 200 else None
        except Exception:
            return None
