"""Tests for the generic reconciliation-to-typed-operation bridge."""

from __future__ import annotations

from wellplot.agent.operation_executor import execute_typed_submissions
from wellplot.agent.reconciliation_bridge import compile_reconciliation_plan
from wellplot.authoring_reconciler import (
    AuthoringOperation,
    AuthoringOperationAction,
    AuthoringOperationObjectKind,
    AuthoringOperationPhase,
    AuthoringReconciliationPlan,
)
from wellplot.authoring_service import AuthoringService
from wellplot.model.authoring import AuthoringDocumentSpec, AuthoringStyle


def _plan() -> AuthoringReconciliationPlan:
    """Build one cross-branch generic plan without domain-specific defaults."""
    return AuthoringReconciliationPlan(
        ready=True,
        operations=[
            AuthoringOperation(
                operation_id="update-report",
                phase=AuthoringOperationPhase.REPORT,
                action=AuthoringOperationAction.UPDATE,
                object_kind=AuthoringOperationObjectKind.REPORT,
                object_id="report",
                payload={"patch": {"title": "Revised"}},
                reason="Update the report title.",
            ),
            AuthoringOperation(
                operation_id="create-curves",
                phase=AuthoringOperationPhase.TRACKS,
                action=AuthoringOperationAction.CREATE,
                object_kind=AuthoringOperationObjectKind.TRACK,
                object_id="curves",
                section_id="main",
                payload={
                    "object": {
                        "id": "curves",
                        "title": "Curves",
                        "kind": "normal",
                        "width_mm": 30,
                    }
                },
                reason="Create the curves track.",
            ),
            AuthoringOperation(
                operation_id="bind-gr",
                phase=AuthoringOperationPhase.BINDINGS,
                action=AuthoringOperationAction.CREATE,
                object_kind=AuthoringOperationObjectKind.CURVE_BINDING,
                object_id="gr-1",
                section_id="main",
                track_id="curves",
                payload={
                    "object": {
                        "binding_id": "gr-1",
                        "channel": "GR",
                    }
                },
                depends_on=["create-curves"],
                reason="Bind the GR source channel.",
            ),
        ],
    )


def _service() -> AuthoringService:
    """Build a canonical document with a depth track parent."""
    return AuthoringService(
        AuthoringDocumentSpec(
            name="bridge-test",
            title="Original",
            sections=[
                {
                    "id": "main",
                    "title": "Main",
                    "tracks": [
                        {
                            "id": "depth",
                            "title": "Depth",
                            "kind": "reference",
                            "width_mm": 20,
                        }
                    ],
                }
            ],
        )
    )


def test_bridge_compiles_cross_branch_operations_for_typed_execution() -> None:
    """Compile generic report, track, and binding operations without packet logic."""
    service = _service()
    compilation = compile_reconciliation_plan(
        _plan(),
        service=service,
        defaults_provenance={"sections[main].tracks[curves].width_mm": "generic_form"},
    )

    assert [submission.branch for submission in compilation.submissions] == [
        "report",
        "structure",
        "scalar",
    ]
    assert [unit.object_family for unit in compilation.work_units] == [
        "report",
        "track",
        "curve_binding",
    ]
    result = execute_typed_submissions(
        service,
        compilation.submissions,
        compilation.work_units,
        defaults_provenance_by_operation=compilation.defaults_provenance_by_operation,
    )

    assert result.success is True, result.errors
    assert [outcome.operation_id for outcome in result.outcomes] == [
        "update-report",
        "create-curves",
        "bind-gr",
    ]
    assert result.outcomes[1].defaults_provenance == {
        "sections[main].tracks[curves].width_mm": "generic_form"
    }
    assert service.document.title == "Revised"
    curves = service.document.sections[0].tracks[1]
    assert curves.id == "curves"
    assert curves.bindings[0].channel == "GR"


