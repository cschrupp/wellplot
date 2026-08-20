"""Tests for the L0 capability evaluation harness."""

from __future__ import annotations

import asyncio
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

    assert grade_document(correct_path, initial_task)["status"] == "passed"
    wrong_result = grade_document(wrong_path, initial_task)
    assert wrong_result["status"] == "failed"
    assert any("subtitle" in error for error in wrong_result["errors"])


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
    final_payload = dict(baseline_payload)
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


def test_pending_tasks_are_not_reported_as_success() -> None:
    """Unimplemented task rows remain explicit and cannot pass accidentally."""
    _, tasks = load_task_suite(TASK_SUITE)

    result = grade_document(None, tasks[2])

    assert result["status"] == "not_run"
    assert "pending" in result["reason"]


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
                project_dir=REPOSITORY_ROOT / "tmp-agent-eval-test",
                max_rounds=1,
            )
        )
