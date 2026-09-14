"""Bounded, provider-neutral repair coordination for failed programs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ...authoring_program.models import ProgramDiagnostic, ProgramMetrics
from ..providers.base import (
    ModelBackendProtocol,
    ProgramGenerationRequest,
    ProviderRequestError,
)


class ProgramRepairStopReason(StrEnum):
    """Stable terminal reason for one bounded repair coordination call."""

    NOT_REQUIRED = "not_required"
    REPAIRED = "repaired"
    SECOND_FORMAT_REPAIR_SUCCEEDED = "second_format_repair_succeeded"
    REPAIR_LIMIT_REACHED = "repair_limit_reached"
    PROVIDER_FAILURE = "provider_failure"
    NONREPAIRABLE_GENERATION_FAILURE = "nonrepairable_generation_failure"


class ProgramRepairResult(BaseModel):
    """Immutable evidence returned by the bounded repair coordinator."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str | None = None
    diagnostics: tuple[ProgramDiagnostic, ...] = ()
    repair_count: int = Field(default=0, ge=0, le=2)
    generation_call_count: int = Field(default=0, ge=0, le=2)
    stop_reason: ProgramRepairStopReason
    metrics: ProgramMetrics = Field(default_factory=ProgramMetrics)

    @model_validator(mode="after")
    def validate_counts_and_source(self) -> ProgramRepairResult:
        """Keep repair metrics and terminal evidence internally consistent."""
        if self.metrics.program_repairs != self.repair_count:
            raise ValueError("program_repairs must equal repair_count.")
        if self.generation_call_count != self.repair_count:
            raise ValueError("generation_call_count must equal repair_count.")
        if (
            self.stop_reason
            in {
                ProgramRepairStopReason.REPAIRED,
                ProgramRepairStopReason.SECOND_FORMAT_REPAIR_SUCCEEDED,
            }
            and self.source is None
        ):
            raise ValueError("A successful repair result requires source.")
        if self.stop_reason is ProgramRepairStopReason.NOT_REQUIRED and (
            self.source is not None or self.repair_count or self.diagnostics
        ):
            raise ValueError("A not-required result cannot contain repair evidence.")
        return self


class ProgramRepairFormatFailure(Exception):
    """Explicit provider-neutral signal for a repair output format failure."""

    def __init__(self, diagnostic: ProgramDiagnostic) -> None:
        """Create a format failure from one compact stable diagnostic."""
        self.diagnostic = diagnostic
        super().__init__(diagnostic.message)


