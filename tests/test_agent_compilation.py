"""Tests for typed request compilation and bounded intent correction."""

from __future__ import annotations

import json
from functools import partial
from pathlib import Path
from types import SimpleNamespace

import anyio
import pytest

import wellplot.agent.compilation as compilation_module
from wellplot.agent import AuthoringSession
from wellplot.agent.compilation import (
    AuthoringAnnotationIntentSubmission,
    AuthoringIntentCoverage,
    AuthoringIntentSubmission,
    AuthoringRasterIntentSubmission,
    AuthoringReportIntentSubmission,
    AuthoringRequestInventory,
    AuthoringRequestInventoryItem,
    AuthoringRequestWorkUnit,
    AuthoringScalarIntentSubmission,
    AuthoringStructureIntentSubmission,
    branch_operation_submission_model,
    build_request_manifest,
    build_request_work_units,
    group_request_inventory,
    merge_scoped_intents,
    scoped_submission_model,
    validate_intent_coverage,
    validate_operation_submission,
    validate_reconciliation_fulfillment,
    validate_request_inventory,
    validate_scoped_intent_semantics,
)
from wellplot.agent.core import AuthoringToolCall, ProviderAdapterError
from wellplot.authoring_context import AuthoringContextSnapshot
from wellplot.model.intent import AuthoringDocumentIntent


def test_request_manifest_assigns_stable_items_to_bulleted_requests() -> None:
    """Keep request coverage identifiers stable for one prompt shape."""
    manifest = build_request_manifest(
        """
        Build the supported report.

        Data Sources:
        - main: main.dlis
        - repeat: repeat.dlis

        - Add a VDL array track.
        - Use the explicit blue dashed curve style.
        """
    )

    assert [item.item_id for item in manifest.items] == [
        "request-001",
        "request-002",
        "request-003",
        "request-004",
        "request-005",
        "request-006",
    ]
    assert manifest.items[1].text == "Data Sources:"
    assert manifest.items[2].text == "main: main.dlis"
    assert manifest.items[5].text == "Use the explicit blue dashed curve style."


def test_intent_coverage_reports_missing_and_invalid_items() -> None:
    """Reject a provider submission that cannot account for the full request."""
    manifest = build_request_manifest("- Set the title.\n- Add the CBL track.")
    coverage = [
        AuthoringIntentCoverage(
            unit_id="unit-request-001",
            status="mapped",
        ),
        AuthoringIntentCoverage(
            unit_id="unit-request-999",
            status="mapped",
        ),
    ]

    errors = validate_intent_coverage(manifest, coverage)

    assert any("unknown work unit" in error for error in errors)
    assert any("Missing coverage" in error for error in errors)


def test_scoped_semantics_rejects_add_request_that_clears_remarks() -> None:
    """Do not accept a coverage claim that clears the requested report content."""
    inventory = [
        AuthoringRequestInventoryItem(
            request_item_id="request-001",
            status="mapped",
            action="add",
            object_family="remarks",
        )
    ]
    submission = AuthoringReportIntentSubmission.model_validate(
        {
            "intent": {"remarks": {"operation": "clear"}},
            "coverage": [
                {
                    "unit_id": "unit-request-001",
                    "status": "mapped",
                }
            ],
        }
    )

    errors = validate_scoped_intent_semantics(
        inventory,
        submission.intent,
        submission.coverage,
    )

    assert errors == [
        "Request 'unit-request-001' adds 'remarks', but the submitted intent explicitly "
        "clears 'remarks'."
    ]


def test_scoped_semantics_accepts_add_request_with_populated_remark() -> None:
    """Allow a normal populated report object to satisfy an add request."""
    inventory = [
        AuthoringRequestInventoryItem(
            request_item_id="request-001",
            status="mapped",
            action="add",
            object_family="remarks",
        )
    ]
    submission = AuthoringReportIntentSubmission.model_validate(
        {
            "intent": {
                "remarks": [
                    {
                        "remark_id": "quicklook_note",
                        "title": "Notes",
                        "text": "This quicklook is an iterative interpretation artifact.",
                    }
                ]
            },
            "coverage": [
                {
                    "unit_id": "unit-request-001",
                    "status": "mapped",
                }
            ],
        }
    )

    assert (
        validate_scoped_intent_semantics(
            inventory,
            submission.intent,
            submission.coverage,
        )
        == []
    )


