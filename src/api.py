import asyncio
import json
import os
import subprocess
from queue import Queue
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect
from sse_starlette.sse import EventSourceResponse
import requests

import netapp_utils

from vector_store import context_vector_store
from streaming import streaming_manager, stream_event_to_agents
from agent_workflow import network_agent
from core_manager import core_manager, initialize_cores

try:
    from langchain_openai import OpenAI, ChatOpenAI

    LANGCHAIN_AVAILABLE = True
except ImportError:
    OpenAI = None
    ChatOpenAI = None
    LANGCHAIN_AVAILABLE = False

try:
    from langchain_core.tools import tool as _tool
except ImportError:
    try:
        from langchain.tools import tool as _tool
    except ImportError:
        _tool = None

if _tool is None:

    def tool(func=None, *args, **kwargs):
        if func is not None and callable(func):
            return func

        def decorator(inner):
            return inner

        return decorator

else:
    tool = _tool

app = FastAPI(
    title="ZorteNet 5G NetApp",
    version="2.0.0",
    description="Agentic 5G Network Application with Context Enhancement",
)


def register_function():
    subprocess.run(["sh", "./prepare.sh"], stderr=subprocess.PIPE, text=True)


policy_db: Dict[str, Any] = {}

vapp_db: Dict[str, Any] = {"host_name": "", "port": 0, "token": ""}

q: Queue = Queue(maxsize=1)

callback_url = os.getenv("CALLBACK_ADDRESS", "localhost:5000")
netapp_host = os.getenv("NETAPP_HOSTNAME", "zortenetapp")

capif_host = os.getenv("CAPIF_HOSTNAME", "capifcore")
capif_port_http = os.getenv("CAPIF_PORT_HTTP", "8080")
capif_port_https = os.getenv("CAPIF_PORT_HTTPS", "443")
capif_certs_path = os.getenv("PATH_TO_CERTS", "./capif_onboarding")

nef_address = os.getenv("NEF_ADDRESS", "localhost:8080")
nef_user = os.getenv("NEF_USER", "")
nef_pass = os.getenv("NEF_PASSWORD", "")


def _normalize_base_url(address: str, default: str) -> str:
    value = address or default
    if value.startswith(("http://", "https://")):
        return value
    return f"http://{value}"


nef_url = _normalize_base_url(nef_address, "http://localhost:8080")
_nef_token: Optional[str] = None
_cores_initialized = False


def _require_fields(data: Dict[str, Any], fields: List[str]):
    missing = [field_name for field_name in fields if field_name not in data]
    if missing:
        raise HTTPException(
            status_code=422, detail=f"Missing required fields: {', '.join(missing)}"
        )


def _callback_destination() -> str:
    if callback_url.startswith(("http://", "https://")):
        return f"{callback_url.rstrip('/')}/netAppCallback"
    return f"http://{callback_url}/netAppCallback"


def get_nef_token(force_refresh: bool = False) -> str:
    global _nef_token

    if _nef_token and not force_refresh:
        return _nef_token

    fallback_token = os.getenv("NEF_BEARER_TOKEN", "")
    if not nef_user or not nef_pass:
        _nef_token = fallback_token
        return _nef_token

    try:
        _nef_token = netapp_utils.get_token(nef_user, nef_pass, nef_url)
    except Exception:
        _nef_token = fallback_token

    return _nef_token


def ensure_core_manager_initialized(force_reload: bool = False):
    global _cores_initialized

    if force_reload or not _cores_initialized:
        initialize_cores(force_reload=force_reload)
        _cores_initialized = True


ensure_core_manager_initialized()


