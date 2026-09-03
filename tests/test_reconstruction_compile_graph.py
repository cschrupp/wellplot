"""Compile-only LangGraph reconstruction tests."""

###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

import asyncio

import pytest
from pydantic import BaseModel

pytest.importorskip("langgraph")

from wellplot.agent.graph import (
    ReconstructionGraphDependencies,
    ReconstructionPlanner,
    ReportCompiler,
    SectionCompiler,
    build_compile_graph,
)
from wellplot.agent.graph.models import ReconstructionPlan
from wellplot.capabilities import create_builtin_registry


class _FakeStructuredModel:
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
        del instructions, tool_description, max_rounds, response_validator
        if response_model is ReconstructionPlan:
            return ReconstructionPlan.model_validate(
                {
                    "summary": "Two logging passes.",
                    "sections": [
                        {
                            "section_id": "main_pass",
                            "capability_id": "section.log_plot",
                            "goal": "Compile main pass.",
                            "components": [],
                        },
                        {
                            "section_id": "repeat_pass",
                            "capability_id": "section.log_plot",
                            "goal": "Compile repeat pass.",
                            "components": [],
                        },
                    ],
                }
            )
        if tool_name == "submit_report_artifact":
            return response_model.model_validate({"intent": {"title": "Compiled report"}})
        if tool_name == "submit_section_artifact":
            section_id = "repeat_pass" if "repeat_pass" in user_message else "main_pass"
            return response_model.model_validate(
                {"section": {"section_id": section_id, "title": section_id.replace("_", " ")}}
            )
        raise AssertionError(f"Unexpected structured model request: {tool_name}")


def test_compile_graph_fans_out_sections_and_merges_intent() -> None:
    """Dynamic section workers fan out and merge without mutating a draft."""
    result = asyncio.run(_compile_two_sections())

    assert result["merged_intent"]["title"] == "Compiled report"
    assert [section["section_id"] for section in result["merged_intent"]["sections"]] == [
        "main_pass",
        "repeat_pass",
    ]


async def _compile_two_sections() -> dict[str, object]:
    """Compile the synthetic two-section request through the generic graph."""
    registry = create_builtin_registry()
    model = _FakeStructuredModel()
    graph = build_compile_graph(
        ReconstructionGraphDependencies(
            planner=ReconstructionPlanner(model=model, registry=registry),
            report_compiler=ReportCompiler(model=model, registry=registry),
            section_compiler=SectionCompiler(model=model, registry=registry),
            registry=registry,
        )
    )

    return await graph.ainvoke(
        {
            "request": "Build main and repeat pass sections.",
            "current_document": {},
            "source_manifest": {},
            "compiled_artifacts": [],
            "diagnostics": [],
            "repair_attempt": 0,
        }
    )