def test_reconciliation_fulfillment_rejects_incompatible_actions_generically() -> None:
    """Keep add requests from being satisfied by removals across object families."""
    inventory = [
        AuthoringRequestInventoryItem(
            request_item_id="request-001",
            status="mapped",
            action="add",
            object_family="remarks",
        ),
        AuthoringRequestInventoryItem(
            request_item_id="request-002",
            status="mapped",
            action="add",
            object_family="track",
        ),
        AuthoringRequestInventoryItem(
            request_item_id="request-003",
            status="mapped",
            action="add",
            object_family="curve_binding",
        ),
    ]
    operations = [
        {"object_kind": "remark", "action": "remove"},
        {"object_kind": "track", "action": "remove"},
        {"object_kind": "curve_binding", "action": "remove"},
    ]

    errors = validate_reconciliation_fulfillment(inventory, operations)

    assert len(errors) == 3
    assert "request-001" in errors[0]
    assert "request-002" in errors[1]
    assert "request-003" in errors[2]


def test_request_inventory_is_compact_and_covers_object_families() -> None:
    """Keep the first-stage provider contract independent of the full intent graph."""
    manifest = build_request_manifest(
        "- Add SP to the overview track.\n- Add a logarithmic resistivity track."
    )
    inventory = AuthoringRequestInventory(
        items=[
            {
                "request_item_id": "request-001",
                "status": "mapped",
                "action": "update",
                "object_family": "curve_binding",
                "target": "SP",
                "parent_scope": "overview track",
                "explicit_values": {"scale": {"minimum": -80, "maximum": 20}},
            },
            {
                "request_item_id": "request-002",
                "status": "mapped",
                "action": "add",
                "object_family": "track",
                "target": "resistivity",
                "explicit_values": {"scale_kind": "logarithmic"},
            },
        ]
    )

    assert validate_request_inventory(manifest, inventory.items) == []
    schema_chars = len(
        json.dumps(
            AuthoringRequestInventory.model_json_schema(),
            separators=(",", ":"),
        )
    )
    assert schema_chars < 10_000


def test_request_inventory_reports_missing_and_unknown_items() -> None:
    """Reject inventory that cannot account for every natural-language item."""
    manifest = build_request_manifest("- Set the title.\n- Add the remarks block.")
    inventory = [
        AuthoringRequestInventoryItem(
            request_item_id="request-999",
            status="mapped",
            action="set",
            object_family="report",
        )
    ]

    errors = validate_request_inventory(manifest, inventory)

    assert any("unknown request item" in error for error in errors)
    assert any("Missing inventory" in error for error in errors)


def test_request_inventory_groups_canonical_object_families() -> None:
    """Route by canonical object role rather than scientific log family."""
    inventory = AuthoringRequestInventory(
        items=[
            {
                "request_item_id": "request-003",
                "status": "mapped",
                "action": "add",
                "object_family": "curve_binding",
            },
            {
                "request_item_id": "request-002",
                "status": "mapped",
                "action": "add",
                "object_family": "track",
            },
            {
                "request_item_id": "request-001",
                "status": "mapped",
                "action": "set",
                "object_family": "page",
            },
            {
                "request_item_id": "request-004",
                "status": "mapped",
                "action": "add",
                "object_family": "raster_binding",
            },
            {
                "request_item_id": "request-005",
                "status": "mapped",
                "action": "add",
                "object_family": "annotation",
            },
            {
                "request_item_id": "request-006",
                "status": "unsupported",
                "action": "explain",
                "object_family": "unknown",
                "reason": "Not represented by the canonical object model.",
            },
        ]
    )

    grouped = group_request_inventory(inventory)

    assert list(grouped) == [
        "report",
        "structure",
        "scalar",
        "raster",
        "annotation",
    ]
    assert grouped["scalar"][0].request_item_id == "request-003"
    assert all(
        item.request_item_id != "request-006" for items in grouped.values() for item in items
    )


