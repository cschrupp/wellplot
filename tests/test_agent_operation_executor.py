"""Tests for transactional hierarchy-operation execution."""

from __future__ import annotations

from wellplot.agent.compilation import (
    AuthoringRequestWorkUnit,
    branch_operation_submission_model,
    build_request_manifest,
    build_request_work_units,
)
from wellplot.agent.operation_executor import (
    TypedOperationExecutionStatus,
    execute_typed_submissions,
)
from wellplot.authoring_service import AuthoringService
from wellplot.model.authoring import AuthoringDocumentSpec


def _service() -> AuthoringService:
    """Build a minimal canonical report for transaction tests."""
    return AuthoringService(
        AuthoringDocumentSpec(
            name="operation-executor-test",
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
                        },
                        {
                            "id": "notes",
                            "title": "Notes",
                            "kind": "normal",
                            "width_mm": 10,
                        },
                    ],
                }
            ],
        )
    )


def _work_units() -> tuple[AuthoringRequestWorkUnit, ...]:
    """Create parent and child work units in one natural request order."""
    manifest = build_request_manifest(
        "- Add a repeat section.\n"
        "- Add a curves track to the repeat section.\n"
        "- Add GR to the curves track."
    )
    inventory = {
        "items": [
            {
                "request_item_id": "request-001",
                "status": "mapped",
                "action": "add",
                "object_family": "section",
                "target": "repeat",
            },
            {
                "request_item_id": "request-002",
                "status": "mapped",
                "action": "add",
                "object_family": "track",
                "target": "curves",
                "natural_parent": "repeat section",
            },
            {
                "request_item_id": "request-003",
                "status": "mapped",
                "action": "add",
                "object_family": "curve_binding",
                "target": "GR",
                "natural_parent": "curves track",
            },
        ]
    }
    from wellplot.agent.compilation import AuthoringRequestInventory

    return build_request_work_units(manifest, AuthoringRequestInventory.model_validate(inventory))


def _submissions() -> tuple[object, object]:
    """Build structure and scalar submissions with a cross-branch dependency."""
    structure_model = branch_operation_submission_model("structure")
    scalar_model = branch_operation_submission_model("scalar")
    structure = structure_model.model_validate(
        {
            "branch": "structure",
            "operations": [
                {
                    "operation_id": "create-repeat",
                    "work_unit_id": "unit-request-001",
                    "action": "create",
                    "request": {
                        "kind": "section",
                        "section": {
                            "id": "repeat",
                            "title": "Repeat",
                            "tracks": [
                                {
                                    "id": "depth",
                                    "title": "Depth",
                                    "kind": "reference",
                                    "width_mm": 20,
                                }
                            ],
                        },
                    },
                },
                {
                    "operation_id": "create-curves",
                    "work_unit_id": "unit-request-002",
                    "depends_on": ["create-repeat"],
                    "action": "create",
                    "request": {
                        "kind": "track",
                        "section_id": "repeat",
                        "track": {
                            "id": "curves",
                            "title": "Curves",
                            "kind": "normal",
                            "width_mm": 30,
                        },
                    },
                },
            ],
            "coverage": [
                {
                    "unit_id": "unit-request-001",
                    "status": "mapped",
                    "operation_ids": ["create-repeat"],
                },
                {
                    "unit_id": "unit-request-002",
                    "status": "mapped",
                    "operation_ids": ["create-curves"],
                },
            ],
        }
    )
    scalar = scalar_model.model_validate(
        {
            "branch": "scalar",
            "operations": [
                {
                    "operation_id": "bind-gr",
                    "work_unit_id": "unit-request-003",
                    "depends_on": ["create-curves"],
                    "action": "create",
                    "request": {
                        "kind": "curve_binding",
                        "section_id": "repeat",
                        "track_id": "curves",
                        "binding": {
                            "binding_id": "gr-1",
                            "channel": "GR",
                        },
                    },
                }
            ],
            "coverage": [
                {"unit_id": "unit-request-003", "status": "mapped", "operation_ids": ["bind-gr"]}
            ],
        }
    )
    return structure, scalar


