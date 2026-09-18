"""EXP-TW-03 first-attempt provider generation experiment."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from scripts.exp_tw00_corpus import FrozenWorkerCorpus, load_corpus
from scripts.exp_tw02i_input import (
    DEFAULT_CONTRACT_PATH,
    TypedWorkerInputBundle,
    build_typed_worker_input,
    serialize_provider_input,
)
from scripts.exp_tw02r_contract import SectionDraft, validate_gate_a
from wellplot.agent.code_mode.enrichment import ResolvedSectionContext
from wellplot.agent.providers.base import (
    ModelBackendProtocol,
    ProviderFailureCategory,
    ProviderMetrics,
    ProviderRequestError,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)

BASELINE_SHA = "ad7a0ad7595be9c2d03b500d314cd6cc0d8a7619"
EXPERIMENT_VERSION = "exp-tw-03.first-attempt.v1"
DEFAULT_SYSTEM_PROMPT = (
    "Return exactly one SectionDraft that matches the typed input bundle. "
    "Use no fields outside the SectionDraft schema."
)
SectionRole = Literal["main_pass", "repeat_pass"]


class _EvidenceModel(BaseModel):
    """Strict immutable model for redacted experiment evidence."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class AttemptConfig(_EvidenceModel):
    """Provider request settings recorded for one independent attempt."""

    temperature: float | None = None
    max_output_tokens: int | None = Field(default=None, gt=0)
    timeout_seconds: float = Field(gt=0)


