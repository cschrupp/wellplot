"""Tests for the post-CM-56R4 typed shadow gate wrapper."""

from __future__ import annotations

import asyncio
from pathlib import Path

from scripts.cm56_post_r4_typed_shadow import (
    PLANNER_TEMPERATURE,
    WORKER_TEMPERATURE,
    ProductionPlannerBoundary,
    _gate_decision,
    attempt_range,
    production_source_summary,
    summarize_jsonl,
)
from scripts.cm56_typed_section_shadow import load_case_definitions


def test_production_source_summary_matches_path_free_workflow_shape() -> None:
    """Planner input exposes labels and empty channel arrays only."""
    case = next(case for case in load_case_definitions() if case["case_id"] == "source_selection")
    summary = production_source_summary(case)

    assert summary == {
        "version": "cm56r3.source-summary.v1",
        "sources": [
            {"labels": ["primary"], "channels": []},
            {"labels": ["secondary"], "channels": []},
        ],
    }
    serialized = str(summary)
    assert "primary-source" not in serialized
    assert "scalar.las" not in serialized
    assert "/" not in serialized


def test_planner_boundary_forces_production_source_summary_and_temperature() -> None:
    """The wrapper prevents stale caller settings from changing the planner boundary."""
    calls: list[dict[str, object]] = []

    class FakePlanner:
        async def plan(self, **kwargs: object) -> str:
            calls.append(kwargs)
            return "plan"

    summary = {"version": "cm56r3.source-summary.v1", "sources": []}
    boundary = ProductionPlannerBoundary(FakePlanner(), summary)  # type: ignore[arg-type]
    result = asyncio.run(
        boundary.plan(
            request="request",
            mode="reconstruct",
            current_document_summary={},
            source_summary={"wrong": True},
            timeout_seconds=900.0,
            temperature=1.0,
            max_output_tokens=16384,
        )
    )

    assert result == "plan"
    assert calls[0]["source_summary"] == summary
    assert calls[0]["temperature"] == PLANNER_TEMPERATURE
    assert WORKER_TEMPERATURE == 1.0


def test_post_r4_attempt_ranges_are_frozen() -> None:
    """Stage one is three attempts and stage two completes the locked totals."""
    assert list(attempt_range("scalar_linear", "stage1")) == [0, 1, 2]
    assert list(attempt_range("cbl_continuity", "stage2")) == list(range(3, 10))
    assert list(attempt_range("scalar_linear", "stage2")) == [3, 4]


def test_gate_order_prioritizes_input_before_schema_and_worker_results() -> None:
    """Input loss remains the first typed-worker stop after planner/enrichment."""
    assert (
        _gate_decision(
            {"INPUT_INSUFFICIENT": 1, "SCHEMA_COMPATIBILITY_FAILURE": 1},
            planner_failures=0,
            enrichment_failures=0,
        )
        == "STOP_INPUT_CONTRACT"
    )
    assert (
        _gate_decision(
            {"SCHEMA_COMPATIBILITY_FAILURE": 1},
            planner_failures=0,
            enrichment_failures=0,
        )
        == "STOP_SCHEMA_COMPATIBILITY"
    )


def test_summary_reads_only_the_requested_stage(tmp_path: Path) -> None:
    """Stage-two summaries do not accidentally include stage-one rows."""
    path = tmp_path / "evidence.jsonl"
    path.write_text(
        '{"stage":"stage1","case_id":"a","classification":"SUCCESS"}\n'
        '{"stage":"stage2","case_id":"b","classification":"SUCCESS"}\n',
        encoding="utf-8",
    )

    summary = summarize_jsonl(path, stage="stage2")

    assert summary["top_level_attempts"] == 1
    assert summary["classification_counts"] == {"SUCCESS": 1}
