"""Provider-free contract tests for D5-5J request obligations."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from wellplot.agent.code_mode.canonical_workers import ReportSemanticResponse
from wellplot.agent.code_mode.enrichment import (
    ExistingCurveContext,
    ResolvedSectionContext,
    SourceContext,
)
from wellplot.agent.code_mode.obligations import (
    ObligationKind,
    ObligationState,
    OwnerKind,
    RepairOperation,
    compile_request_contract,
    extract_supported_anchors,
    extract_supported_obligations,
    validate_report_obligations,
    validate_section_obligations,
    verify_anchor_coverage,
    verify_document_obligations,
    verify_document_preservation,
    verify_lowered_existing_curve_obligations,
    verify_obligation_spans,
    verify_worker_correction_scope,
)
from wellplot.agent.code_mode.planner import (
    PlannerSemanticError,
    SectionTask,
    SemanticPlan,
    _attach_compiled_requirements,
    _attach_request_obligations,
    _validate_extraction_coverage,
)
from wellplot.agent.code_mode.section_semantics import SemanticScale
from wellplot.agent.code_mode.semantic_actions import (
    ExistingCurveSelector,
    SemanticActionError,
    UpdateCurveScaleAction,
)
from wellplot.model import AuthoringDocumentSpec
from wellplot.model.intent import AuthoringCurveBindingIntent, AuthoringDocumentIntent


@pytest.mark.parametrize("operation", ["REMOVE", "MOVE"])
def test_repair_operation_rejects_unsupported_remove_and_move(operation: str) -> None:
    """The bounded repair schema cannot authorize deletion or reordering."""
    with pytest.raises(ValueError):
        RepairOperation.model_validate(
            {
                "requirement_id": "requirement-1",
                "path_prefix": "section.tracks[combo]",
                "operation": operation,
                "owner_kind": "track",
                "owner_ref": "combo",
            }
        )


def test_obligations_use_exact_request_and_utf8_spans() -> None:
    """Extracted facts retain exact request identity and spans."""
    request = 'Rename the report "North Star". Track gamma: normal, width 30 mm.'
    obligations = extract_supported_obligations(request)

    assert obligations
    assert {item.owner_kind for item in obligations} == {OwnerKind.REPORT, OwnerKind.TRACK}
    assert {item.field for item in obligations} == {"title", "kind", "width_mm"}
    verify_obligation_spans(request, obligations)
    verify_anchor_coverage(request, obligations)


def test_sparse_add_track_source_obligation_uses_unique_inspected_context() -> None:
    """An add-track action binds its source through the resolved existing section."""
    request = 'Add a track from "well-a.las".'
    source_obligation = next(
        item
        for item in extract_supported_obligations(request)
        if item.owner_kind is OwnerKind.SOURCE
    )
    context = ResolvedSectionContext(
        task_index=0,
        section_id="main",
        sources=(
            SourceContext(
                candidate_id="source-1",
                labels=("well-a.las",),
                canonical_path="/host/data/well-a.las",
                source_format="las",
            ),
        ),
    )

    validate_section_obligations(
        SimpleNamespace(action="add_track"),
        (source_obligation,),
        section_context=context,
    )


@pytest.mark.parametrize(
    "sources",
    [
        (),
        (
            SourceContext(
                candidate_id="source-1",
                labels=("well-a.las",),
                canonical_path="/host/data/well-a.las",
                source_format="las",
            ),
            SourceContext(
                candidate_id="source-2",
                labels=("well-a.las",),
                canonical_path="/other/data/well-a.las",
                source_format="las",
            ),
        ),
    ],
)
def test_sparse_add_track_source_obligation_fails_closed_without_unique_match(
    sources: tuple[SourceContext, ...],
) -> None:
    """Missing or ambiguous context sources cannot satisfy an explicit source fact."""
    request = 'Add a track from "well-a.las".'
    source_obligation = next(
        item
        for item in extract_supported_obligations(request)
        if item.owner_kind is OwnerKind.SOURCE
    )
    context = ResolvedSectionContext(task_index=0, section_id="main", sources=sources)

    with pytest.raises(ValueError, match="source was not resolved"):
        validate_section_obligations(
            SimpleNamespace(action="add_track"),
            (source_obligation,),
            section_context=context,
        )


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


def test_historical_append_track_request_preserves_all_explicit_facts() -> None:
    """The original 30 mm request is fully represented before planning."""
    request = (
        'Append a 30 mm normal track named "Resistivity QC" to Main Log. '
        'Plot ILD on it as "Resistivity QC" with a logarithmic 0.2–2000 scale.'
    )
    obligations = extract_supported_obligations(request)

    assert {(item.owner_kind, item.field, item.value) for item in obligations} >= {
        (OwnerKind.SECTION, "target", "Main Log"),
        (OwnerKind.TRACK, "title", "Resistivity QC"),
        (OwnerKind.TRACK, "kind", "normal"),
        (OwnerKind.TRACK, "width_mm", 30.0),
        (OwnerKind.BINDING, "channel", "ILD"),
        (OwnerKind.BINDING, "scale_kind", "log"),
        (OwnerKind.BINDING, "scale_minimum", 0.2),
        (OwnerKind.BINDING, "scale_maximum", 2000.0),
    }
    verify_obligation_spans(request, obligations)
    verify_anchor_coverage(request, obligations)


def test_historical_negative_track_request_preserves_width_anchor() -> None:
    """The 24 mm negative case cannot lose its explicit width before planning."""
    request = (
        'In Main Log, add a 24 mm normal track titled "Neutron QC" and '
        "plot NPHI from missing_neutron.las on it with a linear 0–45 scale."
    )
    obligations = extract_supported_obligations(request)

    assert (OwnerKind.TRACK, "width_mm", 24.0) in {
        (item.owner_kind, item.field, item.value) for item in obligations
    }
    verify_anchor_coverage(request, obligations)


def test_independent_anchor_layer_rejects_dropped_width() -> None:
    """Coverage fails when a recognized width is removed from semantic facts."""
    request = 'Append a 30 mm normal track named "Resistivity QC" to Main Log.'
    obligations = extract_supported_obligations(request)
    without_width = tuple(item for item in obligations if item.field != "width_mm")

    assert any("30 mm" in anchor.text for anchor in extract_supported_anchors(request))
    with pytest.raises(ValueError, match="Supported request anchor"):
        verify_anchor_coverage(request, without_width)


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


def test_request_compilation_reports_conflict_and_empty_semantics() -> None:
    """Compilation state distinguishes contradictory and unsupported requests."""
    conflicting = compile_request_contract(
        "Track gamma: normal, width 30 mm. Track gamma: normal, width 32 mm."
    )
    assert conflicting.status.value == "CONFLICTING"
    unsupported = compile_request_contract("Please make the layout attractive.")
    assert unsupported.status.value == "NO_SUPPORTED_SEMANTICS"


def test_compiled_provenance_spans_validate_independently() -> None:
    """Compiled provenance remains byte-accurate for multi-span value sources."""
    request = (
        'On cbl: Use channel CBL. Both labels are "CBL Amplitude". '
        "The first is linear 0..100, #111111, width 0.75. "
        "The second is linear 0..10, #2563eb dashed, width 0.65."
    )
    compilation = compile_request_contract(request)
    verify_obligation_spans(request, compilation.requirements.requirements)
    verify_anchor_coverage(
        request,
        compilation.requirements.requirements,
        anchors=compilation.anchors,
    )
    labels = [
        item
        for item in compilation.requirements.requirements
        if item.field == "label" and item.value == "CBL Amplitude"
    ]
    assert len(labels) == 2
    assert {item.slot_key for item in labels} == {"cbl.binding.1", "cbl.binding.2"}
    assert all(item.provenance for item in labels)


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


def test_planner_binds_explicit_width_independently_of_planner_prose() -> None:
    """Compiled width is attached even when the planner omits it from prose."""
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

    _validate_extraction_coverage(attached)
    width = [item for item in attached.section_tasks[0].obligations if item.field == "width_mm"]
    assert len(width) == 1
    assert width[0].value == 30.0
    assert width[0].requirement_id in attached.section_tasks[0].requirement_refs


def test_section_obligations_are_partitioned_by_target() -> None:
    """Request-owned facts are assigned to one matching section, not broadcast."""
    plan = SemanticPlan(
        summary="Update two sections.",
        section_tasks=(
            SectionTask(
                goal="Main Log GR",
                capability_ids=("section.log_plot",),
                existing_section_hint="Main Log",
                requirements=("Main Log", "GR"),
            ),
            SectionTask(
                goal="Repeat Log CBL",
                capability_ids=("section.log_plot",),
                existing_section_hint="Repeat Log",
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
                existing_section_hint="Main Pass",
                requirements=("cbl", "CBL"),
            ),
            SectionTask(
                goal="Repeat pass",
                capability_ids=("section.log_plot",),
                existing_section_hint="Repeat Pass",
                requirements=("vdl", "VDL"),
            ),
        ),
    )
    attached = _attach_request_obligations(
        plan,
        "In the Main Pass section, plot CBL on cbl. In the Repeat Pass section, plot VDL on vdl.",
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


def test_scope_matrix_s01_independently_declares_ordered_passes() -> None:
    """Expected scopes originate in request compilation before task binding."""
    request = (
        "In the Main Pass section, use GR. In the Repeat Pass section, use GR. "
        "For each pass, keep the main curve."
    )
    compilation = compile_request_contract(request)
    assert [scope.selector_text for scope in compilation.requirements.scopes.scopes] == [
        "Main Pass",
        "Repeat Pass",
    ]
    assert compilation.requirements.shared_scope_rules


def test_scope_matrix_recognizes_comma_form_section_target() -> None:
    """The established 'In Main Log, ...' request form owns its target scope."""
    compilation = compile_request_contract(
        "In Main Log, set the Gamma Ray curve to a linear 5-125 scale."
    )

    assert [scope.selector_text for scope in compilation.requirements.scopes.scopes] == ["Main Log"]
    target_values = [
        item.value for item in compilation.requirements.requirements if item.field == "target"
    ]
    assert target_values == ["Main Log"]


def test_scope_matrix_recognizes_possessive_section_track_target() -> None:
    """A request targeting a section's track declares that existing section."""
    compilation = compile_request_contract(
        "On Main Log's GR track, fill from Gamma Ray to its lower scale boundary."
    )

    assert [scope.selector_text for scope in compilation.requirements.scopes.scopes] == ["Main Log"]
    assert any(
        item.owner_kind is OwnerKind.SECTION and item.field == "target" and item.value == "Main Log"
        for item in compilation.requirements.requirements
    )


