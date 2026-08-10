"""Tests for provider-neutral desired-state reconciliation."""

from __future__ import annotations

from wellplot.authoring_reconciler import (
    AuthoringOperationPhase,
    reconcile_authoring,
)
from wellplot.model import AuthoringDocumentIntent, AuthoringDocumentSpec


def _document() -> AuthoringDocumentSpec:
    """Build a small multi-form document for reconciliation tests."""
    return AuthoringDocumentSpec(
        name="reconcile-test",
        sections=[
            {
                "id": "main",
                "title": "Main",
                "tracks": [
                    {
                        "id": "curves",
                        "title": "Curves",
                        "kind": "normal",
                        "width_mm": 25,
                        "bindings": [
                            {
                                "binding_id": "gr-1",
                                "channel": "GR",
                                "style": {"color": "black"},
                            }
                        ],
                    },
                    {"id": "vdl", "title": "VDL", "kind": "array", "width_mm": 35},
                ],
            },
            {
                "id": "repeat",
                "title": "Repeat",
                "tracks": [{"id": "curves", "title": "Curves", "kind": "normal", "width_mm": 25}],
            },
        ],
    )


def test_reconciler_orders_content_after_structure_and_preserves_duplicates() -> None:
    """Plan track structure before duplicate bindings and dependent fills."""
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "main",
                "tracks": [
                    {
                        "track_id": "curves",
                        "width_mm": 30,
                        "bindings": [
                            {
                                "kind": "curve",
                                "binding_id": "gr-1",
                                "channel": "GR",
                                "style": {"color": "blue", "line_style": "--"},
                            },
                            {
                                "kind": "curve",
                                "binding_id": "gr-2",
                                "channel": "GR",
                                "style": {"color": "red"},
                            },
                        ],
                        "fills": [
                            {
                                "fill_id": "gr-fill",
                                "kind": "between_instances",
                                "binding_id": "gr-1",
                                "other_binding_id": "gr-2",
                                "color": "tan",
                            }
                        ],
                    }
                ],
            }
        ]
    )

    plan = reconcile_authoring(
        intent,
        existing=_document(),
        available_channels={"main": ["GR"]},
    )

    assert plan.ready is True
    assert [operation.phase for operation in plan.operations] == [
        AuthoringOperationPhase.TRACKS,
        AuthoringOperationPhase.BINDINGS,
        AuthoringOperationPhase.CONTENT,
        AuthoringOperationPhase.PRESENTATION,
    ]
    assert [
        operation.object_id
        for operation in plan.operations
        if operation.object_kind == "curve_binding"
    ] == ["gr-2", "gr-1"]
    fill = next(operation for operation in plan.operations if operation.object_kind == "fill")
    assert fill.phase == AuthoringOperationPhase.CONTENT
    assert len(fill.depends_on) == 1
    assert plan.operations[-1].payload == {
        "patch": {"style": {"color": "blue", "line_style": "--"}}
    }


def test_reconciler_is_idempotent_for_matching_values() -> None:
    """Do not emit mutations when explicit desired values already match."""
    intent = AuthoringDocumentIntent(
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
                                "style": {"color": "black"},
                            }
                        ],
                    }
                ],
            }
        ]
    )

    plan = reconcile_authoring(
        intent,
        existing=_document(),
        available_channels={"main": ["GR"]},
    )

    assert plan.ready is True
    assert plan.operations == []
    assert "sections[main].tracks[curves].structure" in plan.unchanged_paths
    assert "sections[main].tracks[curves].bindings[gr-1]" in plan.unchanged_paths


def test_reconciler_reports_exact_missing_track_form_fields() -> None:
    """Explain which user-facing track properties remain unresolved."""
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "main",
                "tracks": [{"track_id": "new_track"}],
            }
        ]
    )

    plan = reconcile_authoring(intent, existing=_document())

    assert plan.ready is False
    issue = next(issue for issue in plan.issues if issue.code == "track_create_incomplete")
    assert issue.message == (
        "Cannot create track 'new_track': missing display title, track form, track width. "
        "These values could not be resolved from the request, existing draft, or generic "
        "form defaults."
    )
    assert "width_mm" not in issue.message


def test_reconciler_reports_only_the_unresolved_track_form() -> None:
    """Do not report fields that the request already supplied."""
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "main",
                "tracks": [
                    {"track_id": "new_track", "title": "New Track", "width_mm": 24}
                ],
            }
        ]
    )

    plan = reconcile_authoring(intent, existing=_document())

    issue = next(issue for issue in plan.issues if issue.code == "track_create_incomplete")
    assert issue.message.startswith("Cannot create track 'new_track': missing track form.")


def test_reconciler_creates_track_from_nested_and_root_binding_references() -> None:
    """Create a new track when the provider repeats binding data at root scope."""
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "main",
                "tracks": [
                    {
                        "track_id": "resistivity",
                        "title": "Resistivity",
                        "kind": "normal",
                        "width_mm": 30,
                        "x_scale": {
                            "kind": "log",
                            "minimum": 0.2,
                            "maximum": 2000,
                        },
                        "bindings": [
                            {
                                "kind": "curve",
                                "binding_id": "main.resistivity.ILD.1",
                                "channel": "ILD",
                            }
                        ],
                    }
                ],
            }
        ],
        curve_bindings=[
            {
                "kind": "curve",
                "binding_id": "main.resistivity.ILD.1",
                "section_id": "main",
                "track_id": "resistivity",
                "style": {"color": "black", "line_width": 1.1},
            }
        ],
    )

    plan = reconcile_authoring(
        intent,
        existing=_document(),
        available_channels={"main": [{"mnemonic": "ILD", "kind": "scalar"}]},
    )

    assert plan.ready is True
    assert any(
        operation.object_kind == "track" and operation.object_id == "resistivity"
        for operation in plan.operations
    )
    binding = next(
        operation
        for operation in plan.operations
        if operation.object_kind == "curve_binding"
    )
    assert binding.payload["object"]["style"] == {
        "color": "black",
        "line_width": 1.1,
    }


