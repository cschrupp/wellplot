#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODEL_DIR="$ROOT/artifacts/models/Qwen3-1.7B"
PART1="$MODEL_DIR/model-00001-of-00002.safetensors"
PART2="$MODEL_DIR/model-00002-of-00002.safetensors"
# Expected sizes from HF (approx): part1 ~3235MB, part2 smaller
# Wait until both files exist and are stable for 30s
echo "Waiting for complete local Qwen3-1.7B weights in $MODEL_DIR"
while true; do
  if [[ -f "$PART1" && -f "$PART2" ]]; then
    s1=$(stat -c%s "$PART1")
    s2=$(stat -c%s "$PART2")
    sleep 30
    s1b=$(stat -c%s "$PART1")
    s2b=$(stat -c%s "$PART2")
    if [[ "$s1" == "$s1b" && "$s2" == "$s2b" && "$s1" -gt 3000000000 && "$s2" -gt 100000000 ]]; then
      echo "Weights ready: part1=$s1 part2=$s2"
      break
    fi
    echo "Still downloading/stabilizing part1=$s1b part2=$s2b"
  else
    echo "Missing shards; part1=$(stat -c%s "$PART1" 2>/dev/null || echo 0)"
    sleep 60
  fi
done
cd "$ROOT"
source .venv/bin/activate
export HF_HOME="$ROOT/artifacts/model_cache"
python scripts/run_heldout_baselines.py --model "$MODEL_DIR" --arms Q1,Q2,Q3
python scaffold/qlora/export_training_data.py --split development --out artifacts/exports/dev_sft.jsonl
echo HOLDOUT_COMPLETE