def test_bridge_handles_non_scalar_families_and_canonical_clear_markers() -> None:
    """Compile every child branch without domain-specific packet assumptions."""
    service = AuthoringService(
        AuthoringDocumentSpec(
            name="object-families",
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
                            "width_mm": 30,
                            "bindings": [
                                {"binding_id": "gr-1", "channel": "GR"},
                                {"binding_id": "sp-1", "channel": "SP"},
                            ],
                            "fills": [
                                {
                                    "fill_id": "fill-1",
                                    "kind": "between_curves",
                                    "binding_id": "gr-1",
                                    "other_binding_id": "sp-1",
                                    "color": "#aaaaaa",
                                }
                            ],
                        },
                        {
                            "id": "array",
                            "title": "Array",
                            "kind": "array",
                            "width_mm": 40,
                            "bindings": [
                                {
                                    "kind": "raster",
                                    "binding_id": "vdl-1",
                                    "channel": "VDL",
                                }
                            ],
                        },
                        {
                            "id": "annotations",
                            "title": "Annotations",
                            "kind": "annotation",
                            "width_mm": 25,
                            "annotations": [
                                {
                                    "kind": "marker",
                                    "annotation_id": "marker-1",
                                    "depth": 100,
                                }
                            ],
                        },
                    ],
                }
            ],
            remarks=[
                {
                    "remark_id": "notes-1",
                    "text": "Original notes",
                }
            ],
        )
    )
    plan = AuthoringReconciliationPlan(
        ready=True,
        operations=[
            AuthoringOperation(
                operation_id="page-update",
                phase=AuthoringOperationPhase.REPORT,
                action=AuthoringOperationAction.UPDATE,
                object_kind=AuthoringOperationObjectKind.PAGE,
                object_id="page",
                payload={"patch": {"continuous": True}},
                reason="Enable continuous output.",
            ),
            AuthoringOperation(
                operation_id="section-update",
                phase=AuthoringOperationPhase.SECTIONS,
                action=AuthoringOperationAction.UPDATE,
                object_kind=AuthoringOperationObjectKind.SECTION,
                object_id="main",
                payload={"patch": {"subtitle": "Updated"}},
                reason="Update the section subtitle.",
            ),
            AuthoringOperation(
                operation_id="track-update",
                phase=AuthoringOperationPhase.TRACKS,
                action=AuthoringOperationAction.UPDATE,
                object_kind=AuthoringOperationObjectKind.TRACK,
                object_id="curves",
                section_id="main",
                payload={"patch": {"width_mm": 32}},
                reason="Update the generic track width.",
            ),
            AuthoringOperation(
                operation_id="curve-clear",
                phase=AuthoringOperationPhase.PRESENTATION,
                action=AuthoringOperationAction.UPDATE,
                object_kind=AuthoringOperationObjectKind.CURVE_BINDING,
                object_id="gr-1",
                section_id="main",
                track_id="curves",
                payload={"patch": {"style": {"operation": "clear"}}},
                reason="Reset one curve style.",
            ),
            AuthoringOperation(
                operation_id="fill-update",
                phase=AuthoringOperationPhase.PRESENTATION,
                action=AuthoringOperationAction.UPDATE,
                object_kind=AuthoringOperationObjectKind.FILL,
                object_id="fill-1",
                section_id="main",
                track_id="curves",
                payload={"patch": {"color": "#00a6a6"}},
                reason="Update a fill color.",
            ),
            AuthoringOperation(
                operation_id="raster-clear",
                phase=AuthoringOperationPhase.PRESENTATION,
                action=AuthoringOperationAction.UPDATE,
                object_kind=AuthoringOperationObjectKind.RASTER_BINDING,
                object_id="vdl-1",
                section_id="main",
                track_id="array",
                payload={"patch": {"style": {"operation": "clear"}}},
                reason="Reset one raster style.",
            ),
            AuthoringOperation(
                operation_id="annotation-update",
                phase=AuthoringOperationPhase.PRESENTATION,
                action=AuthoringOperationAction.UPDATE,
                object_kind=AuthoringOperationObjectKind.ANNOTATION,
                object_id="marker-1",
                section_id="main",
                track_id="annotations",
                payload={
                    "object": {
                        "kind": "marker",
                        "annotation_id": "marker-1",
                        "depth": 110,
                        "label": "Updated",
                    }
                },
                reason="Replace one annotation object.",
            ),
            AuthoringOperation(
                operation_id="remark-update",
                phase=AuthoringOperationPhase.PRESENTATION,
                action=AuthoringOperationAction.UPDATE,
                object_kind=AuthoringOperationObjectKind.REMARK,
                object_id="notes-1",
                payload={"patch": {"text": "Updated notes"}},
                reason="Update report notes.",
            ),
        ],
    )

    compilation = compile_reconciliation_plan(plan, service=service)
    result = execute_typed_submissions(
        service,
        compilation.submissions,
        compilation.work_units,
    )

    assert result.success is True, result.errors
    assert service.document.page.continuous is True
    assert service.document.sections[0].subtitle == "Updated"
    assert service.document.sections[0].tracks[0].width_mm == 32
    assert service.document.sections[0].tracks[0].fills[0].color == "#00a6a6"
    assert service.document.sections[0].tracks[1].bindings[0].style == AuthoringStyle()
    assert service.document.sections[0].tracks[2].annotations[0].depth == 110
    assert service.document.remarks[0].text == "Updated notes"


def test_bridge_uses_discriminated_validation_for_annotation_creation() -> None:
    """Create a typed annotation through the generic bridge."""
    service = AuthoringService(
        AuthoringDocumentSpec(
            name="annotation-create",
            sections=[
                {
                    "id": "main",
                    "title": "Main",
                    "tracks": [
                        {
                            "id": "annotations",
                            "title": "Annotations",
                            "kind": "annotation",
                            "width_mm": 25,
                        }
                    ],
                }
            ],
        )
    )
    plan = AuthoringReconciliationPlan(
        ready=True,
        operations=[
            AuthoringOperation(
                operation_id="create-marker",
                phase=AuthoringOperationPhase.CONTENT,
                action=AuthoringOperationAction.CREATE,
                object_kind=AuthoringOperationObjectKind.ANNOTATION,
                object_id="marker-1",
                section_id="main",
                track_id="annotations",
                payload={
                    "object": {
                        "kind": "marker",
                        "annotation_id": "marker-1",
                        "depth": 100,
                    }
                },
                reason="Create one marker annotation.",
            )
        ],
    )

    compilation = compile_reconciliation_plan(plan, service=service)
    result = execute_typed_submissions(
        service,
        compilation.submissions,
        compilation.work_units,
    )

    assert result.success is True, result.errors
    assert service.document.sections[0].tracks[0].annotations[0].annotation_id == "marker-1"
