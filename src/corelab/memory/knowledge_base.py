"""Dependency-light knowledge base: chunking + Okapi BM25 + cited search hits.

Why BM25 and not embeddings here: the toolkit's light install must answer spec questions with
citations on a laptop with zero ML dependencies. BM25 over well-chunked standards text is a
strong, honest baseline (and the retrieval interface — ``search(query, k) -> hits with
source citations`` — is what packs program against; an embedding backend can replace the scorer
without touching callers).

Ingest accepts ``.txt``/``.md`` files (paragraph-chunked) and ``.jsonl`` (one ``{"text": ...,
"source"?: ..., "meta"?: {...}}`` per line — the shape of Tele-Data/TSpec-LLM-style corpus
extracts pulled via the dataset registry). Corpora are never vendored into the repo.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

_TOKEN = re.compile(r"[a-z0-9]+")

# BM25 constants (standard Okapi defaults)
_K1 = 1.5
_B = 0.75


def _tokenize(text: str) -> List[str]:
    return _TOKEN.findall(text.lower())


def chunk_text(text: str, max_chars: int = 1200) -> List[str]:
    """Group paragraphs into chunks of at most ``max_chars`` (oversized paragraphs split hard)."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: List[str] = []
    current = ""
    for para in paragraphs:
        while len(para) > max_chars:  # pathological paragraph: hard split
            chunks.append(para[:max_chars])
            para = para[max_chars:]
        if current and len(current) + len(para) + 2 > max_chars:
            chunks.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current:
        chunks.append(current)
    return chunks


@dataclass
class Chunk:
    chunk_id: str
    text: str
    source: str
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchHit:
    chunk: Chunk
    score: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.chunk.text,
            "citation": {"source": self.chunk.source, "chunk_id": self.chunk.chunk_id},
            "score": round(self.score, 4),
            **({"meta": self.chunk.meta} if self.chunk.meta else {}),
        }


class KnowledgeBase:
    def __init__(self) -> None:
        self._chunks: List[Chunk] = []
        self._term_freqs: List[Counter] = []
        self._doc_freq: Counter = Counter()
        self._total_len = 0
        self._source_counts: Counter = Counter()

    # ---- ingest -----------------------------------------------------------

    def add_text(
        self, text: str, source: str, meta: Optional[Dict[str, Any]] = None
    ) -> int:
        added = 0
        for chunk_text_ in chunk_text(text):
            tokens = _tokenize(chunk_text_)
            if not tokens:
                continue
            chunk = Chunk(
                chunk_id=f"{source}#{self._source_counts[source]}",
                text=chunk_text_,
                source=source,
                meta=meta or {},
            )
            self._source_counts[source] += 1
            tf = Counter(tokens)
            self._chunks.append(chunk)
            self._term_freqs.append(tf)
            self._doc_freq.update(tf.keys())
            self._total_len += len(tokens)
            added += 1
        return added

    def ingest_file(self, path: str | Path) -> int:
        """Ingest one file (.txt/.md → chunked text; .jsonl → one record per line)."""
        path = Path(path)
        if path.suffix.lower() == ".jsonl":
            added = 0
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                text = record.get("text", "")
                if text:
                    added += self.add_text(
                        text,
                        source=record.get("source", f"{path.name}:{i}"),
                        meta=record.get("meta") or {},
                    )
            return added
        return self.add_text(path.read_text(encoding="utf-8"), source=path.name)

    def ingest_dir(self, directory: str | Path) -> Dict[str, int]:
        """Ingest every .txt/.md/.jsonl under a directory (recursive); returns per-file counts."""
        directory = Path(directory)
        report: Dict[str, int] = {}
        if not directory.is_dir():
            return report
        for path in sorted(directory.rglob("*")):
            if path.suffix.lower() in {".txt", ".md", ".jsonl"} and path.is_file():
                report[str(path.relative_to(directory))] = self.ingest_file(path)
        return report

    # ---- search ------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._chunks)

    @property
    def sources(self) -> List[str]:
        return sorted({c.source for c in self._chunks})

    def search(self, query: str, k: int = 5) -> List[SearchHit]:
        """Okapi BM25 ranking; returns the top-k chunks with citations."""
        if not self._chunks:
            return []
        terms = _tokenize(query)
        if not terms:
            return []
        n_docs = len(self._chunks)
        avg_len = self._total_len / n_docs
        scored: List[SearchHit] = []
        for chunk, tf in zip(self._chunks, self._term_freqs):
            doc_len = sum(tf.values())
            score = 0.0
            for term in terms:
                freq = tf.get(term)
                if not freq:
                    continue
                df = self._doc_freq[term]
                idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1.0)
                score += idf * (freq * (_K1 + 1)) / (
                    freq + _K1 * (1 - _B + _B * doc_len / avg_len)
                )
            if score > 0:
                scored.append(SearchHit(chunk=chunk, score=score))
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:k]
