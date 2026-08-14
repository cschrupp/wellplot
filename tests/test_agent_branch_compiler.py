"""Tests for direct parent-scoped branch-operation compilation."""

from __future__ import annotations

import json
from types import SimpleNamespace

import anyio

from wellplot.agent.branch_compiler import (
    BranchOperationGroup,
    build_branch_operation_groups,
    compile_direct_branch_operations,
)
from wellplot.agent.compilation import (
    AuthoringRequestInventory,
    AuthoringRequestWorkUnit,
    branch_operation_submission_model,
    build_request_manifest,
    build_request_work_units,
)


def _remark_group(*, parent_scope: str | None = None) -> BranchOperationGroup:
    """Build one report work unit for direct compiler tests."""
    unit = AuthoringRequestWorkUnit(
        unit_id="unit-request-001" if parent_scope is None else "unit-request-002",
        request_item_id="request-001" if parent_scope is None else "request-002",
        clause_text="Add one concise note.",
        status="mapped",
        action="add",
        branch="remarks",
        object_family="remarks",
        natural_parent=parent_scope,
        target="note",
    )
    return BranchOperationGroup(
        scope="report",
        parent_scope=parent_scope,
        work_units=(unit,),
        context={"selected_parent": {"object_kind": "report", "object_id": "report"}},
    )


def _remark_submission(
    *, operation_id: str, work_unit_id: str, depends_on: list[str] | None = None
) -> dict[str, object]:
    """Build a valid direct report operation payload."""
    operation: dict[str, object] = {
        "operation_id": operation_id,
        "work_unit_id": work_unit_id,
        "action": "create",
        "request": {
            "kind": "remark",
            "remark": {
                "remark_id": operation_id,
                "title": "Notes",
                "text": "A concise note.",
            },
        },
    }
    if depends_on:
        operation["depends_on"] = depends_on
    return {
        "branch": "report",
        "operations": [operation],
        "coverage": [
            {
                "unit_id": work_unit_id,
                "status": "mapped",
                "operation_ids": [operation_id],
            }
        ],
    }


class _RecordedDirectBackend:
    """Provider double that records scoped direct-compiler calls."""

    provider = "fixture"
    model = "fixture-model"
    credential_source = "fixture"
    supports_desired_state = True

    def __init__(self, *, correction: bool = False) -> None:
        self.correction = correction
        self.calls = 0
        self.messages: list[str] = []
        self.tool_names: list[str] = []

    async def run_authoring(self, **kwargs: object) -> object:
        """Submit one valid operation, optionally after one invalid attempt."""
        self.calls += 1
        tool_name = str(kwargs["required_tool_name"])
        self.tool_names.append(tool_name)
        self.messages.append(str(kwargs["initial_user_message"]))
        tool_caller = kwargs["tool_caller"]
        work_unit_id = "unit-request-001" if self.calls == 1 else "unit-request-002"
        operation_id = "note-1" if self.calls == 1 else "note-2"
        if self.correction:
            first = await tool_caller(
                tool_name,
                {
                    "branch": "report",
                    "operations": [],
                    "coverage": [],
                },
            )
            assert first["is_error"] is True
        accepted = await tool_caller(
            tool_name,
            _remark_submission(
                operation_id=operation_id,
                work_unit_id=work_unit_id,
                depends_on=["note-1"] if self.calls == 2 else None,
            ),
        )
        assert accepted["accepted"] is True
        return SimpleNamespace(final_text="Direct operations submitted.", tool_trace=())


def test_direct_compiler_groups_work_by_canonical_scope_and_parent() -> None:
    """Keep section, track, and binding work in distinct generic groups."""
    manifest = build_request_manifest(
        "- Add a repeat section.\n"
        "- Add a curves track to the repeat section.\n"
        "- Add GR to the curves track."
    )
    inventory = AuthoringRequestInventory.model_validate(
        {
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
    )
    units = build_request_work_units(manifest, inventory)

    groups = build_branch_operation_groups(
        units,
        context={"parent_snapshots": {"repeat section": {"id": "repeat"}}},
    )

    assert [(group.scope, group.parent_scope) for group in groups] == [
        ("structure", None),
        ("structure", "repeat section"),
        ("scalar", "curves track"),
    ]
    assert groups[1].context["selected_parent"] == {"id": "repeat"}


def test_direct_compiler_uses_only_one_branch_schema() -> None:
    """Do not expose full-document or unrelated scientific operation schemas."""
    schema = branch_operation_submission_model("report").model_json_schema()
    schema_text = json.dumps(schema)

    assert "curve_binding" not in schema_text
    assert "raster_binding" not in schema_text
    assert "AuthoringDocumentIntent" not in schema_text


def test_direct_compiler_accepts_valid_submission_for_typed_execution() -> None:
    """Return validated operations without mutating or invoking MCP."""
    backend = _RecordedDirectBackend()
    result = anyio.run(compile_direct_branch_operations, backend, (_remark_group(),))

    assert result.success is True
    assert len(result.submissions) == 1
    assert result.submissions[0].operations[0].operation_id == "note-1"
    assert result.blocked_reasons == ()
    assert backend.tool_names == ["submit_report_operations"]
    assert "request_items" in backend.messages[0]
    assert "selected_parent" in backend.messages[0]


def test_direct_compiler_allows_one_bounded_correction() -> None:
    """Record the invalid attempt while returning only the corrected submission."""
    backend = _RecordedDirectBackend(correction=True)
    result = anyio.run(compile_direct_branch_operations, backend, (_remark_group(),))

    assert result.success is True
    assert backend.calls == 1
    assert len(result.correction_errors) == 1
    assert result.correction_errors[0]["scope"] == "report"
    assert result.submissions[0].operations[0].operation_id == "note-1"


def test_direct_compiler_passes_prior_operation_ids_to_child_groups() -> None:
    """Expose resolved prior operation identities without merging parent groups."""
    backend = _RecordedDirectBackend()
    groups = (_remark_group(), _remark_group(parent_scope="notes"))

    result = anyio.run(compile_direct_branch_operations, backend, groups)

    assert result.success is True
    assert len(result.submissions) == 2
    assert "available_operation_ids" in backend.messages[1]
    assert "note-1" in backend.messages[1]
    assert "resolved_parent_objects" in backend.messages[1]
    assert result.submissions[1].operations[0].depends_on == ["note-1"]
