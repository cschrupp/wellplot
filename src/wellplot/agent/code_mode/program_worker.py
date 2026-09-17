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

_SDK_REFERENCE = """Exact executable Wellplot SDK contract:
Use only the keyword arguments listed for each call. Do not infer aliases or
additional keywords from the semantic task.

wp.report(): title, subtitle
wp.source(candidate_id): candidate_id (positional or keyword)
wp.section(report): id_hint, title, subtitle, depth_minimum, depth_maximum, source
wp.target_section(report): no keyword arguments; the host supplies the target
wp.update_section(target): title, subtitle, depth_minimum, depth_maximum
wp.track(section): id_hint, kind, title, width_mm, scale_minimum, scale_maximum,
    scale_kind, reverse
wp.curve(track): channel, id_hint, label, scale_minimum, scale_maximum, scale_kind,
    reverse, color, line_style, line_width
wp.raster(track): channel, id_hint, label, profile, normalization, color_minimum,
    color_maximum, colormap, alpha

Use wp.section(report) only for a new section. Use
wp.target_section(report) followed by wp.update_section() for an existing
target. The target-section call accepts no section ID; the host supplies the
opaque target. Use only source candidate IDs and channel mnemonics supplied in
the task context. Do not invent, derive, suffix, expand, or rename them.
Multiple bindings may reference the same source channel. Do not select or
update existing tracks, bindings, fills, or annotations. Do not use report-wide
settings or filesystem operations. Never create a second section in an
existing-target task.
Return only the program source, with no markdown fences or explanation."""

_CHANNEL_GROUNDING_RULE = (
    "Use only exact supplied channel mnemonics or explicitly supplied aliases. "
    "Never invent, derive, suffix, expand, or rename channel names. Multiple "
    "bindings may reference the same source channel."
)


@dataclass(frozen=True, slots=True)
class ProgramSectionCompiler:
    """Compile one host-scoped section program without mutating a document."""

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
            semantic_task=_repair_context_text(task, section_context),
            sdk_docs=_sdk_reference(section_context),
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
            section_id = _validate_section_intent(
                intent,
                expected_section_id=section_context.section_id,
            )
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
                    remediation_hint=(
                        "Use the host-selected target for revision or return one new "
                        "section using only the selected capabilities."
                    ),
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
        "section_task": _semantic_task_payload(task),
        "capabilities": capabilities,
        "section_context": _bounded_section_context(section_context),
        "sdk_reference": _sdk_reference(section_context),
    }
    if section_context.section_id is None:
        if section_context.sources:
            instruction = (
                "Create one new section from this scoped context. When a source "
                "candidate is needed, resolve its exact candidate_id with the supplied "
                "source handle examples and pass the handle to wp.section(). "
            )
        else:
            instruction = (
                "Create one new section from this scoped context. No host source "
                "candidate is available for this task, so do not associate a source. "
            )
    else:
        instruction = (
            "Revise the one host-selected existing section from this scoped context. "
            "Use wp.target_section(report) without an ID, then apply a sparse section "
            "update or add requested new child tracks. Do not create a second section. "
        )
    return (
        instruction
        + _CHANNEL_GROUNDING_RULE
        + " Do not add report-wide settings or use context outside this task.\n\n"
        + json.dumps(payload, sort_keys=True, separators=(",", ":"))
    )


def _sdk_reference(section_context: ResolvedSectionContext) -> str:
    """Build executable SDK documentation from host-approved source handles."""
    source_ids = tuple(source.candidate_id for source in section_context.sources)
    lines = [_SDK_REFERENCE]
    if source_ids:
        lines.extend(
            [
                "Host-approved source handles for this task:",
                *(
                    f"source_{index} = wp.source({json.dumps(candidate_id)})"
                    for index, candidate_id in enumerate(source_ids, start=1)
                ),
            ]
        )
        if len(source_ids) == 1:
            lines.append("For this task, the new-section source argument may use source_1.")
        else:
            lines.append(
                "Multiple source handles are available; pass only the handle selected "
                "by the task and do not prefer one by position."
            )
    else:
        lines.append("No host-approved source handle is available; omit source association.")

    channel_examples: list[str] = []
    seen_channels: set[tuple[str, str]] = set()
    for source in section_context.sources:
        for channel in source.channels:
            identity = (channel.mnemonic, channel.kind)
            if identity in seen_channels:
                continue
            seen_channels.add(identity)
            channel_literal = json.dumps(channel.mnemonic)
            if channel.kind == "array":
                channel_examples.append(f"wp.raster(array, channel={channel_literal})")
            else:
                channel_examples.append(f"wp.curve(normal, channel={channel_literal})")
    if channel_examples:
        lines.extend(
            [
                "Context-valid executable channel examples; use only these exact literals:",
                *channel_examples,
            ]
        )
    else:
        lines.append(
            "No host-approved channel is available; omit wp.curve and wp.raster binding examples."
        )
    return "\n".join(lines)


def _semantic_task_payload(task: SectionTask) -> dict[str, object]:
    """Return the planner-approved semantic task without document mechanics."""
    return {
        "goal": task.goal,
        "capability_ids": list(task.capability_ids),
        "requirements": list(task.requirements),
        "constraints": list(task.constraints),
    }


def _bounded_section_context(section_context: ResolvedSectionContext) -> dict[str, object]:
    """Project only source candidates and exact channel facts into a worker prompt."""
    return {
        "target": {"kind": "existing" if section_context.section_id else "new"},
        "sources": [
            {
                "candidate_id": source.candidate_id,
                "channels": [
                    {
                        "mnemonic": channel.mnemonic,
                        "kind": channel.kind,
                        "aliases": list(channel.aliases),
                        "unit": channel.unit,
                    }
                    for channel in source.channels
                ],
            }
            for source in section_context.sources
        ],
    }


def _repair_context_text(
    task: SectionTask,
    section_context: ResolvedSectionContext,
) -> str:
    """Build bounded repair context with the same channel facts as initial generation."""
    return json.dumps(
        {
            "task": _semantic_task_payload(task),
            "target": {"kind": "existing" if section_context.section_id else "new"},
            "section_context": _bounded_section_context(section_context),
            "channel_grounding_rule": _CHANNEL_GROUNDING_RULE,
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
    if section_context.section_id is not None:
        builder.register_section_target(section_context.section_id)
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


def _validate_section_intent(
    intent: AuthoringDocumentIntent,
    *,
    expected_section_id: str | None,
) -> str:
    """Reject leakage and enforce the host-selected section target."""
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
    section = intent.sections[0]
    if expected_section_id is None:
        return section.section_id
    if section.section_id != expected_section_id:
        raise ProgramDryRunError(
            "Existing-section programs must use the host-selected target.",
            remediation_hint=(
                "Use wp.target_section(report) and do not create or identify a section."
            ),
        )
    if not section.supplied_fields().difference({"section_id"}):
        raise ProgramDryRunError(
            "Existing-section programs must contain a sparse section mutation.",
            remediation_hint=(
                "Apply a section title, subtitle, depth range, or create a new child "
                "track beneath wp.target_section(report)."
            ),
        )
    return section.section_id


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
