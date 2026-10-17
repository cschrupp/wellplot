#!/usr/bin/env bash
# Smoke: ~8 held-out cases × Q2 on arms C→D→A→B
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${ROOT}/.venv/bin/python"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
LIMIT="${LIMIT:-8}"
PORT="${PORT:-8890}"
BASE_URL="http://127.0.0.1:${PORT}/v1"

echo "=== SLM-01B smoke limit=$LIMIT ==="

for ARM in C D; do
  bash "$ROOT/scripts/run_slm01b_gguf_server.sh" "$ARM" "$PORT"
  "$PY" scripts/run_slm01b_heldout.py \
    --model-arms "$ARM" \
    --prompt-arms Q2 \
    --limit "$LIMIT" \
    --base-url "$BASE_URL"
  pkill -f 'llama-server' 2>/dev/null || true
  sleep 2
done

for ARM in A B; do
  "$PY" scripts/run_slm01b_heldout.py \
    --model-arms "$ARM" \
    --prompt-arms Q2 \
    --limit "$LIMIT" \
    --gpu-memory-gib 4.0
done

"$PY" scripts/run_slm01b_heldout.py --model-arms C,D,A,B --limit "$LIMIT" --aggregate-only
echo "=== smoke complete; see benchmark/evidence/slm01b_*.json ==="
