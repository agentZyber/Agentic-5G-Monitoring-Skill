"""Knowledge base: chunking, BM25 ranking, citations, ingest formats, and the spec-kb pack."""

import json

from zortenet.memory.knowledge_base import KnowledgeBase, chunk_text
from zortenet.packs.spec_kb import build_registry

AMF_TEXT = (
    "The Access and Mobility Management Function (AMF) handles registration management, "
    "connection management, and mobility management for UEs in the 5G core network."
)
SMF_TEXT = (
    "The Session Management Function (SMF) is responsible for PDU session establishment, "
    "modification and release, and selects the UPF for the user plane path."
)
COOKING_TEXT = "Slice the onions thinly and caramelize them slowly over low heat."


# ---- chunking ----------------------------------------------------------------


def test_chunk_text_groups_paragraphs():
    text = "para one\n\npara two\n\npara three"
    assert chunk_text(text, max_chars=1200) == ["para one\n\npara two\n\npara three"]
    # small budget forces splits on paragraph boundaries
    chunks = chunk_text(text, max_chars=10)
    assert chunks == ["para one", "para two", "para three"]


def test_chunk_text_hard_splits_oversized_paragraph():
    chunks = chunk_text("x" * 2500, max_chars=1000)
    assert [len(c) for c in chunks] == [1000, 1000, 500]


# ---- BM25 search -----------------------------------------------------------------


def _kb():
    kb = KnowledgeBase()
    kb.add_text(AMF_TEXT, source="ts23501-amf.txt")
    kb.add_text(SMF_TEXT, source="ts23501-smf.txt")
    kb.add_text(COOKING_TEXT, source="cookbook.txt")
    return kb


def test_search_ranks_relevant_chunk_first_with_citation():
    hits = _kb().search("which function handles UE registration and mobility management")
    assert hits, "expected hits"
    top = hits[0].to_dict()
    assert top["citation"]["source"] == "ts23501-amf.txt"
    assert "#0" in top["citation"]["chunk_id"]
    assert "AMF" in top["text"]


def test_search_distinguishes_topics():
    hits = _kb().search("PDU session establishment UPF selection")
    assert hits[0].chunk.source == "ts23501-smf.txt"


def test_search_empty_kb_and_empty_query():
    assert KnowledgeBase().search("anything") == []
    assert _kb().search("") == []
    assert _kb().search("zzzzunknowntermzzz") == []


# ---- ingest formats ---------------------------------------------------------------


def test_ingest_jsonl_and_dir(tmp_path):
    (tmp_path / "specs").mkdir()
    (tmp_path / "specs" / "amf.md").write_text(AMF_TEXT)
    records = [
        {"text": SMF_TEXT, "source": "TS 23.501 §6.2.2", "meta": {"release": "18"}},
        {"text": ""},  # skipped: empty
        {"not_text": "ignored"},
    ]
    (tmp_path / "corpus.jsonl").write_text("\n".join(json.dumps(r) for r in records))

    kb = KnowledgeBase()
    report = kb.ingest_dir(tmp_path)
    assert report["specs/amf.md"] == 1
    assert report["corpus.jsonl"] == 1
    assert len(kb) == 2
    assert "TS 23.501 §6.2.2" in kb.sources

    hit = kb.search("UPF selection for the user plane")[0].to_dict()
    assert hit["citation"]["source"] == "TS 23.501 §6.2.2"
    assert hit["meta"]["release"] == "18"


def test_ingest_missing_dir_is_empty_report():
    assert KnowledgeBase().ingest_dir("/nonexistent/path") == {}


# ---- spec-kb pack ------------------------------------------------------------------


def test_spec_kb_pack_with_injected_kb():
    reg = build_registry(kb=_kb())
    out = reg.get("search_specs").invoke(query="AMF registration management", k=2)
    assert out["hits"][0]["citation"]["source"] == "ts23501-amf.txt"

    status = reg.get("kb_status").invoke()
    assert status["chunks"] == 3
    assert "cookbook.txt" in status["sources"]


def test_spec_kb_pack_lazy_ingest_from_dir(tmp_path):
    (tmp_path / "smf.txt").write_text(SMF_TEXT)
    reg = build_registry(kb_dir=str(tmp_path))
    status = reg.get("kb_status").invoke()
    assert status["chunks"] == 1
    assert status["ingest_report"] == {"smf.txt": 1}


def test_spec_kb_pack_empty_dir_says_so(tmp_path):
    reg = build_registry(kb_dir=str(tmp_path / "void"))
    out = reg.get("search_specs").invoke(query="anything")
    assert out["hits"] == []
    assert "empty" in out["note"]
    assert "tspec-llm" in out["note"]  # points the user at the registry
