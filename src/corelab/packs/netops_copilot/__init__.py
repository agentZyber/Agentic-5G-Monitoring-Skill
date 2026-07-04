"""netops-copilot — "talk to your 5G network": NL Q&A and diagnosis over live telemetry.

The flagship Stage-1 pack. Tools read from the Open5GS core and Prometheus; every tool degrades
gracefully (a structured "unavailable" result, never an exception) so the agent can tell the
operator exactly what access is missing instead of crashing.

Clients are injected into :func:`build_registry` for testability; defaults come from the
environment (``OPEN5GS_BASE_URL``, ``PROMETHEUS_URL``) and match the testbed overlay.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from corelab.agent.tools import ToolRegistry
from corelab.connectors.open5gs import Open5GSClient
from corelab.connectors.prometheus import PrometheusClient
from corelab.core.bus import EventStore

PACK: Dict[str, Any] = {
    "name": "netops-copilot",
    "description": "Natural-language Q&A and diagnosis over the live 5G network (core + telemetry).",
    "connectors": ["open5gs", "prometheus"],
    "datasets": ["tele-data", "tspec-llm"],  # RAG grounding (ingest lands in Stage 2)
    "system_prompt": (
        "You are NetOps Copilot, a 5G network-operations agent. Answer operator questions about "
        "the live network using the provided tools. Ground every claim in tool results; quote "
        "concrete numbers. If a backend is unavailable, report which one and what it would "
        "provide. Prefer checking overall health before drilling into specifics."
    ),
}

_UNAVAILABLE = "unavailable: {what} is not reachable ({hint})"


def build_registry(
    open5gs: Optional[Open5GSClient] = None,
    prometheus: Optional[PrometheusClient] = None,
    store: Optional["EventStore"] = None,
) -> ToolRegistry:
    core = open5gs or Open5GSClient()
    prom = prometheus or PrometheusClient()
    reg = ToolRegistry()

    @reg.tool(
        name="get_recent_events",
        description=(
            "Query the multi-domain event store: recent network events, filterable by domain "
            "(location/qos/throughput/slice/energy/security/ran_kpi/signaling), entity id, and "
            "minimum severity. The cross-domain memory of the network."
        ),
        parameters={
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Optional domain filter"},
                "entity_id": {"type": "string", "description": "Optional entity filter"},
                "min_severity": {"type": "string", "description": "info|warning|alert|critical"},
                "limit": {"type": "integer", "description": "Max events (default 20)"},
            },
        },
        tags=("observability", "events"),
    )
    def get_recent_events(
        domain: Optional[str] = None,
        entity_id: Optional[str] = None,
        min_severity: Optional[str] = None,
        limit: int = 20,
    ) -> Any:
        if store is None:
            return "unavailable: no event store wired (run inside the toolkit app)"
        events = store.recent(
            domain=domain, entity_id=entity_id, min_severity=min_severity, limit=limit
        )
        return {
            "count": len(events),
            "stats": store.stats(),
            "events": [e.text_repr() for e in events],
        }

    @reg.tool(
        name="network_health_overview",
        description=(
            "Quick health snapshot: which telemetry/core backends are reachable and the "
            "up/down state of all Prometheus scrape targets. Start here."
        ),
        tags=("observability", "health"),
    )
    def network_health_overview() -> Dict[str, Any]:
        prom_up = prom.is_available()
        overview: Dict[str, Any] = {
            "prometheus_reachable": prom_up,
            "open5gs_reachable": core.is_available(),
        }
        if prom_up:
            try:
                overview["scrape_targets"] = prom.targets_health()
            except Exception as exc:
                overview["scrape_targets_error"] = str(exc)
        return overview

    @reg.tool(
        name="query_kpi",
        description=(
            "Run a PromQL instant query against network telemetry (e.g. "
            "'fivegs_amffunction_rm_registeredsubnbr' for registered UEs on the Open5GS AMF). "
            "Returns metric labels and current values."
        ),
        parameters={
            "type": "object",
            "properties": {
                "promql": {"type": "string", "description": "The PromQL expression to evaluate"}
            },
            "required": ["promql"],
        },
        tags=("telemetry", "kpi"),
    )
    def query_kpi(promql: str) -> Any:
        if not prom.is_available():
            return _UNAVAILABLE.format(what="Prometheus", hint=prom.base_url)
        try:
            result = prom.instant_query(promql)
        except Exception as exc:
            return f"query failed: {exc}"
        return {"query": promql, "result_count": len(result), "results": result[:20]}

    @reg.tool(
        name="list_core_subscriptions",
        description="List active monitoring subscriptions on the 5G core (Open5GS).",
        tags=("core", "subscriptions"),
    )
    def list_core_subscriptions() -> Any:
        if not core.is_available():
            return _UNAVAILABLE.format(what="the Open5GS core API", hint=core.base_url)
        subs = core.list_subscriptions()
        return {"count": len(subs), "subscriptions": subs[:50]}

    @reg.tool(
        name="get_ue_status",
        description=(
            "Fetch current info and location for a UE by external id (e.g. 'ue1@testbed'). "
            "Combines the core's UE-info and UE-location views."
        ),
        parameters={
            "type": "object",
            "properties": {
                "external_id": {"type": "string", "description": "UE external identifier"}
            },
            "required": ["external_id"],
        },
        tags=("core", "ue"),
    )
    def get_ue_status(external_id: str) -> Any:
        if not core.is_available():
            return _UNAVAILABLE.format(what="the Open5GS core API", hint=core.base_url)
        info = core.get_ue_info(external_id)
        location = core.get_ue_location(external_id)
        if info is None and location is None:
            return f"no data for UE '{external_id}' (unknown id, or the core exposes no data for it)"
        return {"external_id": external_id, "info": info, "location": location}

    return reg
