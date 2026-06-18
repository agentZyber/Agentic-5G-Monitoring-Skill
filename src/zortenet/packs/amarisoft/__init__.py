"""amarisoft — live 5G RAN+core telemetry from an Amarisoft callbox, as agent tools.

Promotes the validated live tools (proven against a real 2023-12-15 Mini, 5G NR SA) into a
first-class pack. Wraps :class:`~zortenet.connectors.amarisoft.AmarisoftClient` (remote WS API,
Origin-header handshake + ready-frame consume). Clients are context-injected by the app from
``AMARISOFT_WS_URL`` (gNB, :9001) and ``AMARISOFT_CORE_WS_URL`` (core, :9000); every tool degrades
gracefully (a structured "unavailable" string) when the box isn't configured/reachable.

Opt-in (not in DEFAULT_PACKS): enable with ``ZORTENET_PACKS=...,amarisoft`` + the env URLs.
Read-only today; control/fault-injection flows through the intent approval ledger (Stage 3).
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from zortenet.agent.tools import ToolRegistry
from zortenet.connectors.amarisoft import AmarisoftClient, websocket_transport

PACK: Dict[str, Any] = {
    "name": "amarisoft",
    "description": "Live 5G RAN + core telemetry from an Amarisoft callbox (read-only).",
    "connectors": ["amarisoft"],
    "datasets": [],
    "system_prompt": (
        "You can read live status from an Amarisoft 5G gNB and core via tools. Ground every claim "
        "in the tool results and quote concrete numbers. If a tool reports 'unavailable', tell the "
        "operator the Amarisoft box isn't reachable rather than guessing."
    ),
}

_UNAVAILABLE = "unavailable: Amarisoft {what} not configured/reachable (set {env})"


def _client_from_env(env_var: str) -> Optional[AmarisoftClient]:
    url = os.getenv(env_var)
    return AmarisoftClient(transport=websocket_transport(url)) if url else None


def build_registry(
    amarisoft: Optional[AmarisoftClient] = None,
    amarisoft_core: Optional[AmarisoftClient] = None,
) -> ToolRegistry:
    gnb = amarisoft if amarisoft is not None else _client_from_env("AMARISOFT_WS_URL")
    core = amarisoft_core if amarisoft_core is not None else _client_from_env("AMARISOFT_CORE_WS_URL")
    reg = ToolRegistry()

    @reg.tool(
        name="amari_gnb_status",
        description="Live 5G gNB status: active NR cells, RF ports, and CPU load.",
        tags=("amarisoft", "ran"),
    )
    def amari_gnb_status() -> Any:
        if gnb is None:
            return _UNAVAILABLE.format(what="gNB", env="AMARISOFT_WS_URL")
        result = gnb.stats()
        if not result["ok"]:
            return result
        s = result["response"]
        cells = s.get("cells") or {}
        rf = s.get("rf_ports")
        return {
            "active_cells": list(cells.keys()),
            "num_cells": len(cells),
            "rf_ports": list(rf.keys()) if isinstance(rf, dict) else rf,
            "cpu": s.get("cpu"),
        }

    @reg.tool(
        name="amari_attached_ues",
        description="UEs currently attached to the live gNB (with radio metrics when present).",
        tags=("amarisoft", "ue"),
    )
    def amari_attached_ues() -> Any:
        if gnb is None:
            return _UNAVAILABLE.format(what="gNB", env="AMARISOFT_WS_URL")
        ues = (gnb.ue_list().get("response") or {}).get("ue_list") or []
        return {"attached_ue_count": len(ues), "ues": ues[:20]}

    @reg.tool(
        name="amari_cell_kpis",
        description="Per-cell KPIs (DL/UL rate, PRB usage, UE count) from the live gNB.",
        parameters={
            "type": "object",
            "properties": {"cell_id": {"type": "string", "description": "Cell id, e.g. '1'"}},
            "required": ["cell_id"],
        },
        tags=("amarisoft", "ran", "kpi"),
    )
    def amari_cell_kpis(cell_id: str) -> Any:
        if gnb is None:
            return _UNAVAILABLE.format(what="gNB", env="AMARISOFT_WS_URL")
        cells = (gnb.stats().get("response") or {}).get("cells") or {}
        cell = cells.get(str(cell_id))
        if cell is None:
            return {"error": f"cell '{cell_id}' not active", "active_cells": list(cells.keys())}
        # scalar fields only — keeps the payload bounded and model-friendly
        return {"cell_id": cell_id, **{k: v for k, v in cell.items() if not isinstance(v, (dict, list))}}

    @reg.tool(
        name="amari_core_registration",
        description="Registered-UE count and NG(5G)/S1(LTE) connections from the core.",
        tags=("amarisoft", "core"),
    )
    def amari_core_registration() -> Any:
        if core is None:
            return _UNAVAILABLE.format(what="core", env="AMARISOFT_CORE_WS_URL")
        s = core.stats().get("response") or {}
        return {k: s.get(k) for k in ("emm_registered_ue_count", "ng_connections", "s1_connections", "users")}

    return reg
