"""MCP server exposing the ToolRegistry over the Model Context Protocol.

Per the verified spec (research pass #2): MCP defines exactly two standard transports — **stdio**
(local/co-located) and **Streamable HTTP** (remote) — and tool descriptors carry an
``inputSchema``. The current released spec is 2025-11-25; the transport design is stable.

The pure descriptor generation (:func:`build_mcp_tools`) is unit-tested here. The live server
(:func:`create_server` / :func:`run_stdio`) lazily imports the ``mcp`` SDK and is exercised by
bringing the server up (documented in testbed/README.md) rather than in unit tests.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from corelab.agent.tools import ToolRegistry, registry as default_registry
from corelab.interop.schemas import to_mcp_tools


def build_mcp_tools(registry: Optional[ToolRegistry] = None) -> List[Dict[str, Any]]:
    """Return MCP tool descriptors ({name, description, inputSchema}) for the registry."""
    return to_mcp_tools(registry or default_registry)


def create_server(registry: Optional[ToolRegistry] = None, name: str = "corelab-5g"):
    """Build a low-level MCP ``Server`` wired to the registry. Requires ``pip install mcp``.

    Uses the low-level Server so the registry's exact ``inputSchema`` is advertised verbatim
    (rather than re-derived from Python signatures).
    """
    reg = registry or default_registry
    try:
        from mcp.server import Server
        from mcp.types import TextContent, Tool as MCPTool
    except ImportError as exc:  # pragma: no cover - depends on optional SDK
        raise RuntimeError(
            "The MCP SDK is not installed. Install it with `pip install mcp` to run the MCP server."
        ) from exc

    server = Server(name)

    @server.list_tools()
    async def _list_tools() -> List["MCPTool"]:  # noqa: F821
        return [
            MCPTool(name=d["name"], description=d["description"], inputSchema=d["inputSchema"])
            for d in to_mcp_tools(reg)
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: Optional[Dict[str, Any]]):
        result = reg.get(name).invoke(**(arguments or {}))
        return [TextContent(type="text", text=str(result))]

    return server


async def run_stdio(registry: Optional[ToolRegistry] = None, name: str = "corelab-5g") -> None:  # pragma: no cover
    """Serve the MCP server over stdio (the local transport)."""
    from mcp.server.stdio import stdio_server

    server = create_server(registry, name)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def make_streamable_http_app(
    registry: Optional[ToolRegistry] = None,
    name: str = "corelab-5g",
    json_response: bool = True,
    stateless: bool = True,
):
    """Build the Streamable HTTP face (the MCP remote transport).

    Returns ``(asgi_app, session_manager)``. Mount the ASGI app at a path (e.g. ``/mcp``) and
    enter ``session_manager.run()`` in the host app's lifespan. Stateless + JSON-response mode
    is used so each request is independent — the simplest correct deployment for a toolkit
    endpoint (and what the spec's deprecation of HTTP+SSE pushes toward).
    """
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

    server = create_server(registry, name)
    manager = StreamableHTTPSessionManager(
        app=server, json_response=json_response, stateless=stateless
    )

    async def asgi(scope, receive, send):  # plain ASGI callable, host-framework agnostic
        await manager.handle_request(scope, receive, send)

    return asgi, manager


if __name__ == "__main__":  # pragma: no cover - `python -m corelab.interop.mcp_server`
    import anyio

    from corelab.packs import DEFAULT_PACKS, load_packs

    import os

    pack_names = [p for p in os.getenv("CORELAB_PACKS", ",".join(DEFAULT_PACKS)).split(",") if p.strip()]
    reg, _ = load_packs(pack_names)
    anyio.run(run_stdio, reg)
