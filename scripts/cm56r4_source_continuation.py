"""Run the missing CM-56R4 source-selection attempts only."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from scripts.cm56_typed_section_shadow import case_corpus_sha256, load_case_definitions
from scripts.cm56r4_planner_forensics import (
    CASE_CORPUS_SHA256,
    run_attempt,
)

CONTINUATION_ATTEMPTS = 7
CASE_ID = "source_selection"


async def run_continuation(args: argparse.Namespace) -> None:
    """Invoke the frozen forensic attempt for seven source cases."""
    if case_corpus_sha256() != CASE_CORPUS_SHA256:
        raise RuntimeError("CM-56 corpus hash changed from the frozen CM-56R4 baseline.")
    if args.output_jsonl.exists():
        raise FileExistsError(
            f"Refusing to append to existing continuation evidence: {args.output_jsonl}"
        )
    cases = [case for case in load_case_definitions() if case["case_id"] == CASE_ID]
    if len(cases) != 1:
        raise RuntimeError("CM-56 corpus must contain exactly one source_selection case.")
    case = cases[0]
    args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with args.output_jsonl.open("x", encoding="utf-8") as handle:
        for attempt_index in range(CONTINUATION_ATTEMPTS):
            row = await run_attempt(case, args=args, attempt_index=attempt_index)
            handle.write(json.dumps(row, sort_keys=True) + "\n")
            handle.flush()


def _parser() -> argparse.ArgumentParser:
    """Build the fixed-control continuation CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key-file")
    parser.add_argument("--api-key-env", default="OPENAI_COMPAT_API_KEY")
    parser.add_argument("--max-output-tokens", type=int, default=16384)
    parser.add_argument(
        "--max-tokens-parameter",
        choices=("max_tokens", "max_completion_tokens"),
        default="max_tokens",
    )
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--output-jsonl", type=Path, required=True)
    return parser


def main() -> None:
    """Run the fixed seven-attempt continuation."""
    asyncio.run(run_continuation(_parser().parse_args()))


if __name__ == "__main__":  # pragma: no cover
    main()
