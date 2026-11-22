"""Tests for deterministic execution and checkpoints."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from unittest.mock import patch

import pytest

from wellplot.agent._private_apply import (
    _apply_private_authoring,
    _OrderedPrivateApply,
    _PrivateStepAdmission,
)
from wellplot.agent.code_mode.canonical_workers import (
    ReportSemanticResponse,
    _lower_report,
    _validate_report_operation_contract,
)
from wellplot.agent.code_mode.enrichment import inspect_report_context
from wellplot.agent.code_mode.obligations import compile_request_contract
from wellplot.agent.code_mode.planner import ReportTask, SemanticFieldValue, SemanticOperation
from wellplot.agent.code_mode.worker_contracts import build_report_operation_contract
from wellplot.authoring_executor import (
    AuthoringExecutionStatus,
    _document_digest,
    execute_authoring_plan,
)
from wellplot.authoring_reconciler import (
    AuthoringOperation,
    AuthoringOperationAction,
    AuthoringOperationObjectKind,
    AuthoringOperationPhase,
    AuthoringReconciliationPlan,
    reconcile_authoring,
)
from wellplot.authoring_service import (
    AuthoringService,
    SectionPatch,
    UpdateReportRequest,
    UpdateSectionRequest,
)
from wellplot.model import AuthoringDocumentIntent, AuthoringDocumentSpec
from wellplot.model.authoring import AuthoringDataSource
from wellplot.model.intent import AuthoringTailIntent


def _document() -> AuthoringDocumentSpec:
    """Build a small canonical document for executor tests."""
    return AuthoringDocumentSpec(
        name="executor-test",
        title="Original",
        sections=[
            {
                "id": "main",
                "title": "Main",
                "tracks": [
                    {
                        "id": "curves",
                        "title": "Curves",
                        "kind": "normal",
                        "width_mm": 20,
                        "bindings": [
                            {
                                "binding_id": "gr-1",
                                "channel": "GR",
                                "style": {"color": "black"},
                            }
                        ],
                    }
                ],
            }
        ],
    )


_ORDERED_REQUEST = (
    "Rename the report 'Gamma Study'. Set the report subtitle to 'Run 02'. Keep the report tail."
)


def _ordered_report() -> _OrderedPrivateApply:
    facts = compile_request_contract(_ORDERED_REQUEST).requirements.requirements
    assert {item.field for item in facts} == {"title", "subtitle", "tail_enabled"}
    return _OrderedPrivateApply(
        request=_ORDERED_REQUEST,
        document=_document(),
        step_ids=("one", "two", "noop"),
        obligations=facts,
    )


def _admit_report(
    before: AuthoringDocumentSpec,
    step: str,
    fields: tuple[str, ...],
    *,
    depends: tuple[str, ...] = (),
) -> tuple[_PrivateStepAdmission, AuthoringDocumentIntent]:
    facts = tuple(
        item
        for item in compile_request_contract(_ORDERED_REQUEST).requirements.requirements
        if item.field in fields
    )
    digest = _document_digest(before)
    context = inspect_report_context(before, digest)
    task = ReportTask(
        goal="Apply exact request-owned report facts.",
        capability_ids=("report.standard",),
        obligations=facts,
        operations=tuple(
            SemanticOperation(
                local_ref=item.field,
                scope_ref="report",
                verb="SET",
                object_kind="report_field",
                target_clue=item.field,
                field_values=(SemanticFieldValue(field=item.field, state="SET", value=item.value),),
            )
            for item in facts
        ),
    )
    if facts:
        admitted = build_report_operation_contract(task, context)
        response = ReportSemanticResponse.model_validate({item.field: item.value for item in facts})
        _validate_report_operation_contract(response, admitted)
        intent = _lower_report(response, context)
    else:
        intent = AuthoringDocumentIntent(title=before.title)
    return _PrivateStepAdmission(
        step_id=step,
        outcome_id=step,
        request_sha256=hashlib.sha256(_ORDERED_REQUEST.encode()).hexdigest(),
        before_sha256=digest,
        plan=reconcile_authoring(intent, existing=before),
        obligations=facts,
        depends_on=depends,
    ), intent


def _complete_ordered_report() -> _OrderedPrivateApply:
    ledger = _ordered_report()
    for name, fields, prerequisites in (
        ("one", ("title", "tail_enabled"), ()),
        ("two", ("subtitle",), ("one",)),
        ("noop", (), ("two",)),
    ):
        ledger.apply(*_admit_report(ledger.candidate, name, fields, depends=prerequisites))
    return ledger


def test_ordered_private_execution_keeps_intact_plans_and_cumulative_state() -> None:
    """Exercise host report admission and real private apply over refreshed readback."""
    ledger = _complete_ordered_report()
    first, second, noop = ledger.occurrences
    assert [op.operation_id for op in first.admission.plan.operations] == [
        "update:report:report",
        "update:tail:tail",
    ]
    assert [op.operation_id for op in second.admission.plan.operations] == ["update:report:report"]
    assert first.occurrence_id != second.occurrence_id
    assert first.after_sha256 == second.admission.before_sha256
    assert second.after_sha256 == noop.admission.before_sha256 == noop.after_sha256
    assert noop.execution.outcomes == ()
    assert first.execution.phase_summaries and first.execution.outcomes[0].postcondition_verified
    final = ledger.finish(ledger.occurrences, ledger.candidate)
    assert (final.title, final.subtitle, final.tail.enabled) == ("Gamma Study", "Run 02", True)


@pytest.mark.parametrize(
    "defect", ["duplicate", "missing", "reordered", "operation", "digest", "final"]
)
def test_ordered_private_execution_rejects_tampered_readback(defect: str) -> None:
    """Do not authorize a final JSON match with incomplete or altered history."""
    ledger = _complete_ordered_report()
    first, second, noop = ledger.occurrences
    candidate = ledger.candidate
    match = "Missing, altered or reordered"
    if defect == "duplicate":
        second = replace(second, occurrence_id=first.occurrence_id)
    elif defect == "missing":
        with pytest.raises(ValueError, match=match):
            ledger.finish((first, noop), candidate)
        return
    elif defect == "reordered":
        first, second = second, first
    elif defect == "operation":
        first.execution.outcomes = first.execution.outcomes[1:]
    elif defect == "digest":
        first = replace(first, after_sha256="0" * 64)
    else:
        candidate.subtitle = "Unauthorized"
        match = "differs from the cumulative verified readback"
    with pytest.raises(ValueError, match=match):
        ledger.finish((first, second, noop), candidate)


@pytest.mark.parametrize(
    "defect", ["request", "snapshot", "dependency", "extra", "overwrite", "duplicate"]
)
def test_failed_ordered_step_never_advances_or_allows_continuation(defect: str) -> None:
    """Reject stale admission or failed retained outcome before advancing."""
    ledger = _ordered_report()
    ledger.apply(*_admit_report(ledger.candidate, "one", ("title", "tail_enabled")))
    previous = ledger.candidate
    admission, intent = _admit_report(previous, "two", ("subtitle",), depends=("one",))
    if defect == "request":
        admission = replace(admission, request_sha256="0" * 64)
    elif defect == "snapshot":
        admission = replace(admission, before_sha256="0" * 64)
    elif defect == "dependency":
        admission = replace(admission, depends_on=("noop",))
    elif defect == "extra":
        intent.title = "Unpermitted extra effect"
    elif defect == "overwrite":
        intent.title = "Invalidates a prior outcome"
        admission = replace(admission, plan=reconcile_authoring(intent, existing=previous))
    else:
        admission.plan.operations += admission.plan.operations
    with pytest.raises(ValueError):
        ledger.apply(admission, intent)
    assert ledger.candidate == previous
    assert len(ledger.occurrences) == 1
    with pytest.raises(ValueError, match="closed"):
        ledger.apply(*_admit_report(previous, "two", ("subtitle",), depends=("one",)))


def test_executor_applies_typed_operations_and_captures_phase_previews() -> None:
    """Apply a plan through the service and expose persisted phase snapshots."""
    document = _document()
    service = AuthoringService(document)
    intent = AuthoringDocumentIntent(
        title="Revised",
        sections=[
            {
                "section_id": "main",
                "tracks": [
                    {
                        "track_id": "curves",
                        "width_mm": 25,
                        "bindings": [
                            {
                                "kind": "curve",
                                "binding_id": "gr-1",
                                "channel": "GR",
                                "style": {"color": "blue"},
                            },
                            {"kind": "curve", "binding_id": "gr-2", "channel": "GR"},
                        ],
                    }
                ],
            }
        ],
    )
    plan = reconcile_authoring(
        intent,
        existing=document,
        available_channels={"main": ["GR"]},
    )

    result = execute_authoring_plan(
        service,
        plan,
        preview_callback=lambda _document, phase: phase.value.encode("ascii"),
    )

    assert result.success is True
    assert result.stopped is False
    assert all(item.postcondition_verified for item in result.outcomes)
    assert all(item.before_document_sha256 for item in result.outcomes)
    assert all(item.after_document_sha256 for item in result.outcomes)
    assert [item.after_document_sha256 for item in result.outcomes[:-1]] == [
        item.before_document_sha256 for item in result.outcomes[1:]
    ]
    assert [item.phase for item in result.phase_summaries] == [
        AuthoringOperationPhase.REPORT,
        AuthoringOperationPhase.TRACKS,
        AuthoringOperationPhase.BINDINGS,
        AuthoringOperationPhase.PRESENTATION,
    ]
    assert result.phase_summaries[0].preview_png == b"report"
    assert service.document.title == "Revised"
    track = service.document.sections[0].tracks[0]
    assert track.width_mm == 25
    assert [binding.binding_id for binding in track.bindings] == ["gr-1", "gr-2"]
    assert track.bindings[0].style.color == "blue"


@pytest.mark.parametrize(
    "defect", ["source", "sibling", "compatibility", "future_tail", "extra_null"]
)
def test_executor_blocks_transient_unapproved_operation_effect(defect: str) -> None:
    """Reject the first bad boundary even if the next operation would restore it."""
    document = _document()
    source_a = AuthoringDataSource(source_path="a.las")
    source_b = AuthoringDataSource(source_path="b.las")
    document.sections[0].data_source = source_a if defect != "compatibility" else None
    document.extensions["compatibility"] = {"legacy_data": {"source_path": "a.las"}}
    service = AuthoringService(document)
    intent = AuthoringDocumentIntent(title="Revised", tail=AuthoringTailIntent(enabled=True))
    plan = reconcile_authoring(intent, existing=document)
    assert [item.operation_id for item in plan.operations] == [
        "update:report:report",
        "update:tail:tail",
    ]
    clean = execute_authoring_plan(AuthoringService(document), plan)
    assert clean.success and len(clean.outcomes) == 2
    real_update = service.update
    calls = []

    def update(request: object) -> object:
        calls.append(request)
        value = real_update(request)
        if isinstance(request, UpdateReportRequest):
            if defect == "source":
                real_update(
                    UpdateSectionRequest(
                        section_id="main", patch=SectionPatch(data_source=source_b)
                    )
                )
            else:
                changed = service.document
                if defect == "sibling":
                    changed.subtitle = "Unapproved"
                elif defect == "compatibility":
                    changed.extensions["compatibility"]["legacy_data"]["source_path"] = "b.las"
                elif defect == "extra_null":
                    changed.extensions["unapproved"] = None
                else:
                    changed.tail.enabled = True
                service.replace_document(changed)
        elif defect == "source":
            real_update(
                UpdateSectionRequest(section_id="main", patch=SectionPatch(data_source=source_a))
            )
        return value

    with patch.object(service, "update", side_effect=update):
        rejected = execute_authoring_plan(service, plan)
    assert not rejected.success and rejected.stopped
    assert len(calls) == len(rejected.outcomes) == 1
    assert rejected.outcomes[0].after_document_sha256 is None
    assert "outside the authorized reconciliation envelope" in rejected.errors[0]


def test_executor_rejects_snapshot_drift_between_phases() -> None:
    """Drift after one verified operation cannot become the next baseline."""
    document = _document()
    service = AuthoringService(document)
    intent = AuthoringDocumentIntent(
        title="Revised",
        sections=[{"section_id": "main", "tracks": [{"track_id": "curves", "width_mm": 25}]}],
    )
    plan = reconcile_authoring(intent, existing=document)

    def drift(_document: AuthoringDocumentSpec, _phase: AuthoringOperationPhase) -> None:
        changed = service.document
        changed.subtitle = "Unapproved"
        service.replace_document(changed)

    result = execute_authoring_plan(service, plan, preview_callback=drift)
    assert not result.success and result.stopped
    assert "drifted before the next operation" in result.errors[0]
    assert result.outcomes[0].postcondition_verified
    assert not result.outcomes[1].postcondition_verified
    assert service.document.sections[0].tracks[0].width_mm == 20


def test_private_apply_does_not_return_candidate_after_operation_failure() -> None:
    """A failed target readback after mutation is not a publishable candidate."""
    document = _document()
    original = AuthoringService.update

    def update(service: AuthoringService, request: object) -> object:
        value = original(service, request)
        changed = service.document
        changed.title = "Incorrect"
        service.replace_document(changed)
        return value

    with patch.object(AuthoringService, "update", update):
        result = _apply_private_authoring(
            document=document,
            intent=AuthoringDocumentIntent(title="Expected"),
            obligations=(),
            inspected=None,
            semantic_contract=None,
        )
    assert result.candidate is None and result.rolled_back
    assert result.failure_status == "execution_failed"
    assert "Read-after-write postcondition" in result.errors[0]
    assert document.title == "Original"


def test_executor_keeps_plan_local_ids_and_accepts_noop() -> None:
    """Independent report edits keep their IDs and a verified no-op performs no writes."""
    service = AuthoringService(_document())
    previous = None
    for intent in (AuthoringDocumentIntent(title="Study"), AuthoringDocumentIntent(subtitle="Run")):
        plan = reconcile_authoring(intent, existing=service.document)
        duplicate = plan.model_copy(update={"operations": (*plan.operations, *plan.operations)})
        rejected = execute_authoring_plan(service, duplicate)
        assert not rejected.success and "Duplicate operation id" in rejected.errors[0]
        result = execute_authoring_plan(service, plan)
        assert result.success
        (outcome,) = result.outcomes
        assert outcome.operation_id == "update:report:report"
        if previous is not None:
            assert outcome.before_document_sha256 == previous
        previous = outcome.after_document_sha256
    assert service.document.title == "Study" and service.document.subtitle == "Run"
    noop = execute_authoring_plan(
        service,
        reconcile_authoring(AuthoringDocumentIntent(title="Study"), existing=service.document),
    )
    assert noop.success and noop.outcomes == ()


def test_executor_observes_move_and_remove_as_separate_effects() -> None:
    """Validate exact collection changes at distinct operation boundaries."""
    document = _document()
    tracks = document.sections[0].tracks
    second = tracks[0].model_copy(deep=True, update={"id": "second", "bindings": []})
    third = second.model_copy(deep=True, update={"id": "third"})
    tracks.extend((second, third))
    service = AuthoringService(document)
    plan = AuthoringReconciliationPlan(
        ready=True,
        operations=[
            AuthoringOperation(
                operation_id="move-third",
                phase=AuthoringOperationPhase.TRACKS,
                action=AuthoringOperationAction.MOVE,
                object_kind=AuthoringOperationObjectKind.TRACK,
                section_id="main",
                object_id="third",
                payload={"new_index": 0},
                reason="Test move.",
            ),
            AuthoringOperation(
                operation_id="remove-second",
                phase=AuthoringOperationPhase.TRACKS,
                action=AuthoringOperationAction.REMOVE,
                object_kind=AuthoringOperationObjectKind.TRACK,
                section_id="main",
                object_id="second",
                depends_on=["move-third"],
                reason="Test remove.",
            ),
        ],
    )
    result = execute_authoring_plan(service, plan)
    assert result.success, result.errors
    first, second = result.outcomes
    assert first.after_document_sha256 == second.before_document_sha256
    assert [track.id for track in service.document.sections[0].tracks] == ["third", "curves"]


def test_executor_does_not_preview_a_blocked_phase() -> None:
    """Do not present a preview when a phase has no verified mutation."""
    service = AuthoringService(_document())
    plan = AuthoringReconciliationPlan(
        ready=True,
        operations=[
            AuthoringOperation(
                operation_id="duplicate-curves",
                phase=AuthoringOperationPhase.TRACKS,
                action=AuthoringOperationAction.CREATE,
                object_kind=AuthoringOperationObjectKind.TRACK,
                object_id="curves",
                section_id="main",
                payload={
                    "object": {
                        "id": "curves",
                        "title": "Duplicate",
                        "kind": "normal",
                        "width_mm": 20,
                    }
                },
                reason="test precondition failure",
            )
        ],
    )
    preview_calls: list[AuthoringOperationPhase] = []

    result = execute_authoring_plan(
        service,
        plan,
        preview_callback=lambda _document, phase: preview_calls.append(phase) or b"preview",
    )

    assert result.success is False
    assert result.phase_summaries[0].status == AuthoringExecutionStatus.BLOCKED
    assert result.phase_summaries[0].preview_png is None
    assert preview_calls == []


def test_executor_assembles_new_section_tracks_and_array_bindings() -> None:
    """Persist a generic multi-track section in dependency order."""
    document = _document()
    service = AuthoringService(document)
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "packet_pass",
                "title": "Packet Pass",
                "tracks": [
                    {
                        "track_id": "packet_curves",
                        "title": "Packet Curves",
                        "kind": "normal",
                        "width_mm": 24,
                        "bindings": [
                            {
                                "kind": "curve",
                                "binding_id": "packet-gr-1",
                                "channel": "GR",
                            },
                            {
                                "kind": "curve",
                                "binding_id": "packet-gr-2",
                                "channel": "GR",
                            },
                        ],
                    },
                    {
                        "track_id": "packet_waveform",
                        "title": "Packet Waveform",
                        "kind": "array",
                        "width_mm": 30,
                        "bindings": [
                            {
                                "kind": "raster",
                                "binding_id": "packet-vdl",
                                "channel": "VDL",
                            }
                        ],
                    },
                ],
            }
        ]
    )
    plan = reconcile_authoring(
        intent,
        existing=document,
        available_channels={
            "packet_pass": [
                {"mnemonic": "GR", "kind": "scalar"},
                {"mnemonic": "VDL", "kind": "raster"},
            ]
        },
    )

    result = execute_authoring_plan(service, plan)

    assert result.success is True
    assert [checkpoint.phase for checkpoint in result.phase_summaries] == [
        AuthoringOperationPhase.SECTIONS,
        AuthoringOperationPhase.TRACKS,
        AuthoringOperationPhase.BINDINGS,
    ]
    packet = next(section for section in service.document.sections if section.id == "packet_pass")
    assert [track.id for track in packet.tracks] == ["packet_curves", "packet_waveform"]
    assert [binding.binding_id for binding in packet.tracks[0].bindings] == [
        "packet-gr-1",
        "packet-gr-2",
    ]
    assert packet.tracks[1].bindings[0].binding_id == "packet-vdl"


def test_executor_creates_track_from_partial_grid_intent() -> None:
    """Apply only specified grid controls and retain canonical grid defaults."""
    service = AuthoringService(_document())
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "main",
                "tracks": [
                    {
                        "track_id": "resistivity",
                        "title": "Resistivity",
                        "kind": "normal",
                        "width_mm": 32.0,
                        "x_scale": {
                            "kind": "log",
                            "minimum": 0.2,
                            "maximum": 2000.0,
                            "unit": "ohm.m",
                        },
                        "grid": {
                            "vertical_main_scale": "logarithmic",
                            "vertical_main_spacing_mode": "scale",
                        },
                    }
                ],
            }
        ]
    )
    plan = reconcile_authoring(intent, existing=service.document)

    result = execute_authoring_plan(service, plan)

    assert result.success is True
    track = next(
        track for track in service.document.sections[0].tracks if track.id == "resistivity"
    )
    assert track.grid.major is True
    assert track.grid.vertical_main_scale == "logarithmic"
    assert track.grid.vertical_main_spacing_mode == "scale"


def test_executor_stops_on_failed_operation_without_running_later_phases() -> None:
    """Stop at a typed service failure and preserve the last valid snapshot."""
    service = AuthoringService(_document())
    plan = AuthoringReconciliationPlan(
        ready=True,
        operations=[
            AuthoringOperation(
                operation_id="bad-width",
                phase=AuthoringOperationPhase.TRACKS,
                action=AuthoringOperationAction.UPDATE,
                object_kind=AuthoringOperationObjectKind.TRACK,
                object_id="curves",
                section_id="main",
                payload={"patch": {"width_mm": -1}},
                reason="Test invalid mutation",
            ),
            AuthoringOperation(
                operation_id="should-not-run",
                phase=AuthoringOperationPhase.PRESENTATION,
                action=AuthoringOperationAction.UPDATE,
                object_kind=AuthoringOperationObjectKind.REPORT,
                object_id="report",
                payload={"patch": {"title": "Unexpected"}},
                reason="Must not execute after failure",
            ),
        ],
    )

    result = execute_authoring_plan(service, plan)

    assert result.success is False
    assert result.stopped is True
    assert result.outcomes[-1].status == AuthoringExecutionStatus.BLOCKED
    assert result.outcomes[-1].operation_id == "bad-width"
    assert service.document.title == "Original"
    assert service.document.sections[0].tracks[0].width_mm == 20
    assert [item.phase for item in result.phase_summaries] == [AuthoringOperationPhase.TRACKS]


def test_executor_rejects_invalid_dependency_plan_before_mutation() -> None:
    """Reject unknown dependencies before any operation can change the document."""
    service = AuthoringService(_document())
    plan = AuthoringReconciliationPlan(
        ready=True,
        operations=[
            AuthoringOperation(
                operation_id="report-update",
                phase=AuthoringOperationPhase.REPORT,
                action=AuthoringOperationAction.UPDATE,
                object_kind=AuthoringOperationObjectKind.REPORT,
                object_id="report",
                payload={"patch": {"title": "No mutation"}},
                depends_on=["missing"],
                reason="Invalid dependency",
            )
        ],
    )

    result = execute_authoring_plan(service, plan)

    assert result.success is False
    assert result.stopped is True
    assert "unknown operation" in result.errors[0]
    assert service.document.title == "Original"


def test_executor_orders_same_phase_dependencies_not_input_order() -> None:
    """Honor explicit CRUD dependencies even when the plan lists them backwards."""
    service = AuthoringService(_document())
    plan = AuthoringReconciliationPlan(
        ready=True,
        operations=[
            AuthoringOperation(
                operation_id="second-track",
                phase=AuthoringOperationPhase.TRACKS,
                action=AuthoringOperationAction.CREATE,
                object_kind=AuthoringOperationObjectKind.TRACK,
                object_id="second",
                section_id="main",
                payload={
                    "object": {
                        "id": "second",
                        "title": "Second",
                        "kind": "normal",
                        "width_mm": 20,
                    }
                },
                depends_on=["first-track"],
                reason="Depends on the first track operation.",
            ),
            AuthoringOperation(
                operation_id="first-track",
                phase=AuthoringOperationPhase.TRACKS,
                action=AuthoringOperationAction.CREATE,
                object_kind=AuthoringOperationObjectKind.TRACK,
                object_id="first",
                section_id="main",
                payload={
                    "object": {
                        "id": "first",
                        "title": "First",
                        "kind": "normal",
                        "width_mm": 20,
                    }
                },
                reason="Dependency target.",
            ),
        ],
    )

    result = execute_authoring_plan(service, plan)

    assert result.success is True
    assert [outcome.operation_id for outcome in result.outcomes] == [
        "first-track",
        "second-track",
    ]
    assert {track.id for track in service.document.sections[0].tracks} >= {
        "curves",
        "first",
        "second",
    }


def test_executor_rejects_dependency_cycle_before_mutation() -> None:
    """A cyclic same-phase dependency graph cannot mutate the private candidate."""
    service = AuthoringService(_document())
    operations = [
        AuthoringOperation(
            operation_id="first",
            phase=AuthoringOperationPhase.TRACKS,
            action=AuthoringOperationAction.CREATE,
            object_kind=AuthoringOperationObjectKind.TRACK,
            object_id="first",
            section_id="main",
            payload={"object": {"id": "first", "title": "First", "kind": "normal"}},
            depends_on=["second"],
            reason="Cycle test.",
        ),
        AuthoringOperation(
            operation_id="second",
            phase=AuthoringOperationPhase.TRACKS,
            action=AuthoringOperationAction.CREATE,
            object_kind=AuthoringOperationObjectKind.TRACK,
            object_id="second",
            section_id="main",
            payload={"object": {"id": "second", "title": "Second", "kind": "normal"}},
            depends_on=["first"],
            reason="Cycle test.",
        ),
    ]

    result = execute_authoring_plan(
        service,
        AuthoringReconciliationPlan(ready=True, operations=operations),
    )

    assert result.success is False
    assert "contain a cycle" in result.errors[0]
    assert [track.id for track in service.document.sections[0].tracks] == ["curves"]
