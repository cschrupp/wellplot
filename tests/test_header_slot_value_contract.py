"""Header value updates must agree with final semantic verification."""

from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from wellplot.agent.graph.executor import execute_document_intent
from wellplot.agent.graph.verifier import verify_document_intent
from wellplot.agent.graph.worker_contracts import report_contract
from wellplot.authoring import load_authoring_document
from wellplot.authoring_service import AuthoringService
from wellplot.model.authoring import AuthoringDocumentSpec
from wellplot.model.intent import AuthoringDocumentIntent


def _document() -> AuthoringDocumentSpec:
    return load_authoring_document(
        Path(__file__).parent / "fixtures/agentic_cbl/cased_hole_starter.log.yaml"
    )


@pytest.mark.parametrize("reconstruct", [True, False])
@pytest.mark.parametrize(
    "collection,slot",
    [("general_fields", "general.company"), ("detail_fields", "detail.row_1.value_1")],
)
@pytest.mark.parametrize("field", ["key", "label", "aliases", "layout_path"])
def test_worker_rejects_slot_metadata(
    reconstruct: bool, collection: str, slot: str, field: str
) -> None:
    """Both schema validators reject fields the value service cannot change."""
    model = report_contract(_document().model_dump(mode="json"), reconstruct=reconstruct)
    payload = {
        "intent": {
            "header": {collection: [{"slot_id": slot, "value": {"value": "Requested value"}}]}
        }
    }
    validator = Draft202012Validator(model.model_json_schema())
    model.model_validate(payload)
    assert not list(validator.iter_errors(payload))
    payload["intent"]["header"][collection][0][field] = ["hint"] if field == "aliases" else "hint"
    with pytest.raises(ValidationError):
        model.model_validate(payload)
    assert list(validator.iter_errors(payload))


@pytest.mark.parametrize(
    "collection,slot",
    [("general_fields", "general.company"), ("detail_fields", "detail.row_1.value_1")],
)
def test_legacy_slot_hints_do_not_leave_unmet_postconditions(collection: str, slot: str) -> None:
    """Previously accepted metadata must not prevent value updates from converging."""
    document = _document()
    before = document.model_copy(deep=True)
    service = AuthoringService(document)
    intent = AuthoringDocumentIntent.model_validate(
        {
            "header": {
                collection: [
                    {
                        "slot_id": slot,
                        "key": "descriptive-key",
                        "label": "Descriptive Label",
                        "aliases": ["descriptive alias"],
                        "layout_path": "descriptive.path",
                        "value": {"value": "Requested value", "provenance": "user"},
                    }
                ]
            }
        }
    )
    execution = execute_document_intent(service, intent)
    assert execution.success, execution.errors
    verification = verify_document_intent(service.document, intent)
    assert verification.success, verification.issues
    second = execute_document_intent(service, intent)
    assert second.success, second.errors
    assert second.reconciliation_plan.operations == []
    expected = before
    cell = (
        next(field for field in expected.header.general_fields if field.slot_id == slot)
        if collection == "general_fields"
        else expected.header.detail.rows[0].values[0]
    )
    cell.value.value = "Requested value"
    cell.value.provenance = "user"
    assert service.document == expected
