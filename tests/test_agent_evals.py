"""Tests for the L0 capability evaluation harness."""

from __future__ import annotations

import asyncio
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from scripts.agent_eval_support import (
    canonical_diff,
    collect_architecture_metrics,
    grade_document,
    load_task_suite,
    redact,
)
from scripts.run_agent_evals import _control_document, _run_live, _write_control

from wellplot.authoring import authoring_document_from_mapping, authoring_document_to_yaml

REPOSITORY_ROOT = Path(__file__).parents[1]
TASK_SUITE = REPOSITORY_ROOT / "tests" / "evals" / "agent_tasks.json"


def _write_document(path: Path, payload: dict[str, object]) -> None:
    document = authoring_document_from_mapping(payload)
    authoring_document_to_yaml(document, path)


def test_correct_and_wrong_documents_are_graded_by_end_state(tmp_path: Path) -> None:
    """A claimed successful run cannot pass when its persisted document is wrong."""
    _, tasks = load_task_suite(TASK_SUITE)
    initial_task = tasks[0]
    correct_path = tmp_path / "correct.log.yaml"
    wrong_path = tmp_path / "wrong.log.yaml"
    _write_control(correct_path, correct=True)
    _write_control(wrong_path, correct=False)

    assert (
        grade_document(correct_path, initial_task, baseline_path=correct_path)["status"] == "passed"
    )
    wrong_result = grade_document(wrong_path, initial_task, baseline_path=wrong_path)
    assert wrong_result["status"] == "failed"
    assert any("Interactive LAS tutorial draft" in error for error in wrong_result["errors"])


def test_document_cannot_pass_without_a_baseline(tmp_path: Path) -> None:
    """Initial-state and isolation checks are mandatory for a final grade."""
    _, tasks = load_task_suite(TASK_SUITE)
    path = tmp_path / "correct.log.yaml"
    _write_control(path, correct=True)

    result = grade_document(path, tasks[0])

    assert result["status"] == "failed"
    assert any("baseline document is required" in error for error in result["errors"])


def test_canonical_diff_is_independent_of_mapping_order() -> None:
    """Equivalent canonical objects do not produce a false change."""
    before = {"b": 2, "nested": {"x": 1, "y": [1, 2]}}
    after = {"nested": {"y": [1, 2], "x": 1}, "b": 2}

    assert canonical_diff(before, after) == []


def test_remarks_grader_checks_content_and_isolation(tmp_path: Path) -> None:
    """The remarks task checks the saved text and rejects unrelated mutations."""
    _, tasks = load_task_suite(TASK_SUITE)
    remarks_task = tasks[1]
    baseline_path = tmp_path / "baseline.log.yaml"
    final_path = tmp_path / "final.log.yaml"
    baseline_payload = _control_document(correct=True)
    _write_document(baseline_path, baseline_payload)
    final_payload = copy.deepcopy(baseline_payload)
    final_payload["remarks"] = [
        {
            "remark_id": "remark-1",
            "text": (
                "Open-hole quicklook built from a user-supplied LAS file. "
                "Only channels confirmed through source inspection should be plotted. "
                "This is an iterative interpretation artifact."
            ),
        }
    ]
    _write_document(final_path, final_payload)

    result = grade_document(final_path, remarks_task, baseline_path=baseline_path)

    assert result["status"] == "passed"


def test_every_development_task_has_a_complete_deterministic_contract() -> None:
    """The provider matrix cannot run a task that lacks executable semantics."""
    _, tasks = load_task_suite(TASK_SUITE)

    assert len(tasks) == 12
    assert all(task.status == "active" for task in tasks)
    assert all(task.initial_state["fixture"] for task in tasks)
    assert all(task.initial_state["preconditions"] for task in tasks)
    assert all(task.expected for task in tasks)
    assert all(task.prohibited_change_paths for task in tasks)


def test_resistivity_grader_matches_bindings_by_semantic_identity(tmp_path: Path) -> None:
    """Track verification does not depend on list positions or provider binding ids."""
    _, tasks = load_task_suite(TASK_SUITE)
    resistivity_task = next(task for task in tasks if task.task_id == "resistivity_track")
    baseline_path = tmp_path / "baseline.log.yaml"
    final_path = tmp_path / "final.log.yaml"
    baseline_payload = _control_document(correct=True)
    _write_document(baseline_path, baseline_payload)
    final_payload = copy.deepcopy(baseline_payload)
    final_payload["sections"][0]["tracks"].append(
        {
            "id": "resistivity",
            "title": "Resistivity",
            "kind": "normal",
            "width_mm": 28,
            "x_scale": {"kind": "log", "minimum": 0.2, "maximum": 2000.0},
            "bindings": [
                {
                    "binding_id": "provider-chosen-deep-id",
                    "channel": "ILD",
                    "scale": {"kind": "log", "minimum": 0.2, "maximum": 2000.0},
                    "style": {"line_width": 1.2},
                },
                {
                    "binding_id": "provider-chosen-medium-id",
                    "channel": "ILM",
                    "scale": {"kind": "log", "minimum": 0.2, "maximum": 2000.0},
                },
                {
                    "binding_id": "provider-chosen-shallow-id",
                    "channel": "MSFL",
                    "scale": {"kind": "log", "minimum": 0.2, "maximum": 2000.0},
                },
            ],
        }
    )
    _write_document(final_path, final_payload)

    result = grade_document(final_path, resistivity_task, baseline_path=baseline_path)

    assert result["status"] == "passed"


