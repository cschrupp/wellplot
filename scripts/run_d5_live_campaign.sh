#!/usr/bin/env bash
set -euo pipefail

readonly REPO_ROOT="/home/user/projects/well_log_os"
readonly WATCHDOG_SECONDS=10800
readonly TERMINATION_GRACE_SECONDS=10

usage() {
    printf 'Usage: %s {preflight|execute|planner-smoke} {d4|final|a10-53|h1-development|h1b-development|s03-revised-development|isolated-specialists} AUTHORIZATION_JSON\n' "$0" >&2
}

if [[ $# -ne 3 ]]; then
    usage
    exit 64
fi

mode="$1"
population="$2"
authorization_path="$3"

case "$mode" in
    preflight)
        runner_mode="--provider-free-preflight"
        ;;
    execute)
        runner_mode="--execute-live"
        ;;
    planner-smoke)
        runner_mode="--execute-planner-smoke"
        ;;
    *)
        usage
        exit 64
        ;;
esac

case "$population" in
    d4|final|a10-53|h1-development|h1b-development|s03-revised-development|isolated-specialists) ;;
    *)
        usage
        exit 64
        ;;
esac

if [[ "$authorization_path" != /* ]]; then
    authorization_path="$REPO_ROOT/$authorization_path"
fi
if [[ ! -f "$authorization_path" ]]; then
    printf 'Authorization descriptor not found: %s\n' "$authorization_path" >&2
    exit 66
fi

cd -- "$REPO_ROOT"
if [[ "$(pwd -P)" != "$REPO_ROOT" ]] ||
    [[ "$(git rev-parse --show-toplevel)" != "$REPO_ROOT" ]]; then
    printf 'Canonical repository root mismatch.\n' >&2
    exit 78
fi

umask 077
exec timeout \
    --signal=TERM \
    --kill-after="${TERMINATION_GRACE_SECONDS}s" \
    "${WATCHDOG_SECONDS}s" \
    env PYTHONPATH="$REPO_ROOT:$REPO_ROOT/src:$REPO_ROOT/scripts" \
    "$REPO_ROOT/.venv/bin/python" \
    -m scripts.nlp_d5_live_semantic_qualification \
    "$runner_mode" \
    --population "$population" \
    --authorization-json "$authorization_path"
