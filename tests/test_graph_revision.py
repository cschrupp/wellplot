"""Tests for compile-only graph revision mode."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest
from pydantic import BaseModel

pytest.importorskip("langgraph")

from langgraph.graph.state import CompiledStateGraph

from wellplot.agent.graph import (
    ReconstructionGraphDependencies,
    ReconstructionPlanner,
    ReportCompiler,
    SectionCompiler,
    build_compile_graph,
    compile_document_revision,
    execute_document_intent,
)
from wellplot.authoring_service import AuthoringService
from wellplot.capabilities import create_builtin_registry
from wellplot.model.authoring import AuthoringDocumentSpec


@dataclass
class _RevisionModel:
    """Fixture-backed provider that compiles only the selected section."""

    compiled_section_id: str = "main_pass"
    tool_calls: list[str] = field(default_factory=list)
    planner_instructions: str = ""
    planner_message: str = ""

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
        """Return deterministic scoped revision artifacts."""
        del tool_description, max_rounds, response_validator
        self.tool_calls.append(tool_name)
        if tool_name == "submit_reconstruction_plan":
            self.planner_instructions = instructions
            self.planner_message = user_message
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
            assert "Compile section 'main_pass'." in user_message
            return response_model.model_validate(
                {
                    "section": {
                        "section_id": self.compiled_section_id,
                        "title": "Main pass revised",
                    }
                }
            )
        raise AssertionError(f"Unexpected structured model request: {tool_name}")


def _document() -> AuthoringDocumentSpec:
    """Build a two-section canonical document with independent stable ids."""
    return AuthoringDocumentSpec(
        name="revision-test",
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


def _graph(model: _RevisionModel) -> CompiledStateGraph:
    """Build the generic graph with a deterministic structured model."""
    registry = create_builtin_registry()
    return build_compile_graph(
        ReconstructionGraphDependencies(
            planner=ReconstructionPlanner(model=model, registry=registry),
            report_compiler=ReportCompiler(model=model, registry=registry),
            section_compiler=SectionCompiler(model=model, registry=registry),
            registry=registry,
        )
    )


def test_revision_compiles_only_affected_section_and_preserves_unrelated_state() -> None:
    """A scoped revision produces a partial intent that keeps other sections."""
    model = _RevisionModel()
    document = _document()

    result = asyncio.run(
        compile_document_revision(
            _graph(model),
            request="Rename only the main pass.",
            current_document=document,
        )
    )

    assert "This is a revision" in model.planner_instructions
    assert '"mode": "revise"' in model.planner_message
    assert model.tool_calls == [
        "submit_reconstruction_plan",
        "submit_report_artifact",
        "submit_section_artifact",
    ]
    assert result.affected_section_ids == ("main_pass",)
    assert result.preserved_section_ids == ("repeat_pass",)
    assert [section.section_id for section in result.intent.sections or []] == ["main_pass"]

    service = AuthoringService(document.model_copy(deep=True))
    execution = execute_document_intent(service, result.intent)

    assert execution.success is True, execution.errors
    assert [section.id for section in service.document.sections] == ["main_pass", "repeat_pass"]
    assert service.document.sections[0].title == "Main pass revised"
    assert service.document.sections[1].title == "Repeat pass"


def test_revision_rejects_compiled_sections_outside_its_plan() -> None:
    """A worker cannot extend a revision beyond the planner's selected scope."""
    model = _RevisionModel(compiled_section_id="repeat_pass")

    with pytest.raises(ValueError, match="not selected by the revision plan"):
        asyncio.run(
            compile_document_revision(
                _graph(model),
                request="Rename only the main pass.",
                current_document=_document(),
            )
        )


def test_compile_graph_defaults_to_reconstruction_mode() -> None:
    """Existing compile callers retain reconstruction behavior when mode is omitted."""
    model = _RevisionModel()

    result = asyncio.run(
        _graph(model).ainvoke(
            {
                "request": "Build a main pass.",
                "current_document": {},
                "source_manifest": {},
                "compiled_artifacts": [],
                "diagnostics": [],
                "repair_attempt": 0,
            }
        )
    )

    assert "This is a reconstruction" in model.planner_instructions
    assert result["merged_intent"]["sections"][0]["section_id"] == "main_pass"
