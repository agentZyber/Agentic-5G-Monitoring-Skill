"""Amarisoft callbox connector — telemetry **and control** over the remote API (mock-first).

Amarisoft's remote API is WebSocket-JSON: each request is one JSON object with a ``message``
field (``stats``, ``config_get``, ``config_set``, ``ue_get``, …) sent to the component's port
(gNB/eNB, MME/AMF, IMS each listen separately). This client wraps that behind an injectable
``transport`` callable so it is fully testable without hardware, and so live deployments can
swap in a websocket transport (lazy-imported ``websockets``; an optional extra, not a base dep).

**Validation status:** message names and call shapes follow the Amarisoft Remote API
documentation; the exact field schemas vary by release and are **validated against the real
callbox at Tier-3 bring-up** (IMPLEMENTATION_PLAN Stage 3). Until then: mock-tested only.
Control operations are expected to be driven through the intent approval flow
(``intent-to-network``), not called freely.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, Optional

# transport(request_dict) -> response_dict
Transport = Callable[[Dict[str, Any]], Dict[str, Any]]

DEFAULT_WS_URL = os.getenv("AMARISOFT_WS_URL", "ws://localhost:9001")


def websocket_transport(url: str = DEFAULT_WS_URL, timeout: float = 10.0) -> Transport:
    """Build a one-shot websocket transport (requires ``pip install websockets``)."""

    def send(request: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from websockets.sync.client import connect  # lazy: optional extra
        except ImportError as exc:
            raise RuntimeError(
                "the Amarisoft websocket transport needs `pip install websockets`"
            ) from exc
        with connect(url, open_timeout=timeout, close_timeout=timeout) as ws:
            ws.send(json.dumps(request))
            return json.loads(ws.recv(timeout=timeout))

    return send


class AmarisoftClient:
    def __init__(
        self,
        transport: Optional[Transport] = None,
        url: str = DEFAULT_WS_URL,
    ) -> None:
        self.url = url
        self.transport = transport or websocket_transport(url)

    def _call(self, message: str, **fields: Any) -> Dict[str, Any]:
        request = {"message": message, **fields}
        try:
            response = self.transport(request)
        except Exception as exc:
            return {"ok": False, "message": message, "error": f"amarisoft unreachable: {exc}"}
        if isinstance(response, dict) and response.get("error"):
            return {"ok": False, "message": message, "error": str(response["error"])}
        return {"ok": True, "message": message, "response": response}

    def is_available(self) -> bool:
        return self._call("config_get")["ok"]

    # ---- telemetry (read) ---------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        """Component statistics (cell load, PRB usage, UE counts — release-dependent fields)."""
        return self._call("stats")

    def ue_list(self) -> Dict[str, Any]:
        """Connected UEs with radio metrics (``ue_get`` in the remote API)."""
        return self._call("ue_get", stats=True)

    def config_get(self) -> Dict[str, Any]:
        return self._call("config_get")

    # ---- control (write — drive through the intent approval flow) -------------

    def config_set(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Apply a configuration change (e.g. rate limits, power). Approval-gated upstream."""
        return self._call("config_set", **params)

    def handover(self, ue_id: int, target_cell: int) -> Dict[str, Any]:
        return self._call("handover", ue_id=ue_id, pcell_id=target_cell)

    # ---- fault injection (lab scenarios; approval-gated upstream) ---------------

    def set_noise_level(self, level_db: float) -> Dict[str, Any]:
        """Channel-simulator noise injection (callbox channel simulator required)."""
        return self._call("config_set", channel_sim={"noise_level": level_db})

    def cell_power(self, cell_id: int, gain_db: float) -> Dict[str, Any]:
        """Adjust a cell's TX gain — the 'coverage degradation' fault primitive."""
        return self._call("config_set", cells={str(cell_id): {"gain": gain_db}})


class AmarisoftExecutor:
    """Intent executor mapping expectation metrics to Amarisoft control calls.

    Same interface as ``SimulatedExecutor`` (plan/apply); selected at live bring-up via the
    app's executor wiring. Plans mirror the simulated routes; ``apply`` performs real
    ``config_set`` calls and reports per-action results.
    """

    name = "amarisoft"

    METRIC_PARAMS = {
        "throughput_dl_mbps": lambda exp: {"rate_limit": {"dl": exp.value, "object": exp.object_instance}},
        "throughput_ul_mbps": lambda exp: {"rate_limit": {"ul": exp.value, "object": exp.object_instance}},
        "energy_kwh": lambda exp: {"power_profile": {"target": exp.value, "object": exp.object_instance}},
    }

    def __init__(self, client: AmarisoftClient) -> None:
        self.client = client

    def plan(self, intent) -> list:
        actions = []
        for exp in intent.expectations:
            builder = self.METRIC_PARAMS.get(exp.metric)
            if builder is None:
                actions.append(
                    {"target": "amarisoft", "op": None, "executable": False,
                     "reason": f"no Amarisoft mapping for metric '{exp.metric}'"}
                )
            else:
                actions.append(
                    {"target": "amarisoft", "op": "config_set", "executable": True,
                     "object": exp.object_instance, "params": builder(exp)}
                )
        return actions

    def apply(self, intent, plan) -> Dict[str, Any]:
        results = []
        for action in plan:
            if not action.get("executable"):
                results.append({**action, "result": "skipped"})
                continue
            outcome = self.client.config_set(action["params"])
            results.append({**action, "result": outcome})
        ok = all(r.get("result", {}).get("ok") for r in results if r.get("executable"))
        return {"simulated": False, "ok": ok, "actions": results}