def test_request_work_units_preserve_clause_and_hierarchy_context() -> None:
    """Keep each natural-language clause isolated for its parent compiler."""
    manifest = build_request_manifest(
        "- Fill the Company header value.\n"
        "- Add a resistivity track after depth.\n"
        "- Do not add remarks."
    )
    inventory = AuthoringRequestInventory(
        items=[
            {
                "request_item_id": "request-001",
                "status": "mapped",
                "action": "update",
                "object_family": "header_slot",
                "target": "Company",
                "natural_parent": "open-hole header",
                "preserve_constraints": ["keep all other header slots"],
            },
            {
                "request_item_id": "request-002",
                "status": "mapped",
                "action": "add",
                "object_family": "track",
                "target": "resistivity",
                "natural_parent": "main section",
                "dependencies": ["depth track"],
            },
            {
                "request_item_id": "request-003",
                "status": "preserved",
                "action": "preserve",
                "object_family": "remarks",
                "preserve_constraints": ["do not create or replace remarks"],
            },
        ]
    )

    units = build_request_work_units(manifest, inventory)

    assert isinstance(units[0], AuthoringRequestWorkUnit)
    assert [unit.unit_id for unit in units] == [
        "unit-request-001",
        "unit-request-002",
        "unit-request-003",
    ]
    assert units[0].branch == "header"
    assert units[0].clause_text == "Fill the Company header value."
    assert units[0].natural_parent == "open-hole header"
    assert units[0].preserve_constraints == ["keep all other header slots"]
    assert units[1].branch == "track"
    assert units[1].dependencies == ["depth track"]
    assert units[2].status == "preserved"


def test_request_work_unit_derives_canonical_hierarchy_branch() -> None:
    """Derive hierarchy ownership from the canonical object family."""
    manifest = build_request_manifest("- Add a resistivity track.")
    inventory = AuthoringRequestInventory(
        items=[
            {
                "request_item_id": "request-001",
                "status": "mapped",
                "action": "add",
                "object_family": "track",
            }
        ]
    )

    assert validate_request_inventory(manifest, inventory.items) == []
    units = build_request_work_units(manifest, inventory)
    assert units[0].branch == "track"


def test_provider_contract_uses_work_units_without_yaml_paths_or_branches() -> None:
    """Keep hierarchy and intent paths out of provider-authored contracts."""
    inventory_fields = AuthoringRequestInventoryItem.model_fields
    coverage_fields = AuthoringIntentCoverage.model_fields

    assert "top_level_branch" not in inventory_fields
    assert "intent_paths" not in coverage_fields
    assert set(coverage_fields) == {"unit_id", "status", "reason"}


def test_branch_operation_contract_is_parent_scoped_and_typed() -> None:
    """Accept a typed track operation while excluding unrelated bindings."""
    manifest = build_request_manifest("- Add a resistivity track after depth.")
    inventory = AuthoringRequestInventory(
        items=[
            {
                "request_item_id": "request-001",
                "status": "mapped",
                "action": "add",
                "object_family": "track",
                "target": "resistivity",
                "natural_parent": "main section",
                "dependencies": ["depth track"],
            }
        ]
    )
    work_units = build_request_work_units(manifest, inventory)
    submission_model = branch_operation_submission_model("structure")
    submission = submission_model.model_validate(
        {
            "branch": "structure",
            "operations": [
                {
                    "operation_id": "create-resistivity",
                    "work_unit_id": "unit-request-001",
                    "action": "create",
                    "request": {
                        "kind": "track",
                        "section_id": "main",
                        "track": {
                            "id": "resistivity",
                            "title": "Resistivity",
                            "kind": "normal",
                            "width_mm": 35,
                        },
                    },
                }
            ],
            "coverage": [
                {
                    "unit_id": "unit-request-001",
                    "status": "mapped",
                    "operation_ids": ["create-resistivity"],
                }
            ],
        }
    )

    assert validate_operation_submission("structure", submission, work_units) == []
    assert submission.operations[0].request.kind == "track"
    assert "curve_binding" not in submission_model.model_json_schema()["$defs"]


