#!/bin/bash
# Dedicated war-game defender — chained train -> eval (single process tree). Logs to train_wargame.log.
cd /home/localadmin/zt || exit 1
PY=/home/localadmin/zortenet-train/bin/python
echo "[wargame] training start $(date +%H:%M)"
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True $PY -u run_sft.py --config sft_config_wargame.json
echo "[wargame] training exit $? at $(date +%H:%M)"
if [ -f output_wargame/adapter_model.safetensors ]; then
  echo "[wargame] adapter saved -> G2 war-game eval (base vs fine-tuned blue agent)"
  ZT_ADAPTER=/home/localadmin/zt/output_wargame ZT_G2_OUT=/home/localadmin/zt/g2_wargame.json \
    PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True $PY -u g2_wargame_eval.py
  echo "[wargame] eval exit $? at $(date +%H:%M)"
else
  echo "[wargame] NO adapter at output_wargame/ -> training failed; skipping eval"
fi
echo "[wargame] DONE $(date +%H:%M)"
