"""spec-kb — spec-grounded retrieval tools over the telecom knowledge base.

Gives the agent ``search_specs`` (BM25 over ingested 3GPP/telecom corpus extracts, with
citations) and ``kb_status``. Content is ingested lazily on first use from ``CORELAB_KB_DIR``
(default ``datasets/kb``) — drop ``.txt``/``.md``/``.jsonl`` extracts there via the dataset
registry's pull flow; nothing is vendored, licences stay with their sources.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from corelab.agent.tools import ToolRegistry
from corelab.memory.knowledge_base import KnowledgeBase

PACK: Dict[str, Any] = {
    "name": "spec-kb",
    "description": "Spec-grounded retrieval (BM25 + citations) over ingested telecom corpora.",
    "connectors": [],
    "datasets": ["tspec-llm", "tele-data"],
    "system_prompt": (
        "When answering standards/specification questions, search the knowledge base first and "
        "cite the returned sources (source + chunk_id). If the knowledge base is empty or has "
        "no relevant hits, say so explicitly rather than answering from memory alone."
    ),
}

DEFAULT_KB_DIR = "datasets/kb"


def build_registry(kb: Optional[KnowledgeBase] = None, kb_dir: Optional[str] = None) -> ToolRegistry:
    directory = kb_dir or os.getenv("CORELAB_KB_DIR", DEFAULT_KB_DIR)
    state: Dict[str, Any] = {"kb": kb, "ingest_report": None}

    def _ensure_kb() -> KnowledgeBase:
        if state["kb"] is None:
            knowledge = KnowledgeBase()
            state["ingest_report"] = knowledge.ingest_dir(directory)
            state["kb"] = knowledge
        elif state["ingest_report"] is None:
            state["ingest_report"] = {}  # injected KB: caller owns ingestion
        return state["kb"]

    reg = ToolRegistry()

    @reg.tool(
        name="search_specs",
        description=(
            "Search the ingested telecom knowledge base (3GPP/spec extracts) and return the "
            "most relevant passages WITH citations. Use for standards questions."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to look up"},
                "k": {"type": "integer", "description": "Number of passages (default 5)"},
            },
            "required": ["query"],
        },
        tags=("rag", "specs"),
    )
    def search_specs(query: str, k: int = 5) -> Dict[str, Any]:
        knowledge = _ensure_kb()
        if len(knowledge) == 0:
            return {
                "hits": [],
                "note": (
                    f"knowledge base is empty — put .txt/.md/.jsonl corpus extracts under "
                    f"'{directory}' (see the dataset registry: tspec-llm, tele-data)"
                ),
            }
        return {"hits": [hit.to_dict() for hit in knowledge.search(query, k=k)]}

    @reg.tool(
        name="kb_status",
        description="Knowledge-base status: chunk count, sources, and the last ingest report.",
        tags=("rag",),
    )
    def kb_status() -> Dict[str, Any]:
        knowledge = _ensure_kb()
        return {
            "chunks": len(knowledge),
            "sources": knowledge.sources,
            "kb_dir": directory,
            "ingest_report": state["ingest_report"],
        }

    return reg
