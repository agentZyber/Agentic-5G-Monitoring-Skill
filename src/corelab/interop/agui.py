"""AG-UI face (v0) — stream agent runs to frontends in the AG-UI event taxonomy.

AG-UI (CopilotKit-led; deliberately independent of LF/AAIF — research pass #2) standardizes the
agent↔frontend channel as a typed event stream over HTTP POST + SSE. This v0 emits the core
taxonomy — RUN_STARTED, TOOL_CALL_START/ARGS/END, TOOL_CALL_RESULT, TEXT_MESSAGE_START/CONTENT/
END, RUN_FINISHED — derived from a completed :class:`AgentRuntime` run.

**Honesty note:** v0 streams *post-hoc* (the run executes, then its events stream in order) —
the event shapes follow AG-UI's published taxonomy, but token-level streaming and conformance
against the official ag-ui client are validated when provider streaming lands (Stage 4 polish).
"""

# NOTE: no `from __future__ import annotations` here — the AG-UI router defines its pydantic
# request model inside the factory function, and postponed (stringified) annotations would make
# FastAPI unable to resolve that local name, silently demoting the body param to a query param.

import json
import uuid
from typing import Any, Dict, Iterator, List, Optional

from corelab.agent.runtime import AgentResult, AgentRuntime, parse_tool_call


def agui_events(
    result: AgentResult,
    thread_id: Optional[str] = None,
    run_id: Optional[str] = None,
) -> Iterator[Dict[str, Any]]:
    """Translate a completed run into the AG-UI event sequence (pure, testable)."""
    thread_id = thread_id or f"thread_{uuid.uuid4().hex[:12]}"
    run_id = run_id or f"run_{uuid.uuid4().hex[:12]}"
    yield {"type": "RUN_STARTED", "threadId": thread_id, "runId": run_id}

    pending_ids: List[str] = []  # FIFO: tool calls awaiting their result message
    counter = 0
    for message in result.messages:
        role = message.get("role")
        if role == "assistant" and message.get("tool_calls"):
            for tc in message["tool_calls"]:
                counter += 1
                call_id = f"call_{counter}"
                try:
                    name, args = parse_tool_call(tc)
                except Exception:
                    name, args = "unknown", {}
                yield {"type": "TOOL_CALL_START", "toolCallId": call_id, "toolCallName": name}
                yield {"type": "TOOL_CALL_ARGS", "toolCallId": call_id, "delta": json.dumps(args)}
                yield {"type": "TOOL_CALL_END", "toolCallId": call_id}
                pending_ids.append(call_id)
        elif role == "tool" and pending_ids:
            yield {
                "type": "TOOL_CALL_RESULT",
                "toolCallId": pending_ids.pop(0),
                "content": message.get("content", ""),
            }

    message_id = f"msg_{uuid.uuid4().hex[:12]}"
    yield {"type": "TEXT_MESSAGE_START", "messageId": message_id, "role": "assistant"}
    yield {"type": "TEXT_MESSAGE_CONTENT", "messageId": message_id, "delta": result.answer}
    yield {"type": "TEXT_MESSAGE_END", "messageId": message_id}
    yield {"type": "RUN_FINISHED", "threadId": thread_id, "runId": run_id}


def make_agui_router(runtime: AgentRuntime):
    """FastAPI router: POST /agui/run {message} → SSE stream of AG-UI events."""
    from fastapi import APIRouter  # lazy, keeps the web stack optional
    from fastapi.responses import StreamingResponse
    from pydantic import BaseModel

    class RunRequest(BaseModel):
        message: str
        thread_id: Optional[str] = None

    router = APIRouter()

    @router.post("/agui/run")
    def run(request: RunRequest) -> StreamingResponse:
        result = runtime.run(request.message, meta={"face": "agui"})

        def stream() -> Iterator[str]:
            for event in agui_events(result, thread_id=request.thread_id):
                yield f"data: {json.dumps(event)}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    return router
