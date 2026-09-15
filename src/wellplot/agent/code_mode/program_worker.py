"""Bounded section program compilation for Code Mode v2."""

from __future__ import annotations

import json
from dataclasses import dataclass

from ...authoring_context import AuthoringChannelCandidate
from ...authoring_program.builders import HandleBuilder
from ...authoring_program.errors import AuthoringProgramError, ProgramDryRunError
from ...authoring_program.ids import IdAllocator
from ...authoring_program.intent_builder import IntentBuilder
from ...authoring_program.interpreter import interpret_authoring_program
from ...authoring_program.models import (
    AuthoringProgram,
    ProgramDiagnostic,
    ProgramExecutionResult,
    ProgramMetrics,
    ProgramSource,
)
from ...authoring_program.program_runtime import ProgramRuntime
from ...capabilities import CapabilityRegistry
from ...model.authoring import AuthoringDataSource, AuthoringDocumentSpec
from ...model.intent import AuthoringDocumentIntent
from ..providers.base import ModelBackendProtocol, ProgramGenerationRequest
from .enrichment import EnrichedSemanticContext, ResolvedSectionContext
from .planner import SectionTask
from .repair import ProgramRepairCoordinator

SECTION_PROGRAM_CAPABILITIES = frozenset(
    {
        "section.log_plot",
        "track.normal",
        "track.reference",
        "track.array",
        "binding.curve",
        "binding.raster",
    }
)

_SDK_REFERENCE = """Executable Wellplot SDK reference:
report = wp.report()
source = wp.source('candidate-id')
section = wp.section(
    report,
    id_hint='new-section',
    title='Section title',
    source=source,
)
normal = wp.track(
    section,
    id_hint='normal',
    kind='normal',
    title='Normal track',
    width_mm=30,
)
reference = wp.track(
    section,
    id_hint='reference',
    kind='reference',
    title='Reference track',
    width_mm=30,
)
array = wp.track(
    section,
    id_hint='array',
    kind='array',
    title='Array track',
    width_mm=30,
)
wp.curve(normal, channel='CHANNEL', label='Curve label')
wp.curve(reference, channel='REFERENCE_CHANNEL', label='Reference label')
wp.raster(array, channel='ARRAY_CHANNEL', label='Array label')

Only the root calls and keyword arguments shown above are executable. Create a
new section only. Use only source candidate IDs supplied in the task context.
Do not use existing document identifiers, selection/update operations,
report-wide settings, or filesystem operations.
Return only the program source, with no markdown fences or explanation."""


