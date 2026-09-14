"""Tests for the L0 capability evaluation harness."""

from __future__ import annotations

import asyncio
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from scripts.agent_eval_matrix import aggregate_matrix, load_fixture_catalog
from scripts.agent_eval_support import (
    ENGINE_METRIC_FIELDS,
    NOT_AVAILABLE,
    canonical_diff,
    collect_architecture_metrics,
    grade_document,
    load_task_suite,
    normalize_engine_metrics,
    redact,
)
from scripts.run_agent_evals import (
    _control_document,
    _parse_args,
    _run_live,
    _write_control,
    main,
    run_deterministic_suite,
)

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


def test_engine_argument_defaults_to_v1_and_rejects_unknown_values() -> None:
    """The command line exposes only the two migration engines."""
    assert _parse_args([]).engine == "v1"
    assert _parse_args(["--engine", "v2"]).engine == "v2"

    with pytest.raises(SystemExit):
        _parse_args(["--engine", "v3"])


def test_engine_metrics_preserve_measured_zero_and_none() -> None:
    """Unavailable metrics remain distinct from a measured zero or recorded null."""
    metrics = normalize_engine_metrics({"program_calls": 0, "program_repairs": None})

    assert metrics["program_calls"] == 0
    assert metrics["program_repairs"] is None
    assert metrics["program_chars"] == NOT_AVAILABLE


def test_deterministic_engine_records_share_the_v1_v2_evidence_shape() -> None:
    """Engine-neutral grading emits every case with stable task-level metrics."""
    _, tasks = load_task_suite(TASK_SUITE)

    v1_report = run_deterministic_suite(tasks, engine="v1")
    v2_report = run_deterministic_suite(tasks, engine="v2")

    assert v1_report["engine"] == "v1"
    assert v2_report["engine"] == "v2"
    assert [task["task_id"] for task in v1_report["tasks"]] == [
        task["task_id"] for task in v2_report["tasks"]
    ]
    assert [task["fixture"] for task in v1_report["tasks"]] == [
        task["fixture"] for task in v2_report["tasks"]
    ]
    for report in (v1_report, v2_report):
        for task in report["tasks"]:
            assert task["engine"] == report["engine"]
            assert all(field_name in task["metrics"] for field_name in ENGINE_METRIC_FIELDS)
            assert all(
                task["metrics"][field_name] == NOT_AVAILABLE for field_name in ENGINE_METRIC_FIELDS
            )


