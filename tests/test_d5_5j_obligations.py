"""Provider-free contract tests for D5-5J request obligations."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from wellplot.agent.code_mode.canonical_workers import ReportSemanticResponse
from wellplot.agent.code_mode.obligations import (
    ObligationKind,
    OwnerKind,
    extract_supported_obligations,
    validate_report_obligations,
    validate_section_obligations,
    verify_obligation_spans,
)
from wellplot.agent.code_mode.planner import (
    PlannerSemanticError,
    SectionTask,
    SemanticPlan,
    _attach_request_obligations,
    _validate_extraction_coverage,
)


def test_obligations_use_exact_request_and_utf8_spans() -> None:
    """Extracted facts retain exact request identity and spans."""
    request = 'Rename the report "North Star". Track gamma: normal, width 30 mm.'
    obligations = extract_supported_obligations(request)

    assert obligations
    assert {item.owner_kind for item in obligations} == {OwnerKind.REPORT, OwnerKind.TRACK}
    assert {item.field for item in obligations} == {"title", "kind", "width_mm"}
    verify_obligation_spans(request, obligations)


def test_obligation_span_tampering_fails_closed() -> None:
    """Tampering with a provenance digest is rejected."""
    request = 'Rename the report "North Star".'
    obligation = extract_supported_obligations(request)[0]
    tampered = obligation.model_copy(update={"span_sha256": "0" * 64})

    with pytest.raises(ValueError, match="span digest"):
        verify_obligation_spans(request, (tampered,))


def test_repeated_numeric_values_keep_distinct_track_owners() -> None:
    """Equal numeric values remain associated with their distinct owners."""
    request = "Track gamma: normal, width 30 mm. Track delta: reference, width 30 mm."
    obligations = extract_supported_obligations(request)
    widths = [item for item in obligations if item.field == "width_mm"]

    assert [(item.owner_ref, item.value) for item in widths] == [
        ("gamma", 30.0),
        ("delta", 30.0),
    ]


def test_supported_obligation_vocabulary_is_closed() -> None:
    """Extraction does not create arbitrary JSON properties."""
    obligations = extract_supported_obligations("Use GR in Main Log.")

    assert all(
        item.kind in {ObligationKind.EXPLICIT_FIELD, ObligationKind.TARGET_REFERENCE}
        for item in obligations
    )
    assert not any(item.field == "arbitrary_json" for item in obligations)


def test_planner_coverage_rejects_dropped_explicit_width() -> None:
    """A typed obligation cannot certify a plan that dropped its width."""
    plan = SemanticPlan(
        summary="Add a track.",
        section_tasks=(
            SectionTask(
                goal="Add gamma.",
                capability_ids=("section.log_plot",),
                requirements=(),
            ),
        ),
    )
    attached = _attach_request_obligations(
        plan,
        "Add Track gamma: normal, width 30 mm.",
    )

    with pytest.raises(PlannerSemanticError, match="did not retain"):
        _validate_extraction_coverage(attached)


def test_worker_satisfaction_rejects_wrong_channel_and_accepts_exact_channel() -> None:
    """Worker validation checks the requested channel rather than inventory presence."""
    obligations = extract_supported_obligations("Use GR.")
    action = SimpleNamespace(
        tracks=(
            SimpleNamespace(
                bindings=(SimpleNamespace(channel="RT"),),
            ),
        )
    )
    with pytest.raises(ValueError, match="channel"):
        validate_section_obligations(action, obligations)

    valid_action = SimpleNamespace(
        tracks=(
            SimpleNamespace(
                bindings=(SimpleNamespace(channel="GR"),),
            ),
        )
    )
    validate_section_obligations(valid_action, obligations)


def test_report_schema_has_nonempty_mutation_alternatives() -> None:
    """The provider-facing report schema carries the non-empty response rule."""
    schema = ReportSemanticResponse.model_json_schema()
    assert any("anyOf" in constraint for constraint in schema.get("allOf", ()))


def test_report_obligation_requires_top_level_title() -> None:
    """A header slot cannot satisfy a report-owned title obligation."""
    obligation = extract_supported_obligations('Rename the report "North Star".')[0]
    with pytest.raises(ValueError, match="report title"):
        validate_report_obligations(SimpleNamespace(title=None), (obligation,))
    validate_report_obligations(SimpleNamespace(title="North Star"), (obligation,))
