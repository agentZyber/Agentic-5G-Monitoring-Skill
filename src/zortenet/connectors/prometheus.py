"""Minimal Prometheus HTTP API client (instant + range queries).

Targets the Prometheus in the local testbed overlay (scraping Open5GS NF metrics and, later,
the toolkit itself). Read-only; results are simplified to plain dicts the agent can consume.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests

DEFAULT_BASE_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")


class PrometheusClient:
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
            resp = self.session.get(f"{self.base_url}/-/ready", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def _query(self, endpoint: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        resp = self.session.get(
            f"{self.base_url}/api/v1/{endpoint}", params=params, timeout=self.timeout
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "success":
            raise RuntimeError(f"Prometheus query failed: {data.get('error', data)}")
        return data.get("data", {}).get("result", [])

    def instant_query(self, query: str) -> List[Dict[str, Any]]:
        """Run a PromQL instant query; returns the raw result list (metric + value)."""
        return self._query("query", {"query": query})

    def range_query(
        self, query: str, start: str, end: str, step: str = "30s"
    ) -> List[Dict[str, Any]]:
        """Run a PromQL range query; returns the raw result list (metric + values)."""
        return self._query(
            "query_range", {"query": query, "start": start, "end": end, "step": step}
        )

    def targets_health(self) -> List[Dict[str, Any]]:
        """Summarize scrape targets: job, instance, up/down — the agent's quick health view."""
        resp = self.session.get(f"{self.base_url}/api/v1/targets", timeout=self.timeout)
        resp.raise_for_status()
        active = resp.json().get("data", {}).get("activeTargets", [])
        return [
            {
                "job": t.get("labels", {}).get("job"),
                "instance": t.get("labels", {}).get("instance"),
                "health": t.get("health"),
                "last_error": t.get("lastError") or None,
            }
            for t in active
        ]
