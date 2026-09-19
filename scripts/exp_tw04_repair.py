"""EXP-TW-04 single semantic-repair experiment."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from scripts.exp_tw02i_input import (
    TypedWorkerInputBundle,
    serialize_provider_input,
)
from scripts.exp_tw03_provider import (
    AttemptConfig,
    AttemptMetrics,
    AttemptOutcome,
    FailureCount,
    GateAEvidence,
    ProviderFailureEvidence,
)
from scripts.exp_tw03s_schema import SectionDraftS
from wellplot.agent.code_mode.enrichment import ResolvedSectionContext
from wellplot.agent.providers.base import (
    ModelBackendProtocol,
    ProviderFailureCategory,
    ProviderRequestError,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)

BASELINE_SHA = "21bd657"
EXPERIMENT_VERSION = "exp-tw-04.single-semantic-repair.v1"
SectionRole = Literal["main_pass", "repeat_pass"]
JsonValue = Any

FIRST_SYSTEM_PROMPT = (
    "Return exactly one SectionDraftS matching the typed input bundle. "
    "Use no fields outside the SectionDraftS schema."
)
REPAIR_SYSTEM_PROMPT = (
    "Return one corrected SectionDraftS. "
    "Change only what is necessary to resolve the supplied mismatches. "
    "Use the original typed task as authoritative."
)


class _EvidenceModel(BaseModel):
    """Strict immutable base for TW-04 evidence and repair contracts."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class SemanticMismatch(_EvidenceModel):
    """One deterministic difference between task semantics and a draft."""

    output_path: str = Field(min_length=1)
    provider_input_path: str = Field(min_length=1)
    issue: Literal["missing", "unexpected", "value_mismatch", "order_mismatch"]
    observed: JsonValue = None
    expected: JsonValue = None


class RepairTask(_EvidenceModel):
    """Path-free repair payload assembled from worker-boundary information."""

    original_input: TypedWorkerInputBundle
    previous_draft: SectionDraftS
    mismatches: tuple[SemanticMismatch, ...]


class RepairAttemptEvidence(_EvidenceModel):
    """Evidence for the single optional semantic repair call."""

    outcome: AttemptOutcome
    provider_failure: ProviderFailureEvidence | None = None
    metrics: AttemptMetrics | None = None
    draft: SectionDraftS | None = None
    gate_a: GateAEvidence | None = None
    normalized_projection: str | None = None


class LogicalAttemptEvidence(_EvidenceModel):
    """Immutable first-attempt and optional-repair evidence for one case."""

    experiment_version: str = EXPERIMENT_VERSION
    baseline_sha: str = BASELINE_SHA
    section_role: SectionRole
    attempt_index: int = Field(ge=1)
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    request: AttemptConfig
    first_outcome: AttemptOutcome
    first_provider_failure: ProviderFailureEvidence | None = None
    first_metrics: AttemptMetrics | None = None
    first_draft: SectionDraftS | None = None
    first_gate_a: GateAEvidence | None = None
    first_normalized_projection: str | None = None
    repair_eligible: bool
    repair_diagnostics: tuple[SemanticMismatch, ...] = ()
    repair_attempt: RepairAttemptEvidence | None = None
    final_outcome: AttemptOutcome