class ContextStore:
    def __init__(self):
        self.history: List[Dict[str, Any]] = []
        self.max_history = 1000

    def add_event(self, event: Dict[str, Any]):
        external_id = event.get("externalId")
        location_info = event.get("locationInfo", {})
        cell_id = location_info.get("cellId") if isinstance(location_info, dict) else None

        if external_id in policy_db and cell_id:
            allowed_cells = policy_db[external_id].get("cells", [])
            if cell_id not in allowed_cells:
                event["type"] = "alert"

        event["timestamp"] = datetime.utcnow().isoformat()
        self.history.append(event)
        if len(self.history) > self.max_history:
            self.history.pop(0)

    def get_recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        return self.history[-limit:]

    def get_context_summary(self) -> Dict[str, Any]:
        if not self.history:
            return {"status": "no_context", "events": []}

        return {
            "status": "available",
            "event_count": len(self.history),
            "latest_event": self.history[-1] if self.history else None,
            "recent_events": self.history[-5:],
            "active_policies": len(policy_db),
            "subscribed_ues": list(
                set(e.get("externalId") for e in self.history if e.get("externalId"))
            ),
        }


context_store = ContextStore()


@tool
def get_network_context() -> str:
    """Get current network context including active policies, subscribed UEs, and recent events."""
    return json.dumps(context_store.get_context_summary(), indent=2)


@tool
def check_ue_location_breach(external_id: str, cell_id: str) -> str:
    """Check if a UE has breached its policy by being in an unauthorized cell."""
    if external_id not in policy_db:
        return json.dumps({"breach": False, "reason": "no_policy_found"})

    policy = policy_db[external_id]
    allowed_cells = policy.get("cells", [])
    breach = cell_id not in allowed_cells

    return json.dumps(
        {
            "breach": breach,
            "external_id": external_id,
            "cell_id": cell_id,
            "allowed_cells": allowed_cells,
        },
        indent=2,
    )


@tool
def get_ue_history(external_id: str, limit: int = 10) -> str:
    """Get location history for a specific UE."""
    events = [e for e in context_store.history if e.get("externalId") == external_id]
    return json.dumps(
        {
            "external_id": external_id,
            "event_count": len(events),
            "events": events[-limit:],
        },
        indent=2,
    )


AGENT_TOOLS = [get_network_context, check_ue_location_breach, get_ue_history]

AGENT_FUNCTION_SCHEMAS = [
    {
        "name": "get_network_context",
        "description": "Get current network context including active policies, subscribed UEs, and recent events.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "check_ue_location_breach",
        "description": "Check if a UE has breached its policy by being in an unauthorized cell.",
        "parameters": {
            "type": "object",
            "properties": {
                "external_id": {
                    "type": "string",
                    "description": "The external ID of the UE",
                },
                "cell_id": {"type": "string", "description": "The cell ID to check"},
            },
            "required": ["external_id", "cell_id"],
        },
    },
    {
        "name": "get_ue_history",
        "description": "Get location history for a specific UE.",
        "parameters": {
            "type": "object",
            "properties": {
                "external_id": {
                    "type": "string",
                    "description": "The external ID of the UE",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of events to return",
                    "default": 10,
                },
            },
            "required": ["external_id"],
        },
    },
]


@app.get("/")
def index():
    return {
        "message": "ZorteNet 5G NetApp - Agentic Context Provider",
        "version": "2.0.0",
    }


@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.post("/vapp_connect")
def vapp_connect(data: dict):
    _require_fields(data, ["vapp_ip", "port"])
    vapp_ip = data["vapp_ip"]
    port = data["port"]
    nef_token = get_nef_token()

    vapp_db["host_name"] = vapp_ip
    vapp_db["port"] = port
    vapp_db["token"] = nef_token

    return {"token": vapp_db["token"]}


@app.post("/subscription_capif")
def subscription_capif(data: dict):
    _require_fields(data, ["id", "num_of_reports", "exp_time"])
    return _create_subscription_with_core_manager(
        external_id=data["id"],
        num_of_reports=data["num_of_reports"],
        exp_time=data["exp_time"],
        netapp_id="zorte_netapp",
    )


