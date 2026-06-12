"""telco-bench: TeleQnA parsing, choice extraction, scoring, and the report."""

import json

from zortenet.llm.base import LLMProvider, LLMResponse
from zortenet.packs.telco_bench.data import load_teleqna, load_teleqna_dict
from zortenet.packs.telco_bench.runner import (
    build_prompt,
    parse_choice,
    run_benchmark,
    to_markdown,
)

TELEQNA_FIXTURE = {
    "question 0": {
        "question": "What does AMF stand for in 5G?",
        "option 1": "Access and Mobility Management Function",
        "option 2": "Application Management Function",
        "option 3": "Antenna Mounting Frame",
        "answer": "option 1: Access and Mobility Management Function",
        "explanation": "3GPP TS 23.501.",
        "category": "Standards specifications",
    },
    "question 1": {
        "question": "Which interface connects gNB and AMF?",
        "option 1": "N3",
        "option 2": "N2",
        "answer": "option 2: N2",
        "category": "Standards specifications",
    },
    "question 2": {
        "question": "Typical 5G NR subcarrier spacing for FR1?",
        "option 1": "15 kHz",
        "option 2": "240 kHz",
        "option 3": "1.4 MHz",
        "option 4": "10 Hz",
        "answer": "option 1: 15 kHz",
        "category": "Lexicon",
    },
    "question broken": {"question": "No options or answer here"},
}


class ScriptedProvider(LLMProvider):
    name = "scripted"
    model = "fake"

    def __init__(self, replies):
        self.replies = list(replies)

    def is_available(self):
        return True

    def chat(self, messages, tools=None, **kwargs):
        return LLMResponse(content=self.replies.pop(0))


def test_loader_parses_and_skips():
    items, skipped = load_teleqna_dict(TELEQNA_FIXTURE)
    assert len(items) == 3
    assert skipped == 1  # the broken entry
    first = items[0]
    assert first.answer_index == 0
    assert first.n_options == 3
    assert first.category == "Standards specifications"


def test_loader_from_file(tmp_path):
    path = tmp_path / "TeleQnA.txt"
    path.write_text(json.dumps(TELEQNA_FIXTURE))
    items, skipped = load_teleqna(path)
    assert (len(items), skipped) == (3, 1)


def test_build_prompt_numbers_options():
    items, _ = load_teleqna_dict(TELEQNA_FIXTURE)
    prompt = build_prompt(items[0])
    assert "1. Access and Mobility Management Function" in prompt
    assert "3. Antenna Mounting Frame" in prompt
    assert "(1-3)" in prompt


def test_parse_choice_variants():
    assert parse_choice("2", 3) == 1
    assert parse_choice("The answer is option 3.", 4) == 2
    assert parse_choice("I think 1 is correct", 3) == 0
    assert parse_choice("42", 3) is None  # out of range
    assert parse_choice("no idea", 3) is None
    assert parse_choice("", 3) is None


def test_run_benchmark_scores_and_categories():
    items, _ = load_teleqna_dict(TELEQNA_FIXTURE)
    # right ("1"), wrong ("1" when answer is 2), unparseable
    provider = ScriptedProvider(["1", "option 1", "I cannot tell"])
    result = run_benchmark(provider, items)

    assert result.total == 3
    assert result.correct == 1
    assert result.unparsed == 1
    assert result.accuracy == 1 / 3
    assert result.by_category["Standards specifications"]["total"] == 2
    assert result.by_category["Standards specifications"]["correct"] == 1
    assert result.by_category["Lexicon"]["correct"] == 0
    assert result.model == "fake" and result.provider == "scripted"


def test_run_benchmark_limit_and_progress():
    items, _ = load_teleqna_dict(TELEQNA_FIXTURE)
    seen = []
    provider = ScriptedProvider(["1"])
    result = run_benchmark(provider, items, limit=1, progress=lambda d, t: seen.append((d, t)))
    assert result.total == 1
    assert seen == [(1, 1)]


def test_markdown_report():
    items, _ = load_teleqna_dict(TELEQNA_FIXTURE)
    provider = ScriptedProvider(["1", "2", "1"])
    report = to_markdown(run_benchmark(provider, items))
    assert "telco-bench" in report
    assert "`fake`" in report
    assert "| Standards specifications |" in report
    assert "eval-only" in report  # the contamination reminder ships with every report
