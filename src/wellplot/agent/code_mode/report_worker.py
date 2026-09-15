"""Bounded report program compilation for Code Mode v2."""

from __future__ import annotations

import json
from dataclasses import dataclass

from ...authoring_program.errors import AuthoringProgramError, ProgramDryRunError
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
from ...model.authoring import AuthoringDocumentSpec
from ...model.intent import AuthoringDocumentIntent
from ..providers.base import ModelBackendProtocol, ProgramGenerationRequest
from .enrichment import ReportContext
from .planner import ReportTask
from .repair import ProgramRepairCoordinator

_SDK_REFERENCE = """Executable Wellplot report SDK reference:
report = wp.report(title='Report title', subtitle='Report subtitle')
wp.header_field(report, key='well', value='Well name', unit='name')
wp.service_title(report, slot_id='service_title_1', value='Quicklook')
wp.detail_field(report, key='detail.run_number', value='ONE', unit='run')
wp.remark(report, remark_id='scope', title='Scope', text='Short note')
wp.page(report, size='letter', orientation='portrait', continuous=False)
wp.depth(report, unit='ft', scale='1:240')
wp.output(report, backend='matplotlib', output_path='wellplot.pdf', dpi=180)
wp.tail(report, enabled=True)

Only the root calls and keyword arguments shown above are executable. Use only
header slot IDs, keys, and labels supplied in the task context. Values must be
literal primitive strings or numbers from the request. Do not inspect, select,
create, or revise sections or child plot objects. Do not use filesystem
operations. Return only the program source, with no markdown fences or
explanation."""


@dataclass(frozen=True, slots=True)
class ReportProgramCompiler:
    """Compile one report-only program without mutating a document."""

    backend: ModelBackendProtocol
    registry: CapabilityRegistry
    repair_coordinator: ProgramRepairCoordinator | None = None

    async def compile(
        self,
        *,
        task: ReportTask,
        report_context: ReportContext,
        document: AuthoringDocumentSpec,
        timeout_seconds: float,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> ProgramExecutionResult:
        """Generate, interpret, and privately dry-run one report program."""
        capabilities = _worker_capabilities(task, self.registry)
        request = ProgramGenerationRequest(
            system_prompt=(
                "You are the Wellplot report Code Mode worker. Write one short "
                "restricted report program using only the executable SDK reference "
                "and scoped task context."
            ),
            user_prompt=_worker_prompt(
                task=task,
                report_context=report_context,
                capabilities=capabilities,
            ),
            timeout_seconds=timeout_seconds,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
        generated = await self.backend.generate_program(request)
        initial = self._attempt(generated.text, document=document)
        if initial.success:
            return initial

        diagnostic = initial.diagnostics[0]
        coordinator = self.repair_coordinator or ProgramRepairCoordinator(self.backend)
        repair = await coordinator.repair(
            semantic_task=_repair_context_text(task, report_context),
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

        repaired = self._attempt(repair.source, document=document)
        return _with_repair_evidence(
            repaired,
            repair_count=repair.repair_count,
            diagnostics=repair.diagnostics,
        )

    def _attempt(
        self,
        source: str,
        *,
        document: AuthoringDocumentSpec,
    ) -> ProgramExecutionResult:
        """Run one candidate with a fresh builder and private canonical runtime."""
        program = AuthoringProgram(
            source=ProgramSource(text=source, logical_name="cm44-report.wpa")
        )
        builder = IntentBuilder()
        try:
            interpretation = interpret_authoring_program(
                program,
                builder.runtime_environment(),
            )
            intent = builder.intent()
            _validate_report_intent(intent)
            return ProgramRuntime(document).dry_run(
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
                    "Report program could not be compiled deterministically.",
                    remediation_hint=(
                        "Return one report-only program using the selected report "
                        "capability and supplied header slots."
                    ),
                ).to_diagnostic(),
                metrics=ProgramMetrics(program_chars=len(source)),
            )


def _worker_capabilities(
    task: ReportTask,
    registry: CapabilityRegistry,
) -> tuple[dict[str, object], ...]:
    """Resolve selected canonical report capabilities into compact worker facts."""
    descriptors: list[dict[str, object]] = []
    for capability_id in task.capability_ids:
        spec = registry.get(capability_id)
        if spec.capability_id != capability_id:
            raise ValueError(f"Capability selection must use canonical id {spec.capability_id!r}.")
        if spec.category != "report":
            raise ValueError(
                f"ReportTask cannot select {spec.category} capability {capability_id!r}."
            )
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
    task: ReportTask,
    report_context: ReportContext,
    capabilities: tuple[dict[str, object], ...],
) -> str:
    """Serialize only semantic report requirements and bounded slot identities."""
    payload = {
        "report_task": _semantic_task_payload(task),
        "capabilities": capabilities,
        "report_context": {
            "header_slots": [slot.model_dump(mode="json") for slot in report_context.header_slots],
        },
        "sdk_reference": _SDK_REFERENCE,
    }
    return (
        "Create one report-only authoring program from this scoped context. "
        "Apply only requested report-wide changes and omit unrelated calls. "
        "Do not create sections or child plot objects.\n\n"
        + json.dumps(payload, sort_keys=True, separators=(",", ":"))
    )


def _semantic_task_payload(task: ReportTask) -> dict[str, object]:
    """Return planner-approved report requirements without document mechanics."""
    return {
        "goal": task.goal,
        "capability_ids": list(task.capability_ids),
        "requirements": list(task.requirements),
        "constraints": list(task.constraints),
    }


def _repair_context_text(task: ReportTask, report_context: ReportContext) -> str:
    """Build bounded repair context with the same report facts as initial generation."""
    return json.dumps(
        {
            "report_task": _semantic_task_payload(task),
            "header_slots": [slot.model_dump(mode="json") for slot in report_context.header_slots],
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _validate_report_intent(intent: AuthoringDocumentIntent) -> None:
    """Reject section-local, global-child, removal, and empty report programs."""
    if intent.sections is not None or any(
        getattr(intent, field_name) is not None
        for field_name in ("curve_bindings", "raster_bindings", "fills", "annotations")
    ):
        raise ProgramDryRunError(
            "Report programs may emit only report-wide authoring intent.",
            remediation_hint=(
                "Remove sections and plot-child calls; emit only report title, "
                "header, page, depth, output, tail, or remarks."
            ),
        )
    if intent.removals:
        raise ProgramDryRunError(
            "Report programs may not emit removals.",
            remediation_hint="Remove all deletion or clear operations from the program.",
        )
    if not _has_report_mutation(intent):
        raise ProgramDryRunError(
            "Report programs must contain at least one report mutation.",
            remediation_hint="Add one requested report setting or remark to wp.report().",
        )


def _has_report_mutation(intent: AuthoringDocumentIntent) -> bool:
    """Return whether a report intent contains an explicit non-empty mutation."""
    if intent.title is not None or intent.subtitle is not None:
        return True
    for field_name in ("header", "page", "depth", "output", "tail"):
        value = getattr(intent, field_name)
        if value is not None and _model_has_explicit_fields(value):
            return True
    return bool(intent.remarks)


def _model_has_explicit_fields(value: object) -> bool:
    """Check nested intent models without treating empty patches as mutations."""
    if hasattr(value, "model_dump"):
        return bool(value.model_dump(exclude_unset=True))
    return True


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


__all__ = ["ReportProgramCompiler"]