@dataclass(frozen=True, slots=True)
class ProgramSectionCompiler:
    """Compile one new section program without mutating a document."""

    backend: ModelBackendProtocol
    registry: CapabilityRegistry
    repair_coordinator: ProgramRepairCoordinator | None = None

    async def compile(
        self,
        *,
        task_index: int,
        context: EnrichedSemanticContext,
        document: AuthoringDocumentSpec,
        timeout_seconds: float,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> ProgramExecutionResult:
        """Generate, interpret, and privately dry-run one section program."""
        task, section_context = _task_context(context, task_index)
        if section_context.section_id is not None:
            raise ValueError(
                "Code Mode new section reconstruction only; existing-section "
                "revision is not available in the restricted SDK."
            )

        capabilities = _worker_capabilities(task, self.registry)
        request = ProgramGenerationRequest(
            system_prompt=(
                "You are the Wellplot section Code Mode worker. "
                "Write one short restricted authoring program using only the "
                "executable SDK reference and scoped task context."
            ),
            user_prompt=_worker_prompt(
                task=task,
                section_context=section_context,
                capabilities=capabilities,
            ),
            timeout_seconds=timeout_seconds,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
        generated = await self.backend.generate_program(request)
        initial = self._attempt(
            generated.text,
            task_index=task_index,
            section_context=section_context,
            document=document,
        )
        if initial.success:
            return initial

        diagnostic = initial.diagnostics[0]
        coordinator = self.repair_coordinator or ProgramRepairCoordinator(self.backend)
        repair = await coordinator.repair(
            semantic_task=_semantic_task_text(task),
            sdk_docs=_SDK_REFERENCE,
            previous_program=generated.text,
            diagnostic=diagnostic,
            timeout_seconds=timeout_seconds,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
        if repair.source is None:
            return _with_repair_evidence(
                initial,
                repair_count=repair.repair_count,
                diagnostics=repair.diagnostics,
            )

        repaired = self._attempt(
            repair.source,
            task_index=task_index,
            section_context=section_context,
            document=document,
        )
        return _with_repair_evidence(
            repaired,
            repair_count=repair.repair_count,
            diagnostics=repair.diagnostics,
        )

    def _attempt(
        self,
        source: str,
        *,
        task_index: int,
        section_context: ResolvedSectionContext,
        document: AuthoringDocumentSpec,
    ) -> ProgramExecutionResult:
        """Run one candidate with a fresh identity builder and private runtime."""
        program = AuthoringProgram(
            source=ProgramSource(text=source, logical_name=f"cm43r-section-{task_index}.wpa")
        )
        builder = _fresh_builder(
            document,
            section_context=section_context,
        )
        try:
            interpretation = interpret_authoring_program(
                program,
                builder.runtime_environment(),
            )
            intent = builder.intent()
            section_id = _validate_section_intent(intent)
            runtime = ProgramRuntime(
                document,
                available_channels={
                    section_id: _available_channels(section_context),
                },
            )
            return runtime.dry_run(
                program,
                intent,
                metrics=interpretation.metrics,
            )
        except AuthoringProgramError as error:
            return _failed_result(
                program,
                error.to_diagnostic(),
                metrics=ProgramMetrics(program_chars=len(source)),
            )
        except Exception:
            return _failed_result(
                program,
                ProgramDryRunError(
                    "Section program could not be compiled deterministically.",
                    remediation_hint="Return one new section using only the selected capabilities.",
                ).to_diagnostic(),
                metrics=ProgramMetrics(program_chars=len(source)),
            )


def _task_context(
    context: EnrichedSemanticContext,
    task_index: int,
) -> tuple[SectionTask, ResolvedSectionContext]:
    """Require one task and its indexed enrichment context to remain paired."""
    if task_index < 0 or task_index >= len(context.plan.section_tasks):
        raise IndexError("Program section task index is outside the semantic plan.")
    if task_index >= len(context.sections):
        raise ValueError("Enriched context does not contain the requested section task.")
    task = context.plan.section_tasks[task_index]
    section_context = context.sections[task_index]
    if section_context.task_index != task_index:
        raise ValueError("Enriched section context does not match the requested task index.")
    return task, section_context


def _worker_capabilities(
    task: SectionTask,
    registry: CapabilityRegistry,
) -> tuple[dict[str, object], ...]:
    """Resolve selected canonical v2 capabilities into compact worker facts."""
    descriptors: list[dict[str, object]] = []
    for capability_id in task.capability_ids:
        spec = registry.get(capability_id)
        if spec.capability_id != capability_id:
            raise ValueError(f"Capability selection must use canonical id {spec.capability_id!r}.")
        if not spec.supports_v2:
            raise ValueError(f"Capability {capability_id!r} does not support Code Mode v2.")
        descriptors.append(
            {
                "id": spec.capability_id,
                "category": spec.category,
                "description": spec.description,
                "allowed_parents": list(spec.allowed_parents),
                "source_kinds": list(spec.source_kinds),
                "worker_hints": list(spec.worker_hints),
            }
        )
    return tuple(descriptors)


def _worker_prompt(
    *,
    task: SectionTask,
    section_context: ResolvedSectionContext,
    capabilities: tuple[dict[str, object], ...],
) -> str:
    """Serialize only the selected section's bounded worker context."""
    payload = {
        "section_task": {
            "goal": task.goal,
            "capability_ids": list(task.capability_ids),
            "requirements": list(task.requirements),
            "constraints": list(task.constraints),
        },
        "capabilities": capabilities,
        "section_context": {
            "task_index": section_context.task_index,
            "section_id": section_context.section_id,
            "channels": [channel.model_dump(mode="json") for channel in section_context.channels],
            "sources": [
                {
                    "candidate_id": source.candidate_id,
                    "source_format": source.source_format,
                    "dataset_name": source.dataset_name,
                    "well_metadata": [
                        item.model_dump(mode="json") for item in source.well_metadata
                    ],
                    "channels": [channel.model_dump(mode="json") for channel in source.channels],
                }
                for source in section_context.sources
            ],
        },
        "sdk_reference": _SDK_REFERENCE,
    }
    return (
        "Create one new section from this scoped context. When a source candidate "
        "is needed, resolve its exact candidate_id with wp.source() and pass the "
        "handle to wp.section(). Do not add report-wide settings or use context "
        "outside this task.\n\n" + json.dumps(payload, sort_keys=True, separators=(",", ":"))
    )


def _semantic_task_text(task: SectionTask) -> str:
    """Format the selected task for the bounded repair prompt."""
    return json.dumps(
        {
            "goal": task.goal,
            "capability_ids": list(task.capability_ids),
            "requirements": list(task.requirements),
            "constraints": list(task.constraints),
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _fresh_builder(
    document: AuthoringDocumentSpec,
    *,
    section_context: ResolvedSectionContext,
) -> IntentBuilder:
    """Create a fresh builder with identities and source candidates reserved."""
    allocator = IdAllocator(
        section_ids=[section.id for section in document.sections],
        track_ids_by_section={
            section.id: [track.id for track in section.tracks] for section in document.sections
        },
        binding_ids=[
            binding.binding_id
            for section in document.sections
            for track in section.tracks
            for binding in getattr(track, "bindings", ())
        ],
        leaf_ids=[
            leaf_id
            for section in document.sections
            for track in section.tracks
            for leaf_id in _track_leaf_ids(track)
        ],
    )
    handles = HandleBuilder(allocator=allocator)
    builder = IntentBuilder(handles=handles)
    for source in section_context.sources:
        builder.register_source(
            source.candidate_id,
            AuthoringDataSource(
                source_path=source.canonical_path,
                source_format=source.source_format,
            ),
        )
    return builder


def _track_leaf_ids(track: object) -> tuple[str, ...]:
    """Return existing fill and annotation identities for allocator seeding."""
    fill_ids = tuple(
        fill.fill_id for fill in getattr(track, "fills", ()) if fill.fill_id is not None
    )
    annotation_ids = tuple(
        annotation.annotation_id
        for annotation in getattr(track, "annotations", ())
        if annotation.annotation_id is not None
    )
    return fill_ids + annotation_ids


def _available_channels(
    section_context: ResolvedSectionContext,
) -> list[AuthoringChannelCandidate]:
    """Project only selected source channels into private dry-run context."""
    return [
        AuthoringChannelCandidate(
            mnemonic=channel.mnemonic,
            kind=channel.kind,
            aliases=list(channel.aliases),
            unit=channel.unit,
            description=channel.description,
            value_shape=list(channel.shape),
            source_path=source.canonical_path,
        )
        for source in section_context.sources
        for channel in source.channels
    ]


def _validate_section_intent(intent: AuthoringDocumentIntent) -> str:
    """Reject report-wide or multi-section output from a section worker."""
    report_fields = (
        "title",
        "subtitle",
        "output",
        "page",
        "depth",
        "header",
        "tail",
        "remarks",
    )
    if any(getattr(intent, field_name) is not None for field_name in report_fields):
        raise ProgramDryRunError(
            "Section programs may emit only section-local authoring intent.",
            remediation_hint="Remove report-wide settings and emit one new section.",
        )
    if intent.removals or any(
        getattr(intent, field_name) is not None
        for field_name in ("curve_bindings", "raster_bindings", "fills", "annotations")
    ):
        raise ProgramDryRunError(
            "Section programs may not emit global child lists or removals.",
            remediation_hint="Create child objects under the new section track.",
        )
    if intent.sections is None or len(intent.sections) != 1:
        raise ProgramDryRunError(
            "Section programs must emit exactly one section fragment.",
            remediation_hint=(
                "Create exactly one new section with section-local tracks and bindings."
            ),
        )
    return intent.sections[0].section_id


def _failed_result(
    program: AuthoringProgram,
    diagnostic: ProgramDiagnostic,
    *,
    metrics: ProgramMetrics,
) -> ProgramExecutionResult:
    """Return failure evidence while retaining the candidate source."""
    return ProgramExecutionResult(
        program=program,
        success=False,
        diagnostics=(diagnostic,),
        metrics=metrics,
    )


def _with_repair_evidence(
    result: ProgramExecutionResult,
    *,
    repair_count: int,
    diagnostics: tuple[ProgramDiagnostic, ...],
) -> ProgramExecutionResult:
    """Overlay bounded repair metrics and diagnostics on final candidate evidence."""
    metrics = result.metrics.model_copy(update={"program_repairs": repair_count})
    return result.model_copy(
        update={
            "diagnostics": result.diagnostics + diagnostics,
            "metrics": metrics,
        }
    )


__all__ = ["ProgramSectionCompiler", "SECTION_PROGRAM_CAPABILITIES"]
