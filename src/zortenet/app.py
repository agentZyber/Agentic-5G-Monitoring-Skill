"""ZorteNet toolkit app — one capability core, every protocol face, in one FastAPI process.

Wires together: enabled capability packs (merged ToolRegistry) → the agent runtime (local-first
LLM) → the interop faces (REST ``/agent/ask``, A2A Agent Card + skills, MCP over Streamable HTTP
at ``/mcp``) → trajectory capture (on by default here; opt out with ``ZORTENET_TRAJECTORIES=off``).

This is the *new* toolkit app (light deps: fastapi + mcp + requests). The legacy NetApp in
``src/api.py`` keeps running unchanged; convergence is Stage-2 scope.

Run:  uvicorn zortenet.app:app --port 5001          (module-level default app)
      python -m zortenet.interop.mcp_server          (stdio MCP face for local clients)
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from zortenet import __version__
from zortenet.agent.runtime import DEFAULT_SYSTEM_PROMPT, AgentRuntime
from zortenet.agent.tools import ToolRegistry
from zortenet.agent.trajectory import TrajectoryLogger
from zortenet.connectors.base import catalog as connector_catalog
from zortenet.core.bus import EventBus
from zortenet.core.events import NetworkEvent
from zortenet.intent.ledger import IntentLedger, IntentTransitionError
from zortenet.interop.a2a_server import make_a2a_router
from zortenet.interop.a2a_tasks import A2ATaskManager, make_a2a_jsonrpc_router
from zortenet.interop.acp import make_acp_router
from zortenet.interop.agntcy import oasf_record
from zortenet.interop.agui import make_agui_router
from zortenet.interop.anp import agent_description, did_document
from zortenet.interop.schemas import to_mcp_tools
from zortenet.llm import get_provider
from zortenet.llm.base import LLMProvider
from zortenet.packs import DEFAULT_PACKS, load_packs

_UNSET = object()


class AskRequest(BaseModel):
    message: str
    include_messages: bool = False


class ApprovalRequest(BaseModel):
    approver: str
    reason: str = ""


def _executor_from_env():
    """Select the intent executor: simulated (default) or real Amarisoft via env opt-in."""
    kind = os.getenv("ZORTENET_EXECUTOR", "simulated").lower()
    if kind == "amarisoft":
        from zortenet.connectors.amarisoft import AmarisoftClient, AmarisoftExecutor

        return AmarisoftExecutor(AmarisoftClient())
    from zortenet.packs.intent_to_network import SimulatedExecutor

    return SimulatedExecutor()


def _packs_from_env() -> List[str]:
    raw = os.getenv("ZORTENET_PACKS", ",".join(DEFAULT_PACKS))
    return [p.strip() for p in raw.split(",") if p.strip()]


def _system_prompt(pack_metas: List[Dict[str, Any]]) -> str:
    prompts = [m.get("system_prompt", "").strip() for m in pack_metas]
    prompts = [p for p in prompts if p]
    return "\n\n".join(prompts) if prompts else DEFAULT_SYSTEM_PROMPT


def create_app(
    packs: Optional[List[str]] = None,
    provider: Optional[LLMProvider] = None,
    trajectory: Any = _UNSET,
    enable_mcp: bool = True,
    bus: Optional[EventBus] = None,
) -> FastAPI:
    pack_names = packs if packs is not None else _packs_from_env()
    event_bus = bus or EventBus()
    ledger = IntentLedger()
    executor = _executor_from_env()
    llm = provider or get_provider()

    # The NOC specialists (ran/core/security agents) exist only when the pack is enabled.
    specialists = None
    if "multi-agent-noc" in {p.strip().lower() for p in pack_names}:
        from zortenet.multiagent.noc import build_default_specialists

        specialists = build_default_specialists(llm, store=event_bus.store, ledger=ledger)

    # Packs opt into shared app objects by build_registry parameter name (see load_packs).
    registry, pack_metas = load_packs(
        pack_names,
        context={
            "store": event_bus.store,
            "bus": event_bus,
            "ledger": ledger,
            "executor": executor,
            "specialists": specialists,
        },
    )
    traj: Optional[TrajectoryLogger] = (
        TrajectoryLogger.from_env(default_dir="trajectories") if trajectory is _UNSET else trajectory
    )
    runtime = AgentRuntime(
        provider=llm,
        registry=registry,
        system_prompt=_system_prompt(pack_metas),
        trajectory=traj,
    )

    # --- MCP face (Streamable HTTP) — built before the app so its lifespan can be attached ---
    mcp_asgi = None
    mcp_manager = None
    if enable_mcp:
        try:
            from zortenet.interop.mcp_server import make_streamable_http_app

            mcp_asgi, mcp_manager = make_streamable_http_app(registry)
        except ImportError:  # mcp SDK not installed — REST/A2A faces still work
            mcp_asgi = None

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if mcp_manager is not None:
            async with mcp_manager.run():
                yield
        else:
            yield

    app = FastAPI(
        title="ZorteNet — Agentic 5G/6G Toolkit",
        version=__version__,
        lifespan=lifespan,
    )

    # --- REST face ---------------------------------------------------------

    @app.get("/health")
    def health() -> Dict[str, Any]:
        return {
            "status": "ok",
            "version": __version__,
            "provider": llm.name,
            "model": getattr(llm, "model", None),
            "provider_available": llm.is_available(),
            "packs": [m["name"] for m in pack_metas],
            "tools": len(registry.list()),
            "mcp_http": mcp_asgi is not None,
            "trajectories": str(traj.directory) if traj else None,
            "executor": getattr(executor, "name", "unknown"),
            "intents": len(ledger.list()),
            "specialists": specialists.names() if specialists else [],
            "faces": ["rest", "mcp", "a2a-card", "a2a-tasks", "acp", "agui", "oasf", "anp-experimental"],
        }

    @app.get("/tools")
    def tools() -> List[Dict[str, Any]]:
        return to_mcp_tools(registry)

    @app.get("/connectors")
    def connectors() -> List[Dict[str, Any]]:
        return connector_catalog()

    # --- event ingest/query (the multi-domain bus) -------------------------

    @app.post("/events")
    def ingest_event(event: Dict[str, Any]) -> Dict[str, Any]:
        """Ingest one event: a NetworkEvent dict, or the legacy location-callback shape."""
        if "domain" in event:
            normalized = NetworkEvent.from_dict(event)
        elif "externalId" in event or "locationInfo" in event:
            normalized = NetworkEvent.from_location_event(event, source="ingest")
        else:
            raise HTTPException(
                status_code=422,
                detail="expected a NetworkEvent dict (with 'domain') or a legacy location callback",
            )
        event_bus.publish(normalized)
        return normalized.to_dict()

    @app.get("/events/recent")
    def recent_events(
        domain: Optional[str] = None,
        entity_id: Optional[str] = None,
        min_severity: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        events = event_bus.store.recent(
            domain=domain, entity_id=entity_id, min_severity=min_severity, limit=limit
        )
        return {"count": len(events), "events": [e.to_dict() for e in events]}

    @app.get("/events/stats")
    def event_stats() -> Dict[str, Any]:
        return event_bus.store.stats()

    # --- intent approval (HUMAN-ONLY gate: deliberately not agent tools) -----

    @app.get("/intents")
    def list_intents(status: Optional[str] = None) -> Dict[str, Any]:
        try:
            records = ledger.list(status=status)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"unknown status '{status}'")
        return {"count": len(records), "intents": [r.to_dict() for r in records]}

    @app.get("/intents/{intent_id}")
    def get_intent(intent_id: str) -> Dict[str, Any]:
        try:
            return ledger.get(intent_id).to_dict()
        except KeyError:
            raise HTTPException(status_code=404, detail=f"unknown intent '{intent_id}'")

    @app.post("/intents/{intent_id}/approve")
    def approve_intent(intent_id: str, request: ApprovalRequest) -> Dict[str, Any]:
        try:
            record = ledger.approve(intent_id, approver=request.approver)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"unknown intent '{intent_id}'")
        except IntentTransitionError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        return record.to_dict()

    @app.post("/intents/{intent_id}/reject")
    def reject_intent(intent_id: str, request: ApprovalRequest) -> Dict[str, Any]:
        try:
            record = ledger.reject(intent_id, approver=request.approver, reason=request.reason)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"unknown intent '{intent_id}'")
        except IntentTransitionError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        return record.to_dict()

    @app.post("/agent/ask")
    def agent_ask(request: AskRequest) -> Dict[str, Any]:
        try:
            result = runtime.run(request.message, meta={"packs": [m["name"] for m in pack_metas]})
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=(
                    f"LLM provider '{llm.name}' failed: {exc}. "
                    "Is the model server running (e.g. `ollama serve`)?"
                ),
            ) from exc
        payload: Dict[str, Any] = {
            "answer": result.answer,
            "iterations": result.iterations,
            "tool_calls_made": result.tool_calls_made,
            "tool_errors": result.tool_errors,
            "stopped_early": result.stopped_early,
        }
        if request.include_messages:
            payload["messages"] = result.messages
        return payload

    # --- agent-protocol faces ---------------------------------------------------

    app.include_router(make_a2a_router(registry, version=__version__))   # Agent Card + skills
    a2a_manager = A2ATaskManager(runtime, agent_name="zortenet-5g")
    app.include_router(make_a2a_jsonrpc_router(a2a_manager))             # A2A task lifecycle (JSON-RPC)
    app.include_router(make_acp_router(runtime))                         # ACP shim (AAIF-tracked)
    app.include_router(make_agui_router(runtime))                        # AG-UI SSE

    public_url = os.getenv("ZORTENET_PUBLIC_URL", "http://localhost:5001")

    @app.get("/.well-known/oasf.json")
    def oasf() -> Dict[str, Any]:
        return oasf_record(registry, base_url=public_url)

    @app.get("/.well-known/did.json")
    def did() -> Dict[str, Any]:
        return did_document(base_url=public_url)  # ANP face: EXPERIMENTAL, unsigned

    @app.get("/.well-known/agent-description.json")
    def anp_agent_description() -> Dict[str, Any]:
        return agent_description(registry, base_url=public_url)

    # --- MCP face mount -------------------------------------------------------

    if mcp_asgi is not None:
        app.mount("/mcp", mcp_asgi)

    # expose internals for tests / introspection
    app.state.registry = registry
    app.state.runtime = runtime
    app.state.pack_metas = pack_metas
    app.state.bus = event_bus
    app.state.ledger = ledger
    app.state.executor = executor
    return app


# Default ASGI entrypoint: `uvicorn zortenet.app:app`
app = create_app()
