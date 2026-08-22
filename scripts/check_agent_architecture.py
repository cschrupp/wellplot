#!/usr/bin/env python3
"""Compare current architecture measurements with an L0 evaluation baseline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from scripts.agent_eval_support import collect_architecture_metrics, redact
except ModuleNotFoundError:
    from agent_eval_support import collect_architecture_metrics, redact  # type: ignore[no-redef]


REPO_ROOT = Path(__file__).resolve().parents[1]


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, help="L0 JSON evidence path.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--output", default=None, help="Write JSON evidence to this path.")
    parser.add_argument(
        "--max-agent-line-growth",
        type=int,
        default=None,
        help=(
            "Fail if total src/wellplot/agent Python LOC grows by more than this "
            "amount relative to the baseline. Use 0 during stabilization."
        ),
    )
    parser.add_argument(
        "--max-production-file-growth",
        type=int,
        default=None,
        help=(
            "Fail if any production file present in both baseline and current metrics "
            "grows by more than this many lines. Use 0 during stabilization."
        ),
    )
    return parser.parse_args(argv)


def _check_baseline(payload: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    architecture = payload.get("architecture")
    if not isinstance(architecture, dict):
        checks.append({"name": "baseline_architecture_present", "passed": False})
    else:
        checks.append({"name": "baseline_architecture_present", "passed": True})
    controls = payload.get("controls")
    control_results = (
        {
            item.get("name"): item.get("result", {}).get("status")
            for item in controls
            if isinstance(item, dict) and isinstance(item.get("result"), dict)
        }
        if isinstance(controls, list)
        else {}
    )
    checks.append(
        {
            "name": "correct_document_control_passes",
            "passed": control_results.get("correct_document_passes") == "passed",
        }
    )
    checks.append(
        {
            "name": "wrong_document_control_fails",
            "passed": control_results.get("wrong_document_fails") == "failed",
        }
    )
    tasks = payload.get("tasks")
    checks.append(
        {
            "name": "pending_tasks_are_explicit",
            "passed": isinstance(tasks, list)
            and all(isinstance(item, dict) and "status" in item for item in tasks),
        }
    )
    return checks


def main(argv: list[str] | None = None) -> int:
    """Validate the baseline and report current metric deltas."""
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    baseline_path = Path(args.baseline).resolve()
    repo_root = Path(args.repo_root).resolve()
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    current = collect_architecture_metrics(repo_root)
    checks = _check_baseline(baseline)
    baseline_architecture = baseline.get("architecture", {})
    deltas: dict[str, Any] = {}
    if isinstance(baseline_architecture, dict):
        for key in (
            "agent_python_lines",
            "mcp_tool_count",
            "generated_submit_symbol_count",
            "authoring_operation_schema_chars",
        ):
            old = baseline_architecture.get(key)
            new = current.get(key)
            if isinstance(old, (int, float)) and isinstance(new, (int, float)):
                deltas[key] = new - old

    if args.max_agent_line_growth is not None:
        growth = deltas.get("agent_python_lines")
        checks.append(
            {
                "name": "agent_python_line_budget",
                "passed": isinstance(growth, (int, float))
                and growth <= args.max_agent_line_growth,
                "actual_growth": growth,
                "allowed_growth": args.max_agent_line_growth,
            }
        )

    if args.max_production_file_growth is not None and isinstance(
        baseline_architecture, dict
    ):
        baseline_counts = baseline_architecture.get("production_line_counts")
        current_counts = current.get("production_line_counts")
        if isinstance(baseline_counts, dict) and isinstance(current_counts, dict):
            file_deltas = {
                path: current_counts[path] - old
                for path, old in baseline_counts.items()
                if isinstance(old, int)
                and isinstance(current_counts.get(path), int)
            }
            deltas["production_line_counts"] = file_deltas
            violating = {
                path: growth
                for path, growth in file_deltas.items()
                if growth > args.max_production_file_growth
            }
            checks.append(
                {
                    "name": "production_file_line_budget",
                    "passed": not violating,
                    "violations": violating,
                    "allowed_growth_per_file": args.max_production_file_growth,
                }
            )
    report = {
        "baseline": str(baseline_path),
        "current": current,
        "deltas_from_baseline": deltas,
        "checks": checks,
        "status": "passed" if all(item["passed"] for item in checks) else "failed",
    }
    serialized = json.dumps(redact(report), indent=2, sort_keys=True) + "\n"
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
