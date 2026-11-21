"""Provider-free regressions for the shared Slice 2 authorization gates."""

from __future__ import annotations

import asyncio
import json
import tempfile
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from tests._mcp_fixtures import REPO_ROOT, create_mcp_fixture_paths

from wellplot.agent.code_mode.obligations import (
    DocumentPostconditionError,
    RequestCompilationStatus,
    compile_request_contract,
    verify_document_postconditions,
    verify_document_preservation,
    verify_obligation_spans,
)
from wellplot.agent.code_mode.planner import _PlannerWirePlan
from wellplot.agent.code_mode.semantic_actions import AddFillAction
from wellplot.agent.composition import create_canonical_compile_facade
from wellplot.agent.direct_notebook import DirectNotebookSession
from wellplot.agent.providers.base import ProviderMetrics, StructuredGenerationResult
from wellplot.agent.session import AgentSession
from wellplot.authoring_executor import execute_authoring_plan
from wellplot.authoring_reconciler import reconcile_authoring
from wellplot.authoring_service import AuthoringService
from wellplot.mcp import service as mcp_service
from wellplot.mcp.agentic import GraphAuthoringMcpOperations, _request_context
from wellplot.model import AuthoringDocumentIntent, AuthoringDocumentSpec

_FIXED_BASELINE_REQUEST = "Create a GR curve and fill it to a baseline of 0."
_SPLIT_REQUEST = "Split the GR curve fill at baseline 0."


def test_gr_only_intent_has_exact_binding_and_no_section_creation() -> None:
    """Bind exact GR to existing host scope rather than authorizing a new section."""
    request = "Create a GR curve."
    compilation = compile_request_contract(request)
    assert compilation.status is RequestCompilationStatus.EXTRACTION_COMPLETE
    (channel,) = compilation.requirements.requirements
    assert (channel.field, channel.value) == ("channel", "GR")
    (scope,) = compilation.requirements.scopes.scopes
    assert (scope.kind, scope.origin) == ("EXISTING_SECTION", "HOST_CONTEXT")
    verify_obligation_spans(request, (channel,))


@pytest.mark.parametrize(
    "quote,title", [("'", "Baseline Fill Summary"), ('"', "Fill to Baseline 0")]
)
def test_report_title_literal_does_not_trigger_fill_rejection(quote: str, title: str) -> None:
    """Compile the exact title and preserve its original request evidence."""
    request = f"Rename the report {quote}{title}{quote}"
    result = compile_request_contract(request)
    assert result.status is RequestCompilationStatus.EXTRACTION_COMPLETE
    (obligation,) = result.requirements.requirements
    assert (obligation.owner_kind, obligation.field, obligation.value) == ("report", "title", title)
    verify_obligation_spans(request, (obligation,))


def test_remark_literal_does_not_trigger_fill_rejection() -> None:
    """Leave numbered report content to the existing remark extractor."""
    request = 'Include the remarks: 1. Shift Notes — "Fill to Baseline 0"'
    result = compile_request_contract(request)
    assert result.status is RequestCompilationStatus.EXTRACTION_COMPLETE
    (obligation,) = result.requirements.requirements
    assert obligation.field == "remark"
    assert json.loads(obligation.value)["text"] == '"Fill to Baseline 0"'


@pytest.mark.parametrize(
    "request_text",
    [
        _FIXED_BASELINE_REQUEST,
        "Plot physical GR with a fill to baseline 0.",
        "Create a curve.",
        _SPLIT_REQUEST + " Then change the page.",
        "Rename the report 'Baseline Fill Summary'. Fill 'GR' to a baseline of 0.",
        "Rename the report 'Baseline Fill Summary' and also fill GR to baseline 0.",
    ],
)
def test_unsupported_fill_or_curve_request_cannot_authorize_partial_work(
    request_text: str,
) -> None:
    """Reject partial matching without issuing any task authority."""
    result = compile_request_contract(request_text)
    assert result.status is RequestCompilationStatus.COVERAGE_FAILURE
    assert not result.requirements.requirements
    assert not result.requirements.scopes.scopes