def test_branch_operation_validation_rejects_cross_branch_and_bad_order() -> None:
    """Block bindings in structure scope and dependencies that run too early."""
    work_units = [
        AuthoringRequestWorkUnit(
            unit_id="unit-track",
            request_item_id="request-track",
            clause_text="Add a track.",
            status="mapped",
            action="add",
            branch="track",
            object_family="track",
        ),
        AuthoringRequestWorkUnit(
            unit_id="unit-section",
            request_item_id="request-section",
            clause_text="Add a section.",
            status="mapped",
            action="add",
            branch="section",
            object_family="section",
        ),
    ]
    submission_model = branch_operation_submission_model("structure")
    submission = submission_model.model_validate(
        {
            "branch": "structure",
            "operations": [
                {
                    "operation_id": "create-track",
                    "work_unit_id": "unit-track",
                    "depends_on": ["create-section"],
                    "action": "create",
                    "request": {
                        "kind": "track",
                        "section_id": "main",
                        "track": {
                            "id": "curves",
                            "title": "Curves",
                            "kind": "normal",
                            "width_mm": 30,
                        },
                    },
                },
                {
                    "operation_id": "create-section",
                    "work_unit_id": "unit-section",
                    "action": "create",
                    "request": {
                        "kind": "section",
                        "section": {
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
                        },
                    },
                },
            ],
            "coverage": [
                {
                    "unit_id": "unit-track",
                    "status": "mapped",
                    "operation_ids": ["create-track"],
                },
                {
                    "unit_id": "unit-section",
                    "status": "mapped",
                    "operation_ids": ["create-section"],
                },
            ],
        }
    )

    errors = validate_operation_submission("structure", submission, work_units)

    assert any("must follow dependency" in error for error in errors)


def test_scoped_submission_schemas_exclude_unrelated_families() -> None:
    """Keep each provider contract substantially smaller than the full graph."""
    full_schema = json.dumps(AuthoringIntentSubmission.model_json_schema())
    scoped_models = (
        AuthoringReportIntentSubmission,
        AuthoringStructureIntentSubmission,
        AuthoringScalarIntentSubmission,
        AuthoringRasterIntentSubmission,
        AuthoringAnnotationIntentSubmission,
    )

    for model in scoped_models:
        assert len(json.dumps(model.model_json_schema())) < len(full_schema) / 2

    structure_properties = AuthoringStructureIntentSubmission.model_json_schema()["$defs"][
        "AuthoringStructureIntentFragment"
    ]["properties"]
    scalar_properties = AuthoringScalarIntentSubmission.model_json_schema()["$defs"][
        "AuthoringScalarIntentFragment"
    ]["properties"]
    report_properties = AuthoringReportIntentSubmission.model_json_schema()["$defs"][
        "AuthoringReportIntentFragment"
    ]["properties"]
    assert "curve_bindings" not in structure_properties
    assert "raster_bindings" not in structure_properties
    assert "header" not in scalar_properties
    assert "raster_bindings" not in scalar_properties
    assert "sections" not in report_properties
    assert scoped_submission_model("scalar") is AuthoringScalarIntentSubmission


def test_scoped_submission_rejects_explicit_nulls_before_canonical_merge() -> None:
    """Return raw nulls to the provider instead of falsely accepting them."""
    with pytest.raises(ValueError, match="Intent field 'subtitle' cannot be null"):
        AuthoringReportIntentSubmission.model_validate(
            {
                "intent": {
                    "subtitle": None,
                    "remarks": [
                        {
                            "remark_id": "source_note",
                            "title": "Source note",
                            "text": "Inspect the source before plotting channels.",
                        }
                    ],
                },
                "coverage": [
                    {
                        "unit_id": "unit-request-001",
                        "status": "mapped",
                    }
                ],
            }
        )


