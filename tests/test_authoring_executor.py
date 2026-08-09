"""Tests for deterministic execution and checkpoints."""

from __future__ import annotations

from wellplot.authoring_executor import (
    AuthoringExecutionStatus,
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
from wellplot.authoring_service import AuthoringService
from wellplot.model import AuthoringDocumentIntent, AuthoringDocumentSpec


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