@app.post("/subscription")
def subscription(data: dict):
    _require_fields(data, ["id", "num_of_reports", "exp_time"])
    return _create_subscription_with_core_manager(
        external_id=data["id"],
        num_of_reports=data["num_of_reports"],
        exp_time=data["exp_time"],
        netapp_id=netapp_host,
    )


@app.post("/setPolicy")
def set_policy(data: dict):
    _require_fields(data, ["pol-id", "id", "cells"])
    pid = data["pol-id"]
    exid = data["id"]
    cells = data["cells"]
    policy_db[exid] = {"policy_id": pid, "cells": cells}
    return {"status": "Policy set", "policy": policy_db[exid]}


@app.get("/get_subscriptions")
def get_subscriptions():
    ensure_core_manager_initialized()
    return {
        "status": "OK",
        "subscriptions": core_manager.get_all_subscriptions(netapp_host),
    }


@app.get("/cores/status")
def get_core_status():
    ensure_core_manager_initialized()
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "callback_destination": _callback_destination(),
        **core_manager.get_status(),
    }


@app.get("/VappConsume")
def vapp_consume():
    log_record = {"nothing": "nothing"}
    if not q.empty():
        log_record = q.get()
    return log_record


def _classify_callback_event(data: Dict[str, Any]) -> str:
    ex_id = data.get("externalId")
    if ex_id in policy_db:
        location_info = data.get("locationInfo", {})
        cell_id = location_info.get("cellId") if isinstance(location_info, dict) else None
        if cell_id not in policy_db[ex_id]["cells"]:
            return "alert"
    return "log"


def _forward_to_vapp(data: Dict[str, Any]):
    payload = {"data": data}
    headers = {"Content-type": "application/json"}

    if not vapp_db["host_name"] or not vapp_db["port"]:
        return

    try:
        requests.post(
            f"http://{vapp_db['host_name']}:{vapp_db['port']}/vapp_callback",
            headers=headers,
            json=payload,
            timeout=5,
        )
    except Exception:
        pass


def _store_latest_callback(data: Dict[str, Any]):
    if q.empty():
        q.put(data)
    else:
        q.get()
        q.put(data)


def _serialize_subscription_response(subscription) -> Optional[Dict[str, Any]]:
    if subscription is None:
        return None

    if hasattr(subscription, "raw_response") and subscription.raw_response:
        payload = dict(subscription.raw_response)
    elif all(
        hasattr(subscription, field_name)
        for field_name in ["subscription_id", "external_id", "netapp_id", "status"]
    ):
        payload = {
            "subscription_id": subscription.subscription_id,
            "external_id": subscription.external_id,
            "netapp_id": subscription.netapp_id,
            "status": subscription.status,
        }
    elif hasattr(subscription, "to_dict"):
        payload = subscription.to_dict()
    elif isinstance(subscription, dict):
        payload = dict(subscription)
    else:
        payload = {"value": subscription}

    core_name = getattr(subscription, "core_name", None)
    if core_name:
        payload["core"] = core_name
    return payload


def _create_subscription_with_core_manager(
    external_id: str, num_of_reports: int, exp_time: str, netapp_id: str
) -> Dict[str, Any]:
    ensure_core_manager_initialized()
    response = core_manager.create_subscription(
        external_id=external_id,
        callback_url=_callback_destination(),
        num_of_reports=num_of_reports,
        exp_time=exp_time,
        netapp_id=netapp_id,
    )

    if response is None:
        return {"status": "failed", "subscription": None}

    status = "OK" if response.status == "active" else response.status
    return {
        "status": status,
        "subscription": _serialize_subscription_response(response),
    }


def _parse_callback_event(
    data: Dict[str, Any], source_core: Optional[str] = None
) -> Dict[str, Any]:
    ensure_core_manager_initialized()

    try:
        event = core_manager.process_callback(
            data=data, source_core=source_core, store_event=False
        )
        normalized_event = dict(data)
        normalized_event.update(event.to_dict())
    except Exception:
        normalized_event = dict(data)
        if source_core:
            normalized_event["source_core"] = source_core

    return normalized_event


