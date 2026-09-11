"""Compile-only LangGraph reconstruction tests."""

###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

import asyncio
import json
from dataclasses import dataclass, field

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


def _track_plan() -> dict[str, object]:
    """Declare a real track for each newly created section."""
    return {
        "component_id": "depth-plan",
        "target_id": "depth",
        "capability_id": "track.reference",
        "goal": "Create a depth track.",
        "parent_component_id": None,
    }


class _FakeStructuredModel:
    section_source_manifests: dict[str, dict[str, object]]

    def __init__(self) -> None:
        self.section_source_manifests = {}

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
        if tool_name == "submit_reconstruction_plan":
            return response_model.model_validate(
                {
                    "summary": "Two logging passes.",
                    "sections": [
                        {
                            "section_id": "main_pass",
                            "capability_id": "section.log_plot",
                            "goal": "Compile main pass.",
                            "components": [_track_plan()],
                        },
                        {
                            "section_id": "repeat_pass",
                            "capability_id": "section.log_plot",
                            "goal": "Compile repeat pass.",
                            "data_source": {
                                "source_path": "repeat.las",
                                "source_format": "las",
                            },
                            "components": [_track_plan()],
                        },
                    ],
                }
            )
        if tool_name == "submit_report_artifact":
            return response_model.model_validate({"intent": {"title": "Compiled report"}})
        if tool_name == "submit_section_artifact":
            context = json.loads(user_message.rsplit("Context:\n", maxsplit=1)[1])
            section_plan = context["section_plan"]
            section_id = section_plan["section_id"]
            self.section_source_manifests[section_id] = context["source_manifest"]
            section: dict[str, object] = {
                "section_id": section_id,
                "title": section_id.replace("_", " "),
                "tracks": [
                    {
                        "track_id": "depth",
                        "title": "Depth",
                        "kind": "reference",
                        "width_mm": 10,
                    }
                ],
            }
            if section_id == "repeat_pass":
                section["data_source"] = section_plan["data_source"]
            return response_model.model_validate(
                {
                    "section": section,
                }
            )
        raise AssertionError(f"Unexpected structured model request: {tool_name}")


def test_compile_graph_fans_out_sections_and_merges_intent() -> None:
    """Dynamic section workers fan out and merge without mutating a draft."""
    result, model = asyncio.run(_compile_two_sections())

    assert result["merged_intent"]["title"] == "Compiled report"
    assert [section["section_id"] for section in result["merged_intent"]["sections"]] == [
        "main_pass",
        "repeat_pass",
    ]
    assert model.section_source_manifests["repeat_pass"]["repeat_pass"]["channels"] == [
        {"mnemonic": "CBL", "kind": "scalar"}
    ]


def test_compile_graph_dispatches_canonicalized_source_routes_to_workers() -> None:
    """The source boundary updates graph state before worker contracts are derived."""
    result, _model = asyncio.run(_compile_two_sections(normalized_source_path="sources/repeat.las"))

    repeat = result["merged_intent"]["sections"][1]
    assert repeat["data_source"] == {
        "source_path": "sources/repeat.las",
        "source_format": "las",
    }


@dataclass
class _PlannedSourceResolver:
    """Test double for deterministic source enrichment before worker dispatch."""

    calls: list[tuple[list[str], list[str]]] = field(default_factory=list)
    normalized_source_path: str | None = None

    def normalize_plan_sources(
        self,
        *,
        plan: ReconstructionPlan,
        logfile_path: str | None,
    ) -> ReconstructionPlan:
        """Optionally canonicalize a route before workers receive the plan."""
        del logfile_path
        if self.normalized_source_path is None:
            return plan
        normalized_sections = []
        for section in plan.sections:
            if section.data_source is None:
                normalized_sections.append(section)
                continue
            normalized_sections.append(
                section.model_copy(
                    update={
                        "data_source": section.data_source.model_copy(
                            update={"source_path": self.normalized_source_path}
                        )
                    }
                )
            )
        return plan.model_copy(update={"sections": normalized_sections})

    def enrich(
        self,
        *,
        plan: ReconstructionPlan,
        source_manifest: dict[str, object],
        logfile_path: str | None,
    ) -> dict[str, object]:
        del logfile_path
        self.calls.append(
            (
                [section.section_id for section in plan.sections],
                sorted(source_manifest),
            )
        )
        return {
            **source_manifest,
            "repeat_pass": {"channels": [{"mnemonic": "CBL", "kind": "scalar"}]},
        }


async def _compile_two_sections(
    *,
    normalized_source_path: str | None = None,
) -> tuple[dict[str, object], _FakeStructuredModel]:
    """Compile the synthetic two-section request through the generic graph."""
    registry = create_builtin_registry()
    model = _FakeStructuredModel()
    source_resolver = _PlannedSourceResolver(normalized_source_path=normalized_source_path)
    graph = build_compile_graph(
        ReconstructionGraphDependencies(
            planner=ReconstructionPlanner(model=model, registry=registry),
            report_compiler=ReportCompiler(model=model, registry=registry),
            section_compiler=SectionCompiler(model=model, registry=registry),
            registry=registry,
            source_context_resolver=source_resolver,  # type: ignore[arg-type]
        )
    )

    return await graph.ainvoke(
        {
            "request": "Build main and repeat pass sections.",
            "current_document": {},
            "source_manifest": {"main_pass": {"channels": []}},
            "compiled_artifacts": [],
            "diagnostics": [],
            "repair_attempt": 0,
        }
    ), model