def test_scope_matrix_recognizes_unicode_dash_to_target() -> None:
    """Section selectors preserve an en dash in the request's target name."""
    compilation = compile_request_contract(
        "Apply that 20–110 linear Gamma Ray scale change only to Main Log – Upper."
    )

    assert [scope.selector_text for scope in compilation.requirements.scopes.scopes] == [
        "Main Log – Upper"
    ]


def test_scope_matrix_s02_rejects_missing_requested_scope() -> None:
    """A missing planner task cannot shrink the request-owned scope set."""
    plan = SemanticPlan(
        summary="Configure passes.",
        section_tasks=(
            SectionTask(
                goal="Configure Main Pass.",
                capability_ids=("section.log_plot",),
                existing_section_hint="Main Pass",
                requirements=(),
            ),
        ),
    )
    with pytest.raises(PlannerSemanticError) as error:
        _attach_compiled_requirements(
            plan,
            compile_request_contract(
                "In the Main Pass section, use GR. In the Repeat Pass section, use GR."
            ),
        )
    assert error.value.code == "missing_requested_scope"


def test_scope_matrix_s03_rejects_duplicate_assignment() -> None:
    """Two tasks cannot consume one expected scope declaration."""
    plan = SemanticPlan(
        summary="Configure passes.",
        section_tasks=tuple(
            SectionTask(
                goal="Configure Main Pass.",
                capability_ids=("section.log_plot",),
                existing_section_hint="Main Pass",
                requirements=(),
            )
            for _ in range(2)
        ),
    )
    with pytest.raises(PlannerSemanticError) as error:
        _attach_compiled_requirements(
            plan,
            compile_request_contract("In the Main Pass section, use GR."),
        )
    assert error.value.code == "duplicate_scope_assignment"