def test_reconciler_blocks_unsupported_kind_and_channel_changes() -> None:
    """Report immutable structural changes instead of inventing replacements."""
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "main",
                "tracks": [
                    {
                        "track_id": "curves",
                        "kind": "reference",
                        "bindings": [
                            {
                                "kind": "curve",
                                "binding_id": "gr-1",
                                "channel": "SP",
                            }
                        ],
                    }
                ],
            }
        ]
    )

    plan = reconcile_authoring(
        intent,
        existing=_document(),
        available_channels={"main": ["GR", "SP"]},
    )

    assert plan.ready is False
    assert {issue.code for issue in plan.issues} == {
        "track_kind_change_unsupported",
        "binding_channel_change_unsupported",
    }
    assert plan.operations == []


def test_reconciler_turns_explicit_child_clear_into_final_removals() -> None:
    """Keep explicit collection clears distinct from omitted child collections."""
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "main",
                "tracks": [
                    {
                        "track_id": "curves",
                        "bindings": {"operation": "clear"},
                    }
                ],
            }
        ]
    )

    plan = reconcile_authoring(intent, existing=_document())

    assert plan.ready is True
    assert len(plan.operations) == 1
    assert plan.operations[0].action.value == "remove"
    assert plan.operations[0].object_kind == "curve_binding"
    assert plan.operations[0].phase == AuthoringOperationPhase.FINALIZE


def test_reconciler_handles_arbitrary_new_sections_and_order_moves() -> None:
    """Keep section IDs generic and plan ordering independently of main/repeat names."""
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "interpretation",
                "title": "Interpretation",
                "tracks": [
                    {
                        "track_id": "notes",
                        "title": "Notes",
                        "kind": "annotation",
                        "width_mm": 18,
                    }
                ],
            },
            {"section_id": "main", "tracks": []},
        ]
    )

    plan = reconcile_authoring(intent, existing=_document())

    assert plan.ready is True
    assert plan.operations[0].object_kind == "section"
    assert plan.operations[0].object_id == "interpretation"
    assert any(
        operation.action.value == "move" and operation.object_kind == "section"
        for operation in plan.operations
    )


def test_reconciler_assembles_new_sections_in_dependency_order() -> None:
    """Create a section bootstrap, then tracks, bindings, and content in order."""
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "packet_pass",
                "title": "Packet Pass",
                "tracks": [
                    {
                        "track_id": "curves",
                        "title": "Curves",
                        "kind": "normal",
                        "width_mm": 24,
                        "bindings": [
                            {"kind": "curve", "binding_id": "gr-1", "channel": "GR"},
                            {"kind": "curve", "binding_id": "gr-2", "channel": "GR"},
                        ],
                        "fills": [
                            {
                                "fill_id": "gr-fill",
                                "kind": "between_instances",
                                "binding_id": "gr-1",
                                "other_binding_id": "gr-2",
                                "color": "tan",
                            }
                        ],
                    },
                    {
                        "track_id": "waveform",
                        "title": "Waveform",
                        "kind": "array",
                        "width_mm": 30,
                        "bindings": [{"kind": "raster", "binding_id": "vdl", "channel": "VDL"}],
                    },
                    {
                        "track_id": "markers",
                        "title": "Markers",
                        "kind": "annotation",
                        "width_mm": 18,
                        "annotations": [
                            {
                                "annotation_id": "top-marker",
                                "annotation": {
                                    "kind": "marker",
                                    "annotation_id": "top-marker",
                                    "depth": 1000,
                                },
                            }
                        ],
                    },
                ],
            }
        ]
    )

    plan = reconcile_authoring(
        intent,
        existing=_document(),
        available_channels={
            "packet_pass": [
                {"mnemonic": "GR", "kind": "scalar"},
                {"mnemonic": "VDL", "kind": "raster"},
            ]
        },
    )

    assert plan.ready is True
    assert list(dict.fromkeys(operation.phase for operation in plan.operations)) == [
        AuthoringOperationPhase.SECTIONS,
        AuthoringOperationPhase.TRACKS,
        AuthoringOperationPhase.BINDINGS,
        AuthoringOperationPhase.CONTENT,
    ]
    section_operation = plan.operations[0]
    assert [track["id"] for track in section_operation.payload["object"]["tracks"]] == ["curves"]
    track_operations = [
        operation for operation in plan.operations if operation.object_kind == "track"
    ]
    assert [operation.object_id for operation in track_operations] == ["waveform", "markers"]
    assert all(
        section_operation.operation_id in operation.depends_on for operation in track_operations
    )
    binding_operations = [
        operation
        for operation in plan.operations
        if operation.object_kind in {"curve_binding", "raster_binding"}
    ]
    assert [operation.object_id for operation in binding_operations] == ["gr-1", "gr-2", "vdl"]
    assert binding_operations[0].depends_on == [section_operation.operation_id]
    assert binding_operations[2].depends_on == [track_operations[0].operation_id]
    content_operations = [
        operation
        for operation in plan.operations
        if operation.phase == AuthoringOperationPhase.CONTENT
    ]
    assert [operation.object_id for operation in content_operations] == ["gr-fill", "top-marker"]
    assert content_operations[0].depends_on == [
        operation.operation_id for operation in binding_operations[:2]
    ]
    assert content_operations[1].depends_on == [track_operations[1].operation_id]