def test_scoped_intents_merge_into_canonical_desired_state() -> None:
    """Preserve explicit values while merging independently validated fragments."""
    report = AuthoringReportIntentSubmission.model_validate(
        {
            "intent": {"title": "Cross-domain report"},
            "coverage": [
                {
                    "unit_id": "unit-request-001",
                    "status": "mapped",
                }
            ],
        }
    )
    structure = AuthoringStructureIntentSubmission.model_validate(
        {
            "intent": {
                "sections": [
                    {
                        "section_id": "main",
                        "tracks": [
                            {
                                "track_id": "measurement",
                                "section_id": "main",
                                "title": "Measurement",
                                "kind": "normal",
                                "width_mm": 24,
                            }
                        ],
                    }
                ]
            },
            "coverage": [
                {
                    "unit_id": "unit-request-002",
                    "status": "mapped",
                }
            ],
        }
    )
    scalar = AuthoringScalarIntentSubmission.model_validate(
        {
            "intent": {
                "curve_bindings": [
                    {
                        "kind": "curve",
                        "binding_id": "main.measurement.signal.1",
                        "section_id": "main",
                        "track_id": "measurement",
                        "channel": "SIGNAL",
                        "label": "Primary signal",
                        "scale": {"kind": "linear", "minimum": -2, "maximum": 8},
                        "style": {
                            "color": "#123456",
                            "line_style": "dashed",
                            "line_width": 1.7,
                        },
                    }
                ]
            },
            "coverage": [
                {
                    "unit_id": "unit-request-003",
                    "status": "mapped",
                }
            ],
        }
    )

    merged = merge_scoped_intents([report.intent, structure.intent, scalar.intent])

    assert merged.title == "Cross-domain report"
    assert merged.sections[0].tracks[0].width_mm == 24
    binding = merged.curve_bindings[0]
    assert binding.label == "Primary signal"
    assert binding.scale.minimum == -2
    assert binding.scale.maximum == 8
    assert binding.style.color == "#123456"
    assert binding.style.line_style == "dashed"
    assert binding.style.line_width == 1.7


def test_scoped_intent_merge_rejects_duplicate_identities() -> None:
    """Stop ambiguous provider output before defaults or reconciliation."""
    scalar = AuthoringScalarIntentSubmission.model_validate(
        {
            "intent": {
                "curve_bindings": [
                    {
                        "kind": "curve",
                        "binding_id": "duplicate",
                        "section_id": "main",
                        "track_id": "left",
                        "channel": "A",
                    },
                    {
                        "kind": "curve",
                        "binding_id": "duplicate",
                        "section_id": "main",
                        "track_id": "right",
                        "channel": "B",
                    },
                ]
            },
            "coverage": [
                {
                    "unit_id": "unit-request-001",
                    "status": "mapped",
                }
            ],
        }
    )

    with pytest.raises(ValueError, match="Duplicate binding_id"):
        merge_scoped_intents([scalar.intent])


class _CorrectionBackend:
    """Provider double that needs one deterministic coverage correction."""

    provider = "fake"
    model = "fake-model"
    credential_source = "test"

    def __init__(self) -> None:
        self.attempts = 0
        self.initial_user_messages: list[str] = []
        self.tool_names: list[str] = []
        self.required_tool_names: list[str | None] = []

    async def run_authoring(self, **kwargs: object) -> object:
        """Submit an invalid first coverage report and a valid correction."""
        self.initial_user_messages.append(str(kwargs["initial_user_message"]))
        tool_name = kwargs["tool_definitions"][0].name
        self.tool_names.append(tool_name)
        self.required_tool_names.append(kwargs.get("required_tool_name"))
        tool_caller = kwargs["tool_caller"]
        assert callable(tool_caller)
        if tool_name == "submit_request_inventory":
            self.attempts += 1
            response = await tool_caller(
                tool_name,
                {
                    "items": [
                        {
                            "request_item_id": "request-001",
                            "status": "mapped",
                            "action": "set",
                            "object_family": "report",
                            "target": "title",
                            "explicit_values": {"value": "Revised"},
                        }
                    ]
                },
            )
            assert response["accepted"] is True
            return SimpleNamespace(final_text="Inventoried request.", tool_trace=())
        assert tool_name == "submit_report_intent"
        self.attempts += 1
        first = await tool_caller(
            tool_name,
            {
                "intent": {"title": "Revised"},
                "coverage": [],
            },
        )
        assert first["is_error"] is True
        self.attempts += 1
        second = await tool_caller(
            tool_name,
            {
                "intent": {"title": "Revised"},
                "coverage": [
                    {
                        "unit_id": "unit-request-001",
                        "status": "mapped",
                    }
                ],
            },
        )
        assert second["accepted"] is True
        return SimpleNamespace(final_text="Compiled typed intent.", tool_trace=())