async def _process_callback_payload(
    data: Dict[str, Any], source_core: Optional[str] = None
) -> Dict[str, Any]:
    normalized_event = _parse_callback_event(data, source_core=source_core)
    normalized_event["type"] = _classify_callback_event(normalized_event)

    ex_id = normalized_event.get("externalId")
    if ex_id in policy_db:
        normalized_event["policy"] = policy_db[ex_id]

    context_store.add_event(normalized_event)
    context_vector_store.add_event(dict(normalized_event))

    await stream_event_to_agents(normalized_event)

    if network_agent.is_available() and network_agent._initialized:
        asyncio.create_task(network_agent.process_event(dict(normalized_event)))

    _forward_to_vapp(normalized_event)
    _store_latest_callback(normalized_event)

    return normalized_event


@app.post("/netAppCallback")
async def net_app_callback(request: Request):
    try:
        data = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="Invalid JSON payload") from exc

    if not isinstance(data, dict):
        raise HTTPException(status_code=422, detail="JSON payload must be an object.")

    source_core = request.query_params.get("source_core") or request.headers.get(
        "X-Source-Core"
    )
    print(data)
    return await _process_callback_payload(data, source_core=source_core)


@app.get("/agent/context")
def get_agent_context(
    external_id: Optional[str] = None, limit: int = 10, include_raw: bool = False
):
    if external_id:
        events = [
            e for e in context_store.history if e.get("externalId") == external_id
        ]
        filtered_history = events[-limit:]
    else:
        filtered_history = context_store.get_recent(limit)

    response = {
        "context_id": f"context_{datetime.utcnow().timestamp()}",
        "generated_at": datetime.utcnow().isoformat(),
        "source": "5g_core_location",
        "netapp_id": netapp_host,
        "summary": {
            "total_events": len(context_store.history),
            "active_policies": len(policy_db),
            "subscribed_ues": list(
                set(
                    e.get("externalId")
                    for e in context_store.history
                    if e.get("externalId")
                )
            ),
            "recent_alerts": len(
                [e for e in context_store.history if e.get("type") == "alert"]
            ),
        },
        "policies": policy_db,
        "events": filtered_history,
    }

    if include_raw:
        response["raw_history"] = context_store.history

    return response


@app.get("/agent/tools")
def get_agent_tools():
    return {
        "tools": AGENT_FUNCTION_SCHEMAS,
        "tool_count": len(AGENT_TOOLS),
        "langchain_available": LANGCHAIN_AVAILABLE,
    }


@app.post("/agent/reason")
def agent_reason(query: str, model: Optional[str] = "gpt-4"):
    if not LANGCHAIN_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="LangChain not available. Install langchain-openai package.",
        )

    llm = OpenAI(model=model)

    prompt = f"""You are a 5G network reasoning agent. Based on the following context:
    
    Context: {json.dumps(context_store.get_context_summary(), indent=2)}
    
    User Query: {query}
    
    Provide a concise, actionable response."""

    response = llm.invoke(prompt)

    return {"query": query, "model": model, "response": response, "context_used": True}


@app.get("/agent/functions/schema")
def get_openai_schema():
    return {
        "schema_version": "1.0",
        "functions": AGENT_FUNCTION_SCHEMAS,
        "format": "openai_function_call",
    }


@app.get("/agent/functions/schema/anthropic")
def get_anthropic_schema():
    anthropic_tools = []
    for func in AGENT_FUNCTION_SCHEMAS:
        anthropic_tools.append(
            {
                "name": func["name"],
                "description": func["description"],
                "input_schema": func["parameters"],
            }
        )
    return {
        "schema_version": "1.0",
        "tools": anthropic_tools,
        "format": "anthropic_tool_use",
    }


