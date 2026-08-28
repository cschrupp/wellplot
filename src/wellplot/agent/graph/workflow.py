###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""LangGraph topology for the compile-only reconstruction starter.

ARCHITECTURAL INVARIANT:
    This module must not contain domain-specific track/section capability names.
    New Wellplot capabilities are registered; they do not add graph branches.

The starter intentionally stops after producing ``merged_intent``. Mutation,
verification and visual QA are added in later migration slices after the
planner/worker compiler is proven against the frozen reconstruction baseline.
"""

from __future__ import annotations

from dataclasses import dataclass

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

from ...capabilities import CapabilityRegistry
from ...model.intent import AuthoringDocumentIntent
from .merge import merge_compiled_artifacts
from .models import CompiledArtifact, ReconstructionPlan, SectionPlan
from .planner import ReconstructionPlanner
from .report_worker import ReportCompiler
from .section_worker import SectionCompiler
from .state import CompilationWorkerState, ReconstructionState


@dataclass(slots=True)
class ReconstructionGraphDependencies:
    """Dependencies supplied to the generic compile-only graph."""

    planner: ReconstructionPlanner
    report_compiler: ReportCompiler
    section_compiler: SectionCompiler
    registry: CapabilityRegistry


def build_compile_graph(dependencies: ReconstructionGraphDependencies) -> CompiledStateGraph:
    """Build planner -> dynamic workers -> deterministic merge graph."""

    async def plan_node(state: ReconstructionState) -> dict[str, object]:
        plan = await dependencies.planner.plan(
            request=state["request"],
            current_document=state.get("current_document", {}),
            source_manifest=state.get("source_manifest", {}),
        )
        return {"plan": plan.model_dump(mode="json")}

    async def dispatch_workers(state: ReconstructionState) -> list[Send]:
        """Fan out independent report and section compiler work units."""
        plan = ReconstructionPlan.model_validate(state["plan"])
        sends: list[Send] = [
            Send(
                "compile_artifact",
                CompilationWorkerState(
                    request=state["request"],
                    current_document=state.get("current_document", {}),
                    source_manifest=state.get("source_manifest", {}),
                    work_unit="report",
                    plan=plan.model_dump(mode="json"),
                ),
            )
        ]
        for section in plan.sections:
            sends.append(
                Send(
                    "compile_artifact",
                    CompilationWorkerState(
                        request=state["request"],
                        current_document=state.get("current_document", {}),
                        source_manifest=state.get("source_manifest", {}),
                        work_unit="section",
                        section_plan=section.model_dump(mode="json"),
                    ),
                )
            )
        return sends

    async def compile_artifact_node(state: CompilationWorkerState) -> dict[str, object]:
        if state["work_unit"] == "report":
            plan = ReconstructionPlan.model_validate(state["plan"])
            artifact = await dependencies.report_compiler.compile(
                request=state["request"],
                plan=plan,
                current_document=state["current_document"],
                source_manifest=state["source_manifest"],
            )
        else:
            section_plan = SectionPlan.model_validate(state["section_plan"])
            artifact = await dependencies.section_compiler.compile(
                request=state["request"],
                plan=section_plan,
                current_document=state["current_document"],
                source_manifest=state["source_manifest"],
            )
        return {"compiled_artifacts": [artifact.model_dump(mode="json")]}

    async def merge_node(state: ReconstructionState) -> dict[str, object]:
        """Merge compiled artifacts after every dynamic worker has completed."""
        artifacts = [CompiledArtifact.model_validate(item) for item in state["compiled_artifacts"]]
        merged: AuthoringDocumentIntent = merge_compiled_artifacts(
            artifacts,
            registry=dependencies.registry,
        )
        return {"merged_intent": merged.model_dump(mode="json", exclude_unset=True)}

    builder = StateGraph(ReconstructionState)
    builder.add_node("plan", plan_node)
    builder.add_node("compile_artifact", compile_artifact_node)
    builder.add_node("merge", merge_node)

    builder.add_edge(START, "plan")
    builder.add_conditional_edges(
        "plan",
        dispatch_workers,
        ["compile_artifact"],
    )
    builder.add_edge("compile_artifact", "merge")
    builder.add_edge("merge", END)
    return builder.compile()
