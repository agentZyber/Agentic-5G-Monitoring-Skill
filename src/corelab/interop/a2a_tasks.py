"""A2A task lifecycle — the full agent-to-agent protocol face (v1.0 shapes).

Implements the A2A v1.0 JSON-RPC methods ``message/send``, ``tasks/get`` and ``tasks/cancel``
with the v1 object shapes: a **Message** (``role``, ``parts: [{kind: "text", text}]``,
``messageId``) creates or continues a **Task** (``id``, ``contextId``, ``status.state`` ∈
submitted/working/completed/failed/canceled, ``artifacts``, ``history``). Execution is
synchronous: a sent message runs the wrapped :class:`AgentRuntime` and the task completes with
the answer as a text artifact.

**Conformance honesty:** shapes follow the A2A v1.0 specification (stable Mar 2026 — research
pass #2); streaming (``message/stream``), push notifications, and validation against the
official a2a SDK/client are live/Stage-4-polish items. This is the same single-codebase pattern
as the MCP face: one ToolRegistry+runtime, another protocol face.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from corelab.agent.runtime import AgentRuntime

TERMINAL_STATES = {"completed", "failed", "canceled", "rejected"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text_message(role: str, text: str, task_id: str, context_id: str) -> Dict[str, Any]:
    return {
        "kind": "message",
        "role": role,
        "parts": [{"kind": "text", "text": text}],
        "messageId": f"msg_{uuid.uuid4().hex[:12]}",
        "taskId": task_id,
        "contextId": context_id,
    }


def message_text(message: Dict[str, Any]) -> str:
    """Extract concatenated text parts from an A2A message."""
    parts = message.get("parts") or []
    return "\n".join(p.get("text", "") for p in parts if p.get("kind") == "text").strip()


@dataclass
class A2ATask:
    task_id: str
    context_id: str
    state: str = "submitted"
    history: List[Dict[str, Any]] = field(default_factory=list)
    artifacts: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": "task",
            "id": self.task_id,
            "contextId": self.context_id,
            "status": {"state": self.state, "timestamp": _now()},
            "artifacts": self.artifacts,
            "history": self.history,
        }


class A2ATaskManager:
    """Owns task records and executes message/send through an AgentRuntime."""

    def __init__(self, runtime: AgentRuntime, agent_name: str = "corelab") -> None:
        self.runtime = runtime
        self.agent_name = agent_name
        self._tasks: Dict[str, A2ATask] = {}
        self._lock = threading.Lock()

    # ---- protocol operations ----------------------------------------------

    def send_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        text = message_text(message)
        if not text:
            raise ValueError("message has no text parts")

        task_id = message.get("taskId") or f"task_{uuid.uuid4().hex[:12]}"
        context_id = message.get("contextId") or f"ctx_{uuid.uuid4().hex[:12]}"
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                task = A2ATask(task_id=task_id, context_id=context_id)
                self._tasks[task_id] = task
            elif task.state in TERMINAL_STATES:
                raise ValueError(f"task '{task_id}' is terminal ({task.state})")

        task.history.append({**message, "taskId": task_id, "contextId": task.context_id})
        task.state = "working"
        try:
            result = self.runtime.run(text, meta={"face": "a2a", "task_id": task_id})
            task.artifacts.append(
                {
                    "artifactId": f"artifact_{uuid.uuid4().hex[:12]}",
                    "name": f"{self.agent_name}-response",
                    "parts": [{"kind": "text", "text": result.answer}],
                }
            )
            task.history.append(
                _text_message("agent", result.answer, task_id, task.context_id)
            )
            task.state = "completed"
        except Exception as exc:
            task.state = "failed"
            task.history.append(
                _text_message("agent", f"execution failed: {exc}", task_id, task.context_id)
            )
        return task.to_dict()

    def get_task(self, task_id: str) -> Dict[str, Any]:
        with self._lock:
            if task_id not in self._tasks:
                raise KeyError(f"unknown task '{task_id}'")
            return self._tasks[task_id].to_dict()

    def cancel_task(self, task_id: str) -> Dict[str, Any]:
        with self._lock:
            if task_id not in self._tasks:
                raise KeyError(f"unknown task '{task_id}'")
            task = self._tasks[task_id]
        if task.state not in TERMINAL_STATES:
            task.state = "canceled"
        return task.to_dict()

    # ---- JSON-RPC dispatch ----------------------------------------------------

    def handle_jsonrpc(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch one JSON-RPC 2.0 request; returns the JSON-RPC response object."""
        request_id = payload.get("id")
        method = payload.get("method", "")
        params = payload.get("params") or {}

        def ok(result: Dict[str, Any]) -> Dict[str, Any]:
            return {"jsonrpc": "2.0", "id": request_id, "result": result}

        def err(code: int, message: str) -> Dict[str, Any]:
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

        try:
            if method == "message/send":
                message = params.get("message") or {}
                return ok(self.send_message(message))
            if method == "tasks/get":
                return ok(self.get_task(params.get("id", "")))
            if method == "tasks/cancel":
                return ok(self.cancel_task(params.get("id", "")))
            return err(-32601, f"method not found: '{method}'")
        except KeyError as exc:
            return err(-32001, str(exc.args[0]) if exc.args else "not found")
        except ValueError as exc:
            return err(-32602, str(exc))
        except Exception as exc:  # defensive: protocol layer never raises
            return err(-32000, f"internal error: {exc}")


def make_a2a_jsonrpc_router(manager: A2ATaskManager):
    """FastAPI router exposing the JSON-RPC endpoint at POST /a2a."""
    from fastapi import APIRouter, Body

    router = APIRouter()

    @router.post("/a2a")
    def a2a_jsonrpc(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        return manager.handle_jsonrpc(payload)

    return router