def test_scope_matrix_s04_rejects_unexpected_assignment() -> None:
    """Planner scope hints cannot introduce an undeclared section."""
    plan = SemanticPlan(
        summary="Configure passes.",
        section_tasks=(
            SectionTask(
                goal="Configure Side Pass.",
                capability_ids=("section.log_plot",),
                existing_section_hint="Side Pass",
                requirements=(),
            ),
        ),
    )
    with pytest.raises(PlannerSemanticError) as error:
        _attach_compiled_requirements(
            plan,
            compile_request_contract("In the Main Pass section, use GR."),
        )
    assert error.value.code == "unexpected_scope_assignment"


def test_scope_matrix_s05_shared_rules_bind_to_each_declared_pass() -> None:
    """Shared requirements instantiate against expected passes, not task count."""
    request = (
        "In the Main Pass section, use GR. In the Repeat Pass section, use GR. "
        "For each pass, set the GR scale to linear 0..100."
    )
    plan = SemanticPlan(
        summary="Configure both passes.",
        section_tasks=tuple(
            SectionTask(
                goal=f"Configure {name}.",
                capability_ids=("section.log_plot",),
                existing_section_hint=name,
                requirements=(),
            )
            for name in ("Main Pass", "Repeat Pass")
        ),
    )
    attached = _attach_compiled_requirements(plan, compile_request_contract(request))
    assert attached.scope_binding.expected_scope_ids == (
        "existing:main_pass",
        "existing:repeat_pass",
    )
    scales = [
        [item.value for item in task.obligations if item.field == "scale_maximum"]
        for task in attached.section_tasks
    ]
    assert scales == [[100.0], [100.0]]


