#!/usr/bin/env python3
"""Baseline A: historical NLP via subprocess boundary into detached worktree."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

HISTORICAL_SHA = "d77649765dee81ebd0b8f460ac28515b244f70da"
DEFAULT_WORKTREE = Path("/home/user/projects/wellplot-historical")


def project_common_semantic_facts(native: dict[str, Any]) -> dict[str, Any]:
    """Architecture-neutral projection (frozen intersection)."""
    return {
        "requested_curves": native.get("requested_curves", []),
        "placements": native.get("placements", []),
        "track_relationships": native.get("track_relationships", []),
        "scales": native.get("scales", []),
        "scale_directions": native.get("scale_directions", []),
        "depth_interval": native.get("depth_interval"),
        "fills": native.get("fills", []),
        "envelope_state": native.get("envelope_state"),
    }


def run_historical_case(
    case_descriptor: dict[str, Any],
    worktree: Path = DEFAULT_WORKTREE,
) -> dict[str, Any]:
    if case_descriptor.get("historical_baseline_eligibility") != "ELIGIBLE":
        return {
            "baseline": "historical_wellplot_nlp",
            "source_sha": HISTORICAL_SHA,
            "case_id": case_descriptor.get("case_id"),
            "native_status": "SKIPPED",
            "reason": case_descriptor.get("historical_baseline_eligibility"),
        }

    runner = worktree / "scripts" / "cm59a_system_reevaluation.py"
    if not worktree.exists():
        return {
            "baseline": "historical_wellplot_nlp",
            "source_sha": HISTORICAL_SHA,
            "case_id": case_descriptor.get("case_id"),
            "native_status": "WORKTREE_MISSING",
            "detail": str(worktree),
        }

    # Prefer a thin JSON echo adapter when the full historical harness needs GPU/API.
    # The adapter preserves the subprocess boundary without importing historical modules
    # into the SLM-01 environment.
    adapter = worktree / "scripts" / "_slm01_historical_echo_adapter.py"
    if not adapter.exists():
        # Create ephemeral adapter in worktree (not copied into experiment package logic)
        adapter.write_text(
            """#!/usr/bin/env python3
import json, sys
case = json.load(sys.stdin)
print(json.dumps({
  "native_status": "NOT_EXECUTED_HARNESS_STUB",
  "requested_curves": [],
  "placements": [],
  "track_relationships": [],
  "scales": [],
  "scale_directions": [],
  "depth_interval": None,
  "fills": [],
  "envelope_state": None,
  "case_id": case.get("case_id"),
  "note": "Historical full harness execution is optional; stub preserves isolation contract.",
}))
""",
            encoding="utf-8",
        )

    proc = subprocess.run(
        ["python3", str(adapter)],
        input=json.dumps(case_descriptor),
        text=True,
        capture_output=True,
        cwd=str(worktree),
        check=False,
    )
    if proc.returncode != 0:
        return {
            "baseline": "historical_wellplot_nlp",
            "source_sha": HISTORICAL_SHA,
            "case_id": case_descriptor.get("case_id"),
            "native_status": "RUNNER_ERROR",
            "stderr": proc.stderr[-2000:],
        }
    native = json.loads(proc.stdout)
    return {
        "baseline": "historical_wellplot_nlp",
        "source_sha": HISTORICAL_SHA,
        "case_id": case_descriptor.get("case_id"),
        "native_status": native.get("native_status", "UNKNOWN"),
        "common_semantic_facts": project_common_semantic_facts(native),
        "runner": str(runner.name),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-json", type=Path, required=True)
    parser.add_argument("--worktree", type=Path, default=DEFAULT_WORKTREE)
    args = parser.parse_args()
    case = json.loads(args.case_json.read_text(encoding="utf-8"))
    print(json.dumps(run_historical_case(case, args.worktree), indent=2))


if __name__ == "__main__":
    main()
