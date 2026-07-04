"""NWDAF analytics client (stub).

Targets the 3GPP Nnwdaf_AnalyticsInfo service API shape
(``GET {base}/nnwdaf-analyticsinfo/v1/analytics?event-id=...``). Marked a **stub** deliberately:
neither Open5GS nor UERANSIM in the default testbed ships an NWDAF — free5GC provides one, and
that pairing is validated when a free5GC profile lands. Until then this client gives packs a
stable interface that degrades gracefully (clearly-labeled "no NWDAF deployed" results).
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import requests

DEFAULT_BASE_URL = os.getenv("NWDAF_BASE_URL", "http://localhost:29520")

# Common Nnwdaf event ids (3GPP TS 29.520 vocabulary)
KNOWN_EVENT_IDS = (
    "LOAD_LEVEL_INFORMATION",
    "NETWORK_PERFORMANCE",
    "NF_LOAD",
    "UE_MOBILITY",
    "UE_COMM",
    "ABNORMAL_BEHAVIOUR",
)


class NWDAFClient:
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
            resp = self.session.get(
                f"{self.base_url}/nnwdaf-analyticsinfo/v1/analytics",
                params={"event-id": "NF_LOAD"},
                timeout=5,
            )
            return resp.status_code < 500
        except Exception:
            return False

    def analytics(self, event_id: str, **filters: Any) -> Dict[str, Any]:
        """Fetch analytics for an event id; structured 'unavailable' result on failure."""
        if event_id not in KNOWN_EVENT_IDS:
            return {
                "available": False,
                "error": f"unknown event-id '{event_id}'; known: {', '.join(KNOWN_EVENT_IDS)}",
            }
        try:
            resp = self.session.get(
                f"{self.base_url}/nnwdaf-analyticsinfo/v1/analytics",
                params={"event-id": event_id, **filters},
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                return {"available": True, "event_id": event_id, "analytics": resp.json()}
            return {
                "available": False,
                "error": f"NWDAF returned HTTP {resp.status_code}",
                "hint": "no NWDAF deployed in the default Open5GS testbed (free5GC ships one)",
            }
        except Exception as exc:
            return {
                "available": False,
                "error": f"NWDAF unreachable: {exc}",
                "hint": "no NWDAF deployed in the default Open5GS testbed (free5GC ships one)",
            }
