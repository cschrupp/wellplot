#!/usr/bin/env bash
# Start llama-server CUDA for one SLM-01B GGUF arm (C or D).
set -euo pipefail

ARM="${1:?arm C or D}"
PORT="${2:-8890}"
LLAMA_SERVER="${LLAMA_SERVER:-$HOME/.unsloth/llama.cpp/build/bin/llama-server}"
HF_HUB="${HF_HUB:-$HOME/.cache/huggingface/hub}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$ROOT/artifacts/runs"
mkdir -p "$LOG_DIR"

case "$ARM" in
  C)
    GGUF="$HF_HUB/models--unsloth--SmolLM3-3B-GGUF/snapshots/a7bc17204c8a326d6bd6e466e076959eddae2025/SmolLM3-3B-UD-Q4_K_XL.gguf"
    ALIAS="smollm3_gguf_q4"
    ;;
  D)
    GGUF="$HF_HUB/models--unsloth--Phi-4-mini-instruct-GGUF/snapshots/78eb92a46fc37e6b524df991ed9aca9bc6aa7b80/Phi-4-mini-instruct-Q4_K_M.gguf"
    ALIAS="phi4mini_gguf_q4"
    ;;
  *)
    echo "Unknown arm: $ARM (use C or D)" >&2
    exit 1
    ;;
esac

if [[ ! -e "$GGUF" ]]; then
  echo "GGUF missing: $GGUF" >&2
  exit 1
fi

# Free GPU from other llama-server instances if any
pkill -f 'llama-server' 2>/dev/null || true
sleep 1

LOG="$LOG_DIR/llama_server_01b_${ARM}.log"
echo "Starting llama-server arm=$ARM port=$PORT gguf=$GGUF"
"$LLAMA_SERVER" \
  -m "$GGUF" \
  --port "$PORT" \
  --host 127.0.0.1 \
  -ngl 99 \
  -c 8192 \
  --jinja \
  --alias "$ALIAS" \
  >"$LOG" 2>&1 &
echo $! >"$LOG_DIR/llama_server_01b_${ARM}.pid"

# Wait for readiness
for i in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1 \
    || curl -sf "http://127.0.0.1:${PORT}/v1/models" >/dev/null 2>&1; then
    echo "llama-server ready on :$PORT (arm $ARM)"
    exit 0
  fi
  sleep 2
done
echo "llama-server failed to become ready; see $LOG" >&2
tail -n 40 "$LOG" >&2 || true
exit 1
