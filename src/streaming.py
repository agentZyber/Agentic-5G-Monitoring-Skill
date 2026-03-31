import json
import asyncio
from typing import Dict, Any, List, Callable, Optional, Set
from datetime import datetime
from collections import defaultdict
from enum import Enum


class EventType(str, Enum):
    LOCATION = "location"
    ALERT = "alert"
    POLICY_CHANGE = "policy_change"
    SUBSCRIPTION = "subscription"
    BREACH = "breach"
    SYSTEM = "system"


class EventBus:
    def __init__(self):
        self._subscribers: Dict[EventType, Set[Callable]] = defaultdict(set)
        self._all_subscribers: Set[Callable] = set()

    def subscribe(
        self, callback: Callable, event_types: Optional[List[EventType]] = None
    ):
        if event_types is None:
            self._all_subscribers.add(callback)
        else:
            for et in event_types:
                self._subscribers[et].add(callback)

    def unsubscribe(self, callback: Callable):
        self._all_subscribers.discard(callback)
        for subscribers in self._subscribers.values():
            subscribers.discard(callback)

    async def publish(self, event: Dict[str, Any]):
        event["_published_at"] = datetime.utcnow().isoformat()

        for callback in self._all_subscribers:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception as e:
                print(f"Event callback error: {e}")

        event_type = EventType(event.get("type", "system"))
        for callback in self._subscribers.get(event_type, set()):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception as e:
                print(f"Event callback error: {e}")


class StreamingManager:
    def __init__(self):
        self.event_bus = EventBus()
        self._ws_connections: List = []
        self._sse_connections: List = []

    async def broadcast_ws(self, message: Dict[str, Any]):
        disconnected = []
        for ws in self._ws_connections:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)

        for ws in disconnected:
            self._ws_connections.remove(ws)

    async def broadcast_sse(self, event: str, data: Dict[str, Any]):
        disconnected = []
        for sse in self._sse_connections:
            try:
                await sse.send(event=event, data=json.dumps(data))
            except Exception:
                disconnected.append(sse)

        for sse in disconnected:
            self._sse_connections.remove(sse)

    def add_ws_connection(self, ws):
        self._ws_connections.append(ws)

    def remove_ws_connection(self, ws):
        if ws in self._ws_connections:
            self._ws_connections.remove(ws)

    def add_sse_connection(self, sse):
        self._sse_connections.append(sse)

    def remove_sse_connection(self, sse):
        if sse in self._sse_connections:
            self._sse_connections.remove(sse)

    @property
    def connection_count(self) -> int:
        return len(self._ws_connections) + len(self._sse_connections)


streaming_manager = StreamingManager()


class StreamingEventFormatter:
    @staticmethod
    def format_location_event(event: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "event_type": "location",
            "timestamp": event.get("timestamp", datetime.utcnow().isoformat()),
            "external_id": event.get("externalId"),
            "cell_id": event.get("locationInfo", {}).get("cellId")
            if isinstance(event.get("locationInfo"), dict)
            else None,
            "ue_location_timestamp": event.get("locationInfo", {}).get(
                "ueLocationTimestamp"
            )
            if isinstance(event.get("locationInfo"), dict)
            else None,
            "source": "5g_nef",
        }

    @staticmethod
    def format_alert_event(event: Dict[str, Any]) -> Dict[str, Any]:
        base = StreamingEventFormatter.format_location_event(event)
        base["event_type"] = "alert"
        base["alert_reason"] = (
            "policy_breach" if event.get("type") == "alert" else "unknown"
        )
        base["policy_id"] = (
            event.get("policy", {}).get("policy_id")
            if isinstance(event.get("policy"), dict)
            else None
        )
        return base

    @staticmethod
    def format_event(event: Dict[str, Any]) -> Dict[str, Any]:
        event_type = event.get("type", "unknown")

        if event_type == "alert":
            return StreamingEventFormatter.format_alert_event(event)
        else:
            return StreamingEventFormatter.format_location_event(event)


async def stream_event_to_agents(event: Dict[str, Any]):
    formatted = StreamingEventFormatter.format_event(event)

    ws_message = {"stream_type": "event", "data": formatted, "raw": event}

    await streaming_manager.broadcast_ws(ws_message)
    await streaming_manager.broadcast_sse(event=formatted["event_type"], data=formatted)

    await streaming_manager.event_bus.publish(event)