class RepairExperimentSummary(_EvidenceModel):
    """Aggregate first-attempt, repair, and final TW-04 measurements."""

    section_role: SectionRole
    attempts: tuple[LogicalAttemptEvidence, ...] = Field(min_length=1)
    logical_attempts: int = Field(ge=1)
    first_provider_call_successes: int = Field(ge=0)
    first_structurally_valid_count: int = Field(ge=0)
    first_gate_a_success_count: int = Field(ge=0)
    repair_eligible_count: int = Field(ge=0)
    repair_calls: int = Field(ge=0)
    repair_provider_call_successes: int = Field(ge=0)
    repair_structurally_valid_count: int = Field(ge=0)
    repair_gate_a_success_count: int = Field(ge=0)
    repair_conversion_count: int = Field(ge=0)
    final_success_count: int = Field(ge=0)
    final_outcome_counts: tuple[FailureCount, ...]
    first_input_tokens_total: int | None = None
    first_output_tokens_total: int | None = None
    first_total_tokens_total: int | None = None
    first_latency_ms_total: float | None = None
    repair_input_tokens_total: int | None = None
    repair_output_tokens_total: int | None = None
    repair_total_tokens_total: int | None = None
    repair_latency_ms_total: float | None = None
    total_tokens_total: int | None = None
    total_latency_ms: float | None = None


class RepairContractError(ValueError):
    """Raised when the bounded semantic-repair protocol is violated."""


def semantic_mismatches(
    bundle: TypedWorkerInputBundle,
    draft: SectionDraftS,
) -> tuple[SemanticMismatch, ...]:
    """Compare a draft only with the typed task visible at the worker boundary."""
    expected = bundle.task.model_dump(mode="json")
    expected.pop("section_role", None)
    observed = draft.model_dump(mode="json")
    return tuple(
        _compare_values(
            expected,
            observed,
            output_path="SectionDraft",
            provider_path="task",
        )
    )


def build_repair_task(
    bundle: TypedWorkerInputBundle,
    previous_draft: SectionDraftS,
) -> RepairTask:
    """Build a deterministic repair task without evaluator or golden access."""
    return RepairTask(
        original_input=bundle,
        previous_draft=previous_draft,
        mismatches=semantic_mismatches(bundle, previous_draft),
    )