class _FillBackend:
    """Only the model is replaced; compiler, inspection and actions are real."""

    def __init__(self, baseline: float = 0) -> None:
        self.calls: list[object] = []
        self.baseline = baseline

    async def generate_structured(
        self, request: object, *, response_model: type[object]
    ) -> StructuredGenerationResult[object]:
        self.calls.append(response_model)
        if response_model is _PlannerWirePlan:
            value = _PlannerWirePlan.model_validate(
                {
                    "version": "wellplot.semantic-plan.v2",
                    "summary": "Split the existing GR fill.",
                    "section_tasks": [
                        {
                            "goal": "Split the GR curve fill at baseline zero.",
                            "existing_section_hint": None,
                            "scope_ref": "main",
                            "capability_ids": [
                                "section.log_plot",
                                "track.normal",
                                "binding.curve",
                                "fill.curve",
                            ],
                            "operations": [
                                {
                                    "local_ref": "add_fill",
                                    "scope_ref": "main",
                                    "verb": "CREATE",
                                    "object_kind": "fill",
                                    "semantic_ref": "split_fill",
                                    "target_clue": "GR",
                                }
                            ],
                        }
                    ],
                }
            )
        elif response_model is AddFillAction:
            handle = json.loads(request.user_prompt)["section_work_contract"]["target_handle"]
            value = AddFillAction.model_validate(
                {
                    "action": "add_fill",
                    "target": {"handle": handle},
                    "fill": {
                        "kind": "baseline_split",
                        "semantic_id": "split_fill",
                        "target_binding": handle,
                        "baseline": self.baseline,
                    },
                }
            )
        else:
            raise AssertionError(f"Unexpected response model: {response_model}")
        return StructuredGenerationResult(value=value, metrics=ProviderMetrics())


