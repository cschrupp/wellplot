"""Provider-free contract tests for D5-5J request obligations."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from wellplot.agent.code_mode.canonical_workers import ReportSemanticResponse
from wellplot.agent.code_mode.obligations import (
    ObligationKind,
    ObligationState,
    OwnerKind,
    extract_supported_obligations,
    validate_report_obligations,
    validate_section_obligations,
    verify_document_preservation,
    verify_obligation_spans,
    verify_worker_correction_scope,
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


def test_unicode_request_offsets_are_utf8_byte_offsets() -> None:
    """Offsets remain valid when multibyte text precedes an obligation."""
    request = 'Use the "Señal" report title and rename the report "North Star".'
    obligation = extract_supported_obligations(request)[0]

    assert obligation.start_byte > request.index("rename the report")
    verify_obligation_spans(request, (obligation,))


def test_paraphrased_add_track_extracts_only_supported_semantics() -> None:
    """Natural add-track wording produces typed facts without prose tokens."""
    request = (
        'In the Main Log section, add a new normal track titled "Caliper QC" '
        "with width 28 mm and plot the CALI curve with a linear scale from 6 to 12."
    )
    obligations = extract_supported_obligations(request)

    assert {(item.field, item.value) for item in obligations} >= {
        ("kind", "normal"),
        ("width_mm", 28.0),
        ("target", "Main Log"),
        ("channel", "CALI"),
        ("scale_kind", "linear"),
        ("scale_minimum", 6.0),
        ("scale_maximum", 12.0),
    }
    assert not {str(item.value).casefold() for item in obligations} & {
        "these",
        "the",
        "four",
        "a",
        "only",
    }


def test_negation_and_conflict_states_are_explicit() -> None:
    """Forbidden and contradictory facts cannot be silently treated as SET."""
    forbidden = extract_supported_obligations("Do not use GR.")
    assert forbidden[0].state is ObligationState.FORBIDDEN

    conflicting = extract_supported_obligations(
        "Track gamma: normal, width 30 mm. Track gamma: normal, width 32 mm."
    )
    assert {item.state for item in conflicting if item.field == "width_mm"} == {
        ObligationState.CONFLICTING
    }


def test_percentage_alpha_span_accepts_normalized_fraction() -> None:
    """Percentage request syntax remains valid after alpha normalization."""
    request = "Fill the track using #f2e8a0 at 20% opacity."
    obligations = extract_supported_obligations(request)
    alpha = next(item for item in obligations if item.field == "alpha")

    assert alpha.value == 0.2
    verify_obligation_spans(request, (alpha,))


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


def test_section_obligations_are_partitioned_by_target() -> None:
    """Request-owned facts are assigned to one matching section, not broadcast."""
    plan = SemanticPlan(
        summary="Update two sections.",
        section_tasks=(
            SectionTask(
                goal="Main Log GR",
                capability_ids=("section.log_plot",),
                requirements=("Main Log", "GR"),
            ),
            SectionTask(
                goal="Repeat Log CBL",
                capability_ids=("section.log_plot",),
                requirements=("Repeat Log", "CBL"),
            ),
        ),
    )
    attached = _attach_request_obligations(
        plan,
        "In the Main Log section, plot GR. In the Repeat Log section, plot CBL.",
    )

    assert [
        [item.value for item in task.obligations if item.field == "channel"]
        for task in attached.section_tasks
    ] == [["GR"], ["CBL"]]
    _validate_extraction_coverage(attached)


def test_targeted_channels_remain_bound_to_their_grounded_task() -> None:
    """Targeted channel facts are not broadcast to every section worker."""
    plan = SemanticPlan(
        summary="Update two tracks.",
        section_tasks=(
            SectionTask(
                goal="Main pass",
                capability_ids=("section.log_plot",),
                requirements=("cbl", "CBL"),
            ),
            SectionTask(
                goal="Repeat pass",
                capability_ids=("section.log_plot",),
                requirements=("vdl", "VDL"),
            ),
        ),
    )
    attached = _attach_request_obligations(
        plan,
        "On cbl: plot CBL. On vdl: plot VDL.",
    )

    assert [
        [item.value for item in task.obligations if item.field == "channel"]
        for task in attached.section_tasks
    ] == [["CBL"], ["VDL"]]


def test_final_document_preservation_rejects_unrelated_binding_mutation() -> None:
    """A valid requested track update cannot hide an unrelated binding change."""
    before = {
        "sections": [
            {
                "id": "main",
                "tracks": [
                    {"id": "gamma", "width_mm": 20, "bindings": [{"id": "g", "channel": "GR"}]},
                    {"id": "depth", "width_mm": 10, "bindings": [{"id": "d", "channel": "DEPTH"}]},
                ],
            }
        ]
    }
    after = {
        "sections": [
            {
                "id": "main",
                "tracks": [
                    {"id": "gamma", "width_mm": 30, "bindings": [{"id": "g", "channel": "GR"}]},
                    {"id": "depth", "width_mm": 10, "bindings": [{"id": "d", "channel": "BAD"}]},
                ],
            }
        ]
    }
    operation = SimpleNamespace(
        object_kind="track",
        object_id="gamma",
        action="update",
        payload={"patch": {"width_mm": 30}},
    )

    with pytest.raises(ValueError, match="authorized reconciliation envelope"):
        verify_document_preservation(before, after, (operation,))

    valid = {
        "sections": [
            {
                "id": "main",
                "tracks": [
                    {"id": "gamma", "width_mm": 30, "bindings": [{"id": "g", "channel": "GR"}]},
                    {"id": "depth", "width_mm": 10, "bindings": [{"id": "d", "channel": "DEPTH"}]},
                ],
            }
        ]
    }
    verify_document_preservation(before, valid, (operation,))


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


def test_worker_satisfaction_reads_nested_section_tracks() -> None:
    """Canonical reconstruction actions expose tracks under their section."""
    obligations = extract_supported_obligations("Use GR.")
    action = SimpleNamespace(
        section=SimpleNamespace(
            tracks=(
                SimpleNamespace(
                    bindings=(SimpleNamespace(channel="GR"),),
                ),
            )
        )
    )

    validate_section_obligations(action, obligations)


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


def test_correction_scope_rejects_unrelated_mutation() -> None:
    """A correction cannot change fields outside the violated obligation set."""
    before = SimpleNamespace(model_dump=lambda mode: {"width_mm": 30, "color": "blue"})
    after = SimpleNamespace(model_dump=lambda mode: {"width_mm": 32, "color": "red"})

    with pytest.raises(ValueError, match="unauthorized"):
        verify_worker_correction_scope(before, after, frozenset({"width_mm"}))