def test_document_preservation_allows_authorized_collection_create() -> None:
    """A created remark may change its canonical collection, but not unrelated data."""
    before = {"remarks": [], "title": "unchanged"}
    after = {
        "remarks": [
            {
                "remark_id": "scope",
                "title": "Scope",
                "lines": ["Supported scope"],
            }
        ],
        "title": "unchanged",
    }
    operation = SimpleNamespace(
        object_kind="remark",
        object_id="scope",
        action="create",
        payload={"object": after["remarks"][0]},
    )

    verify_document_preservation(before, after, (operation,))

    invalid = {
        **after,
        "title": "unexpected mutation",
    }
    with pytest.raises(ValueError, match="authorized reconciliation envelope"):
        verify_document_preservation(before, invalid, (operation,))


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


def _existing_gr_context() -> ResolvedSectionContext:
    """Build the host-owned identity used by the frozen D4 scale update."""
    return ResolvedSectionContext(
        task_index=0,
        section_id="main-log",
        existing_curves=(
            ExistingCurveContext(
                track_id="gr-track",
                track_title="Gamma Ray",
                track_kind="normal",
                binding_id="main.gr.GR.1",
                channel="GR",
                label="Gamma Ray",
                scale_kind="linear",
                scale_minimum=0.0,
                scale_maximum=150.0,
            ),
        ),
    )


def _existing_gr_scale_action(
    *, kind: str = "linear", maximum: float = 125.0
) -> UpdateCurveScaleAction:
    """Build the sparse existing-object action for D4-L01:T2."""
    return UpdateCurveScaleAction(
        action="update_curve_scale",
        target=ExistingCurveSelector(handle="curve-1"),
        scale=SemanticScale(kind=kind, minimum=5.0, maximum=maximum),
    )


def test_existing_curve_scale_obligation_uses_host_grounded_selector() -> None:
    """The exact D4-L01:T2 sparse action satisfies the selected GR obligations."""
    request = "In Main Log, set the Gamma Ray curve to a linear 5–125 scale."
    obligations = extract_supported_obligations(request)
    context = _existing_gr_context()
    action = _existing_gr_scale_action()

    validate_section_obligations(
        action,
        obligations,
        section_context=context,
        section_title="Main Log",
    )
    intent = AuthoringDocumentIntent(
        curve_bindings=[
            AuthoringCurveBindingIntent(
                kind="curve",
                binding_id="main.gr.GR.1",
                section_id="main-log",
                track_id="gr-track",
                scale={"kind": "linear", "minimum": 5.0, "maximum": 125.0},
            )
        ]
    )
    verify_lowered_existing_curve_obligations(
        action,
        intent,
        obligations,
        section_context=context,
    )


@pytest.mark.parametrize(
    ("kind", "maximum"),
    [("linear", 120.0), ("log", 125.0)],
)
def test_existing_curve_scale_obligation_rejects_wrong_scale(kind: str, maximum: float) -> None:
    """Scale kind and bounds remain independently enforced."""
    request = "In Main Log, set the Gamma Ray curve to a linear 5–125 scale."
    with pytest.raises(ValueError, match="scale_"):
        validate_section_obligations(
            _existing_gr_scale_action(kind=kind, maximum=maximum),
            extract_supported_obligations(request),
            section_context=_existing_gr_context(),
            section_title="Main Log",
        )


def test_existing_curve_scale_obligation_rejects_wrong_selector_and_channel() -> None:
    """Selector and grounded channel mismatches fail without fuzzy substitution."""
    context = _existing_gr_context()
    request = "In Main Log, set the Gamma Ray curve to a linear 5–125 scale."
    wrong_selector = _existing_gr_scale_action().model_copy(
        update={"target": ExistingCurveSelector(handle="curve-2")}
    )
    with pytest.raises(SemanticActionError, match="No grounded existing curve"):
        validate_section_obligations(
            wrong_selector,
            extract_supported_obligations(request),
            section_context=context,
        )

    channel_request = "Plot ILD with a linear 5–125 scale."
    with pytest.raises(ValueError, match="channel"):
        validate_section_obligations(
            _existing_gr_scale_action(),
            extract_supported_obligations(channel_request),
            section_context=context,
        )


