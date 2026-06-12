"""Memory layer: knowledge base (retrieval) over telecom corpora.

Stage-2 ships a dependency-light BM25 knowledge base (pure Python — no PyTorch/Chroma tax) so
spec-grounded answers work in the light install. A Chroma/embedding backend can slot behind the
same interface later for semantic search (the legacy app already carries that stack).
"""

from zortenet.memory.knowledge_base import Chunk, KnowledgeBase, SearchHit

__all__ = ["Chunk", "KnowledgeBase", "SearchHit"]