@dataclass(frozen=True, slots=True)
class ProgramRepairCoordinator:
    """Request at most one normal repair and one format-only second repair."""

    backend: ModelBackendProtocol
    allow_format_second_pass: bool = True

    async def repair(
        self,
        *,
        semantic_task: str,
        sdk_docs: str,
        previous_program: str,
        diagnostic: ProgramDiagnostic | None,
        timeout_seconds: float,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> ProgramRepairResult:
        """Return a candidate source without semantic revalidation or mutation."""
        if diagnostic is None:
            return _result(stop_reason=ProgramRepairStopReason.NOT_REQUIRED)

        request = _repair_request(
            semantic_task=semantic_task,
            sdk_docs=sdk_docs,
            previous_program=previous_program,
            diagnostic=diagnostic,
            timeout_seconds=timeout_seconds,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
        try:
            generated = await self.backend.generate_program(request)
        except ProgramRepairFormatFailure as failure:
            first_failure = failure.diagnostic
            if not self.allow_format_second_pass:
                return _result(
                    diagnostics=(first_failure,),
                    repair_count=1,
                    stop_reason=ProgramRepairStopReason.REPAIR_LIMIT_REACHED,
                )
            try:
                second = await self.backend.generate_program(request)
            except ProgramRepairFormatFailure as second_failure:
                return _result(
                    diagnostics=(first_failure, second_failure.diagnostic),
                    repair_count=2,
                    stop_reason=ProgramRepairStopReason.REPAIR_LIMIT_REACHED,
                )
            except ProviderRequestError as second_failure:
                return _result(
                    diagnostics=(first_failure, _provider_diagnostic(second_failure)),
                    repair_count=2,
                    stop_reason=ProgramRepairStopReason.PROVIDER_FAILURE,
                )
            except Exception:
                return _result(
                    diagnostics=(first_failure, _generic_failure_diagnostic()),
                    repair_count=2,
                    stop_reason=ProgramRepairStopReason.NONREPAIRABLE_GENERATION_FAILURE,
                )
            return _result(
                source=second.text,
                repair_count=2,
                stop_reason=ProgramRepairStopReason.SECOND_FORMAT_REPAIR_SUCCEEDED,
            )
        except ProviderRequestError as failure:
            return _result(
                diagnostics=(_provider_diagnostic(failure),),
                repair_count=1,
                stop_reason=ProgramRepairStopReason.PROVIDER_FAILURE,
            )
        except Exception:
            return _result(
                diagnostics=(_generic_failure_diagnostic(),),
                repair_count=1,
                stop_reason=ProgramRepairStopReason.NONREPAIRABLE_GENERATION_FAILURE,
            )
        return _result(
            source=generated.text,
            repair_count=1,
            stop_reason=ProgramRepairStopReason.REPAIRED,
        )


def _repair_request(
    *,
    semantic_task: str,
    sdk_docs: str,
    previous_program: str,
    diagnostic: ProgramDiagnostic,
    timeout_seconds: float,
    temperature: float | None,
    max_output_tokens: int | None,
) -> ProgramGenerationRequest:
    """Build the only prompt context available to a repair generation call."""
    user_prompt = "\n\n".join(
        (
            f"Semantic task:\n{semantic_task}",
            f"Relevant SDK documentation:\n{sdk_docs}",
            f"Previous program:\n<previous_program>\n{previous_program}\n</previous_program>",
            "Diagnostic:\n"
            + json.dumps(
                diagnostic.model_dump(mode="json", exclude_none=True),
                sort_keys=True,
                separators=(",", ":"),
            ),
            "Return only the corrected program source.",
        )
    )
    return ProgramGenerationRequest(
        system_prompt=(
            "Repair one failed Wellplot authoring program. Preserve the task, use only "
            "the supplied SDK documentation, and return only program source."
        ),
        user_prompt=user_prompt,
        timeout_seconds=timeout_seconds,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )


def _provider_diagnostic(error: ProviderRequestError) -> ProgramDiagnostic:
    """Convert only stable provider error fields into compact diagnostic evidence."""
    return ProgramDiagnostic(
        stage="provider",
        code=f"provider.{error.category.value}",
        message=error.safe_message,
        remediation_hint="Resolve the provider failure before attempting another repair.",
    )


def _generic_failure_diagnostic() -> ProgramDiagnostic:
    """Return a redacted diagnostic for an unexpected backend boundary failure."""
    return ProgramDiagnostic(
        stage="repair",
        code="program.repair_generation_failure",
        message="Repair generation failed before a candidate program was returned.",
    )


def _result(
    *,
    stop_reason: ProgramRepairStopReason,
    source: str | None = None,
    diagnostics: tuple[ProgramDiagnostic, ...] = (),
    repair_count: int = 0,
) -> ProgramRepairResult:
    """Construct one result with repair metrics aligned to its attempt count."""
    return ProgramRepairResult(
        source=source,
        diagnostics=diagnostics,
        repair_count=repair_count,
        generation_call_count=repair_count,
        stop_reason=stop_reason,
        metrics=ProgramMetrics(program_repairs=repair_count),
    )


__all__ = [
    "ProgramRepairCoordinator",
    "ProgramRepairFormatFailure",
    "ProgramRepairResult",
    "ProgramRepairStopReason",
]
