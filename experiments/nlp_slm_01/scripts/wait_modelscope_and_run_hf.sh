#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
LOG=artifacts/runs/wait_modelscope_hf.log
exec > >(tee -a "$LOG") 2>&1
echo "Watching ModelScope download (incomplete allowed until final)..."
while true; do
  if grep -q 'MODELSCOPE_DONE' artifacts/runs/modelscope_dl.log 2>/dev/null; then
    echo "Found MODELSCOPE_DONE marker"
    break
  fi
  total=$(find artifacts/modelscope_cache -name 'model-*.safetensors' -o -name 'model-*.safetensors.incomplete' 2>/dev/null | xargs -r stat -c%s 2>/dev/null | awk '{s+=$1} END{print s+0}')
  echo "$(date -Is) modelscope_weight_bytes=$total"
  # complete only when final non-incomplete shards exist and sum > 4GB
  final=$(find artifacts/modelscope_cache -name 'model-00001-of-00002.safetensors' -o -name 'model-00002-of-00002.safetensors' 2>/dev/null | grep -v incomplete | xargs -r stat -c%s 2>/dev/null | awk '{s+=$1} END{print s+0}')
  if [[ "$final" -gt 4000000000 ]]; then
    sleep 20
    final2=$(find artifacts/modelscope_cache -name 'model-00001-of-00002.safetensors' -o -name 'model-00002-of-00002.safetensors' 2>/dev/null | grep -v incomplete | xargs -r stat -c%s 2>/dev/null | awk '{s+=$1} END{print s+0}')
    if [[ "$final" == "$final2" ]]; then
      echo "Final shards stable at $final2"
      break
    fi
  fi
  sleep 120
done
MODEL_DIR=$(python - <<'PY'
from pathlib import Path
root=Path('artifacts/modelscope_cache')
for cfg in root.rglob('config.json'):
    parent=cfg.parent
    if (parent/'model.safetensors.index.json').exists() and (parent/'model-00001-of-00002.safetensors').exists() and (parent/'model-00002-of-00002.safetensors').exists():
        print(parent); break
PY
)
echo "Using model dir: $MODEL_DIR"
test -n "$MODEL_DIR"
python scripts/run_heldout_baselines.py --model "$MODEL_DIR" --arms Q1,Q2,Q3
echo HF_HOLDOUT_COMPLETE
