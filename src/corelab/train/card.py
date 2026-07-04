"""G3 — the hedged model card, generated from gate evidence (never from optimism).

The card refuses to overclaim by construction: every quantitative line comes from recorded gate
evidence; the licence checklist and the limitations section are mandatory boilerplate.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from corelab.train.gates import GATE_ORDER, TrainingGates

LICENCE_CHECKLIST = """\
## Licence checklist (complete before publishing — G3 requirement)

- [ ] **Base model licence** permits adapter redistribution (prefer Apache-2.0 bases).
- [ ] **Self-generated trajectories**: publishable (ours), but confirm no proprietary API
      responses are embedded verbatim (Amarisoft remote-API caveat).
- [ ] **TeleQnA**: eval-only — confirm it never entered training data (contamination report).
- [ ] **Tele-Data / TSpec-LLM**: 3GPP/ETSI-derived — check redistribution terms if any extract
      was used for RAG-augmented data generation.
- [ ] **5G3E**: no explicit LICENSE file upstream — contact authors before publishing anything
      derived from it.
"""

LIMITATIONS = """\
## Limitations (mandatory honesty)

- Evaluated on **TeleAgentBench v0** (5 public dev scenarios + held-out set where stated) and
  TeleQnA — narrow proxies for real network operations.
- Judges are programmatic/state-based but scenarios are **simulated**; real-RF behavior is not
  covered unless explicitly stated.
- Control actions in deployment remain **human-approval-gated** (the toolkit enforces this);
  this model does not change that and must not be deployed without the gate.
"""


def generate_model_card(
    gates: TrainingGates,
    model_name: str = "corelab-netops-lora",
    base_model: str = "(base model)",
    curation_stats: Optional[Dict[str, Any]] = None,
) -> str:
    status = gates.status()
    lines = [
        f"# {model_name}",
        "",
        f"LoRA adapter for **{base_model}**, tuned for agentic 5G/6G network operations "
        "(tool calling, intent drafting, evidence-grounded diagnosis) with the "
        "[CORE Lab NCSRD toolkit](https://github.com/akiskourtis/Agentic-5G-Monitoring-Skill).",
        "",
        "## Gate evidence (the pipeline's audit trail)",
        "",
    ]
    for gate in GATE_ORDER:
        entry = status[gate]
        mark = "✅" if entry["passed"] else "❌ NOT PASSED"
        lines.append(f"- **{gate}** {mark} — {entry['meaning']}")
        evidence = gates.state.get(gate, {}).get("evidence") or {}
        for key, value in list(evidence.items())[:6]:
            lines.append(f"    - {key}: `{value}`")
    if not all(status[g]["passed"] for g in GATE_ORDER):
        lines += [
            "",
            "> ⚠️ **This card is a DRAFT**: not all gates have passed. Do not publish until "
            "every gate above is ✅ (G3 includes the licence checklist below).",
        ]
    if curation_stats:
        lines += ["", "## Training data (curated)", ""]
        for key, value in curation_stats.items():
            lines.append(f"- {key}: `{value}`")
    lines += ["", LIMITATIONS, LICENCE_CHECKLIST]
    return "\n".join(lines)