def test_v2_live_stub_never_imports_or_constructs_the_legacy_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CM-03 v2 evidence cannot be legacy execution with a renamed label."""
    _, tasks = load_task_suite(TASK_SUITE)
    monkeypatch.delenv("WELLPLOT_RUN_LIVE_AGENT_EVALS", raising=False)
    monkeypatch.setitem(sys.modules, "wellplot.agent.notebook", object())

    results = asyncio.run(
        _run_live(
            tasks,
            repo_root=REPOSITORY_ROOT,
            provider="openai",
            model="unused-model",
            base_url="https://example.test/v1",
            api_key_file=None,
            source_logfile=None,
            initial_document=None,
            project_dir=REPOSITORY_ROOT / "tmp-agent-eval-test",
            max_rounds=1,
            engine="v2",
        )
    )

    assert len(results) == len(tasks)
    assert {result["status"] for result in results} == {"not_implemented"}
    assert {result["reason"] for result in results} == {
        "Code Mode execution is introduced in CM-10+."
    }
    assert [result["task_id"] for result in results] == [task.task_id for task in tasks]
    assert [result["fixture"] for result in results] == [
        task.initial_state["fixture"] for task in tasks
    ]
    for result in results:
        assert result["engine"] == "v2"
        assert all(
            result["metrics"][field_name] == NOT_AVAILABLE for field_name in ENGINE_METRIC_FIELDS
        )


def test_v2_live_cli_does_not_enter_the_legacy_live_adapter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CLI bypasses _run_live entirely until a v2 execution path exists."""
    output_path = tmp_path / "v2-evidence.json"

    def legacy_live_adapter(*args: object, **kwargs: object) -> None:
        raise AssertionError("v2 evidence must not enter the legacy live adapter")

    monkeypatch.setattr("scripts.run_agent_evals._run_live", legacy_live_adapter)

    assert (
        main(
            [
                "--mode",
                "live",
                "--engine",
                "v2",
                "--task",
                "initial_open_hole",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["engine"] == "v2"
    assert report["tasks"][0]["status"] == "not_implemented"


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


def test_fixture_catalog_resolves_paths_without_allowing_escape(tmp_path: Path) -> None:
    """Fixture paths are explicit and remain confined to the catalog root."""
    catalog_path = tmp_path / "catalog.json"
    fixture_root = tmp_path / "fixtures" / "open_hole"
    fixture_root.mkdir(parents=True)
    (fixture_root / "starter.log.yaml").write_text("starter", encoding="utf-8")
    catalog_path.write_text(
        '{"version": 1, "root": "fixtures", "fixtures": {'
        '"open_hole": {"starter_logfile": "starter.log.yaml"}}}',
        encoding="utf-8",
    )

    catalog = load_fixture_catalog(catalog_path, repo_root=tmp_path)

    fixture = catalog["open_hole"]
    assert fixture.starter_logfile == (fixture_root / "starter.log.yaml").resolve()
    assert fixture.missing_paths == ()


def test_fixture_catalog_reports_missing_artifacts(tmp_path: Path) -> None:
    """A clean checkout never silently substitutes a notebook draft."""
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(
        '{"version": 1, "root": "fixtures", "fixtures": {'
        '"open_hole": {"initial_document": "draft.log.yaml"}}}',
        encoding="utf-8",
    )

    fixture = load_fixture_catalog(catalog_path, repo_root=tmp_path)["open_hole"]

    assert fixture.missing_paths
    assert fixture.initial_document is not None
    assert fixture.initial_document.name == "draft.log.yaml"


def test_missing_live_fixture_is_not_reported_as_a_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live evaluation stops before provider creation when the fixture is absent."""
    _, tasks = load_task_suite(TASK_SUITE)
    task = tasks[0]
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(
        '{"version": 1, "root": "fixtures", "fixtures": {'
        '"open_hole_clean_starter": {"starter_logfile": "starter.log.yaml", '
        '"baseline_document": "baseline.log.yaml"}}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("WELLPLOT_RUN_LIVE_AGENT_EVALS", "1")

    results = asyncio.run(
        _run_live(
            (task,),
            repo_root=tmp_path,
            provider="openai",
            model=None,
            base_url=None,
            api_key_file=None,
            source_logfile=None,
            initial_document=None,
            fixture_catalog=catalog_path,
            project_dir=tmp_path / "project",
            max_rounds=1,
        )
    )

    assert results[0]["status"] == "not_run"
    assert "fixture directory is missing" in results[0]["reason"]
    assert results[0]["engine"] == "v1"
    assert all(
        results[0]["metrics"][field_name] == NOT_AVAILABLE for field_name in ENGINE_METRIC_FIELDS
    )


def test_matrix_aggregation_reports_pass_at_one_and_failure_category() -> None:
    """Matrix summaries preserve provider/task status and classify failures."""
    report = aggregate_matrix(
        [
            {
                "provider": "nvidia_cloud",
                "model": "model-a",
                "tasks": [
                    {"task_id": "remarks_only", "status": "passed"},
                    {
                        "task_id": "resistivity_track",
                        "status": "failed",
                        "errors": ["schema validation failed"],
                    },
                ],
            },
            {
                "provider": "unsloth",
                "model": "model-b",
                "tasks": [{"task_id": "remarks_only", "status": "not_run", "reason": "no key"}],
            },
        ]
    )

    assert report["providers"]["nvidia_cloud"]["pass_at_1"] == 0.5
    assert report["providers"]["unsloth"]["pass_at_1"] is None
    assert report["failure_categories"] == {"contract/schema": 1}
    assert report["not_run_cases"] == 1


def test_matrix_pairs_v1_and_v2_without_counting_not_implemented_as_failure() -> None:
    """Historical v1 evidence can pair with a CM-03 v2 placeholder incrementally."""
    report = aggregate_matrix(
        [
            {
                "provider": "openai",
                "model": "model-a",
                "tasks": [
                    {
                        "task_id": "initial_open_hole",
                        "fixture": "open_hole_clean_starter",
                        "status": "passed",
                        "metrics": {"program_calls": 0},
                    }
                ],
            },
            {
                "engine": "v2",
                "provider": "openai",
                "model": "model-a",
                "tasks": [
                    {
                        "task_id": "initial_open_hole",
                        "fixture": "open_hole_clean_starter",
                        "engine": "v2",
                        "status": "not_implemented",
                        "reason": "Code Mode execution is introduced in CM-10+.",
                        "metrics": dict.fromkeys(ENGINE_METRIC_FIELDS, NOT_AVAILABLE),
                    }
                ],
            },
        ]
    )

    assert report["providers"]["openai"] == {
        "passed": 1,
        "failed": 0,
        "not_run": 0,
        "not_implemented": 1,
        "eligible_cases": 1,
        "pass_at_1": 1.0,
    }
    assert report["engines"]["v1"]["pass_at_1"] == 1.0
    assert report["engines"]["v2"] == {
        "passed": 0,
        "failed": 0,
        "not_run": 0,
        "not_implemented": 1,
        "eligible_cases": 0,
        "pass_at_1": None,
    }
    comparison = report["comparisons"]
    assert len(comparison) == 1
    assert comparison[0]["v1"]["status"] == "passed"
    assert comparison[0]["v1"]["metrics"]["program_calls"] == 0
    assert comparison[0]["v2"]["status"] == "not_implemented"
    assert comparison[0]["v2"]["metrics"]["program_chars"] == NOT_AVAILABLE

    one_sided = aggregate_matrix(
        [
            {
                "provider": "openai",
                "model": "model-a",
                "tasks": [
                    {
                        "task_id": "initial_open_hole",
                        "fixture": "open_hole_clean_starter",
                        "status": "passed",
                    }
                ],
            }
        ]
    )
    assert one_sided["comparisons"][0]["v1"]["status"] == "passed"
    assert one_sided["comparisons"][0]["v2"] is None