def serialize_repair_task(task: RepairTask) -> str:
    """Serialize the complete repair payload with stable JSON ordering."""
    return json.dumps(task.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def first_request(
    bundle: TypedWorkerInputBundle,
    config: AttemptConfig,
) -> StructuredGenerationRequest:
    """Build the one first-attempt request."""
    return StructuredGenerationRequest(
        system_prompt=FIRST_SYSTEM_PROMPT,
        user_prompt=serialize_provider_input(bundle),
        timeout_seconds=config.timeout_seconds,
        temperature=config.temperature,
        max_output_tokens=config.max_output_tokens,
    )


def repair_request(
    task: RepairTask,
    config: AttemptConfig,
) -> StructuredGenerationRequest:
    """Build the one semantic-repair request."""
    return StructuredGenerationRequest(
        system_prompt=REPAIR_SYSTEM_PROMPT,
        user_prompt=serialize_repair_task(task),
        timeout_seconds=config.timeout_seconds,
        temperature=config.temperature,
        max_output_tokens=config.max_output_tokens,
    )


async def run_logical_attempt(
    section_role: SectionRole,
    backend: ModelBackendProtocol,
    *,
    provider_id: str,
    model_id: str,
    config: AttemptConfig,
    attempt_index: int = 1,
    bundle: TypedWorkerInputBundle | None = None,
    section_context: ResolvedSectionContext | None = None,
    gate_requirements: Mapping[str, object] | None = None,
) -> LogicalAttemptEvidence:
    """Run one first attempt and at most one semantic repair call."""
    if bundle is None or section_context is None or gate_requirements is None:
        raise ValueError("TW-04 requires explicit bundle, context, and Gate-A requirements.")

    common = {
        "section_role": section_role,
        "attempt_index": attempt_index,
        "provider_id": provider_id,
        "model_id": model_id,
        "request": config,
    }
    first_result = await _generate_structured(
        backend,
        first_request(bundle, config),
        is_repair=False,
    )
    if isinstance(first_result, _TerminalGeneration):
        return LogicalAttemptEvidence(
            **common,
            first_outcome=first_result.outcome,
            first_provider_failure=first_result.provider_failure,
            first_metrics=first_result.metrics,
            repair_eligible=False,
            final_outcome=first_result.outcome,
        )

    first_draft = first_result.value
    first_gate = _evaluate_gate_a(
        first_draft,
        section_role=section_role,
        section_context=section_context,
        requirements=gate_requirements,
    )
    first_projection = _normalized_draft(first_draft)
    if first_gate.semantic_usable:
        return LogicalAttemptEvidence(
            **common,
            first_outcome=AttemptOutcome.SUCCESS,
            first_metrics=first_result.metrics,
            first_draft=first_draft,
            first_gate_a=first_gate,
            first_normalized_projection=first_projection,
            repair_eligible=False,
            final_outcome=AttemptOutcome.SUCCESS,
        )

    repair_task = build_repair_task(bundle, first_draft)
    repair_result = await _generate_structured(
        backend,
        repair_request(repair_task, config),
        is_repair=True,
    )
    repair_evidence = _repair_evidence(
        repair_result,
        section_role=section_role,
        section_context=section_context,
        requirements=gate_requirements,
    )
    return LogicalAttemptEvidence(
        **common,
        first_outcome=AttemptOutcome.GATE_A_FAILURE,
        first_metrics=first_result.metrics,
        first_draft=first_draft,
        first_gate_a=first_gate,
        first_normalized_projection=first_projection,
        repair_eligible=True,
        repair_diagnostics=repair_task.mismatches,
        repair_attempt=repair_evidence,
        final_outcome=repair_evidence.outcome,
    )


async def run_section_attempts(
    section_role: SectionRole,
    backend_factory: Callable[[], ModelBackendProtocol],
    *,
    provider_id: str,
    model_id: str,
    config: AttemptConfig,
    bundle: TypedWorkerInputBundle,
    section_context: ResolvedSectionContext,
    gate_requirements: Mapping[str, object],
    attempt_count: int = 10,
) -> RepairExperimentSummary:
    """Run independent logical attempts with no cross-attempt feedback."""
    if attempt_count < 1:
        raise ValueError("attempt_count must be at least one.")
    attempts = tuple(
        [
            await run_logical_attempt(
                section_role,
                backend_factory(),
                provider_id=provider_id,
                model_id=model_id,
                config=config,
                attempt_index=index,
                bundle=bundle,
                section_context=section_context,
                gate_requirements=gate_requirements,
            )
            for index in range(1, attempt_count + 1)
        ]
    )
    return summarize_attempts(section_role, attempts)


def summarize_attempts(
    section_role: SectionRole,
    attempts: tuple[LogicalAttemptEvidence, ...],
) -> RepairExperimentSummary:
    """Aggregate bounded first-attempt and repair evidence deterministically."""
    if not attempts:
        raise ValueError("attempts must contain at least one result.")
    repair_attempts = [
        attempt.repair_attempt for attempt in attempts if attempt.repair_attempt is not None
    ]
    first_metrics = [attempt.first_metrics for attempt in attempts if attempt.first_metrics]
    repair_metrics = [attempt.metrics for attempt in repair_attempts if attempt and attempt.metrics]
    return RepairExperimentSummary(
        section_role=section_role,
        attempts=attempts,
        logical_attempts=len(attempts),
        first_provider_call_successes=sum(
            attempt.first_outcome is not AttemptOutcome.PROVIDER_FAILURE for attempt in attempts
        ),
        first_structurally_valid_count=sum(attempt.first_draft is not None for attempt in attempts),
        first_gate_a_success_count=sum(
            attempt.first_outcome is AttemptOutcome.SUCCESS for attempt in attempts
        ),
        repair_eligible_count=sum(attempt.repair_eligible for attempt in attempts),
        repair_calls=len(repair_attempts),
        repair_provider_call_successes=sum(
            attempt.outcome is not AttemptOutcome.PROVIDER_FAILURE for attempt in repair_attempts
        ),
        repair_structurally_valid_count=sum(
            attempt.draft is not None for attempt in repair_attempts
        ),
        repair_gate_a_success_count=sum(
            attempt.outcome is AttemptOutcome.SUCCESS for attempt in repair_attempts
        ),
        repair_conversion_count=sum(
            attempt.outcome is AttemptOutcome.SUCCESS for attempt in repair_attempts
        ),
        final_success_count=sum(
            attempt.final_outcome is AttemptOutcome.SUCCESS for attempt in attempts
        ),
        final_outcome_counts=_counts(attempt.final_outcome.value for attempt in attempts),
        first_input_tokens_total=_sum_metric(first_metrics, "input_tokens"),
        first_output_tokens_total=_sum_metric(first_metrics, "output_tokens"),
        first_total_tokens_total=_sum_metric(first_metrics, "total_tokens"),
        first_latency_ms_total=_sum_metric(first_metrics, "latency_ms"),
        repair_input_tokens_total=_sum_metric(repair_metrics, "input_tokens"),
        repair_output_tokens_total=_sum_metric(repair_metrics, "output_tokens"),
        repair_total_tokens_total=_sum_metric(repair_metrics, "total_tokens"),
        repair_latency_ms_total=_sum_metric(repair_metrics, "latency_ms"),
        total_tokens_total=_sum_metric(first_metrics + repair_metrics, "total_tokens"),
        total_latency_ms=_sum_metric(first_metrics + repair_metrics, "latency_ms"),
    )


def serialize_evidence(
    evidence: LogicalAttemptEvidence | RepairExperimentSummary,
) -> str:
    """Serialize bounded evidence with deterministic JSON ordering."""
    return json.dumps(
        evidence.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )


@dataclass(frozen=True, slots=True)
class _TerminalGeneration:
    """Internal terminal result for one provider call."""

    outcome: AttemptOutcome
    provider_failure: ProviderFailureEvidence | None = None
    metrics: AttemptMetrics | None = None


@dataclass(frozen=True, slots=True)
class _SuccessfulGeneration:
    """Internal validated result for one provider call."""

    value: SectionDraftS
    metrics: AttemptMetrics


async def _generate_structured(
    backend: ModelBackendProtocol,
    request: StructuredGenerationRequest,
    *,
    is_repair: bool,
) -> _TerminalGeneration | _SuccessfulGeneration:
    """Classify only typed provider failures; unexpected errors propagate."""
    try:
        result = await backend.generate_structured(request, response_model=SectionDraftS)
    except ProviderRequestError as error:
        if error.category in {
            ProviderFailureCategory.INVALID_RESPONSE,
            ProviderFailureCategory.VALIDATION,
        }:
            outcome = AttemptOutcome.STRUCTURED_OUTPUT_FAILURE
        else:
            outcome = AttemptOutcome.PROVIDER_FAILURE
        return _TerminalGeneration(
            outcome=outcome,
            provider_failure=ProviderFailureEvidence(**error.public_metadata()),
        )
    if not isinstance(result, StructuredGenerationResult):
        return _TerminalGeneration(
            outcome=AttemptOutcome.STRUCTURED_OUTPUT_FAILURE,
            provider_failure=ProviderFailureEvidence(
                category=ProviderFailureCategory.INVALID_RESPONSE,
                safe_message=(
                    "The repair provider returned no validated SectionDraftS."
                    if is_repair
                    else "The provider returned no validated SectionDraftS."
                ),
                retryable=False,
            ),
        )
    if not isinstance(result.value, SectionDraftS):
        return _TerminalGeneration(
            outcome=AttemptOutcome.STRUCTURED_OUTPUT_FAILURE,
            provider_failure=ProviderFailureEvidence(
                category=ProviderFailureCategory.INVALID_RESPONSE,
                safe_message=(
                    "The repair provider returned no validated SectionDraftS."
                    if is_repair
                    else "The provider returned no validated SectionDraftS."
                ),
                retryable=False,
            ),
            metrics=_attempt_metrics(result.metrics),
        )
    return _SuccessfulGeneration(
        value=result.value,
        metrics=_attempt_metrics(result.metrics),
    )


def _repair_evidence(
    result: _TerminalGeneration | _SuccessfulGeneration,
    *,
    section_role: SectionRole,
    section_context: ResolvedSectionContext,
    requirements: Mapping[str, object],
) -> RepairAttemptEvidence:
    """Score the one repair result without any further repair path."""
    if isinstance(result, _TerminalGeneration):
        return RepairAttemptEvidence(
            outcome=result.outcome,
            provider_failure=result.provider_failure,
            metrics=result.metrics,
        )
    gate = _evaluate_gate_a(
        result.value,
        section_role=section_role,
        section_context=section_context,
        requirements=requirements,
    )
    outcome = AttemptOutcome.SUCCESS if gate.semantic_usable else AttemptOutcome.GATE_A_FAILURE
    return RepairAttemptEvidence(
        outcome=outcome,
        metrics=result.metrics,
        draft=result.value,
        gate_a=gate,
        normalized_projection=_normalized_draft(result.value),
    )


def _evaluate_gate_a(
    draft: SectionDraftS,
    *,
    section_role: SectionRole,
    section_context: ResolvedSectionContext,
    requirements: Mapping[str, object],
) -> GateAEvidence:
    """Run the unchanged Gate-A evaluator against the strengthened values."""
    from scripts.exp_tw02r_contract import validate_gate_a

    return GateAEvidence.model_validate(
        validate_gate_a(
            draft.model_dump(mode="json"),
            section_key=section_role,
            section_context=section_context,
            requirements=requirements,
        )
    )


def _compare_values(
    expected: JsonValue,
    observed: JsonValue,
    *,
    output_path: str,
    provider_path: str,
) -> list[SemanticMismatch]:
    """Recursively compare semantic JSON values without evaluator access."""
    if isinstance(expected, Mapping) and isinstance(observed, Mapping):
        mismatches: list[SemanticMismatch] = []
        expected_keys = set(expected)
        observed_keys = set(observed)
        for key in sorted(expected_keys - observed_keys):
            mismatches.append(
                SemanticMismatch(
                    output_path=f"{output_path}.{key}",
                    provider_input_path=f"{provider_path}.{key}",
                    issue="missing",
                    expected=expected[key],
                )
            )
        for key in sorted(observed_keys - expected_keys):
            mismatches.append(
                SemanticMismatch(
                    output_path=f"{output_path}.{key}",
                    provider_input_path=f"{provider_path}.{key}",
                    issue="unexpected",
                    observed=observed[key],
                )
            )
        for key in sorted(expected_keys & observed_keys):
            mismatches.extend(
                _compare_values(
                    expected[key],
                    observed[key],
                    output_path=f"{output_path}.{key}",
                    provider_path=f"{provider_path}.{key}",
                )
            )
        return mismatches
    if isinstance(expected, list) and isinstance(observed, list):
        return _compare_lists(expected, observed, output_path, provider_path)
    if expected != observed:
        return [
            SemanticMismatch(
                output_path=output_path,
                provider_input_path=provider_path,
                issue="value_mismatch",
                observed=observed,
                expected=expected,
            )
        ]
    return []


def _compare_lists(
    expected: list[JsonValue],
    observed: list[JsonValue],
    output_path: str,
    provider_path: str,
) -> list[SemanticMismatch]:
    """Compare ordered tracks/bindings using their semantic identities."""
    identity_field = _identity_field(expected, observed)
    if identity_field is not None:
        expected_ids = [item[identity_field] for item in expected]
        observed_ids = [item[identity_field] for item in observed]
        if expected_ids != observed_ids and sorted(expected_ids) == sorted(observed_ids):
            mismatches = [
                SemanticMismatch(
                    output_path=output_path,
                    provider_input_path=provider_path,
                    issue="order_mismatch",
                    observed=observed_ids,
                    expected=expected_ids,
                )
            ]
        else:
            mismatches = []
        expected_by_id = {
            item[identity_field]: item for item in expected if isinstance(item, Mapping)
        }
        observed_by_id = {
            item[identity_field]: item for item in observed if isinstance(item, Mapping)
        }
        for identity in sorted(set(expected_by_id) & set(observed_by_id)):
            mismatches.extend(
                _compare_values(
                    expected_by_id[identity],
                    observed_by_id[identity],
                    output_path=f"{output_path}[{identity}]",
                    provider_path=f"{provider_path}[{identity}]",
                )
            )
        for identity in sorted(set(expected_by_id) - set(observed_by_id)):
            mismatches.append(
                SemanticMismatch(
                    output_path=f"{output_path}[{identity}]",
                    provider_input_path=f"{provider_path}[{identity}]",
                    issue="missing",
                    expected=expected_by_id[identity],
                )
            )
        for identity in sorted(set(observed_by_id) - set(expected_by_id)):
            mismatches.append(
                SemanticMismatch(
                    output_path=f"{output_path}[{identity}]",
                    provider_input_path=f"{provider_path}[{identity}]",
                    issue="unexpected",
                    observed=observed_by_id[identity],
                )
            )
        return mismatches

    mismatches = []
    if len(expected) != len(observed):
        issue = "missing" if len(expected) > len(observed) else "unexpected"
        mismatches.append(
            SemanticMismatch(
                output_path=output_path,
                provider_input_path=provider_path,
                issue=issue,
                observed=observed,
                expected=expected,
            )
        )
    for index, (expected_item, observed_item) in enumerate(zip(expected, observed, strict=False)):
        mismatches.extend(
            _compare_values(
                expected_item,
                observed_item,
                output_path=f"{output_path}[{index}]",
                provider_path=f"{provider_path}[{index}]",
            )
        )
    return mismatches


def _identity_field(
    expected: list[JsonValue],
    observed: list[JsonValue],
) -> str | None:
    """Select a semantic identity only when both sequences have unique IDs."""
    for field in ("role", "semantic_id"):
        if all(isinstance(item, Mapping) and field in item for item in expected + observed):
            expected_ids = [item[field] for item in expected]
            observed_ids = [item[field] for item in observed]
            if len(set(expected_ids)) == len(expected_ids) and len(set(observed_ids)) == len(
                observed_ids
            ):
                return field
    return None


def _attempt_metrics(metrics: object) -> AttemptMetrics:
    """Copy provider-neutral metrics into immutable experiment evidence."""
    return AttemptMetrics.model_validate(metrics.public_metadata())


def _normalized_draft(draft: SectionDraftS) -> str:
    """Return one deterministic semantic projection."""
    return json.dumps(draft.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def _counts(values: Sequence[str]) -> tuple[FailureCount, ...]:
    """Count final outcomes in deterministic order."""
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return tuple(FailureCount(category=key, count=counts[key]) for key in sorted(counts))


def _sum_metric(metrics: list[AttemptMetrics], field_name: str) -> int | float | None:
    """Sum available metrics while preserving unavailable-all semantics."""
    values = [getattr(metric, field_name) for metric in metrics]
    values = [value for value in values if value is not None]
    return sum(values) if values else None


__all__ = [
    "BASELINE_SHA",
    "EXPERIMENT_VERSION",
    "LogicalAttemptEvidence",
    "RepairAttemptEvidence",
    "RepairContractError",
    "RepairExperimentSummary",
    "RepairTask",
    "SemanticMismatch",
    "build_repair_task",
    "first_request",
    "repair_request",
    "run_logical_attempt",
    "run_section_attempts",
    "semantic_mismatches",
    "serialize_evidence",
    "serialize_repair_task",
    "summarize_attempts",
]