class AttemptMetrics(_EvidenceModel):
    """Provider measurements copied from the provider-neutral result."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: float | None = None


class ProviderFailureEvidence(_EvidenceModel):
    """Redacted provider failure metadata."""

    category: ProviderFailureCategory
    safe_message: str = Field(min_length=1)
    retryable: bool
    status_code: int | None = None


class GateAEvidence(_EvidenceModel):
    """Corrected Gate-A booleans recorded without hidden evaluator data."""

    host_reference_valid: bool
    channel_valid: bool
    semantic_usable: bool
    source_selection_valid: bool
    titles_valid: bool
    semantic_fields_valid: bool


class AttemptOutcome(StrEnum):
    """Mutually exclusive first-attempt outcome categories."""

    PROVIDER_FAILURE = "provider_failure"
    STRUCTURED_OUTPUT_FAILURE = "structured_output_failure"
    GATE_A_FAILURE = "gate_a_failure"
    SUCCESS = "success"


class FirstAttemptEvidence(_EvidenceModel):
    """Immutable, redacted evidence for one provider call."""

    experiment_version: str = EXPERIMENT_VERSION
    baseline_sha: str = BASELINE_SHA
    section_role: SectionRole
    attempt_index: int = Field(ge=1)
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    provider_input_sha256: str = Field(min_length=64, max_length=64)
    response_schema_sha256: str = Field(min_length=64, max_length=64)
    request: AttemptConfig
    outcome: AttemptOutcome
    provider_failure: ProviderFailureEvidence | None = None
    metrics: AttemptMetrics | None = None
    draft: SectionDraft | None = None
    gate_a: GateAEvidence | None = None
    normalized_review_projection: str | None = None


class FailureCount(_EvidenceModel):
    """One deterministic failure-category count."""

    category: str = Field(min_length=1)
    count: int = Field(ge=0)


class ExperimentSummary(_EvidenceModel):
    """Per-section first-attempt evidence and aggregate measurements."""

    section_role: SectionRole
    attempts: tuple[FirstAttemptEvidence, ...] = Field(min_length=1)
    total_attempts: int = Field(ge=1)
    provider_call_successes: int = Field(ge=0)
    structurally_valid_outputs: int = Field(ge=0)
    gate_a_valid_outputs: int = Field(ge=0)
    outcome_counts: tuple[FailureCount, ...]
    provider_failure_counts: tuple[FailureCount, ...]
    input_tokens_total: int | None = None
    output_tokens_total: int | None = None
    total_tokens_total: int | None = None
    latency_ms_total: float | None = None


def provider_input_sha256(bundle: TypedWorkerInputBundle) -> str:
    """Hash the exact deterministic TW-02I provider payload."""
    return _sha256_text(serialize_provider_input(bundle))


def response_schema_sha256() -> str:
    """Hash the corrected TW-02R response schema deterministically."""
    payload = json.dumps(
        SectionDraft.model_json_schema(),
        sort_keys=True,
        separators=(",", ":"),
    )
    return _sha256_text(payload)


def structured_request(
    bundle: TypedWorkerInputBundle,
    config: AttemptConfig,
) -> StructuredGenerationRequest:
    """Build one request whose sole user payload is the TW-02I serialization."""
    return StructuredGenerationRequest(
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        user_prompt=serialize_provider_input(bundle),
        timeout_seconds=config.timeout_seconds,
        temperature=config.temperature,
        max_output_tokens=config.max_output_tokens,
    )


async def run_first_attempt(
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
) -> FirstAttemptEvidence:
    """Perform and score exactly one provider call without corrective behavior."""
    corpus = None
    if bundle is None or section_context is None or gate_requirements is None:
        corpus = load_corpus()
    if bundle is None:
        bundle = build_typed_worker_input(section_role, contract_path=DEFAULT_CONTRACT_PATH)
    if section_context is None:
        source_corpus = load_corpus() if corpus is None else corpus
        section_context = _context_for_role(source_corpus, section_role)
    if gate_requirements is None:
        gate_requirements = _requirements_for_role(
            load_corpus() if corpus is None else corpus,
            section_role,
        )

    request = structured_request(bundle, config)
    common = {
        "section_role": section_role,
        "attempt_index": attempt_index,
        "provider_id": provider_id,
        "model_id": model_id,
        "provider_input_sha256": provider_input_sha256(bundle),
        "response_schema_sha256": response_schema_sha256(),
        "request": config,
    }
    try:
        result = await backend.generate_structured(
            request,
            response_model=SectionDraft,
        )
    except ProviderRequestError as error:
        if error.category in {
            ProviderFailureCategory.INVALID_RESPONSE,
            ProviderFailureCategory.VALIDATION,
        }:
            outcome = AttemptOutcome.STRUCTURED_OUTPUT_FAILURE
        else:
            outcome = AttemptOutcome.PROVIDER_FAILURE
        return FirstAttemptEvidence(
            **common,
            outcome=outcome,
            provider_failure=ProviderFailureEvidence(
                **error.public_metadata(),
            ),
        )
    except ValidationError:
        return FirstAttemptEvidence(
            **common,
            outcome=AttemptOutcome.STRUCTURED_OUTPUT_FAILURE,
            provider_failure=ProviderFailureEvidence(
                category=ProviderFailureCategory.VALIDATION,
                safe_message="The provider returned an invalid SectionDraft.",
                retryable=False,
                status_code=None,
            ),
        )

    if not isinstance(result, StructuredGenerationResult) or not isinstance(
        result.value, SectionDraft
    ):
        return FirstAttemptEvidence(
            **common,
            outcome=AttemptOutcome.STRUCTURED_OUTPUT_FAILURE,
            provider_failure=ProviderFailureEvidence(
                category=ProviderFailureCategory.INVALID_RESPONSE,
                safe_message="The provider returned no validated SectionDraft.",
                retryable=False,
                status_code=None,
            ),
        )

    metrics = _attempt_metrics(result.metrics)
    draft = result.value
    gate = GateAEvidence.model_validate(
        validate_gate_a(
            draft,
            section_key=section_role,
            section_context=section_context,
            requirements=gate_requirements,
        )
    )
    outcome = AttemptOutcome.SUCCESS if gate.semantic_usable else AttemptOutcome.GATE_A_FAILURE
    return FirstAttemptEvidence(
        **common,
        outcome=outcome,
        metrics=metrics,
        draft=draft,
        gate_a=gate,
        normalized_review_projection=_normalized_draft(draft),
    )


async def run_section_attempts(
    section_role: SectionRole,
    backend_factory: Callable[[], ModelBackendProtocol],
    *,
    provider_id: str,
    model_id: str,
    config: AttemptConfig,
    attempt_count: int = 10,
) -> ExperimentSummary:
    """Run independent first attempts without sharing outputs or failure feedback."""
    if attempt_count < 1:
        raise ValueError("attempt_count must be at least one.")
    corpus = load_corpus()
    bundle = build_typed_worker_input(section_role, contract_path=DEFAULT_CONTRACT_PATH)
    context = _context_for_role(corpus, section_role)
    requirements = _requirements_for_role(corpus, section_role)
    attempts = tuple(
        [
            await run_first_attempt(
                section_role,
                backend_factory(),
                provider_id=provider_id,
                model_id=model_id,
                config=config,
                attempt_index=index,
                bundle=bundle,
                section_context=context,
                gate_requirements=requirements,
            )
            for index in range(1, attempt_count + 1)
        ]
    )
    return summarize_attempts(section_role, attempts)


def summarize_attempts(
    section_role: SectionRole,
    attempts: tuple[FirstAttemptEvidence, ...],
) -> ExperimentSummary:
    """Aggregate immutable first-attempt evidence deterministically."""
    if not attempts:
        raise ValueError("attempts must contain at least one result.")
    outcome_counts = _counts(attempt.outcome.value for attempt in attempts)
    provider_failure_counts = _counts(
        attempt.provider_failure.category.value
        for attempt in attempts
        if attempt.provider_failure is not None
    )
    metrics = [attempt.metrics for attempt in attempts if attempt.metrics is not None]
    return ExperimentSummary(
        section_role=section_role,
        attempts=attempts,
        total_attempts=len(attempts),
        provider_call_successes=sum(attempt.metrics is not None for attempt in attempts),
        structurally_valid_outputs=sum(attempt.draft is not None for attempt in attempts),
        gate_a_valid_outputs=sum(attempt.outcome is AttemptOutcome.SUCCESS for attempt in attempts),
        outcome_counts=outcome_counts,
        provider_failure_counts=provider_failure_counts,
        input_tokens_total=_sum_metric(metrics, "input_tokens"),
        output_tokens_total=_sum_metric(metrics, "output_tokens"),
        total_tokens_total=_sum_metric(metrics, "total_tokens"),
        latency_ms_total=_sum_metric(metrics, "latency_ms"),
    )


def serialize_evidence(evidence: FirstAttemptEvidence | ExperimentSummary) -> str:
    """Serialize redacted evidence with stable key and numeric ordering."""
    return json.dumps(
        evidence.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )


def _attempt_metrics(metrics: ProviderMetrics) -> AttemptMetrics:
    """Copy provider-neutral metrics into immutable experiment evidence."""
    return AttemptMetrics(**metrics.public_metadata())


def _normalized_draft(draft: SectionDraft) -> str:
    """Return the unchanged semantic result in deterministic review form."""
    return json.dumps(draft.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def _context_for_role(
    corpus: FrozenWorkerCorpus,
    section_role: SectionRole,
) -> ResolvedSectionContext:
    """Resolve the frozen host context by its opaque source candidate."""
    candidate_id = "source-1" if section_role == "main_pass" else "source-2"
    for section in corpus.sections:
        if any(source.candidate_id == candidate_id for source in section.sources):
            return section
    raise ValueError(f"Frozen corpus has no context for {section_role!r}.")


def _requirements_for_role(
    corpus: FrozenWorkerCorpus,
    section_role: SectionRole,
) -> Mapping[str, object]:
    """Return only the frozen Gate-A requirement projection for scoring."""
    return corpus.gate_a["section_requirements"][section_role]


def _counts(values: object) -> tuple[FailureCount, ...]:
    """Count deterministic string values in first-seen sorted order."""
    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    return tuple(FailureCount(category=key, count=counts[key]) for key in sorted(counts))


def _sum_metric(metrics: list[AttemptMetrics], field_name: str) -> int | float | None:
    """Sum available metrics while preserving unavailable-all semantics."""
    values = [getattr(metric, field_name) for metric in metrics]
    values = [value for value in values if value is not None]
    return sum(values) if values else None


def _sha256_text(value: str) -> str:
    """Hash one deterministic UTF-8 representation."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = [
    "AttemptConfig",
    "AttemptMetrics",
    "AttemptOutcome",
    "ExperimentSummary",
    "FailureCount",
    "FirstAttemptEvidence",
    "GateAEvidence",
    "ProviderFailureEvidence",
    "response_schema_sha256",
    "run_first_attempt",
    "run_section_attempts",
    "serialize_evidence",
    "structured_request",
    "summarize_attempts",
]
