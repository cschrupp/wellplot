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
from typing import cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

from ...capabilities import CapabilityRegistry
from ...model.intent import AuthoringDocumentIntent
from ..execution_trace import current_agent_trace
from .merge import merge_compiled_artifacts
from .models import CompilationMode, CompiledArtifact, ReconstructionPlan, SectionPlan
from .planner import ReconstructionPlanner
from .report_worker import ReportCompiler
from .section_worker import SectionCompiler
from .source_context import PlannedSourceContextResolver
from .state import CompilationWorkerState, ReconstructionState


@dataclass(slots=True)
class ReconstructionGraphDependencies:
    """Dependencies supplied to the generic compile-only graph."""

    planner: ReconstructionPlanner
    report_compiler: ReportCompiler
    section_compiler: SectionCompiler
    registry: CapabilityRegistry
    source_context_resolver: PlannedSourceContextResolver | None = None


def _compilation_mode(value: object) -> CompilationMode:
    """Validate the explicit compilation mode carried in graph state."""
    if value not in {"reconstruct", "revise"}:
        raise ValueError("Graph compilation mode must be 'reconstruct' or 'revise'.")
    return cast(CompilationMode, value)


def build_compile_graph(dependencies: ReconstructionGraphDependencies) -> CompiledStateGraph:
    """Build planner -> dynamic workers -> deterministic merge graph."""

    async def plan_node(state: ReconstructionState) -> dict[str, object]:
        mode = _compilation_mode(state.get("mode", "reconstruct"))
        plan = await dependencies.planner.plan(
            request=state["request"],
            current_document=state.get("current_document", {}),
            source_manifest=state.get("source_manifest", {}),
            mode=mode,
        )
        return {"plan": plan.model_dump(mode="json")}

    async def resolve_planned_sources_node(state: ReconstructionState) -> dict[str, object]:
        """Load only explicit planner-selected sources before worker fan-out."""
        resolver = dependencies.source_context_resolver
        if resolver is None:
            return {}
        plan = ReconstructionPlan.model_validate(state["plan"])
        normalized_plan = resolver.normalize_plan_sources(
            plan=plan,
            logfile_path=state.get("logfile_path"),
        )
        trace = current_agent_trace()
        source_manifest = state.get("source_manifest", {})
        if trace is None:
            enriched = resolver.enrich(
                plan=normalized_plan,
                source_manifest=source_manifest,
                logfile_path=state.get("logfile_path"),
            )
        else:
            with trace.stage("source_context"):
                enriched = resolver.enrich(
                    plan=normalized_plan,
                    source_manifest=source_manifest,
                    logfile_path=state.get("logfile_path"),
                )
                trace.record(
                    "planned_source_context_ready",
                    status="ready",
                    details={
                        "planned_section_ids": [
                            section.section_id for section in normalized_plan.sections
                        ],
                        "source_section_ids": sorted(enriched),
                    },
                )
        return {
            "plan": normalized_plan.model_dump(mode="json"),
            "source_manifest": enriched,
        }

    async def dispatch_workers(state: ReconstructionState) -> list[Send]:
        """Fan out independent report and section compiler work units."""
        plan = ReconstructionPlan.model_validate(state["plan"])
        mode = _compilation_mode(state.get("mode", "reconstruct"))
        sends: list[Send] = [
            Send(
                "compile_artifact",
                CompilationWorkerState(
                    request=state["request"],
                    mode=mode,
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
                        mode=mode,
                        current_document=state.get("current_document", {}),
                        source_manifest=state.get("source_manifest", {}),
                        work_unit="section",
                        section_plan=section.model_dump(mode="json"),
                    ),
                )
            )
        return sends

    async def compile_artifact_node(state: CompilationWorkerState) -> dict[str, object]:
        mode = _compilation_mode(state.get("mode", "reconstruct"))
        if state["work_unit"] == "report":
            plan = ReconstructionPlan.model_validate(state["plan"])
            artifact = await dependencies.report_compiler.compile(
                request=state["request"],
                plan=plan,
                current_document=state["current_document"],
                source_manifest=state["source_manifest"],
                mode=mode,
            )
        else:
            section_plan = SectionPlan.model_validate(state["section_plan"])
            artifact = await dependencies.section_compiler.compile(
                request=state["request"],
                plan=section_plan,
                current_document=state["current_document"],
                source_manifest=state["source_manifest"],
                mode=mode,
            )
        return {"compiled_artifacts": [artifact.model_dump(mode="json")]}

    async def merge_node(state: ReconstructionState) -> dict[str, object]:
        """Merge compiled artifacts after every dynamic worker has completed."""
        trace = current_agent_trace()
        if trace is None:
            artifacts = [
                CompiledArtifact.model_validate(item) for item in state["compiled_artifacts"]
            ]
            merged: AuthoringDocumentIntent = merge_compiled_artifacts(
                artifacts,
                registry=dependencies.registry,
            )
        else:
            with trace.stage("merge"):
                artifacts = [
                    CompiledArtifact.model_validate(item) for item in state["compiled_artifacts"]
                ]
                merged = merge_compiled_artifacts(
                    artifacts,
                    registry=dependencies.registry,
                )
                trace.record(
                    "merged_intent",
                    status="accepted",
                    payload=merged.model_dump(mode="json", exclude_unset=True),
                )
        return {"merged_intent": merged.model_dump(mode="json", exclude_unset=True)}

    builder = StateGraph(ReconstructionState)
    builder.add_node("plan", plan_node)
    builder.add_node("resolve_planned_sources", resolve_planned_sources_node)
    builder.add_node("compile_artifact", compile_artifact_node)
    builder.add_node("merge", merge_node)

    builder.add_edge(START, "plan")
    builder.add_edge("plan", "resolve_planned_sources")
    builder.add_conditional_edges(
        "resolve_planned_sources",
        dispatch_workers,
        ["compile_artifact"],
    )
    builder.add_edge("compile_artifact", "merge")
    builder.add_edge("merge", END)
    return builder.compile()
