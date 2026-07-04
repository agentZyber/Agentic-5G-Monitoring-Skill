"""Telecom & agentic dataset registry.

Datasets are **referenced, never vendored** — the registry records where each lives, its
licence, and its role, and a future ``corelab datasets pull <name>`` fetches it on demand.
This keeps the repo light and licence-clean.

Roles:
  - ``eval``    benchmark the agent / model (e.g. score a local Ollama model on TeleQnA)
  - ``rag``     ingest into the telecom knowledge base for retrieval-augmented reasoning
  - ``replay``  feed the testbed event bus to simulate live traffic / anomalies

Only entries that survived adversarial verification in research pass #1 are marked
``verified=True``. Candidates surfaced but not yet independently verified are
``verified=False`` and carry a note.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

VALID_ROLES = ("eval", "rag", "replay")


@dataclass(frozen=True)
class Dataset:
    name: str
    source: str                 # Hugging Face id, GitHub repo, or URL
    description: str
    size: str
    license: str                # "unknown" / "verify" where not explicitly stated
    roles: Tuple[str, ...]
    citation: str = ""
    verified: bool = True
    note: str = ""

    def __post_init__(self) -> None:
        bad = [r for r in self.roles if r not in VALID_ROLES]
        if bad:
            raise ValueError(f"{self.name}: invalid role(s) {bad}; valid roles are {VALID_ROLES}")


REGISTRY: Dict[str, Dataset] = {
    "teleqna": Dataset(
        name="TeleQnA",
        source="hf:netop/TeleQnA",
        description="10,000 telecom multiple-choice questions across five categories; the "
        "canonical telecom-LLM knowledge benchmark.",
        size="10k MCQs",
        license="see HF card",
        roles=("eval",),
        citation="Maatouk et al., arXiv:2310.15051",
        verified=True,
    ),
    "tele-data": Dataset(
        name="Tele-Data",
        source="hf:AliMaatouk/Tele-Data",
        description="Telecom-domain pretraining/RAG corpus from arXiv papers, 3GPP standards, "
        "telecom Wikipedia, and Common Crawl (LLM-filtered). Backs the Tele-LLMs series.",
        size="~2.5B tokens / 12.1 GB",
        license="see HF card",
        roles=("rag",),
        citation="Maatouk et al., arXiv:2409.05314",
        verified=True,
    ),
    "5g3e": Dataset(
        name="5G3E",
        source="https://github.com/cedric-cnam/5G3E-dataset",
        description="Open 5G time-series system metrics (radio, computing, network) for "
        "data-driven network-automation / anomaly experiments.",
        size="~1.1 TB / 14 days",
        license="verify",  # no explicit LICENSE file in repo as of research pass #1
        roles=("replay",),
        citation="Phung et al., 6GNet 2022 (HAL hal-03698732)",
        verified=True,
        note="No explicit LICENSE file found; verify licensing before redistribution.",
    ),
    "tspec-llm": Dataset(
        name="TSpec-LLM",
        source="hf:rasoul-nikbakht/TSpec-LLM",
        description="3GPP-specification corpus for spec-grounded telecom LLM Q&A and retrieval.",
        size="3GPP specs corpus",
        license="see HF card",
        roles=("rag", "eval"),
        verified=True,
        note="Source confirmed in research pass #2; verify exact size/licence on the HF card.",
    ),
    # --- candidates surfaced in research, pending independent verification ---
    "telecomts": Dataset(
        name="TelecomTS",
        source="hf:AliMaatouk/TelecomTS",
        description="Telecom time-series / multimodal observability dataset (candidate for "
        "replay + anomaly detection).",
        size="unknown",
        license="see HF card",
        roles=("replay",),
        verified=False,
        note="Surfaced in research pass #1 sources; confirming size/licence in pass #2.",
    ),
    "telequad": Dataset(
        name="TeleQuAD",
        source="https://github.com/EricssonResearch/TeleQuAD",
        description="Telecom extractive question-answering dataset (Ericsson Research).",
        size="unknown",
        license="see repo",
        roles=("eval", "rag"),
        verified=False,
        note="Surfaced in research pass #1 sources; confirming size/licence in pass #2.",
    ),
}


def list_datasets(verified_only: bool = False) -> List[Dataset]:
    items = list(REGISTRY.values())
    if verified_only:
        items = [d for d in items if d.verified]
    return items


def get_dataset(name: str) -> Dataset:
    key = name.lower().replace("_", "-")
    if key not in REGISTRY:
        raise KeyError(f"Unknown dataset '{name}'. Known: {', '.join(sorted(REGISTRY))}")
    return REGISTRY[key]


def datasets_for_role(role: str) -> List[Dataset]:
    if role not in VALID_ROLES:
        raise ValueError(f"Invalid role '{role}'; valid roles are {VALID_ROLES}")
    return [d for d in REGISTRY.values() if role in d.roles]