@pytest.mark.parametrize("adapter", ["notebook", "mcp"])
@pytest.mark.parametrize(
    "request_text,baseline",
    [(_SPLIT_REQUEST, 0), (_SPLIT_REQUEST, 1), (_FIXED_BASELINE_REQUEST, 0)],
)
def test_split_fill_through_canonical_adapters(
    adapter: str, request_text: str, baseline: float
) -> None:
    """Keep split geometry, baseline zero and one physical binding through publication."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="split-fill-gate-") as temp_dir:
        fixture = create_mcp_fixture_paths(Path(temp_dir) / "fixture")
        mapping = yaml.safe_load(fixture.single_logfile.read_text())
        mapping["document"]["layout"]["log_sections"][0]["data"]["source_path"] = str(
            fixture.las_path
        )
        fixture.single_logfile.write_text(yaml.safe_dump(mapping))
        original = fixture.single_logfile.read_bytes()
        backend = _FillBackend(baseline)
        session = AgentSession(
            compiler=create_canonical_compile_facade(backend=backend, server_root=REPO_ROOT)
        )
        with patch.object(
            mcp_service, "persist_authoring_document", wraps=mcp_service.persist_authoring_document
        ) as persist:
            if adapter == "notebook":
                notebook = DirectNotebookSession(
                    session=session,
                    provider="test",
                    model="test",
                    credential_source=None,
                    server_root=REPO_ROOT,
                )
                result = asyncio.run(
                    notebook.revise(feedback=request_text, logfile_path=fixture.single_logfile)
                )
                success = result.report_facts["success"]
                errors = result.user_report.warnings_or_errors
            else:
                mcp = GraphAuthoringMcpOperations.create(session=session, root=REPO_ROOT)
                result = asyncio.run(
                    mcp.revise(logfile_path=str(fixture.single_logfile), request=request_text)
                )
                success = result.success
                errors = result.errors
        if request_text == _FIXED_BASELINE_REQUEST:
            assert not backend.calls
            assert not success
            persist.assert_not_called()
            assert fixture.single_logfile.read_bytes() == original
        elif baseline != 0:
            assert AddFillAction in backend.calls
            assert not success
            persist.assert_not_called()
            assert fixture.single_logfile.read_bytes() == original
        else:
            assert success, errors
            assert backend.calls == [_PlannerWirePlan, AddFillAction]
            persist.assert_called_once()
            after = _request_context(str(fixture.single_logfile), root=REPO_ROOT).document
            (track,) = [track for track in after.sections[0].tracks if getattr(track, "fills", ())]
            (fill,) = track.fills
            assert (fill.kind, fill.baseline.value) == ("baseline_split", 0)
            assert [
                (binding.binding_id, binding.channel)
                for binding in track.bindings
                if binding.binding_id == fill.binding_id
            ] == [(fill.binding_id, "GR")]


def _track(track_id: str) -> dict[str, object]:
    return {"id": track_id, "title": track_id, "kind": "normal", "width_mm": 25}


@pytest.mark.parametrize(
    "tamper",
    [None, "rename", "binding_style", "add", "remove", "duplicate", "reorder", "child", "replace"],
)
def test_track_create_has_exact_object_delta(tamper: str | None) -> None:
    """Only the authorized collection effect may survive the shared verifier."""
    original = _track("sibling")
    original["bindings"] = [{"kind": "curve", "binding_id": "existing.gr", "channel": "GR"}]
    before = AuthoringDocumentSpec.model_validate(
        {
            "name": "fixture",
            "sections": [{"id": "main", "title": "Main", "tracks": [original, _track("other")]}],
        }
    )
    intent = AuthoringDocumentIntent.model_validate(
        {
            "sections": [
                {
                    "section_id": "main",
                    "tracks": [
                        {"track_id": "new", "title": "New", "kind": "normal", "width_mm": 30}
                    ],
                }
            ]
        }
    )
    plan = reconcile_authoring(intent, existing=before)
    applied = execute_authoring_plan(AuthoringService(before), plan)
    assert plan.ready and applied.success
    if tamper is None:
        verify_document_postconditions(before, applied.document, (), plan.operations)
        return

    after = applied.document.model_dump(mode="json")
    tracks = after["sections"][0]["tracks"]
    if tamper == "rename":
        tracks[0]["title"] = "Unauthorized"
    elif tamper == "binding_style":
        tracks[0]["bindings"][0]["style"] = {"color": "#123456"}
    elif tamper == "add":
        tracks.append(_track("unexpected"))
    elif tamper == "remove":
        tracks.pop(1)
    elif tamper == "duplicate":
        tracks.append(deepcopy(tracks[-1]))
        with pytest.raises(ValueError, match="authorized reconciliation envelope"):
            verify_document_preservation(before, after, plan.operations)
        return
    elif tamper == "reorder":
        tracks[0], tracks[1] = tracks[1], tracks[0]
    elif tamper == "replace":
        tracks[1] = _track("replacement")
    else:
        tracks[-1]["bindings"] = [{"kind": "curve", "binding_id": "unexpected", "channel": "GR"}]
    with pytest.raises(DocumentPostconditionError, match="authorized reconciliation envelope"):
        verify_document_postconditions(
            before, AuthoringDocumentSpec.model_validate(after), (), plan.operations
        )


def test_authorized_update_move_and_remove_preserve_their_scope() -> None:
    """Accept canonical membership/order effects with a separately authorized update."""
    before = AuthoringDocumentSpec.model_validate(
        {
            "name": "fixture",
            "sections": [
                {
                    "id": "main",
                    "title": "Main",
                    "tracks": [_track("first"), _track("second"), _track("removed")],
                }
            ],
        }
    )
    intent = AuthoringDocumentIntent.model_validate(
        {
            "sections": [
                {
                    "section_id": "main",
                    "tracks": [{"track_id": "second", "title": "Updated"}, {"track_id": "first"}],
                }
            ],
            "removals": [
                {
                    "object_kind": "track",
                    "object_id": "removed",
                    "section_id": "main",
                    "track_id": "removed",
                }
            ],
        }
    )
    plan = reconcile_authoring(intent, existing=before)
    assert plan.ready and {op.action.value for op in plan.operations} == {
        "update",
        "move",
        "remove",
    }
    applied = execute_authoring_plan(AuthoringService(before), plan)
    assert applied.success
    assert [(track.id, track.title) for track in applied.document.sections[0].tracks] == [
        ("second", "Updated"),
        ("first", "first"),
    ]
    verify_document_postconditions(before, applied.document, (), plan.operations)


@pytest.mark.parametrize(
    "altered_field,altered_value", [("text", "Unauthorized"), ("depth", 120), (None, None)]
)
def test_annotation_replacement_requires_exact_canonical_payload(
    altered_field: str | None, altered_value: str | int | None
) -> None:
    """Accept a real replacement, but reject a changed field under the same ID."""
    annotation = {"kind": "text", "annotation_id": "note", "depth": 100, "text": "Before"}
    track = {**_track("notes"), "kind": "annotation", "annotations": [annotation]}
    before = AuthoringDocumentSpec.model_validate(
        {"name": "fixture", "sections": [{"id": "main", "title": "Main", "tracks": [track]}]}
    )
    intent = AuthoringDocumentIntent.model_validate(
        {
            "annotations": [
                {
                    "section_id": "main",
                    "track_id": "notes",
                    "annotation_id": "note",
                    "annotation": {**annotation, "depth": 110, "text": "Authorized"},
                }
            ],
            "removals": [
                {
                    "object_kind": "annotation",
                    "object_id": "note",
                    "section_id": "main",
                    "track_id": "notes",
                }
            ]
            if altered_field is None
            else [],
        }
    )
    plan = reconcile_authoring(intent, existing=before)
    operation = plan.operations[0]
    assert plan.ready and (operation.action, operation.object_kind) == ("update", "annotation")
    assert "object" in operation.payload and "patch" not in operation.payload
    applied = execute_authoring_plan(AuthoringService(before), plan)
    assert applied.success
    verify_document_postconditions(before, applied.document, (), plan.operations)
    if altered_field is None:
        assert [item.action for item in plan.operations] == ["update", "remove"]
        assert not applied.document.sections[0].tracks[0].annotations
        return

    altered = applied.document.model_dump(mode="json")
    altered["sections"][0]["tracks"][0]["annotations"][0][altered_field] = altered_value
    with pytest.raises(
        DocumentPostconditionError, match="authorized reconciliation envelope"
    ) as error:
        verify_document_postconditions(
            before, AuthoringDocumentSpec.model_validate(altered), (), plan.operations
        )
    assert error.value.check == "preservation"