@app.get("/agent/rag/search")
def rag_search(
    query: str,
    n_results: int = 5,
    external_id: Optional[str] = None,
    mode: Optional[str] = "auto",
):
    if mode == "vector" and not context_vector_store.rag_available:
        raise HTTPException(
            status_code=503,
            detail="Vector store not available. Install chromadb and sentence-transformers.",
        )

    results = context_vector_store.search_similar(
        query=query, n_results=n_results, external_id=external_id
    )

    return {"query": query, "timestamp": datetime.utcnow().isoformat(), **results}


@app.get("/agent/rag/ue/{external_id}/mobility")
def get_ue_mobility(external_id: str):
    pattern = context_vector_store.get_ue_mobility_pattern(external_id)
    return {
        "external_id": external_id,
        "generated_at": datetime.utcnow().isoformat(),
        "pattern_analysis": pattern,
    }


@app.get("/agent/rag/summary")
def get_rag_summary():
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "context_summary": context_vector_store.get_context_summary(),
        "vector_available": context_vector_store.rag_available,
        "features": {
            "semantic_search": context_vector_store.rag_available,
            "mobility_patterns": True,
            "event_history": True,
            "alert_tracking": True,
        },
    }


@app.post("/agent/rag/reason")
def agent_rag_reason(
    query: str,
    model: Optional[str] = "gpt-4",
    use_rag: bool = True,
    n_context_results: int = 5,
):
    if not LANGCHAIN_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="LangChain not available. Install langchain-openai package.",
        )

    context_results = context_vector_store.search_similar(
        query, n_results=n_context_results
    )

    context_text = ""
    if context_results.get("results"):
        for r in context_results["results"]:
            if context_results["mode"] == "vector":
                context_text += r.get("content", "") + "\n\n"
            else:
                context_text += json.dumps(r.get("event", {})) + "\n\n"

    system_prompt = """You are a 5G network reasoning agent with access to real-time network context.
Answer user queries based on the provided context. If the context is insufficient, note what additional information would be needed.
Be concise and actionable in your responses."""

    user_prompt = f"""Context:
{context_text if context_text else "No relevant context found."}

Query: {query}

Provide a concise, actionable response based on the context above."""

    chat = ChatOpenAI(model=model, temperature=0)
    response = chat.invoke(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    )

    return {
        "query": query,
        "model": model,
        "response": response.content,
        "rag_used": use_rag,
        "context_mode": context_results.get("mode", "none"),
        "context_results_count": len(context_results.get("results", [])),
    }


@app.delete("/agent/rag/cleanup")
def rag_cleanup(days: int = 7):
    deleted = context_vector_store.vector_store.delete_old_events(days)
    return {
        "deleted_events": deleted,
        "retention_days": days,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/agent/rag/stats")
def rag_stats():
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "vector_store": context_vector_store.vector_store.get_stats(),
        "context_summary": context_vector_store.get_context_summary(),
    }


