"""G0 — the baseline matrix: base vs base+RAG, across providers, on both benchmarks.

The gate question (MODEL_PIPELINE.md §4): *is there a measurable gap that RAG alone doesn't
close?* If not, the honest move is to stop and publish that finding. ``decide_gap`` encodes the
rule; the runner produces the evidence either way.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from corelab.bench.teleagent import builtin_scenarios, run_teleagent_bench
from corelab.llm.base import LLMProvider, LLMResponse, ToolSpec
from corelab.memory.knowledge_base import KnowledgeBase
from corelab.packs.telco_bench.data import MCQItem
from corelab.packs.telco_bench.runner import run_benchmark


class RAGWrappedProvider(LLMProvider):
    """Wrap any provider with knowledge-base retrieval: top-k hits for the latest user message
    are prepended as a context system message. This is the '+RAG' arm of the G0 ablation."""

    def __init__(self, inner: LLMProvider, kb: KnowledgeBase, k: int = 3) -> None:
        self.inner = inner
        self.kb = kb
        self.k = k
        self.name = f"{inner.name}+rag"
        self.model = getattr(inner, "model", "")

    def is_available(self) -> bool:
        return self.inner.is_available()

    def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[ToolSpec]] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        query = next(
            (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), ""
        )
        hits = self.kb.search(query, k=self.k) if len(self.kb) else []
        if hits:
            context = "\n\n".join(
                f"[{h.chunk.source}#{h.chunk.chunk_id}] {h.chunk.text}" for h in hits
            )
            messages = [
                messages[0],
                {
                    "role": "system",
                    "content": f"Relevant reference material (cite sources when used):\n{context}",
                },
                *messages[1:],
            ] if messages and messages[0].get("role") == "system" else [
                {"role": "system", "content": f"Relevant reference material:\n{context}"},
                *messages,
            ]
        return self.inner.chat(messages, tools=tools, **kwargs)


@dataclass
class G0Row:
    label: str
    rag: bool
    telco_accuracy: Optional[float]      # None when no TeleQnA items supplied
    teleagent_success: float
    invalid_call_rate: float

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class G0Report:
    rows: List[G0Row] = field(default_factory=list)
    target_success: float = 0.9

    def decide_gap(self) -> Tuple[bool, str]:
        """Gap exists iff the BEST +RAG arm still misses the agentic target. Telco-knowledge
        accuracy is reported as evidence but the gate decision is agentic (TeleAgentBench)."""
        rag_rows = [r for r in self.rows if r.rag] or self.rows
        if not rag_rows:
            return False, "no rows — run the matrix first"
        best = max(rag_rows, key=lambda r: r.teleagent_success)
        if best.teleagent_success >= self.target_success:
            return (
                False,
                f"NO GAP: '{best.label}' (+RAG) reaches {best.teleagent_success:.0%} ≥ target "
                f"{self.target_success:.0%} — per MODEL_PIPELINE §4, stop and publish this "
                "finding instead of training.",
            )
        return (
            True,
            f"GAP: best +RAG arm '{best.label}' reaches only {best.teleagent_success:.0%} "
            f"< target {self.target_success:.0%} — proceed to G1.",
        )

    def to_markdown(self) -> str:
        gap, verdict = self.decide_gap()
        lines = [
            "# G0 — Baseline matrix (base vs base+RAG)",
            "",
            "| Arm | RAG | TeleQnA acc | TeleAgentBench success | invalid-call rate |",
            "|---|---|---|---|---|",
        ]
        for row in self.rows:
            telco = f"{row.telco_accuracy:.1%}" if row.telco_accuracy is not None else "—"
            lines.append(
                f"| {row.label} | {'✅' if row.rag else '—'} | {telco} "
                f"| {row.teleagent_success:.0%} | {row.invalid_call_rate:.1%} |"
            )
        lines += ["", f"**Gate decision:** {'GAP EXISTS' if gap else 'NO GAP'} — {verdict}"]
        return "\n".join(lines)


def run_g0(
    providers: List[Tuple[str, LLMProvider]],
    kb: Optional[KnowledgeBase] = None,
    teleqna_items: Optional[List[MCQItem]] = None,
    teleqna_limit: Optional[int] = 100,
    scenarios=None,
    target_success: float = 0.9,
) -> G0Report:
    """Run each provider twice (base, +RAG when a KB is supplied) over both benchmarks."""
    report = G0Report(target_success=target_success)
    scenario_list = scenarios if scenarios is not None else builtin_scenarios()

    arms: List[Tuple[str, LLMProvider, bool]] = []
    for label, provider in providers:
        arms.append((label, provider, False))
        if kb is not None and len(kb):
            arms.append((label, RAGWrappedProvider(provider, kb), True))

    for label, provider, rag in arms:
        telco_acc = None
        if teleqna_items:
            telco = run_benchmark(provider, teleqna_items, limit=teleqna_limit)
            telco_acc = telco.accuracy
        agentic = run_teleagent_bench(provider, scenarios=scenario_list)
        report.rows.append(
            G0Row(
                label=label,
                rag=rag,
                telco_accuracy=telco_acc,
                teleagent_success=agentic.success_rate,
                invalid_call_rate=agentic.invalid_call_rate,
            )
        )
    return report
