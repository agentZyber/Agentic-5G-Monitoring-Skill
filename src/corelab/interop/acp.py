"""ACP face (shim) — REST-native agent runs in the Agent Communication Protocol shape.

ACP (IBM/BeeAI lineage) is, like MCP and A2A, an **LF AAIF foundational project** (research
pass #2). Its REST surface: discover agents (``GET /agents``), execute runs
(``POST /runs`` with message ``parts`` carrying ``content`` + ``content_type``), poll runs.
This shim exposes the toolkit's runtime through those shapes — synchronous runs only.

**Honesty:** shapes follow the pre-AAIF ACP REST convention (BeeAI ACP 0.x/1.x); ACP↔A2A
convergence under AAIF is in motion, so this face is a tracked *shim*, re-validated against
whatever the foundation publishes. The research left ACP's merge status an open question —
treat this as compatibility plumbing, not a conformance claim.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from corelab.agent.runtime import AgentRuntime


class ACPRunStore:
    def __init__(self) -> None:
        self._runs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def put(self, run: Dict[str, Any]) -> None:
        with self._lock:
            self._runs[run["run_id"]] = run

    def get(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._runs.get(run_id)


def _message_content(messages: List[Dict[str, Any]]) -> str:
    chunks: List[str] = []
    for message in messages or []:
        for part in message.get("parts", []):
            content = part.get("content", "")
            if content:
                chunks.append(str(content))
    return "\n".join(chunks).strip()


def make_acp_router(runtime: AgentRuntime, agent_name: str = "corelab-5g", description: str = ""):
    from fastapi import APIRouter, Body, HTTPException

    router = APIRouter(prefix="/acp")
    store = ACPRunStore()

    @router.get("/agents")
    def list_agents() -> Dict[str, Any]:
        return {
            "agents": [
                {
                    "name": agent_name,
                    "description": description
                    or "Agentic 5G/6G network operations (observe, reason, act).",
                }
            ]
        }

    @router.post("/runs")
    def create_run(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        requested = payload.get("agent_name", agent_name)
        if requested != agent_name:
            raise HTTPException(status_code=404, detail=f"unknown agent '{requested}'")
        text = _message_content(payload.get("input") or [])
        if not text:
            raise HTTPException(status_code=422, detail="input has no content parts")

        run_id = f"run_{uuid.uuid4().hex[:12]}"
        try:
            result = runtime.run(text, meta={"face": "acp", "run_id": run_id})
            run = {
                "run_id": run_id,
                "agent_name": agent_name,
                "status": "completed",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "output": [
                    {
                        "role": "agent",
                        "parts": [{"content": result.answer, "content_type": "text/plain"}],
                    }
                ],
            }
        except Exception as exc:
            run = {
                "run_id": run_id,
                "agent_name": agent_name,
                "status": "failed",
                "error": str(exc),
                "output": [],
            }
        store.put(run)
        return run

    @router.get("/runs/{run_id}")
    def get_run(run_id: str) -> Dict[str, Any]:
        run = store.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"unknown run '{run_id}'")
        return run

    return router
