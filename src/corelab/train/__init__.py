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

from corelab.train.configs import G0_SHORTLIST, PRESETS, build_config, write_config
from corelab.train.curate import (
    ContaminationGuard,
    CurationConfig,
    CurationReport,
    curate_trajectories,
    split_train_val,
    write_jsonl,
)
from corelab.train.g0 import G0Report, RAGWrappedProvider, run_g0
from corelab.train.gates import GateError, TrainingGates
from corelab.train.mixture import MixtureReport, assemble_mixture
from corelab.train.synth import (
    synth_correlation_trajectories,
    synth_diagnosis_pairs,
    synth_intent_pairs,
)

__all__ = [
    "G0_SHORTLIST",
    "PRESETS",
    "build_config",
    "write_config",
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
    "synth_correlation_trajectories",
    "synth_diagnosis_pairs",
    "synth_intent_pairs",
]
