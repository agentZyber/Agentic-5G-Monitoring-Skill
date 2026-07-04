#!/bin/bash
# v2.6 chained train -> eval (single process tree, reliable). Logs to run_v26.log.
cd /home/localadmin/zt || exit 1
PY=/home/localadmin/corelab-train/bin/python
echo "[run_v26] training start $(date +%H:%M)"
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True $PY -u run_sft.py --config sft_config_v26.json
echo "[run_v26] training exit $? at $(date +%H:%M)"
if [ -f output_v26/adapter_model.safetensors ]; then
  echo "[run_v26] adapter saved -> G2 multi-UC eval"
  ZT_ADAPTER=/home/localadmin/zt/output_v26 ZT_G2_OUT=/home/localadmin/zt/g2_sixg_v26.json \
    PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True $PY -u g2_sixg_eval.py
  echo "[run_v26] eval exit $? at $(date +%H:%M)"
else
  echo "[run_v26] NO adapter at output_v26/ -> training failed; skipping eval"
fi
echo "[run_v26] DONE $(date +%H:%M)"