class _NoToolBackend:
    """Provider double that returns prose without submitting the typed tool."""

    provider = "fake"
    model = "fake-model"
    credential_source = "test"

    async def run_authoring(self, **_: object) -> object:
        """Return a normal prose response with no tool call."""
        return SimpleNamespace(
            final_text=(
                "I can describe the requested changes, but I will not call a tool. "
                "Token sk-testtoken123456 was not used."
            ),
            tool_trace=(),
            report_facts={
                "provider_response": {
                    "adapter": "fixture",
                    "finish_reasons": ["stop"],
                }
            },
        )


class _InvalidSubmissionBackend:
    """Provider double that submits malformed typed arguments."""

    provider = "fake"
    model = "fake-model"
    credential_source = "test"

    async def run_authoring(self, **kwargs: object) -> object:
        """Submit one invalid intent and stop."""
        tool_caller = kwargs["tool_caller"]
        assert callable(tool_caller)
        response = await tool_caller(
            "submit_request_inventory",
            {"items": [{"unexpected": True}]},
        )
        assert response["is_error"] is True
        return SimpleNamespace(final_text="The typed submission was rejected.", tool_trace=())


class _CoverageFailureBackend:
    """Provider double that submits typed data without complete coverage."""

    provider = "fake"
    model = "fake-model"
    credential_source = "test"

    async def run_authoring(self, **kwargs: object) -> object:
        """Submit an intent that omits one request item from coverage."""
        tool_name = kwargs["tool_definitions"][0].name
        tool_caller = kwargs["tool_caller"]
        assert callable(tool_caller)
        if tool_name == "submit_request_inventory":
            response = await tool_caller(
                tool_name,
                {
                    "items": [
                        {
                            "request_item_id": "request-001",
                            "status": "mapped",
                            "action": "set",
                            "object_family": "report",
                        },
                        {
                            "request_item_id": "request-002",
                            "status": "mapped",
                            "action": "add",
                            "object_family": "remarks",
                        },
                    ]
                },
            )
            assert response["accepted"] is True
            return SimpleNamespace(final_text="Inventoried request.", tool_trace=())
        assert tool_name == "submit_report_intent"
        response = await tool_caller(
            tool_name,
            {
                "intent": {"title": "Revised"},
                "coverage": [
                    {
                        "unit_id": "unit-request-001",
                        "status": "mapped",
                    }
                ],
            },
        )
        assert response["is_error"] is True
        return SimpleNamespace(final_text="Coverage was incomplete.", tool_trace=())


class _RoundBudgetBackend:
    """Provider double that exhausts extraction rounds before submission."""

    provider = "fake"
    model = "fake-model"
    credential_source = "test"

    async def run_authoring(self, **_: object) -> object:
        """Raise the adapter's conventional round-budget error."""
        raise RuntimeError("The OpenAI-compatible authoring loop exceeded 3 rounds.")


class _RequiredToolFailureBackend:
    """Provider double that reports a normalized required-tool failure."""

    provider = "fake"
    model = "fake-model"
    credential_source = "test"

    async def run_authoring(self, **_: object) -> object:
        """Simulate an adapter that returned prose instead of the submission tool."""
        raise ProviderAdapterError(
            "required_tool_not_called",
            "Provider returned prose without the required submission tool.",
        )


