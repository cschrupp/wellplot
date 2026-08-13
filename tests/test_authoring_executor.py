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
