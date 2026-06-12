"""ANP face (EXPERIMENTAL) — DID-based decentralized agent identity/discovery.

ANP (Agent Network Protocol) proposes ``did:wba`` Web-Based-Agent identities plus JSON-LD agent
descriptions for cross-operator agent federation. **Status honesty (research pass #2): ANP's
adoption/maturity was NOT independently verified — this face is explicitly experimental**, kept
tiny: a DID document at ``/.well-known/did.json`` whose service endpoints point at the real,
tested faces (A2A / MCP / agent description). No signing/auth — identity verification is out of
v0 scope and stated as such.
"""

from __future__ import annotations

from typing import Any, Dict
from urllib.parse import urlparse

from zortenet.agent.tools import ToolRegistry


def _host_of(base_url: str) -> str:
    parsed = urlparse(base_url)
    return parsed.netloc or parsed.path or "localhost"


def did_document(base_url: str = "http://localhost:5001") -> Dict[str, Any]:
    base = base_url.rstrip("/")
    did = f"did:wba:{_host_of(base)}"
    return {
        "@context": ["https://www.w3.org/ns/did/v1"],
        "id": did,
        # No verificationMethod in v0: unsigned, experimental — do not treat as authenticated identity.
        "service": [
            {"id": f"{did}#agent-description", "type": "AgentDescription", "serviceEndpoint": f"{base}/.well-known/agent-description.json"},
            {"id": f"{did}#a2a", "type": "A2AService", "serviceEndpoint": f"{base}/a2a"},
            {"id": f"{did}#mcp", "type": "MCPService", "serviceEndpoint": f"{base}/mcp"},
        ],
    }


def agent_description(registry: ToolRegistry, base_url: str = "http://localhost:5001") -> Dict[str, Any]:
    base = base_url.rstrip("/")
    return {
        "@context": {"@vocab": "https://schema.org/"},
        "@type": "SoftwareAgent",
        "name": "ZorteNet — Agentic 5G/6G Toolkit",
        "identifier": f"did:wba:{_host_of(base)}",
        "url": base,
        "experimental": True,
        "capabilities": [t.name for t in registry.list()],
        "interfaces": {
            "a2a": f"{base}/a2a",
            "mcp": f"{base}/mcp",
            "acp": f"{base}/acp",
            "rest": f"{base}/agent/ask",
        },
    }
