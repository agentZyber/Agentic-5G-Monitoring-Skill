"""A2A (Agent2Agent) face — advertise the toolkit's skills via an Agent Card.

Per the verified spec (research pass #2): A2A reached stable v1.0.0 (Mar 2026), is LF/AAIF-governed,
and agents discover each other via an **Agent Card** served at ``/.well-known/agent-card.json``.
A2A is complementary to MCP (agent↔agent vs. agent↔tool).

:func:`build_agent_card` (in schemas.py) is the tested, pure renderer. :func:`make_a2a_router`
mounts it (plus a minimal task endpoint) onto an existing FastAPI app; FastAPI is imported lazily
so importing this module never requires the web stack.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from corelab.agent.tools import ToolRegistry, registry as default_registry
from corelab.interop.schemas import build_agent_card


def make_a2a_router(registry: Optional[ToolRegistry] = None, **card_kwargs: Any):
    """Return a FastAPI router exposing the Agent Card and a minimal synchronous task endpoint."""
    from fastapi import APIRouter  # lazy: keeps the web stack optional

    reg = registry or default_registry
    router = APIRouter()

    @router.get("/.well-known/agent-card.json")
    def agent_card() -> Dict[str, Any]:
        return build_agent_card(reg, **card_kwargs)

    @router.post("/a2a/skills/{skill_id}")
    def invoke_skill(skill_id: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # Minimal direct-skill invocation (a full A2A task lifecycle is a later milestone).
        tool = reg.get(skill_id)
        result = tool.invoke(**(arguments or {}))
        return {"skill": skill_id, "result": result}

    return router
