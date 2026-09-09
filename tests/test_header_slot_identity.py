"""Exact header identity takes precedence over descriptive alias lookup."""

from pathlib import Path

import pytest

from wellplot.agent.graph.executor import execute_document_intent
from wellplot.authoring import load_authoring_document
from wellplot.authoring_context import resolve_authoring_context
from wellplot.authoring_service import AuthoringService
from wellplot.model.intent import AuthoringDocumentIntent


@pytest.mark.parametrize("source", ["existing", "scaffold"])
@pytest.mark.parametrize("configured_alias", [False, True])
def test_exact_detail_slot_wins_over_shared_label(source: str, configured_alias: bool) -> None:
    """An exact date cell cannot be redirected or broadened by aliases or labels."""
    document = load_authoring_document(
        Path(__file__).parent / "fixtures/agentic_cbl/cased_hole_starter.log.yaml"
    )
    intent = AuthoringDocumentIntent.model_validate(
        {
            "header": {
                "detail_fields": [
                    {
                        "slot_id": "detail.row_1.value_1",
                        "key": "date",
                        "label": "Date",
                        "value": {"value": "08-May-2023"},
                    }
                ]
            }
        }
    )
    result = resolve_authoring_context(
        intent,
        **{source: document},
        header_aliases={"detail.row_1.value_1": ["detail.row_1.value_2"]}
        if configured_alias
        else None,
    )
    assert result.ready, result.issues
    decisions = [
        item for item in result.decisions if item.path == "header.detail_fields[0].slot_id"
    ]
    assert len(decisions) == 1
    assert decisions[0].value == "detail.row_1.value_1"
    assert decisions[0].matched_alias is None
    assert decisions[0].candidates == ["detail.row_1.value_1"]


@pytest.mark.parametrize(
    "requested,code", [("Date", "header_slot_ambiguous"), ("nonexistent", "header_slot_missing")]
)
def test_nonexact_header_requests_still_require_unambiguous_match(
    requested: str, code: str
) -> None:
    """Without an exact ID the resolver must not choose an arbitrary date cell."""
    document = load_authoring_document(
        Path(__file__).parent / "fixtures/agentic_cbl/cased_hole_starter.log.yaml"
    )
    result = resolve_authoring_context(
        AuthoringDocumentIntent.model_validate(
            {"header": {"detail_fields": [{"slot_id": requested, "value": {"value": "date"}}]}}
        ),
        existing=document,
    )
    assert not result.ready
    assert code in {issue.code for issue in result.issues}


def test_exact_detail_update_changes_only_selected_cell() -> None:
    """Execute a shared-label update without changing the neighboring date slot."""
    document = load_authoring_document(
        Path(__file__).parent / "fixtures/agentic_cbl/cased_hole_starter.log.yaml"
    )
    before = document.model_copy(deep=True)
    service = AuthoringService(document)
    result = execute_document_intent(
        service,
        AuthoringDocumentIntent.model_validate(
            {
                "header": {
                    "detail_fields": [
                        {
                            "slot_id": "detail.row_1.value_1",
                            "key": "date",
                            "label": "Date",
                            "value": {"value": "08-May-2023"},
                        }
                    ]
                }
            }
        ),
    )
    assert result.success, result.errors
    row = service.document.header.detail.rows[0]
    assert row.values[0].value.value == "08-May-2023"
    assert row.values[1] == before.header.detail.rows[0].values[1]
    assert service.document.header.detail.rows[1:] == before.header.detail.rows[1:]
