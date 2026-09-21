"""Deterministic tests for the CM-56R2 planner-only diagnostic harness."""

from __future__ import annotations

import json

from scripts.cm56r2_planner_diagnostic import (
    VARIANTS,
    diagnostic_request,
    safe_plan_projection,
    source_summary,
)

from wellplot.agent.code_mode.planner import SectionTask, SemanticPlan


def _case() -> dict[str, object]:
    """Return a compact path-bearing source fixture for diagnostic tests."""
    return {
        "case_id": "diagnostic",
        "request": "Build a section from the secondary source.",
        "sources": [
            {
                "candidate_id": "secret-source-id",
                "filename": "/secret/well/main.dlis",
                "labels": ["secondary", "Main Pass"],
                "channels": [
                    {"mnemonic": "CBL", "kind": "scalar"},
                    {"mnemonic": "VDL", "kind": "array"},
                ],
            }
        ],
    }


def test_variants_are_fixed_factorial_conditions() -> None:
    """The diagnostic matrix changes only source-summary inclusion and temperature."""
    assert VARIANTS["A"].temperature == 1.0
    assert VARIANTS["A"].include_source_summary is False
    assert VARIANTS["B"].temperature == 0.0
    assert VARIANTS["B"].include_source_summary is False
    assert VARIANTS["C"].temperature == 1.0
    assert VARIANTS["C"].include_source_summary is True
    assert VARIANTS["D"].temperature == 0.0
    assert VARIANTS["D"].include_source_summary is True


def test_source_summary_is_bounded_and_path_free() -> None:
    """Experimental source context includes labels/channels but no host identity."""
    summary = source_summary(_case())
    text = json.dumps(summary, sort_keys=True)

    assert "secondary" in text
    assert "CBL" in text
    assert "VDL" in text
    assert "secret-source-id" not in text
    assert "/secret/well/main.dlis" not in text
    assert "filename" not in text
    assert "candidate_id" not in text


def test_source_summary_is_the_only_request_variant_delta() -> None:
    """A/B and C/D preserve the frozen request and add only bounded context."""
    case = _case()
    baseline = diagnostic_request(case, include_source_summary=False)
    enriched = diagnostic_request(case, include_source_summary=True)

    assert enriched.startswith(baseline)
    assert "Bounded source summary for planning only:" in enriched
    assert "secret-source-id" not in enriched
    assert "/secret/well/main.dlis" not in enriched


def test_safe_plan_projection_preserves_semantics_and_redacts_paths() -> None:
    """Planner evidence retains semantic fields without leaking host paths."""
    plan = SemanticPlan(
        summary="Build a section.",
        section_tasks=(
            SectionTask(
                goal="Use the secondary source.",
                capability_ids=("section.log_plot",),
                source_hints=("secondary source", "/secret/well/main.dlis"),
                requirements=("Use 0 to 150 and reverse direction.",),
            ),
        ),
    )
    projection = safe_plan_projection(plan)
    text = json.dumps(projection, sort_keys=True)

    assert projection["section_tasks"][0]["source_hints"] == [
        "secondary source",
        "[redacted-path]",
    ]
    assert "0 to 150" in text
    assert "/secret/well/main.dlis" not in text