def _move_submission() -> tuple[object, tuple[AuthoringRequestWorkUnit, ...]]:
    """Build one track move submission with a matching work unit."""
    manifest = build_request_manifest("- Move the notes track before the depth track.")
    from wellplot.agent.compilation import AuthoringRequestInventory

    inventory = AuthoringRequestInventory.model_validate(
        {
            "items": [
                {
                    "request_item_id": "request-001",
                    "status": "mapped",
                    "action": "update",
                    "object_family": "track",
                    "target": "notes",
                    "natural_parent": "main section",
                }
            ]
        }
    )
    work_units = build_request_work_units(manifest, inventory)
    submission_model = branch_operation_submission_model("structure")
    submission = submission_model.model_validate(
        {
            "branch": "structure",
            "operations": [
                {
                    "operation_id": "move-notes",
                    "work_unit_id": "unit-request-001",
                    "action": "move",
                    "request": {
                        "object_kind": "track",
                        "object_id": "notes",
                        "section_id": "main",
                        "new_index": 0,
                    },
                }
            ],
            "coverage": [
                {"unit_id": "unit-request-001", "status": "mapped", "operation_ids": ["move-notes"]}
            ],
        }
    )
    return submission, work_units


def test_typed_submissions_execute_parent_first_and_read_back() -> None:
    """Execute structure before scalar content across branch submissions."""
    result = execute_typed_submissions(_service(), _submissions(), _work_units())

    assert result.success is True
    assert [outcome.operation_id for outcome in result.outcomes] == [
        "create-repeat",
        "create-curves",
        "bind-gr",
    ]
    assert all(outcome.postcondition_verified for outcome in result.outcomes)
    repeat = next(section for section in result.document.sections if section.id == "repeat")
    curves = next(track for track in repeat.tracks if track.id == "curves")
    assert curves.bindings[0].channel == "GR"


def test_typed_submissions_roll_back_when_descendant_fails() -> None:
    """Do not publish parent mutations when a child operation is blocked."""
    service = _service()
    structure, scalar = _submissions()
    scalar_payload = scalar.model_dump(mode="json")
    scalar_payload["operations"][0]["request"]["track_id"] = "missing"
    scalar = type(scalar).model_validate(scalar_payload)

    result = execute_typed_submissions(service, (structure, scalar), _work_units())

    assert result.success is False
    assert result.stopped is True
    assert result.outcomes[-1].status == TypedOperationExecutionStatus.BLOCKED
    assert [section.id for section in service.document.sections] == ["main"]


def test_typed_submissions_are_idempotent_for_existing_targets() -> None:
    """Repeat an accepted submission without duplicating canonical objects."""
    service = _service()
    submissions = _submissions()
    first = execute_typed_submissions(service, submissions, _work_units())
    second = execute_typed_submissions(service, submissions, _work_units())

    assert first.success is True
    assert second.success is True
    assert all(
        outcome.status == TypedOperationExecutionStatus.SKIPPED for outcome in second.outcomes
    )
    repeat_sections = [section for section in service.document.sections if section.id == "repeat"]
    assert len(repeat_sections) == 1
    assert [track.id for track in repeat_sections[0].tracks].count("curves") == 1


def test_typed_create_conflict_does_not_overwrite_existing_object() -> None:
    """Reject a same-id create whose payload differs from the persisted object."""
    service = _service()
    submissions = _submissions()
    first = execute_typed_submissions(service, submissions, _work_units())
    assert first.success is True

    structure_payload = submissions[0].model_dump(mode="json")
    structure_payload["operations"][1]["request"]["track"]["title"] = "Other Curves"
    conflicting_structure = type(submissions[0]).model_validate(structure_payload)
    result = execute_typed_submissions(
        service,
        (conflicting_structure, submissions[1]),
        _work_units(),
    )

    assert result.success is False
    assert "conflicts with existing track 'curves'" in result.errors[0]
    repeat = next(section for section in service.document.sections if section.id == "repeat")
    curves = next(track for track in repeat.tracks if track.id == "curves")
    assert curves.title == "Curves"


def test_typed_move_verifies_new_collection_index() -> None:
    """Verify moves through the canonical collection reference after mutation."""
    service = _service()
    submission, work_units = _move_submission()

    result = execute_typed_submissions(service, (submission,), work_units)

    assert result.success is True
    assert result.outcomes[0].postcondition_verified is True
    assert [track.id for track in result.document.sections[0].tracks] == ["notes", "depth"]
