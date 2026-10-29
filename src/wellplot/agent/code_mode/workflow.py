"""Compile-only LangGraph orchestration for Code Mode v2."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Iterable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

from ...capabilities import create_builtin_registry
from ...model.authoring import AuthoringDocumentSpec
from ...model.intent import AuthoringDocumentIntent
from ..inspection import AuthoringInspectionFacade
from ..providers.base import ProviderFailureCategory, ProviderRequestError
from ..providers.response_diagnostics import (
    ProviderResponseFailureReason,
    StructuredResponseProviderError,
)
from ..semantic_runtime import SemanticDiagnostic, SemanticMetrics, SemanticStageEvidence
from .capability_safety import CapabilitySafetyFailure, enforce_capability_safety
from .enrichment import (
    EnrichedSemanticContext,
    ReportContext,
    ResolvedSectionContext,
    SemanticEnricher,
    SemanticEnrichmentError,
    SourceCandidate,
)
from .planner import (
    ReportTask,
    SectionTask,
    SemanticPlan,
    SemanticPlanner,
)
from .report_boundary_safety import ReportBoundarySafetyFailure, enforce_report_boundary_safety
from .section_leaf_safety import SectionLeafSafetyFailure, enforce_section_leaf_safety
from .state import CodeModeGraphState, CodeModeWorkerState, WorkerOutcome
from .worker_contracts import (
    SectionWorkContract,
    SectionWorkContractError,
    build_section_work_contract,
)


@dataclass(frozen=True, slots=True)
class CodeModeGraphDependencies:
    """Host-owned dependencies supplied to one isolated v2 graph."""

    planner: SemanticPlanner
    enricher: SemanticEnricher
    # The shared composition supplies canonical semantic workers. Historical
    # worker implementations remain accepted here only for frozen evidence
    # tests and research fixtures.
    report_compiler: object
    section_compiler: object
    diagnostic_callback: Callable[[Mapping[str, Any]], None] | None = None
    trace_callback: Callable[[Mapping[str, Any]], None] | None = None


def _trace(
    dependencies: CodeModeGraphDependencies,
    event: str,
    **fields: object,
) -> None:
    """Emit optional orchestration evidence without changing graph results."""
    if dependencies.trace_callback is not None:
        dependencies.trace_callback({"event": event, **fields})


def _trace_failure(error: Exception) -> dict[str, object]:
    """Project only stable, explicitly safe error attributes."""
    result: dict[str, object] = {
        "exception_type": type(error).__name__,
        "exception_module": type(error).__module__,
    }
    for attribute in ("code", "safe_message"):
        value = getattr(error, attribute, None)
        if isinstance(value, str):
            result[attribute] = value
    affected_paths = getattr(error, "affected_paths", None)
    if isinstance(affected_paths, tuple) and all(isinstance(path, str) for path in affected_paths):
        result["affected_paths"] = list(affected_paths)
    return result


def build_compile_graph(dependencies: CodeModeGraphDependencies) -> CompiledStateGraph:
    """Build plan -> safety layers -> enrich -> fan-out -> deterministic merge."""

    async def plan_node(state: CodeModeGraphState) -> dict[str, object]:
        """Plan from a bounded document summary, never the full document."""
        document = _document(state)
        inspection = AuthoringInspectionFacade(document)
        summary = inspection.document_summary().model_dump(mode="json")
        summary["existing_section_hints"] = [
            {
                "title": section.title,
                "subtitle": section.subtitle,
            }
            for section in inspection.sections()
        ]
        summary["revision_inventory"] = _revision_inventory(inspection)
        plan = await dependencies.planner.plan(
            request=state["request"],
            mode=state.get("mode", "reconstruct"),
            current_document_summary=summary,
            source_summary=_planner_source_summary(state),
            timeout_seconds=state["timeout_seconds"],
            temperature=state.get("planner_temperature", 0.0),
            max_output_tokens=state.get("max_output_tokens"),
        )
        return {"plan": plan.model_dump(mode="json")}

    async def capability_safety_node(state: CodeModeGraphState) -> dict[str, object]:
        """Apply provider-free admissibility rules before enrichment."""
        plan = SemanticPlan.model_validate(state["plan"])
        registry = getattr(dependencies.planner, "registry", None)
        if registry is None:
            registry = create_builtin_registry()
        _trace(dependencies, "CAPABILITY_SAFETY_ENTER")
        try:
            result = enforce_capability_safety(
                request=state["request"],
                plan=plan,
                registry=registry,
            )
        except CapabilitySafetyFailure as error:
            _trace(dependencies, "CAPABILITY_SAFETY_FAIL", **_trace_failure(error))
            raise
        _trace(dependencies, "CAPABILITY_SAFETY_PASS")
        return {
            "plan": result.safe_plan.model_dump(mode="json"),
            "capability_safety": result.evidence().model_dump(mode="json"),
        }

    async def enrich_node(state: CodeModeGraphState) -> dict[str, object]:
        """Resolve host-provided source candidates into bounded context."""
        plan = SemanticPlan.model_validate(state["plan"])
        _trace(dependencies, "ENRICHMENT_ENTER")
        try:
            context = dependencies.enricher.enrich(
                plan=plan,
                request=state["request"],
                document=_document(state),
                mode=state.get("mode", "reconstruct"),
                source_candidates=tuple(
                    SourceCandidate.model_validate(candidate)
                    for candidate in state.get("source_candidates", [])
                ),
            )
        except SemanticEnrichmentError as error:
            _trace(dependencies, "ENRICHMENT_FAIL", **_trace_failure(error))
            raise
        _trace(dependencies, "ENRICHMENT_PASS")
        return {"enriched_context": context.model_dump(mode="json")}

    async def report_boundary_safety_node(state: CodeModeGraphState) -> dict[str, object]:
        """Apply provider-free report-boundary rules after reference safety."""
        plan = SemanticPlan.model_validate(state["plan"])
        registry = getattr(dependencies.planner, "registry", None)
        if registry is None:
            registry = create_builtin_registry()
        _trace(dependencies, "REPORT_BOUNDARY_ENTER")
        try:
            result = enforce_report_boundary_safety(
                request=state["request"],
                plan=plan,
                registry=registry,
            )
        except ReportBoundarySafetyFailure as error:
            _trace(dependencies, "REPORT_BOUNDARY_FAIL", **_trace_failure(error))
            raise
        _trace(dependencies, "REPORT_BOUNDARY_PASS")
        return {
            "plan": result.safe_plan.model_dump(mode="json"),
            "report_boundary_safety": result.evidence().model_dump(mode="json"),
        }

    async def section_leaf_safety_node(state: CodeModeGraphState) -> dict[str, object]:
        """Apply provider-free section-leaf rules before enrichment."""
        plan = SemanticPlan.model_validate(state["plan"])
        registry = getattr(dependencies.planner, "registry", None)
        if registry is None:
            registry = create_builtin_registry()
        _trace(dependencies, "SECTION_LEAF_ENTER")
        try:
            result = enforce_section_leaf_safety(
                request=state["request"],
                plan=plan,
                registry=registry,
            )
        except SectionLeafSafetyFailure as error:
            _trace(dependencies, "SECTION_LEAF_FAIL", **_trace_failure(error))
            raise
        _trace(dependencies, "SECTION_LEAF_PASS")
        return {
            "plan": result.safe_plan.model_dump(mode="json"),
            "section_leaf_safety": result.evidence().model_dump(mode="json"),
        }

    async def dispatch_workers(state: CodeModeGraphState) -> list[Send]:
        """Dispatch only the task-local context required by each worker."""
        _trace(dependencies, "DISPATCH_ENTER")
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
                error = ValueError("Enriched section context order does not match the plan.")
                _trace(
                    dependencies,
                    "DISPATCH_FAIL",
                    exception_type=type(error).__name__,
                    exception_module=type(error).__module__,
                    code="dispatch_section_context_order_mismatch",
                    safe_message="Enriched section context order does not match the plan.",
                )
                raise error
            try:
                work_contract = build_section_work_contract(task, section_context)
            except SectionWorkContractError as error:
                _trace(
                    dependencies,
                    "SECTION_WORK_CONTRACT_FAIL",
                    code=error.code,
                    plan_order=task_index + 1,
                )
                sends.append(
                    Send(
                        "compile_worker",
                        _worker_payload(
                            state,
                            kind="section",
                            plan_order=task_index + 1,
                            section_work_contract_error=error.code,
                        ),
                    )
                )
                continue
            sends.append(
                Send(
                    "compile_worker",
                    _worker_payload(
                        state,
                        kind="section",
                        plan_order=task_index + 1,
                        section_task=task.model_dump(mode="json"),
                        section_context=section_context.model_dump(mode="json"),
                        section_work_contract=work_contract.model_dump(mode="json"),
                    ),
                )
            )
        if not sends:
            error = ValueError("Semantic plan did not produce any graph work units.")
            _trace(
                dependencies,
                "DISPATCH_FAIL",
                exception_type=type(error).__name__,
                exception_module=type(error).__module__,
                code="dispatch_no_work_units",
                safe_message="Semantic plan did not produce any graph work units.",
            )
            raise error
        _trace(dependencies, "DISPATCH_PASS", work_unit_count=len(sends))
        return sends

    async def compile_worker_node(state: dict[str, Any]) -> dict[str, object]:
        """Run one isolated worker and project only compact safe evidence."""
        worker_state = cast(CodeModeWorkerState, state)
        kind = worker_state["kind"]
        plan_order = worker_state["plan_order"]
        contract_error = worker_state.get("section_work_contract_error")
        if contract_error is not None:
            outcome = WorkerOutcome(
                kind="section",
                plan_order=plan_order,
                success=False,
                diagnostics=(
                    SemanticDiagnostic(
                        stage="worker_obligation",
                        code=contract_error,
                        message="The section work contract could not be established.",
                    ),
                ),
            )
            return _outcome_state(outcome)
        document = AuthoringDocumentSpec.model_validate(worker_state["document"])
        try:
            if kind == "report":
                result = await dependencies.report_compiler.compile(
                    task=ReportTask.model_validate(worker_state["report_task"]),
                    report_context=ReportContext.model_validate(worker_state["report_context"]),
                    document=document,
                    authoritative_request=worker_state["authoritative_request"],
                    timeout_seconds=worker_state["timeout_seconds"],
                    temperature=worker_state.get("temperature"),
                    max_output_tokens=worker_state.get("max_output_tokens"),
                )
            else:
                task = SectionTask.model_validate(worker_state["section_task"])
                section_context = ResolvedSectionContext.model_validate(
                    worker_state["section_context"]
                )
                work_contract = SectionWorkContract.model_validate(
                    worker_state["section_work_contract"]
                )
                isolated_context = _isolated_section_context(task, section_context)
                result = await dependencies.section_compiler.compile(
                    task_index=0,
                    context=isolated_context,
                    document=document,
                    authoritative_request=worker_state["authoritative_request"],
                    work_contract=work_contract,
                    timeout_seconds=worker_state["timeout_seconds"],
                    temperature=worker_state.get("temperature"),
                    max_output_tokens=worker_state.get("max_output_tokens"),
                )
        except ProviderRequestError as error:
            diagnostic = SemanticDiagnostic(
                stage="provider",
                code=_provider_diagnostic_code(error),
                message=error.safe_message,
                remediation_hint="Retry the graph with a functioning provider configuration.",
            )
            outcome = WorkerOutcome(
                kind=kind,
                plan_order=plan_order,
                success=False,
                diagnostics=(diagnostic,),
                metrics=SemanticMetrics(),
            )
            return _outcome_state(outcome)
        except asyncio.CancelledError:
            raise
        except BaseException as error:
            callback = dependencies.diagnostic_callback
            if callback is not None:
                with suppress(Exception):
                    callback(
                        {
                            "event": "worker_exception",
                            "worker_kind": kind,
                            "plan_order": plan_order,
                            "stage": "compile_worker",
                            "exception_type": type(error).__name__,
                            "exception_module": type(error).__module__,
                            "provider_call_in_flight": None,
                            "provider_call_state": "UNKNOWN",
                        }
                    )
            raise

        intent_fragment = getattr(result, "intent_fragment", None)
        if intent_fragment is None and result.success:
            artifact = getattr(result, "artifact", None)
            intent_fragment = None if artifact is None else artifact.intent_fragment
        outcome = WorkerOutcome(
            kind=kind,
            plan_order=plan_order,
            success=result.success,
            intent_fragment=intent_fragment if result.success else None,
            diagnostics=_semantic_diagnostics(result.diagnostics),
            metrics=_semantic_metrics(result.metrics),
            stage_evidence=getattr(result, "stage_evidence", SemanticStageEvidence()),
        )
        return _outcome_state(outcome)

    async def merge_node(state: CodeModeGraphState) -> dict[str, object]:
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
    builder.add_node("capability_safety", capability_safety_node)
    builder.add_node("report_boundary_safety", report_boundary_safety_node)
    builder.add_node("section_leaf_safety", section_leaf_safety_node)
    builder.add_node("enrich_context", enrich_node)
    builder.add_node("compile_worker", compile_worker_node)
    builder.add_node("merge_intent", merge_node)
    builder.add_edge(START, "plan_v2")
    builder.add_edge("plan_v2", "capability_safety")
    builder.add_edge("capability_safety", "report_boundary_safety")
    builder.add_edge("report_boundary_safety", "section_leaf_safety")
    builder.add_edge("section_leaf_safety", "enrich_context")
    builder.add_conditional_edges(
        "enrich_context",
        dispatch_workers,
        ["compile_worker"],
    )
    builder.add_edge("compile_worker", "merge_intent")
    builder.add_edge("merge_intent", END)
    return builder.compile()


def _semantic_metrics(value: object) -> SemanticMetrics:
    """Normalize compatible worker measurements at the shared graph boundary."""
    if isinstance(value, SemanticMetrics):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return SemanticMetrics.model_validate(model_dump(mode="json"))
    raise TypeError("Worker metrics must expose a provider-neutral model mapping.")


def _semantic_diagnostics(values: object) -> tuple[SemanticDiagnostic, ...]:
    """Normalize compatible worker diagnostics at the shared graph boundary."""
    if not isinstance(values, (tuple, list)):
        raise TypeError("Worker diagnostics must be a sequence.")
    diagnostics: list[SemanticDiagnostic] = []
    for value in values:
        if isinstance(value, SemanticDiagnostic):
            diagnostics.append(value)
            continue
        model_dump = getattr(value, "model_dump", None)
        if not callable(model_dump):
            raise TypeError("Worker diagnostics must expose a provider-neutral model mapping.")
        payload = model_dump(mode="json")
        diagnostics.append(
            SemanticDiagnostic(
                stage=payload["stage"],
                message=payload["message"],
                severity=payload.get("severity", "error"),
                code=payload.get("code"),
                remediation_hint=payload.get("remediation_hint"),
            )
        )
    return tuple(diagnostics)


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
    **scoped: object,
) -> CodeModeWorkerState:
    """Build a JSON-safe Send payload with no full enriched context."""
    return cast(
        CodeModeWorkerState,
        {
            "kind": kind,
            "plan_order": plan_order,
            "authoritative_request": state["request"],
            "document": state["document"],
            "timeout_seconds": state["timeout_seconds"],
            "temperature": state.get("temperature"),
            "max_output_tokens": state.get("max_output_tokens"),
            **scoped,
        },
    )


def _planner_source_summary(state: CodeModeGraphState) -> dict[str, object]:
    """Build provider-safe source facts with explicit inspection state."""
    candidates = [
        SourceCandidate.model_validate(candidate)
        for candidate in state.get("source_candidates", [])
    ]
    return {
        "version": "cm56r3.source-summary.v1",
        "sources": [
            {
                "labels": list(candidate.labels),
                "channels": [
                    {
                        "mnemonic": channel.mnemonic,
                        "kind": channel.kind,
                        "unit": channel.unit,
                    }
                    for channel in candidate.channels
                ],
                "inspection_state": candidate.inspection_state,
            }
            for candidate in candidates
        ],
    }


def _revision_inventory(inspection: AuthoringInspectionFacade) -> list[dict[str, object]]:
    """Expose semantic revision facts without host IDs or mutation handles."""
    return [dict(item) for item in inspection.semantic_inventory()]


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


def _provider_diagnostic_code(error: ProviderRequestError) -> str:
    """Classify provider and structured-output failures without raw payloads."""
    if isinstance(error, StructuredResponseProviderError):
        if error.response_reason is ProviderResponseFailureReason.SCHEMA_VALIDATION:
            return "structured_schema_validation_failure"
        return "structured_output_decode_failure"
    if error.category is ProviderFailureCategory.TRANSPORT:
        return "provider_transport_failure"
    return f"provider.{error.category.value}"


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
                    )
                )
                or fragment.removals
            ):
                raise ValueError("Section worker emitted report-wide or global intent.")
            if fragment.sections is not None:
                if len(fragment.sections) != 1:
                    raise ValueError("Section worker must emit exactly one section fragment.")
                section_id = fragment.sections[0].section_id
            else:
                child_fragments = [
                    child
                    for name in ("curve_bindings", "raster_bindings", "fills", "annotations")
                    for child in (getattr(fragment, name) or [])
                ]
                child_section_ids = {
                    getattr(child, "section_id", None) for child in child_fragments
                }
                if not child_fragments or len(child_section_ids) != 1:
                    raise ValueError("Section worker must emit one section-local fragment.")
                section_id = next(iter(child_section_ids))
                if section_id is None:
                    raise ValueError("Section worker fragment must identify its section.")
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
