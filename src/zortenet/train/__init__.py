"""Training pipeline — the Stage-5 / MODEL_PIPELINE.md implementation (gated G0→G3).

The pipeline philosophy, encoded in code:
- **Measure before training** (G0): if base+RAG meets target, the pipeline tells you to stop
  and publish that finding instead of burning GPU-weeks.
- **Outcome-validated data only** (G1): curation filters on judge-stamped outcomes and
  mechanical validity; TeleQnA and the public bench scenarios are contamination-guarded out.
- **Gates are enforced, not advisory**: advancing without the prior gate passed raises —
  the same human-respecting state-machine pattern as the intent ledger.
- **The GPU run itself is live-pending**: configs and the launcher are generated here; the
  actual LoRA-SFT needs the GPU host (and `pip install trl peft transformers`).
"""

from zortenet.train.curate import (
    ContaminationGuard,
    CurationConfig,
    CurationReport,
    curate_trajectories,
    split_train_val,
    write_jsonl,
)
from zortenet.train.g0 import G0Report, RAGWrappedProvider, run_g0
from zortenet.train.gates import GateError, TrainingGates
from zortenet.train.mixture import MixtureReport, assemble_mixture
from zortenet.train.synth import synth_diagnosis_pairs, synth_intent_pairs

__all__ = [
    "ContaminationGuard",
    "CurationConfig",
    "CurationReport",
    "curate_trajectories",
    "split_train_val",
    "write_jsonl",
    "G0Report",
    "RAGWrappedProvider",
    "run_g0",
    "GateError",
    "TrainingGates",
    "MixtureReport",
    "assemble_mixture",
    "synth_diagnosis_pairs",
    "synth_intent_pairs",
]
