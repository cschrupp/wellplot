"""Tests for read-only graph intent verification."""

from __future__ import annotations

import json
from pathlib import Path
from shutil import copyfile

from wellplot.agent.graph import execute_document_intent, verify_document_intent
from wellplot.authoring import load_authoring_document
from wellplot.authoring_service import AuthoringService
from wellplot.model.authoring import AuthoringDocumentSpec
from wellplot.model.intent import AuthoringDocumentIntent

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "agentic_cbl"


def _service() -> AuthoringService:
    """Build a minimal document for generic verifier tests."""
    return AuthoringService(
        AuthoringDocumentSpec(
            name="intent-verifier-test",
            title="Original",
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
                        }
                    ],
                }
            ],
        )
    )


def _generic_intent() -> AuthoringDocumentIntent:
    """Return a small desired state with one source-backed binding."""
    return AuthoringDocumentIntent.model_validate(
        {
            "title": "Revised",
            "sections": [
                {
                    "section_id": "main",
                    "tracks": [
                        {
                            "track_id": "curves",
                            "title": "Curves",
                            "kind": "normal",
                            "width_mm": 30,
                            "bindings": [
                                {
                                    "kind": "curve",
                                    "binding_id": "main.curves.GR.1",
                                    "channel": "GR",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )


def _cased_hole_service(tmp_path: Path) -> AuthoringService:
    """Load a tracked cased-hole scaffold without workspace state."""
    for filename in ("base.template.yaml", "cased_hole_starter.log.yaml"):
        copyfile(_FIXTURE_DIR / filename, tmp_path / filename)
    return AuthoringService(load_authoring_document(tmp_path / "cased_hole_starter.log.yaml"))


def test_intent_verifier_accepts_satisfied_generic_document() -> None:
    """A document produced by direct execution needs no further operations."""
    service = _service()
    intent = _generic_intent()
    source_context = {"main": [{"mnemonic": "GR", "kind": "scalar"}]}

    execution = execute_document_intent(
        service,
        intent,
        available_channels=source_context,
    )
    result = verify_document_intent(
        service.document,
        intent,
        available_channels=source_context,
    )

    assert execution.success is True, execution.errors
    assert result.success is True
    assert result.reconciliation_plan is not None
    assert result.reconciliation_plan.operations == []


def test_intent_verifier_reports_damage_without_mutating_document() -> None:
    """A missing canonical binding is an explicit unmet postcondition."""
    service = _service()
    intent = _generic_intent()
    source_context = {"main": [{"mnemonic": "GR", "kind": "scalar"}]}
    execution = execute_document_intent(
        service,
        intent,
        available_channels=source_context,
    )
    assert execution.success is True, execution.errors

    damaged_payload = service.document.model_dump(mode="python")
    damaged_payload["sections"][0]["tracks"][1]["bindings"] = []
    damaged_document = AuthoringDocumentSpec.model_validate(damaged_payload)
    before = damaged_document.model_dump(mode="json")

    result = verify_document_intent(
        damaged_document,
        intent,
        available_channels=source_context,
    )

    assert result.success is False
    assert result.reconciliation_plan is not None
    assert any(
        issue.code == "postcondition_unmet"
        and issue.operation is not None
        and issue.operation.object_kind == "curve_binding"
        and issue.operation.object_id == "main.curves.GR.1"
        for issue in result.issues
    )
    assert damaged_document.model_dump(mode="json") == before


def test_intent_verifier_accepts_frozen_cbl_execution(tmp_path: Path) -> None:
    """The frozen CBL benchmark passes semantic verification after execution."""
    contract = json.loads((_FIXTURE_DIR / "compile_contract.json").read_text(encoding="utf-8"))
    intent = AuthoringDocumentIntent.model_validate(contract["merged_intent"])
    service = _cased_hole_service(tmp_path)
    source_manifest = contract["source_manifest"]
    source_context = {
        section_id: source["channels"] for section_id, source in source_manifest.items()
    }
    header_aliases = contract["execution_context"]["header_aliases"]

    execution = execute_document_intent(
        service,
        intent,
        available_channels=source_context,
        header_aliases=header_aliases,
    )
    result = verify_document_intent(
        service.document,
        intent,
        available_channels=source_context,
        header_aliases=header_aliases,
    )

    assert execution.success is True, execution.errors
    assert result.success is True
    assert result.reconciliation_plan is not None
    assert result.reconciliation_plan.operations == []
