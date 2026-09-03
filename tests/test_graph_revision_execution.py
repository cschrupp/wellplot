"""Tests for transactional execution of graph-compiled revisions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest
from pydantic import BaseModel

pytest.importorskip("langgraph")

from langgraph.graph.state import CompiledStateGraph

import wellplot.agent.graph.revision_execution as revision_execution
from wellplot.agent.graph import (
    ReconstructionGraphDependencies,
    ReconstructionPlanner,
    ReportCompiler,
    SectionCompiler,
    build_compile_graph,
    execute_document_revision,
)
from wellplot.agent.graph.verifier import (
    DocumentIntentVerificationResult,
    IntentVerificationIssue,
)
from wellplot.authoring_service import AuthoringService
from wellplot.capabilities import create_builtin_registry
from wellplot.model.authoring import AuthoringDocumentSpec


@dataclass
class _RevisionModel:
    """Return one scoped section update without external provider access."""

    async def generate(
        self,
        *,
        instructions: str,
        user_message: str,
        response_model: type[BaseModel],
        tool_name: str,
        tool_description: str,
        max_rounds: int = 3,
        response_validator: object | None = None,
    ) -> BaseModel:
        """Return the exact revision plan and artifacts for this test."""
        del instructions, user_message, tool_description, max_rounds, response_validator
        if tool_name == "submit_reconstruction_plan":
            return response_model.model_validate(
                {
                    "summary": "Revise the main pass title.",
                    "sections": [
                        {
                            "section_id": "main_pass",
                            "capability_id": "section.log_plot",
                            "goal": "Update the main pass only.",
                        }
                    ],
                }
            )
        if tool_name == "submit_report_artifact":
            return response_model.model_validate({"intent": {}})
        if tool_name == "submit_section_artifact":
            return response_model.model_validate(
                {"section": {"section_id": "main_pass", "title": "Main pass revised"}}
            )
        raise AssertionError(f"Unexpected structured model request: {tool_name}")


def _graph() -> CompiledStateGraph:
    """Build the generic graph with deterministic revision responses."""
    registry = create_builtin_registry()
    model = _RevisionModel()
    return build_compile_graph(
        ReconstructionGraphDependencies(
            planner=ReconstructionPlanner(model=model, registry=registry),
            report_compiler=ReportCompiler(model=model, registry=registry),
            section_compiler=SectionCompiler(model=model, registry=registry),
            registry=registry,
        )
    )


def _service() -> AuthoringService:
    """Build a document whose unrelated section must survive revision."""
    return AuthoringService(
        AuthoringDocumentSpec(
            name="revision-execution-test",
            title="Original report",
            sections=[
                {
                    "id": "main_pass",
                    "title": "Main pass",
                    "tracks": [
                        {
                            "id": "depth",
                            "title": "Depth",
                            "kind": "reference",
                            "width_mm": 20,
                        }
                    ],
                },
                {
                    "id": "repeat_pass",
                    "title": "Repeat pass",
                    "tracks": [
                        {
                            "id": "depth",
                            "title": "Depth",
                            "kind": "reference",
                            "width_mm": 20,
                        }
                    ],
                },
            ],
        )
    )


def test_revision_execution_applies_and_verifies_scoped_change() -> None:
    """A revision transaction updates only the selected section."""
    service = _service()

    result = asyncio.run(
        execute_document_revision(
            _graph(),
            service,
            request="Rename only the main pass.",
        )
    )

    assert result.success is True, result.errors
    assert result.rolled_back is False
    assert result.verification is not None
    assert result.verification.success is True
    assert result.revision.affected_section_ids == ("main_pass",)
    assert result.revision.preserved_section_ids == ("repeat_pass",)
    assert [section.id for section in service.document.sections] == ["main_pass", "repeat_pass"]
    assert service.document.sections[0].title == "Main pass revised"
    assert service.document.sections[1].title == "Repeat pass"


def test_revision_execution_rolls_back_when_final_verification_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed final postcondition restores the original canonical document."""
    service = _service()
    before = service.document.model_dump(mode="json")
    original_verifier = revision_execution.verify_document_intent

    def fail_verification(*args: object, **kwargs: object) -> DocumentIntentVerificationResult:
        """Inject one postcondition failure after normal verification succeeds."""
        verified = original_verifier(*args, **kwargs)
        return DocumentIntentVerificationResult(
            document=verified.document,
            resolution=verified.resolution,
            reconciliation_plan=verified.reconciliation_plan,
            issues=(
                IntentVerificationIssue(
                    path="main_pass",
                    code="forced_failure",
                    message="Forced final verification failure.",
                ),
            ),
        )

    monkeypatch.setattr(revision_execution, "verify_document_intent", fail_verification)
    result = asyncio.run(
        execute_document_revision(
            _graph(),
            service,
            request="Rename only the main pass.",
        )
    )

    assert result.success is False
    assert result.rolled_back is True
    assert result.verification is not None
    assert result.verification.success is False
    assert result.errors == ("Forced final verification failure.",)
    assert service.document.model_dump(mode="json") == before
