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
                "tracks": [
                    {"id": "curves", "title": "Curves", "kind": "normal", "width_mm": 25}
                ],
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