def test_isolation_check_rejects_an_unrelated_mutation(tmp_path: Path) -> None:
    """A correct requested remark cannot hide a changed section title."""
    _, tasks = load_task_suite(TASK_SUITE)
    remarks_task = next(task for task in tasks if task.task_id == "remarks_only")
    baseline_path = tmp_path / "baseline.log.yaml"
    final_path = tmp_path / "final.log.yaml"
    baseline_payload = _control_document(correct=True)
    _write_document(baseline_path, baseline_payload)
    final_payload = copy.deepcopy(baseline_payload)
    final_payload["remarks"] = [
        {
            "text": (
                "Open-hole quicklook built from a user-supplied LAS file. "
                "Only channels confirmed through source inspection should be plotted. "
                "This is an iterative interpretation artifact."
            )
        }
    ]
    final_payload["sections"][0]["title"] = "Unexpected mutation"
    _write_document(final_path, final_payload)

    result = grade_document(final_path, remarks_task, baseline_path=baseline_path)

    assert result["status"] == "failed"
    assert any("prohibited unrelated mutation" in error for error in result["errors"])


def test_rejection_task_requires_clarification_without_a_mutation(tmp_path: Path) -> None:
    """Expected rejections grade both the saved state and result outcome."""
    _, tasks = load_task_suite(TASK_SUITE)
    rejection_task = next(
        task for task in tasks if task.task_id == "reject_ambiguous_unavailable_requests"
    )
    baseline_path = tmp_path / "baseline.log.yaml"
    _write_document(baseline_path, _control_document(correct=True))

    result = grade_document(
        baseline_path,
        rejection_task,
        baseline_path=baseline_path,
        outcome={"needs_clarification": True, "has_persisted_mutation": False},
    )

    assert result["status"] == "passed"


def test_redaction_removes_credentials_from_nested_evidence() -> None:
    """Evaluation evidence never exposes credential-like values."""
    value = {
        "api_key": "secret-value",
        "nested": {"authorization": "Bearer secret-value"},
        "url": "https://example.test/v1?token=secret-value",
    }

    redacted = redact(value)

    assert "secret-value" not in str(redacted)
    assert redacted["api_key"] == "<redacted>"
    assert "<redacted>" in redacted["url"]


def test_architecture_metrics_have_required_l0_measurements() -> None:
    """The baseline records the architecture dimensions named by the plan."""
    metrics = collect_architecture_metrics(REPOSITORY_ROOT)

    assert metrics["agent_python_lines"] > 0
    assert metrics["mcp_tool_count"] > 0
    assert metrics["generated_submit_symbol_count"] > 0
    assert metrics["authoring_operation_schema_chars"] > 0


def test_live_mode_requires_explicit_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    """The live runner cannot contact a provider by accident."""
    monkeypatch.delenv("WELLPLOT_RUN_LIVE_AGENT_EVALS", raising=False)

    with pytest.raises(RuntimeError, match="WELLPLOT_RUN_LIVE_AGENT_EVALS=1"):
        asyncio.run(
            _run_live(
                (),
                repo_root=REPOSITORY_ROOT,
                provider="openai",
                model=None,
                base_url=None,
                api_key_file=None,
                source_logfile=None,
                initial_document=None,
                project_dir=REPOSITORY_ROOT / "tmp-agent-eval-test",
                max_rounds=1,
            )
        )


def test_live_mode_rejects_mixed_fixture_groups(monkeypatch: pytest.MonkeyPatch) -> None:
    """A provider run cannot accidentally chain unrelated starter states."""
    _, tasks = load_task_suite(TASK_SUITE)
    monkeypatch.setenv("WELLPLOT_RUN_LIVE_AGENT_EVALS", "1")

    with pytest.raises(RuntimeError, match="one initial-state fixture"):
        asyncio.run(
            _run_live(
                tasks,
                repo_root=REPOSITORY_ROOT,
                provider="openai",
                model=None,
                base_url=None,
                api_key_file=None,
                source_logfile=None,
                initial_document=None,
                project_dir=REPOSITORY_ROOT / "tmp-agent-eval-test",
                max_rounds=1,
            )
        )