class _CorrectedInventoryThenScopedFailureBackend:
    """Provider double for the notebook's corrected-inventory failure shape."""

    provider = "fake"
    model = "fake-model"
    credential_source = "test"

    def __init__(self) -> None:
        self.inventory_attempts = 0

    async def run_authoring(self, **kwargs: object) -> object:
        """Correct inventory once, then fail after a scoped tool call."""
        tool_name = kwargs["tool_definitions"][0].name
        tool_caller = kwargs["tool_caller"]
        assert callable(tool_caller)
        if tool_name == "submit_request_inventory":
            self.inventory_attempts += 1
            first = await tool_caller(
                tool_name,
                {
                    "items": [
                        {
                            "request_item_id": "request-001",
                            "status": "mapped",
                            "action": "explain",
                            "object_family": "service_title",
                            "target": "first service title",
                            "explicit_values": {"value": "Open Hole Quicklook"},
                        }
                    ]
                },
            )
            assert first["is_error"] is True
            second = await tool_caller(
                tool_name,
                {
                    "items": [
                        {
                            "request_item_id": "request-001",
                            "status": "mapped",
                            "action": "set",
                            "object_family": "service_title",
                            "target": "first service title",
                            "explicit_values": {"value": "Open Hole Quicklook"},
                        }
                    ]
                },
            )
            assert second["accepted"] is True
            return SimpleNamespace(final_text="Request inventory validated.", tool_trace=())

        assert tool_name == "submit_report_intent"
        raise ProviderAdapterError(
            "round_budget_exhausted",
            "The fake scoped authoring loop exceeded 3 rounds.",
            tool_trace=(
                AuthoringToolCall(
                    round=3,
                    name=tool_name,
                    arguments={"coverage": []},
                ),
            ),
            report_facts={
                "provider_response": {
                    "adapter": "fixture",
                    "rounds": 3,
                    "tool_calls_emitted": True,
                }
            },
        )


def test_desired_state_extraction_allows_one_coverage_correction() -> None:
    """Accept a corrected submission without exposing mutation tools."""
    backend = _CorrectionBackend()
    session = AuthoringSession(backend=backend, runtime=SimpleNamespace(server_root=Path(".")))
    context = AuthoringContextSnapshot(draft_logfile="draft.log.yaml")

    result, intent = anyio.run(
        partial(
            session._extract_desired_state,
            request_text="Set the report title to Revised.",
            draft_logfile="draft.log.yaml",
            existing=SimpleNamespace(model_dump=lambda **_: {}),
            context_snapshot=context,
            max_rounds=12,
        )
    )

    assert backend.attempts == 3
    assert backend.tool_names == [
        "submit_request_inventory",
        "submit_report_intent",
    ]
    assert backend.required_tool_names == backend.tool_names
    assert intent is not None
    assert intent.title == "Revised"
    assert result.report_facts["request_coverage"][0]["unit_id"] == "unit-request-001"
    assert result.report_facts["request_work_units"] == [
        {
            "unit_id": "unit-request-001",
            "request_item_id": "request-001",
            "clause_text": "Set the report title to Revised.",
            "status": "mapped",
            "action": "set",
            "branch": "report",
            "object_family": "report",
            "target": "title",
            "natural_parent": None,
            "explicit_values": {"value": "Revised"},
            "preserve_constraints": [],
            "dependencies": [],
            "reason": None,
        }
    ]
    assert "request_manifest" in backend.initial_user_messages[0]
    assert all(
        "AuthoringIntentSubmission schema" not in message
        for message in backend.initial_user_messages
    )
    contract = result.report_facts["provider_contract"]
    assert contract["schema_repeated_in_message"] is False
    assert contract["request_inventory_schema_chars"] < contract["full_intent_schema_chars"]
    assert contract["stage_tool_schema_chars"]["report"] < contract["full_intent_schema_chars"]


def _extract_with_backend(backend: object, request_text: str = "Set the report title.") -> object:
    """Run extraction against a small provider double."""
    session = AuthoringSession(backend=backend, runtime=SimpleNamespace(server_root=Path(".")))
    context = AuthoringContextSnapshot(draft_logfile="draft.log.yaml")
    return anyio.run(
        partial(
            session._extract_desired_state,
            request_text=request_text,
            draft_logfile="draft.log.yaml",
            existing=SimpleNamespace(model_dump=lambda **_: {}),
            context_snapshot=context,
            max_rounds=3,
        )
    )