@app.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket):
    await websocket.accept()
    streaming_manager.add_ws_connection(websocket)

    await websocket.send_json(
        {
            "type": "connected",
            "message": "WebSocket connected to 5G NetApp stream",
            "timestamp": datetime.utcnow().isoformat(),
        }
    )

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("action") == "ping":
                    await websocket.send_json(
                        {"type": "pong", "timestamp": datetime.utcnow().isoformat()}
                    )
                elif msg.get("action") == "subscribe":
                    event_types = msg.get("event_types", [])
                    await websocket.send_json(
                        {
                            "type": "subscribed",
                            "event_types": event_types,
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
    except WebSocketDisconnect:
        streaming_manager.remove_ws_connection(websocket)


@app.get("/sse/stream")
async def sse_stream(request: Request):
    class SSEConnection:
        def __init__(self):
            self.connected = True

        async def send(self, event: str, data: str):
            if not self.connected:
                raise Exception("Disconnected")
            return {"event": event, "data": data}

    sse_conn = SSEConnection()
    streaming_manager.add_sse_connection(sse_conn)

    async def event_generator():
        yield {
            "event": "connected",
            "data": json.dumps(
                {
                    "message": "SSE connected to 5G NetApp stream",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            ),
        }

        queue = asyncio.Queue()

        async def subscriber(event):
            await queue.put(event)

        streaming_manager.event_bus.subscribe(subscriber)

        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    formatted = {
                        "timestamp": event.get(
                            "timestamp", datetime.utcnow().isoformat()
                        ),
                        "external_id": event.get("externalId"),
                        "type": event.get("type"),
                        "cell_id": event.get("locationInfo", {}).get("cellId")
                        if isinstance(event.get("locationInfo"), dict)
                        else None,
                    }
                    yield {
                        "event": formatted.get("type", "event"),
                        "data": json.dumps(formatted),
                    }
                except asyncio.TimeoutError:
                    yield {
                        "event": "heartbeat",
                        "data": json.dumps(
                            {"timestamp": datetime.utcnow().isoformat()}
                        ),
                    }
        finally:
            streaming_manager.event_bus.unsubscribe(subscriber)
            streaming_manager.remove_sse_connection(sse_conn)

    return EventSourceResponse(event_generator())


@app.get("/stream/status")
def stream_status():
    return {
        "websocket_connections": len(streaming_manager._ws_connections),
        "sse_connections": len(streaming_manager._sse_connections),
        "total_connections": streaming_manager.connection_count,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/agent/graph/status")
def agent_graph_status():
    return {
        "langgraph_available": network_agent.is_available(),
        "initialized": network_agent._initialized
        if network_agent.is_available()
        else False,
        "features": {
            "event_processing": True,
            "reasoning": True,
            "alert_detection": True,
        },
    }


@app.post("/agent/graph/initialize")
def initialize_agent(model: str = "gpt-4"):
    if not network_agent.is_available():
        raise HTTPException(
            status_code=503,
            detail="LangGraph not available. Install langgraph and langchain-openai packages.",
        )

    try:
        success = network_agent.initialize(model)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Agent initialization failed: {exc}",
        ) from exc
    if success:
        return {"status": "initialized", "model": model}
    return {"status": "failed"}


@app.post("/agent/graph/query")
async def agent_graph_query(question: str):
    if not network_agent.is_available():
        raise HTTPException(
            status_code=503,
            detail="Agent not available. Initialize first with POST /agent/graph/initialize",
        )

    result = await network_agent.query(question)
    return result


@app.get("/agent/graph/process/{external_id}")
async def agent_process_ue(external_id: str):
    if not network_agent.is_available():
        raise HTTPException(status_code=503, detail="Agent not available.")

    events = [
        e
        for e in context_vector_store.in_memory_store
        if e.get("externalId") == external_id
    ]
    if not events:
        raise HTTPException(
            status_code=404, detail=f"No events found for UE {external_id}"
        )

    result = await network_agent.process_event(events[-1])
    return result


@app.get("/agent/graph/events/{external_id}/analysis")
async def agent_analyze_ue_events(external_id: str):
    events = [
        e
        for e in context_vector_store.in_memory_store
        if e.get("externalId") == external_id
    ]

    if not events:
        return {"external_id": external_id, "analysis": "no_events", "event_count": 0}

    cell_visits = {}
    for event in events:
        cell_id = (
            event.get("locationInfo", {}).get("cellId")
            if isinstance(event.get("locationInfo"), dict)
            else None
        )
        if cell_id:
            cell_visits[cell_id] = cell_visits.get(cell_id, 0) + 1

    alerts = [e for e in events if e.get("type") == "alert"]

    return {
        "external_id": external_id,
        "event_count": len(events),
        "unique_cells": len(cell_visits),
        "cell_distribution": cell_visits,
        "alert_count": len(alerts),
        "mobility_stability": "stable" if len(cell_visits) <= 3 else "mobile",
        "risk_level": "high"
        if len(alerts) > 3
        else "medium"
        if len(alerts) > 0
        else "low",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5000)
