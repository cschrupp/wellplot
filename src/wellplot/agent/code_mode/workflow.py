"""Compile-only LangGraph orchestration for Code Mode v2."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

from ...authoring_program.inspection import AuthoringInspectionFacade
from ...authoring_program.models import ProgramDiagnostic, ProgramMetrics
from ...model.authoring import AuthoringDocumentSpec
from ...model.intent import AuthoringDocumentIntent
from ..providers.base import ProviderRequestError
from .enrichment import (
    EnrichedSemanticContext,
    ReportContext,
    ResolvedSectionContext,
    SemanticEnricher,
    SourceCandidate,
)
from .planner import (
    ReportTask,
    SectionTask,
    SemanticPlan,
    SemanticPlanner,
)
from .program_worker import ProgramSectionCompiler
from .report_worker import ReportProgramCompiler
from .state import CodeModeGraphState, CodeModeWorkerState, WorkerOutcome


@dataclass(frozen=True, slots=True)
class CodeModeGraphDependencies:
    """Host-owned dependencies supplied to one isolated v2 graph."""

    planner: SemanticPlanner
    enricher: SemanticEnricher
    report_compiler: ReportProgramCompiler
    section_compiler: ProgramSectionCompiler


def build_compile_graph(dependencies: CodeModeGraphDependencies) -> CompiledStateGraph:
    """Build plan -> enrich -> fan-out -> deterministic merge workflow."""

    def plan_node(state: CodeModeGraphState) -> dict[str, object]:
        """Run the async planner from the synchronous compile graph."""
        return asyncio.run(_plan_node(state))

    async def _plan_node(state: CodeModeGraphState) -> dict[str, object]:
        """Plan from a bounded document summary, never the full document."""
        document = _document(state)
        summary = AuthoringInspectionFacade(document).document_summary()
        plan = await dependencies.planner.plan(
            request=state["request"],
            mode=state.get("mode", "reconstruct"),
            current_document_summary=summary.model_dump(mode="json"),
            timeout_seconds=state["timeout_seconds"],
            temperature=state.get("temperature"),
            max_output_tokens=state.get("max_output_tokens"),
        )
        return {"plan": plan.model_dump(mode="json")}

    def enrich_node(state: CodeModeGraphState) -> dict[str, object]:
        """Resolve host-provided source candidates into bounded context."""
        plan = SemanticPlan.model_validate(state["plan"])
        context = dependencies.enricher.enrich(
            plan=plan,
            document=_document(state),
            source_candidates=tuple(
                SourceCandidate.model_validate(candidate)
                for candidate in state.get("source_candidates", [])
            ),
        )
        return {"enriched_context": context.model_dump(mode="json")}

    def dispatch_workers(state: CodeModeGraphState) -> list[Send]:
        """Dispatch only the task-local context required by each worker."""
        plan = SemanticPlan.model_validate(state["plan"])
        context = EnrichedSemanticContext.model_validate(state["enriched_context"])
        sends: list[Send] = []
        if plan.report_task is not None:
            sends.append(
                Send(
                    "compile_worker",
                    _worker_payload(
                        state,
                        kind="report",
                        plan_order=0,
                        report_task=plan.report_task.model_dump(mode="json"),
                        report_context=context.report.model_dump(mode="json"),
                    ),
                )
            )
        for task_index, task in enumerate(plan.section_tasks):
            section_context = context.sections[task_index]
            if section_context.task_index != task_index:
                raise ValueError("Enriched section context order does not match the plan.")
            sends.append(
                Send(
                    "compile_worker",
                    _worker_payload(
                        state,
                        kind="section",
                        plan_order=task_index + 1,
                        section_task=task.model_dump(mode="json"),
                        section_context=section_context.model_dump(mode="json"),
                    ),
                )
            )
        if not sends:
            raise ValueError("Semantic plan did not produce any graph work units.")
        return sends

    def compile_worker_node(state: dict[str, Any]) -> dict[str, object]:
        """Run one async compiler from a synchronous LangGraph Send node."""
        return asyncio.run(_compile_worker_node(state))

    async def _compile_worker_node(state: dict[str, Any]) -> dict[str, object]:
        """Run one isolated worker and project only compact safe evidence."""
        worker_state = cast(CodeModeWorkerState, state)
        kind = worker_state["kind"]
        plan_order = worker_state["plan_order"]
        document = AuthoringDocumentSpec.model_validate(worker_state["document"])
        try:
            if kind == "report":
                result = await dependencies.report_compiler.compile(
                    task=ReportTask.model_validate(worker_state["report_task"]),
                    report_context=ReportContext.model_validate(worker_state["report_context"]),
                    document=document,
                    timeout_seconds=worker_state["timeout_seconds"],
                    temperature=worker_state.get("temperature"),
                    max_output_tokens=worker_state.get("max_output_tokens"),
                )
            else:
                task = SectionTask.model_validate(worker_state["section_task"])
                section_context = ResolvedSectionContext.model_validate(
                    worker_state["section_context"]
                )
                isolated_context = _isolated_section_context(task, section_context)
                result = await dependencies.section_compiler.compile(
                    task_index=0,
                    context=isolated_context,
                    document=document,
                    timeout_seconds=worker_state["timeout_seconds"],
                    temperature=worker_state.get("temperature"),
                    max_output_tokens=worker_state.get("max_output_tokens"),
                )
        except ProviderRequestError as error:
            diagnostic = ProgramDiagnostic(
                stage="provider",
                code=f"provider.{error.category.value}",
                message=error.safe_message,
                remediation_hint="Retry the graph with a functioning provider configuration.",
            )
            outcome = WorkerOutcome(
                kind=kind,
                plan_order=plan_order,
                success=False,
                diagnostics=(diagnostic,),
                metrics=ProgramMetrics(),
            )
            return _outcome_state(outcome)

        outcome = WorkerOutcome(
            kind=kind,
            plan_order=plan_order,
            success=result.success,
            intent_fragment=(result.artifact.intent_fragment if result.success else None),
            diagnostics=result.diagnostics,
            metrics=result.metrics,
        )
        return _outcome_state(outcome)

    def merge_node(state: CodeModeGraphState) -> dict[str, object]:
        """Reject incomplete/failed fan-out and merge successful intents in plan order."""
        plan = SemanticPlan.model_validate(state["plan"])
        outcomes = tuple(
            WorkerOutcome.model_validate(json.loads(outcome))
            for outcome in state.get("worker_outcomes", [])
        )
        _validate_outcomes(outcomes, plan)
        if any(not outcome.success for outcome in outcomes):
            return {}

        fragments = [
            outcome.intent_fragment
            for outcome in sorted(outcomes, key=lambda item: item.plan_order)
        ]
        typed_fragments = [fragment for fragment in fragments if fragment is not None]
        _validate_fragment_boundaries(outcomes)
        merged = merge_v2_intents(typed_fragments)
        return {"merged_intent": merged.model_dump(mode="json", exclude_unset=True)}

    builder = StateGraph(CodeModeGraphState)
    builder.add_node("plan_v2", plan_node)
    builder.add_node("enrich_context", enrich_node)
    builder.add_node("compile_worker", compile_worker_node)
    builder.add_node("merge_intent", merge_node)
    builder.add_edge(START, "plan_v2")
    builder.add_edge("plan_v2", "enrich_context")
    builder.add_conditional_edges(
        "enrich_context",
        dispatch_workers,
        ["compile_worker"],
    )
    builder.add_edge("compile_worker", "merge_intent")
    builder.add_edge("merge_intent", END)
    return builder.compile()


def merge_v2_intents(
    fragments: Iterable[AuthoringDocumentIntent],
) -> AuthoringDocumentIntent:
    """Merge non-overlapping v2 fragments without importing the legacy graph."""
    merged: dict[str, object] = {}
    for fragment in fragments:
        payload = fragment.model_dump(mode="python", exclude_unset=True)
        for field_name, value in payload.items():
            if field_name not in merged:
                merged[field_name] = value
                continue
            previous = merged[field_name]
            if isinstance(previous, list) and isinstance(value, list):
                merged[field_name] = _merge_identity_list(field_name, previous, value)
                continue
            if previous != value:
                raise ValueError(f"Conflicting v2 intent field {field_name!r}.")
    return AuthoringDocumentIntent.model_validate(merged)


def _merge_identity_list(
    field_name: str,
    left: list[Any],
    right: list[Any],
) -> list[Any]:
    """Merge stable-identity lists while rejecting conflicting definitions."""
    identity_field = {
        "sections": "section_id",
        "remarks": "remark_id",
        "curve_bindings": "binding_id",
        "raster_bindings": "binding_id",
        "fills": "fill_id",
        "annotations": "annotation_id",
    }.get(field_name)
    if identity_field is None:
        return [*left, *right]
    merged = list(left)
    by_id = {
        str(item[identity_field]): item
        for item in merged
        if isinstance(item, dict) and item.get(identity_field) is not None
    }
    for item in right:
        if not isinstance(item, dict) or item.get(identity_field) is None:
            merged.append(item)
            continue
        object_id = str(item[identity_field])
        previous = by_id.get(object_id)
        if previous is None:
            merged.append(item)
            by_id[object_id] = item
        elif previous != item:
            raise ValueError(f"Conflicting v2 {field_name} identity {object_id!r}.")
    return merged


def _worker_payload(
    state: CodeModeGraphState,
    *,
    kind: str,
    plan_order: int,
    **scoped: dict[str, Any],
) -> CodeModeWorkerState:
    """Build a JSON-safe Send payload with no full enriched context."""
    return cast(
        CodeModeWorkerState,
        {
            "kind": kind,
            "plan_order": plan_order,
            "document": state["document"],
            "timeout_seconds": state["timeout_seconds"],
            "temperature": state.get("temperature"),
            "max_output_tokens": state.get("max_output_tokens"),
            **scoped,
        },
    )


def _isolated_section_context(
    task: SectionTask,
    section_context: ResolvedSectionContext,
) -> EnrichedSemanticContext:
    """Rebuild a one-task context so section workers cannot see siblings."""
    plan = SemanticPlan(summary=task.goal, section_tasks=(task,))
    return EnrichedSemanticContext(
        plan=plan,
        sections=(section_context.model_copy(update={"task_index": 0}),),
        report=ReportContext(),
    )


def _outcome_state(outcome: WorkerOutcome) -> dict[str, object]:
    """Project one outcome and its diagnostics into reducer state."""
    payload = outcome.model_dump(mode="json", exclude_unset=True)
    state: dict[str, object] = {
        "worker_outcomes": [
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
        ]
    }
    if outcome.diagnostics:
        state["diagnostics"] = [
            json.dumps(
                diagnostic.model_dump(mode="json"),
                sort_keys=True,
                separators=(",", ":"),
            )
            for diagnostic in outcome.diagnostics
        ]
    return state


def _validate_outcomes(
    outcomes: tuple[WorkerOutcome, ...],
    plan: SemanticPlan,
) -> None:
    """Require exactly one result for every dispatched work unit."""
    expected = {("report", 0)} if plan.report_task is not None else set()
    expected.update(("section", index + 1) for index in range(len(plan.section_tasks)))
    actual = {(outcome.kind, outcome.plan_order) for outcome in outcomes}
    if actual != expected or len(actual) != len(outcomes):
        raise ValueError("Code Mode worker outcomes do not exactly match dispatched work units.")


def _validate_fragment_boundaries(outcomes: Iterable[WorkerOutcome]) -> None:
    """Recheck report/section isolation and reject duplicate section identities."""
    section_ids: set[str] = set()
    for outcome in outcomes:
        fragment = outcome.intent_fragment
        if fragment is None:
            raise ValueError("Successful worker outcome is missing its intent fragment.")
        if outcome.kind == "report":
            if (
                fragment.sections is not None
                or fragment.removals
                or any(
                    getattr(fragment, name) is not None
                    for name in ("curve_bindings", "raster_bindings", "fills", "annotations")
                )
            ):
                raise ValueError("Report worker emitted section or child intent.")
        else:
            if fragment.sections is None or len(fragment.sections) != 1:
                raise ValueError("Section worker must emit exactly one section fragment.")
            if (
                any(
                    getattr(fragment, name) is not None
                    for name in (
                        "title",
                        "subtitle",
                        "output",
                        "page",
                        "depth",
                        "header",
                        "tail",
                        "remarks",
                        "curve_bindings",
                        "raster_bindings",
                        "fills",
                        "annotations",
                    )
                )
                or fragment.removals
            ):
                raise ValueError("Section worker emitted report-wide or global intent.")
            section_id = fragment.sections[0].section_id
            if section_id in section_ids:
                raise ValueError(f"Duplicate v2 section identity {section_id!r}.")
            section_ids.add(section_id)


def _document(state: CodeModeGraphState) -> AuthoringDocumentSpec:
    """Validate the canonical document at each node boundary."""
    return AuthoringDocumentSpec.model_validate(state["document"])


__all__ = [
    "CodeModeGraphDependencies",
    "build_compile_graph",
    "merge_v2_intents",
]
