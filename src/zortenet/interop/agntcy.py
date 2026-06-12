"""AGNTCY / OASF descriptor — make the toolkit discoverable in the Internet of Agents.

AGNTCY (Cisco/Outshift → Linux Foundation, research pass #2) provides the agent-discovery layer:
**OASF** records (OCI-stored data model that explicitly describes A2A agents and MCP servers),
the Agent Directory, and SLIM messaging. This module generates an OASF-style record describing
this toolkit instance — its A2A card, MCP endpoint, and skills — served at
``/.well-known/oasf.json``.

**Honesty:** record generation only. OASF's schema evolves with the project; pushing the record
to an actual Agent Directory (and SLIM transport) is a live integration item — this gets a
toolkit instance *describable*, not yet *published*.
"""

from __future__ import annotations

from typing import Any, Dict

from zortenet import __version__
from zortenet.agent.tools import ToolRegistry


def oasf_record(
    registry: ToolRegistry,
    name: str = "org.zortenet.agentic-5g",
    base_url: str = "http://localhost:5001",
    description: str = "Agentic 5G/6G toolkit: observe, reason, and act on the core & RAN.",
) -> Dict[str, Any]:
    base = base_url.rstrip("/")
    return {
        "schema_version": "0.x",  # OASF evolves; pinned at directory-publish time
        "name": name,
        "version": __version__,
        "description": description,
        "authors": ["ZorteNet — The Agentic 5G/6G Toolkit"],
        "locators": [
            {"type": "a2a-card", "url": f"{base}/.well-known/agent-card.json"},
            {"type": "a2a-jsonrpc", "url": f"{base}/a2a"},
            {"type": "mcp-streamable-http", "url": f"{base}/mcp"},
            {"type": "acp", "url": f"{base}/acp"},
            {"type": "source-code", "url": "https://github.com/akiskourtis/Agentic-5G-Monitoring-Skill"},
        ],
        "skills": [
            {"name": t.name, "description": t.description, "tags": list(t.tags)}
            for t in registry.list()
        ],
        "extensions": [
            {
                "name": "telecom.domains",
                "data": {
                    "verticals": ["5g-core", "o-ran", "intent-management", "network-security"],
                    "standards": ["TMF921/TIO", "3GPP TS 28.312", "O-RAN A1"],
                },
            }
        ],
    }