def test_extraction_reports_no_tool_call_and_sanitized_provider_text() -> None:
    """Identify a prose-only provider response before any MCP mutation."""
    result, intent = _extract_with_backend(_NoToolBackend())

    assert intent is None
    assert result.report_facts["provider_response"] == {
        "adapter": "fixture",
        "finish_reasons": ["stop"],
    }
    extraction = result.report_facts["extraction"]
    assert extraction["status"] == "no_tool_call"
    assert extraction["submission_attempts"] == 0
    assert extraction["tool_calls_emitted"] is False
    assert extraction["validation_failures"] == []
    assert extraction["coverage_failures"] == []
    assert extraction["provider_text"] == (
        "I can describe the requested changes, but I will not call a tool. "
        "Token [REDACTED] was not used."
    )


def test_extraction_reports_schema_validation_failure() -> None:
    """Identify malformed typed arguments separately from a missing tool call."""
    result, intent = _extract_with_backend(_InvalidSubmissionBackend())

    assert intent is None
    assert result.report_facts["extraction"]["status"] == "schema_validation_failed"
    assert result.report_facts["extraction"]["submission_attempts"] == 1
    assert result.report_facts["extraction"]["validation_failures"]


def test_extraction_reports_coverage_failure() -> None:
    """Identify incomplete request accounting after typed validation succeeds."""
    result, intent = _extract_with_backend(
        _CoverageFailureBackend(),
        request_text="- Set the report title.\n- Add a remarks block.",
    )

    assert intent is None
    assert result.report_facts["extraction"]["status"] == "coverage_failed"
    assert result.report_facts["extraction"]["coverage_failures"]


def test_extraction_reports_round_budget_failure() -> None:
    """Convert extraction round exhaustion into structured provider diagnostics."""
    result, intent = _extract_with_backend(_RoundBudgetBackend())

    assert intent is None
    assert result.report_facts["extraction"]["status"] == "round_budget_exhausted"
    assert result.report_facts["provider_error"]


def test_extraction_preserves_normalized_required_tool_failure() -> None:
    """Expose adapter conformance failures without misclassifying MCP execution."""
    result, intent = _extract_with_backend(_RequiredToolFailureBackend())

    assert intent is None
    assert result.report_facts["extraction"]["status"] == "required_tool_not_called"
    assert result.report_facts["provider_error"]


def test_extraction_reports_active_stage_and_corrected_inventory_history() -> None:
    """Do not report a corrected inventory error as the active failure."""
    result, intent = _extract_with_backend(
        _CorrectedInventoryThenScopedFailureBackend(),
        request_text="Set the first service title to Open Hole Quicklook.",
    )

    assert intent is None
    assert result.final_text == ""
    extraction = result.report_facts["extraction"]
    assert extraction["status"] == "round_budget_exhausted"
    assert extraction["failed_stages"] == ["report"]
    assert extraction["inventory_failures"] == []
    assert extraction["provider_stage_failures"] == [
        {
            "stage": "report",
            "status": "round_budget_exhausted",
            "message": "The fake scoped authoring loop exceeded 3 rounds.",
        }
    ]
    assert extraction["corrected_failures"] == [
        {
            "stage": "inventory",
            "errors": ["Inventory for 'request-001' needs an authoring action."],
        }
    ]
    assert [call.name for call in result.tool_trace] == ["submit_report_intent"]
    assert result.report_facts["provider_stages"][-1]["provider_failure_stage"] == "report"
    assert "service_title" not in result.report_facts["reasons"][0]
    assert (
        "Provider report stage failed (round_budget_exhausted)" in result.report_facts["reasons"][0]
    )


def test_intent_submission_keeps_typed_intent_and_coverage_together() -> None:
    """Keep the provider contract independently validatable."""
    submission = AuthoringIntentSubmission(
        intent=AuthoringDocumentIntent(title="Revised"),
        coverage=[
            {
                "unit_id": "unit-request-001",
                "status": "mapped",
            }
        ],
    )

    assert submission.intent.title == "Revised"
    assert submission.coverage[0].status == "mapped"


def test_scoped_compiler_has_no_scientific_family_branches() -> None:
    """Prevent notebook examples from becoming compiler control flow."""
    source = Path(compilation_module.__file__).read_text(encoding="utf-8").lower()

    for domain_token in (
        "resistivity",
        "porosity",
        "caliper",
        "cement bond",
        "cbl",
        "vdl",
        "gamma ray",
    ):
        assert domain_token not in source
