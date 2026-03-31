import time
import os
import subprocess
import json
import asyncio
from queue import Queue
from threading import Thread
from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from sse_starlette.sse import EventSourceResponse
import requests

import netapp_utils
import redis

from evolved5g.sdk import LocationSubscriber, CAPIFInvokerConnector
from evolved5g.swagger_client.rest import ApiException
from evolved5g.swagger_client import LoginApi, User, Configuration, ApiClient
from evolved5g.swagger_client.models import Token

from vector_store import context_vector_store
from streaming import streaming_manager, stream_event_to_agents, EventType
from agent_workflow import network_agent

try:
    from langchain_openai import OpenAI, ChatOpenAI
    from langchain.prompts import PromptTemplate
    from langchain.tools import tool
    from langchain.chains import RetrievalQA

    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False

app = FastAPI(
    title="ZorteNet 5G NetApp",
    version="2.0.0",
    description="Agentic 5G Network Application with Context Enhancement",
)


def register_function():
    subprocess.run(["sh", "./prepare.sh"], stderr=subprocess.PIPE, text=True)


policy_db: Dict[str, Any] = {}

vapp_db: Dict[str, Any] = {"host_name": "", "port": 0, "token": 0}

q: Queue = Queue(maxsize=1)


callback_url = os.environ["CALLBACK_ADDRESS"]
netapp_host = "zortenetapp"

capif_host = os.environ["CAPIF_HOSTNAME"]
capif_port_http = os.environ["CAPIF_PORT_HTTP"]
capif_port_https = os.environ["CAPIF_PORT_HTTPS"]
capif_certs_path = os.environ["PATH_TO_CERTS"]

nef_address = os.environ["NEF_ADDRESS"]
nef_user = os.environ["NEF_USER"]
nef_pass = os.environ["NEF_PASSWORD"]

nef_url = f"http://{nef_address}"

token = netapp_utils.get_token(nef_user, nef_pass, nef_url)


class ContextStore:
    def __init__(self):
        self.history: List[Dict[str, Any]] = []
        self.max_history = 1000

    def add_event(self, event: Dict[str, Any]):
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
    vapp_ip = data["vapp_ip"]
    port = data["port"]

    vapp_db["host_name"] = vapp_ip
    vapp_db["port"] = port
    vapp_db["token"] = token

    return {"token": vapp_db["token"]}


@app.post("/subscription_capif")
def subscription_capif(data: dict):
    _id = data["id"]
    num_of_reports = data["num_of_reports"]
    exp_time = data["exp_time"]

    location_subscriber = LocationSubscriber(
        nef_url=nef_url,
        nef_bearer_access_token=token,
        folder_path_for_certificates_and_capif_api_key=capif_certs_path,
        capif_host=capif_host,
        capif_https_port=capif_port_https,
    )

    subscription = ""
    resp = "OK"

    subscription = location_subscriber.create_subscription(
        netapp_id="zorte_netapp",
        external_id=_id,
        notification_destination=f"http://{callback_url}/netAppCallback",
        maximum_number_of_reports=num_of_reports,
        monitor_expire_time=exp_time,
    )

    monitoring_response = subscription.to_dict()
    print(monitoring_response)

    return {"status": resp, "subscription": monitoring_response}


@app.post("/subscription")
def subscription(data: dict):
    _id = data["id"]
    num_of_reports = data["num_of_reports"]
    exp_time = data["exp_time"]

    token = vapp_db["token"]

    location_subscriber = LocationSubscriber(nef_url, token)

    subscription = ""
    resp = "OK"
    try:
        subscription = location_subscriber.create_subscription(
            netapp_id=netapp_host,
            external_id=_id,
            notification_destination=f"http://{callback_url}/netAppCallback",
            maximum_number_of_reports=num_of_reports,
            monitor_expire_time=exp_time,
        )
    except evolved5g.swagger_client.rest.ApiException as e:
        resp = "ApiException"

    return {"status": resp}


@app.post("/setPolicy")
def set_policy(data: dict):
    pid = data["pol-id"]
    exid = data["id"]
    cells = data["cells"]
    policy_db[exid] = {"policy_id": pid, "cells": cells}
    return {"status": "Policy set", "policy": policy_db[exid]}


@app.get("/get_subscriptions")
def get_subscriptions():
    resp = "OK"
    location_subscriber = LocationSubscriber(nef_url, token)
    try:
        all_subscriptions = location_subscriber.get_all_subscriptions(
            netapp_host, 0, 100
        )
        print(all_subscriptions)
    except ApiException as ex:
        resp = "ApiException"

    return {"status": resp}


@app.get("/VappConsume")
def vapp_consume():
    log_record = {"nothing": "nothing"}
    if not q.empty():
        log_record = q.get()
    return log_record


@app.post("/netAppCallback")
async def net_app_callback(request: Request):
    data = await request.json()

    event = {"policy": dict(policy_db), "raw_data": data}

    print(data)

    ex_id = data.get("externalId")
    if ex_id in policy_db:
        if data.get("locationInfo", {}).get("cellId") not in policy_db[ex_id]["cells"]:
            data["type"] = "alert"
        else:
            data["type"] = "log"
    else:
        data["type"] = "log"

    context_store.add_event(data)
    context_vector_store.add_event(data)

    payload = {"data": data}
    headers = {"Content-type": "application/json"}

    try:
        requests.post(
            f"http://{vapp_db['host_name']}:{vapp_db['port']}/vapp_callback",
            headers=headers,
            json=payload,
        )
    except Exception:
        pass

    if q.empty():
        q.put(data)
    else:
        q.get()
        q.put(data)

    return data


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
        "source": "5g_nef_location",
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


@app.post("/netAppCallback")
async def net_app_callback(request: Request):
    data = await request.json()

    event = {"policy": dict(policy_db), "raw_data": data}

    print(data)

    ex_id = data.get("externalId")
    if ex_id in policy_db:
        if data.get("locationInfo", {}).get("cellId") not in policy_db[ex_id]["cells"]:
            data["type"] = "alert"
        else:
            data["type"] = "log"
    else:
        data["type"] = "log"

    context_store.add_event(data)
    context_vector_store.add_event(data)

    asyncio.create_task(stream_event_to_agents(data))

    if network_agent.is_available() and network_agent._initialized:
        asyncio.create_task(network_agent.process_event(data))

    payload = {"data": data}
    headers = {"Content-type": "application/json"}

    try:
        requests.post(
            f"http://{vapp_db['host_name']}:{vapp_db['port']}/vapp_callback",
            headers=headers,
            json=payload,
        )
    except Exception:
        pass

    if q.empty():
        q.put(data)
    else:
        q.get()
        q.put(data)

    return data


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

    success = network_agent.initialize(model)
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