def test_existing_curve_post_lowering_rejects_arbitrary_binding_identity() -> None:
    """Post-lowering checks use the selector-resolved binding, not a document scan."""
    action = _existing_gr_scale_action()
    obligations = extract_supported_obligations(
        "In Main Log, set the Gamma Ray curve to a linear 5–125 scale."
    )
    wrong_intent = AuthoringDocumentIntent(
        curve_bindings=[
            AuthoringCurveBindingIntent(
                kind="curve",
                binding_id="other.binding",
                section_id="main-log",
                track_id="gr-track",
                scale={"kind": "linear", "minimum": 5.0, "maximum": 125.0},
            )
        ]
    )
    with pytest.raises(ValueError, match="resolved binding identity"):
        verify_lowered_existing_curve_obligations(
            action,
            wrong_intent,
            obligations,
            section_context=_existing_gr_context(),
        )


def test_post_lowering_scale_uses_reconciliation_binding_identity() -> None:
    """A sparse update selects its reconciliation binding among duplicate scales."""
    document = AuthoringDocumentSpec(
        name="identity-test",
        sections=[
            {
                "id": "main-log",
                "title": "Main Log",
                "tracks": [
                    {
                        "id": "gr-track",
                        "title": "Gamma Ray",
                        "kind": "normal",
                        "width_mm": 25,
                        "bindings": [
                            {
                                "binding_id": "main.gr.GR.1",
                                "channel": "GR",
                                "scale": {
                                    "kind": "linear",
                                    "minimum": 5,
                                    "maximum": 125,
                                },
                            },
                            {
                                "binding_id": "other.binding",
                                "channel": "RT",
                                "scale": {
                                    "kind": "linear",
                                    "minimum": 0,
                                    "maximum": 150,
                                },
                            },
                        ],
                    }
                ],
            }
        ],
    )
    operation = SimpleNamespace(
        object_kind="curve_binding",
        object_id="main.gr.GR.1",
        action="update",
    )
    obligations = extract_supported_obligations(
        "In Main Log, set the Gamma Ray curve to a linear 5–125 scale."
    )
    verify_document_obligations(document, obligations, grounded_operations=(operation,))

    wrong_operation = SimpleNamespace(
        object_kind="curve_binding",
        object_id="other.binding",
        action="update",
    )
    with pytest.raises(ValueError, match="Post-lowering scale"):
        verify_document_obligations(
            document,
            obligations,
            grounded_operations=(wrong_operation,),
        )


def test_post_lowering_array_track_scale_reads_canonical_x_scale() -> None:
    """Array track requirements are verified against the persisted x_scale shape."""
    request = "On vdl: linear track scale 200..1200."
    obligations = tuple(
        item
        for item in extract_supported_obligations(request)
        if item.owner_ref.casefold() == "vdl" and item.field.startswith("track_scale_")
    )
    assert {item.field for item in obligations} == {
        "track_scale_kind",
        "track_scale_minimum",
        "track_scale_maximum",
    }

    def document(scale: dict[str, object]) -> SimpleNamespace:
        return SimpleNamespace(
            model_dump=lambda mode: {
                "sections": [
                    {
                        "id": "main_pass",
                        "tracks": [
                            {"id": "vdl", "x_scale": scale, "grid": {}},
                        ],
                    }
                ]
            }
        )

    verify_document_obligations(
        document({"kind": "linear", "minimum": 200.0, "maximum": 1200.0}),
        obligations,
    )
    with pytest.raises(ValueError, match="track_scale_minimum"):
        verify_document_obligations(
            document({"kind": "linear", "minimum": 100.0, "maximum": 1200.0}),
            obligations,
        )


def test_existing_curve_update_preservation_rejects_unrelated_label_change() -> None:
    """An authorized scale update cannot smuggle an unrelated label mutation."""
    before = {
        "bindings": [
            {
                "id": "main.gr.GR.1",
                "scale": {"minimum": 0, "maximum": 150},
                "label": "Gamma Ray",
            }
        ]
    }
    after = {
        "bindings": [
            {
                "id": "main.gr.GR.1",
                "scale": {"minimum": 5, "maximum": 125},
                "label": "Changed",
            }
        ]
    }
    operation = SimpleNamespace(
        object_kind="curve_binding",
        object_id="main.gr.GR.1",
        action="update",
        payload={"patch": {"scale": after["bindings"][0]["scale"]}},
    )
    with pytest.raises(ValueError, match="authorized reconciliation envelope"):
        verify_document_preservation(before, after, (operation,))


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
