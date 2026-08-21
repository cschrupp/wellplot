#!/usr/bin/env python3
"""Run data-driven MCP/agent capability evaluations.

The default modes never contact a provider. Live execution requires the
explicit WELLPLOT_RUN_LIVE_AGENT_EVALS=1 opt-in.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from wellplot.authoring import (
    authoring_document_from_mapping,
    authoring_document_to_yaml,
    load_authoring_document,
)

try:
    from scripts.agent_eval_support import (
        EvalTask,
        collect_architecture_metrics,
        grade_document,
        load_task_suite,
        redact,
    )
except ModuleNotFoundError:
    from agent_eval_support import (  # type: ignore[no-redef]
        EvalTask,
        collect_architecture_metrics,
        grade_document,
        load_task_suite,
        redact,
    )


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUITE = REPO_ROOT / "tests" / "evals" / "agent_tasks.json"


def _control_document(*, correct: bool) -> dict[str, Any]:
    """Return a tiny canonical document for positive and negative controls."""
    return {
        "name": "agent-eval-control",
        "title": "Control",
        "header": {
            "service_titles": [
                {
                    "slot_id": "service_title.1",
                    "value": {"value": "Open Hole Quicklook"},
                }
            ],
            "detail": {
                "kind": "open_hole",
                "rows": [
                    {
                        "row_id": "rm_measured_temp",
                        "key": "rm_measured_temp",
                        "label": "RM @ Measured Temp",
                        "values": [
                            {
                                "slot_id": "rm_measured_temp.value",
                                "value": {"value": ""},
                            }
                        ],
                    }
                ],
            },
        },
        "sections": [
            {
                "id": "main",
                "title": "Main",
                "subtitle": "Interactive LAS tutorial draft" if correct else "Wrong result",
                "tracks": [
                    {
                        "id": "gr_sp",
                        "title": "GR/SP",
                        "kind": "normal",
                        "width_mm": 30,
                        "bindings": [],
                    },
                    {
                        "id": "depth",
                        "title": "Depth",
                        "kind": "reference",
                        "width_mm": 12,
                        "bindings": [],
                    },
                ],
            }
        ],
        "remarks": [],
    }


def _write_control(path: Path, *, correct: bool) -> None:
    document = authoring_document_from_mapping(_control_document(correct=correct))
    authoring_document_to_yaml(document, path)


def run_deterministic_suite(
    tasks: tuple[EvalTask, ...],
    *,
    document: Path | None = None,
    baseline: Path | None = None,
) -> dict[str, Any]:
    """Run local grading controls and optionally grade a supplied document."""
    with tempfile.TemporaryDirectory(prefix="wellplot-agent-eval-") as temporary_dir:
        control_dir = Path(temporary_dir)
        correct_path = control_dir / "correct.log.yaml"
        wrong_path = control_dir / "wrong.log.yaml"
        _write_control(correct_path, correct=True)
        _write_control(wrong_path, correct=False)
        initial_task = next(
            (task for task in tasks if task.task_id == "initial_open_hole"),
            None,
        )
        controls: list[dict[str, Any]] = []
        if initial_task is not None:
            correct_result = grade_document(
                correct_path,
                initial_task,
                baseline_path=correct_path,
            )
            correct_result["canonical_document"] = "<temporary-control-correct>"
            wrong_result = grade_document(
                wrong_path,
                initial_task,
                baseline_path=wrong_path,
            )
            wrong_result["canonical_document"] = "<temporary-control-wrong>"
            controls.append(
                {
                    "name": "correct_document_passes",
                    "result": correct_result,
                }
            )
            controls.append(
                {
                    "name": "wrong_document_fails",
                    "result": wrong_result,
                }
            )
        task_results = [grade_document(document, task, baseline_path=baseline) for task in tasks]
    return {
        "mode": "deterministic",
        "controls": controls,
        "tasks": task_results,
        "live_execution": False,
    }


def _credential_from_file(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if value:
            return value
    return None


def _result_metrics(result: object, elapsed_seconds: float) -> dict[str, Any]:
    """Extract non-sensitive metrics from one AuthoringResult."""
    report_facts_value = getattr(result, "report_facts", {})
    report_facts = report_facts_value if isinstance(report_facts_value, dict) else {}
    tool_trace = getattr(result, "tool_trace", ())
    return {
        "latency_ms": round(elapsed_seconds * 1000, 2),
        "tool_trace_count": len(tool_trace),
        "tool_trace": [item.name for item in tool_trace],
        "rounds": report_facts.get("rounds", report_facts.get("provider_rounds")),
        "context_chars": report_facts.get("context_chars"),
        "prompt_chars": report_facts.get("prompt_chars"),
        "token_usage": redact(report_facts.get("token_usage")),
    }


def _result_outcome(result: object, *, has_persisted_mutation: bool) -> dict[str, Any]:
    """Normalize result fields used by task-level rejection assertions."""
    return {
        "needs_clarification": bool(getattr(result, "needs_clarification", ())),
        "has_persisted_mutation": has_persisted_mutation,
    }


def _task_fixture_name(task: EvalTask) -> str:
    """Return the fixture declared by one already-validated task."""
    return str(task.initial_state["fixture"])


async def _run_live(
    tasks: tuple[EvalTask, ...],
    *,
    repo_root: Path,
    provider: str,
    model: str | None,
    base_url: str | None,
    api_key_file: Path | None,
    source_logfile: Path | None,
    initial_document: Path | None,
    project_dir: Path,
    max_rounds: int,
) -> list[dict[str, Any]]:
    if os.getenv("WELLPLOT_RUN_LIVE_AGENT_EVALS") != "1":
        raise RuntimeError(
            "Live evaluation is disabled. Set WELLPLOT_RUN_LIVE_AGENT_EVALS=1 explicitly."
        )
    fixture_names = {_task_fixture_name(task) for task in tasks if task.status == "active"}
    if len(fixture_names) > 1:
        raise RuntimeError(
            "Live evaluation accepts tasks from one initial-state fixture per invocation. "
            "Select one fixture group with --task."
        )
    if initial_document is not None and not initial_document.exists():
        raise RuntimeError(f"Initial document does not exist: {initial_document}")
    from wellplot.agent.notebook import create_project_session

    api_key = _credential_from_file(api_key_file)
    session, _ = create_project_session(
        server_root=repo_root,
        project_dir=project_dir,
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
        timeout=float(os.getenv("WELLPLOT_AGENT_TIMEOUT", "1800")),
        run_max_rounds=max_rounds,
        revise_max_rounds=max_rounds,
    )
    output_logfile = project_dir / "agent_l0_draft.log.yaml"
    current_document = initial_document
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="wellplot-agent-eval-baselines-") as temporary_dir:
        baseline_dir = Path(temporary_dir)
        for task in tasks:
            if task.status != "active":
                results.append(
                    {
                        "task_id": task.task_id,
                        "status": "not_run",
                        "reason": f"task is marked {task.status}",
                    }
                )
                continue
            if task.kind == "run":
                if source_logfile is None:
                    results.append(
                        {
                            "task_id": task.task_id,
                            "status": "not_run",
                            "reason": "live run requires --source-logfile",
                        }
                    )
                    continue
                baseline_source = source_logfile
            elif current_document is None:
                results.append(
                    {
                        "task_id": task.task_id,
                        "status": "not_run",
                        "reason": "live revision requires --initial-document or a preceding run",
                    }
                )
                continue
            else:
                baseline_source = current_document

            baseline_path = baseline_dir / f"{task.task_id}.baseline.log.yaml"
            shutil.copy2(baseline_source, baseline_path)
            baseline_payload = load_authoring_document(baseline_path).model_dump(mode="json")
            started = time.perf_counter()
            try:
                if task.kind == "run":
                    result = await session.run(
                        goal=task.goal or "",
                        output_logfile=output_logfile,
                        source_logfile_path=source_logfile,
                        max_rounds=max_rounds,
                    )
                else:
                    result = await session.revise(
                        feedback=task.feedback or "",
                        logfile_path=current_document,
                        max_rounds=max_rounds,
                    )
            except Exception as exc:  # noqa: BLE001 - evidence records provider failures.
                results.append(
                    redact(
                        {
                            "task_id": task.task_id,
                            "status": "failed",
                            "errors": [str(exc)],
                            "metrics": {
                                "latency_ms": round((time.perf_counter() - started) * 1000, 2)
                            },
                        }
                    )
                )
                continue
            current_document = result.draft_path
            final_payload = load_authoring_document(current_document).model_dump(mode="json")
            graded = grade_document(
                current_document,
                task,
                baseline_path=baseline_path,
                outcome=_result_outcome(
                    result,
                    has_persisted_mutation=baseline_payload != final_payload,
                ),
            )
            graded["fixture"] = _task_fixture_name(task)
            graded["metrics"] = _result_metrics(result, time.perf_counter() - started)
            graded["provider"] = provider
            graded["model"] = model
            results.append(redact(graded))
    return results


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", default=str(DEFAULT_SUITE), help="JSON evaluation suite path.")
    parser.add_argument(
        "--mode",
        choices=("deterministic", "adapter", "live"),
        default="deterministic",
        help="Evaluation mode; only live can contact a provider.",
    )
    parser.add_argument("--provider", default="openai", help="Provider name for live mode.")
    parser.add_argument("--model", default=None, help="Optional provider model override.")
    parser.add_argument("--base-url", default=None, help="Optional OpenAI-compatible endpoint.")
    parser.add_argument(
        "--api-key-file",
        default=None,
        help="Ignored credential file for live mode.",
    )
    parser.add_argument(
        "--source-logfile",
        default=None,
        help="Clean starter logfile for live mode.",
    )
    parser.add_argument(
        "--initial-document",
        default=None,
        help="Clean canonical draft used as the baseline for live revision tasks.",
    )
    parser.add_argument(
        "--task",
        action="append",
        default=[],
        help="Run one or more task ids from a single initial-state fixture.",
    )
    parser.add_argument("--project-dir", default=None, help="Live evaluation project directory.")
    parser.add_argument("--document", default=None, help="Persisted document to grade.")
    parser.add_argument(
        "--baseline-document",
        default=None,
        help="Baseline document for isolation checks.",
    )
    parser.add_argument("--max-rounds", type=int, default=12)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--output", default=None, help="Write JSON evidence to this path.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the requested evaluation mode and emit redacted JSON evidence."""
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    repo_root = Path(args.repo_root).resolve()
    suite_path = Path(args.suite)
    if args.suite == "development":
        suite_path = repo_root / "tests" / "evals" / "agent_tasks.json"
    elif not suite_path.exists():
        suite_path = repo_root / "tests" / "evals" / f"{args.suite}.json"
    suite_name, tasks = load_task_suite(suite_path)
    if args.task:
        requested_task_ids = set(args.task)
        available_task_ids = {task.task_id for task in tasks}
        unknown_task_ids = sorted(requested_task_ids - available_task_ids)
        if unknown_task_ids:
            raise ValueError(f"Unknown evaluation task ids: {unknown_task_ids}")
        tasks = tuple(task for task in tasks if task.task_id in requested_task_ids)
    document = Path(args.document).resolve() if args.document else None
    baseline = Path(args.baseline_document).resolve() if args.baseline_document else None
    if args.mode in {"deterministic", "adapter"}:
        report = run_deterministic_suite(tasks, document=document, baseline=baseline)
        report["mode"] = args.mode
    else:
        project_dir = (
            Path(args.project_dir).resolve()
            if args.project_dir
            else repo_root / "workspace" / "evaluations" / "agent_l0"
        )
        live_results = asyncio.run(
            _run_live(
                tasks,
                repo_root=repo_root,
                provider=args.provider,
                model=args.model,
                base_url=args.base_url,
                api_key_file=Path(args.api_key_file) if args.api_key_file else None,
                source_logfile=Path(args.source_logfile).resolve() if args.source_logfile else None,
                initial_document=(
                    Path(args.initial_document).resolve() if args.initial_document else None
                ),
                project_dir=project_dir,
                max_rounds=args.max_rounds,
            )
        )
        report = {
            "mode": "live",
            "live_execution": True,
            "provider": args.provider,
            "model": args.model,
            "tasks": live_results,
        }
    report.update(
        {
            "suite": suite_name,
            "suite_path": str(suite_path.resolve()),
            "architecture": collect_architecture_metrics(repo_root),
        }
    )
    serialized = json.dumps(redact(report), indent=2, sort_keys=True) + "\n"
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
