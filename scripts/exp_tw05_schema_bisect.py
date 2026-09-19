"""EXP-TW-05 structured-output schema compatibility characterization."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from scripts.exp_tw00_corpus import FrozenWorkerCorpus, load_corpus
from scripts.exp_tw02i_input import (
    DEFAULT_CONTRACT_PATH,
    TypedWorkerInputBundle,
    build_typed_worker_input,
    serialize_provider_input,
)
from scripts.exp_tw02r_contract import (
    CurveBindingDraft,
    RasterBindingDraft,
    ScaleDraft,
    SectionDraft,
    validate_gate_a,
)
from scripts.exp_tw03_provider import (
    AttemptConfig,
    AttemptMetrics,
    AttemptOutcome,
    GateAEvidence,
    ProviderFailureEvidence,
)
from scripts.exp_tw03s_schema import SectionDraftS
from wellplot.agent.code_mode.enrichment import ResolvedSectionContext
from wellplot.agent.providers.base import (
    ModelBackendProtocol,
    ProviderFailureCategory,
    ProviderMetrics,
    ProviderRequestError,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)

BASELINE_SHA = "91c4151"
EXPERIMENT_VERSION = "exp-tw-05.schema-bisect.v1"
SectionRole = Literal["main_pass", "repeat_pass"]
DEFAULT_SYSTEM_PROMPT = (
    "Return exactly one SectionDraft that matches the typed input bundle. "
    "Use no fields outside the SectionDraft schema."
)
TrackRole = Literal["combo", "depth", "cbl", "vdl"]


class _LadderModel(BaseModel):
    """Strict immutable base for experimental response models."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class NormalTrackDraftS1(_LadderModel):
    """S1 normal track with historical binding permissiveness."""

    role: TrackRole
    kind: Literal["normal"] = "normal"
    title: str = Field(min_length=1)
    x_scale: ScaleDraft | None = None
    bindings: tuple[CurveBindingDraft | RasterBindingDraft, ...] = Field(min_length=1)


class ReferenceTrackDraftS1(_LadderModel):
    """S1 reference track with historical binding permissiveness."""

    role: TrackRole
    kind: Literal["reference"] = "reference"
    title: str = Field(min_length=1)
    x_scale: ScaleDraft | None = None
    bindings: tuple[CurveBindingDraft | RasterBindingDraft, ...] = Field(min_length=1)


class ArrayTrackDraftS1(_LadderModel):
    """S1 array track with optional x scale and mixed bindings."""

    role: TrackRole
    kind: Literal["array"] = "array"
    title: str = Field(min_length=1)
    x_scale: ScaleDraft | None = None
    bindings: tuple[CurveBindingDraft | RasterBindingDraft, ...] = Field(min_length=1)


TrackDraftS1 = Annotated[
    NormalTrackDraftS1 | ReferenceTrackDraftS1 | ArrayTrackDraftS1,
    Field(discriminator="kind"),
]


class SectionDraftS1(_LadderModel):
    """S1 section with only track-level discrimination added."""

    title: str = Field(min_length=1)
    source_candidate: str = Field(min_length=1)
    tracks: tuple[TrackDraftS1, ...] = Field(min_length=1)


class NormalTrackDraftS2(_LadderModel):
    """S2 normal track restricted to scalar curves."""

    role: TrackRole
    kind: Literal["normal"] = "normal"
    title: str = Field(min_length=1)
    x_scale: ScaleDraft | None = None
    bindings: tuple[CurveBindingDraft, ...] = Field(min_length=1)


class ReferenceTrackDraftS2(_LadderModel):
    """S2 reference track restricted to scalar curves."""

    role: TrackRole
    kind: Literal["reference"] = "reference"
    title: str = Field(min_length=1)
    x_scale: ScaleDraft | None = None
    bindings: tuple[CurveBindingDraft, ...] = Field(min_length=1)


class ArrayTrackDraftS2(_LadderModel):
    """S2 array track with the S1 binding union unchanged."""

    role: TrackRole
    kind: Literal["array"] = "array"
    title: str = Field(min_length=1)
    x_scale: ScaleDraft | None = None
    bindings: tuple[CurveBindingDraft | RasterBindingDraft, ...] = Field(min_length=1)


TrackDraftS2 = Annotated[
    NormalTrackDraftS2 | ReferenceTrackDraftS2 | ArrayTrackDraftS2,
    Field(discriminator="kind"),
]


class SectionDraftS2(_LadderModel):
    """S2 section with normal/reference curve-only restrictions."""

    title: str = Field(min_length=1)
    source_candidate: str = Field(min_length=1)
    tracks: tuple[TrackDraftS2, ...] = Field(min_length=1)


class NormalTrackDraftS3(_LadderModel):
    """S3 normal track restricted to scalar curves."""

    role: TrackRole
    kind: Literal["normal"] = "normal"
    title: str = Field(min_length=1)
    x_scale: ScaleDraft | None = None
    bindings: tuple[CurveBindingDraft, ...] = Field(min_length=1)


class ReferenceTrackDraftS3(_LadderModel):
    """S3 reference track restricted to scalar curves."""

    role: TrackRole
    kind: Literal["reference"] = "reference"
    title: str = Field(min_length=1)
    x_scale: ScaleDraft | None = None
    bindings: tuple[CurveBindingDraft, ...] = Field(min_length=1)


class ArrayTrackDraftS3(_LadderModel):
    """S3 array track restricted to raster bindings."""

    role: TrackRole
    kind: Literal["array"] = "array"
    title: str = Field(min_length=1)
    x_scale: ScaleDraft | None = None
    bindings: tuple[RasterBindingDraft, ...] = Field(min_length=1)


TrackDraftS3 = Annotated[
    NormalTrackDraftS3 | ReferenceTrackDraftS3 | ArrayTrackDraftS3,
    Field(discriminator="kind"),
]


class SectionDraftS3(_LadderModel):
    """S3 section with array raster-only restrictions."""

    title: str = Field(min_length=1)
    source_candidate: str = Field(min_length=1)
    tracks: tuple[TrackDraftS3, ...] = Field(min_length=1)


class NormalTrackDraftS4(_LadderModel):
    """S4 normal track restricted to scalar curves."""

    role: TrackRole
    kind: Literal["normal"] = "normal"
    title: str = Field(min_length=1)
    x_scale: ScaleDraft | None = None
    bindings: tuple[CurveBindingDraft, ...] = Field(min_length=1)


class ReferenceTrackDraftS4(_LadderModel):
    """S4 reference track restricted to scalar curves."""

    role: TrackRole
    kind: Literal["reference"] = "reference"
    title: str = Field(min_length=1)
    x_scale: ScaleDraft | None = None
    bindings: tuple[CurveBindingDraft, ...] = Field(min_length=1)


class ArrayTrackDraftS4(_LadderModel):
    """S4 array track with required x scale and raster bindings."""

    role: TrackRole
    kind: Literal["array"] = "array"
    title: str = Field(min_length=1)
    x_scale: ScaleDraft
    bindings: tuple[RasterBindingDraft, ...] = Field(min_length=1)


TrackDraftS4 = Annotated[
    NormalTrackDraftS4 | ReferenceTrackDraftS4 | ArrayTrackDraftS4,
    Field(discriminator="kind"),
]


class SectionDraftS4(_LadderModel):
    """S4 section with the complete strengthened structural constraints."""

    title: str = Field(min_length=1)
    source_candidate: str = Field(min_length=1)
    tracks: tuple[TrackDraftS4, ...] = Field(min_length=1)


class SchemaVariant(StrEnum):
    """Ordered schema variants in the compatibility ladder."""

    S0 = "S0"
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4"
    S5 = "S5"


@dataclass(frozen=True, slots=True)
class SchemaVariantSpec:
    """Static metadata for one schema-ladder response model."""

    variant: SchemaVariant
    feature: str
    response_model: type[BaseModel]


_VARIANTS = (
    SchemaVariantSpec(SchemaVariant.S0, "historical control", SectionDraft),
    SchemaVariantSpec(SchemaVariant.S1, "track discriminator", SectionDraftS1),
    SchemaVariantSpec(
        SchemaVariant.S2,
        "normal/reference curve-only bindings",
        SectionDraftS2,
    ),
    SchemaVariantSpec(SchemaVariant.S3, "array raster-only bindings", SectionDraftS3),
    SchemaVariantSpec(SchemaVariant.S4, "required array x_scale", SectionDraftS4),
    SchemaVariantSpec(SchemaVariant.S5, "exact SectionDraftS", SectionDraftS),
)
_VARIANT_BY_ID = {item.variant: item for item in _VARIANTS}


class _EvidenceModel(BaseModel):
    """Strict immutable base for TW-05 evidence."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class SchemaAttemptEvidence(_EvidenceModel):
    """One redacted provider attempt for one ladder variant."""

    experiment_version: str = EXPERIMENT_VERSION
    baseline_sha: str = BASELINE_SHA
    schema_variant: SchemaVariant
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
    normalized_output: str | None = None
    gate_a: GateAEvidence | None = None


class SchemaSectionSummary(_EvidenceModel):
    """Aggregate evidence for one variant and section role."""

    schema_variant: SchemaVariant
    section_role: SectionRole
    attempts: tuple[SchemaAttemptEvidence, ...] = Field(min_length=1)
    total_attempts: int = Field(ge=1)
    provider_call_successes: int = Field(ge=0)
    structurally_valid_outputs: int = Field(ge=0)
    structured_output_failures: int = Field(ge=0)
    provider_failures: int = Field(ge=0)
    gate_a_successes: int = Field(ge=0)
    input_tokens_total: int | None = None
    output_tokens_total: int | None = None
    total_tokens_total: int | None = None
    latency_ms_total: float | None = None


class SchemaVariantSummary(_EvidenceModel):
    """Aggregate evidence for both sections of one schema variant."""

    schema_variant: SchemaVariant
    feature: str = Field(min_length=1)
    response_schema_sha256: str = Field(min_length=64, max_length=64)
    sections: tuple[SchemaSectionSummary, ...] = Field(min_length=1)
    total_attempts: int = Field(ge=1)
    provider_call_successes: int = Field(ge=0)
    structurally_valid_outputs: int = Field(ge=0)
    structured_output_failures: int = Field(ge=0)
    provider_failures: int = Field(ge=0)
    gate_a_successes: int = Field(ge=0)


def schema_variant_specs() -> tuple[SchemaVariantSpec, ...]:
    """Return the fixed S0-to-S5 ladder in execution order."""
    return _VARIANTS


def response_model_for(variant: SchemaVariant | str) -> type[BaseModel]:
    """Return the static response model for one schema variant."""
    selected = SchemaVariant(variant)
    return _VARIANT_BY_ID[selected].response_model


def schema_sha256(response_model: type[BaseModel]) -> str:
    """Hash a response model's canonical JSON Schema."""
    payload = json.dumps(
        response_model.model_json_schema(),
        sort_keys=True,
        separators=(",", ":"),
    )
    return _sha256_text(payload)


def schema_projection(variant: SchemaVariant | str) -> dict[str, object]:
    """Return one reviewable schema projection with its deterministic hash."""
    selected = SchemaVariant(variant)
    model = response_model_for(selected)
    return {
        "schema_variant": selected.value,
        "response_schema_sha256": schema_sha256(model),
        "schema": model.model_json_schema(),
    }


def schema_diff_summary(
    before: type[BaseModel] | Mapping[str, object],
    after: type[BaseModel] | Mapping[str, object],
) -> dict[str, object]:
    """Summarize adjacent JSON-Schema changes by deterministic JSON paths."""
    before_schema = before.model_json_schema() if isinstance(before, type) else dict(before)
    after_schema = after.model_json_schema() if isinstance(after, type) else dict(after)
    before_paths = _flatten_json_paths(before_schema)
    after_paths = _flatten_json_paths(after_schema)
    before_keys = set(before_paths)
    after_keys = set(after_paths)
    return {
        "added_paths": sorted(after_keys - before_keys),
        "removed_paths": sorted(before_keys - after_keys),
        "changed_paths": sorted(
            path for path in before_keys & after_keys if before_paths[path] != after_paths[path]
        ),
    }


def ladder_schema_artifact() -> dict[str, object]:
    """Build deterministic schema and adjacent-diff review evidence."""
    projections = [schema_projection(item.variant) for item in _VARIANTS]
    adjacent_diffs = [
        {
            "from": previous.variant.value,
            "to": current.variant.value,
            "diff": schema_diff_summary(previous.response_model, current.response_model),
        }
        for previous, current in zip(_VARIANTS, _VARIANTS[1:], strict=False)
    ]
    return {
        "baseline_sha": BASELINE_SHA,
        "experiment_version": EXPERIMENT_VERSION,
        "variants": projections,
        "adjacent_diffs": adjacent_diffs,
    }


def provider_input_sha256(bundle: TypedWorkerInputBundle) -> str:
    """Hash the exact deterministic TW-02I provider payload."""
    return _sha256_text(serialize_provider_input(bundle))


def structured_request(
    bundle: TypedWorkerInputBundle,
    config: AttemptConfig,
) -> StructuredGenerationRequest:
    """Build the identical provider request used for every schema variant."""
    return StructuredGenerationRequest(
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        user_prompt=serialize_provider_input(bundle),
        timeout_seconds=config.timeout_seconds,
        temperature=config.temperature,
        max_output_tokens=config.max_output_tokens,
    )


async def run_schema_attempt(
    section_role: SectionRole,
    variant: SchemaVariant | str,
    backend: ModelBackendProtocol,
    *,
    provider_id: str,
    model_id: str,
    config: AttemptConfig,
    attempt_index: int = 1,
    bundle: TypedWorkerInputBundle | None = None,
    section_context: ResolvedSectionContext | None = None,
    gate_requirements: Mapping[str, object] | None = None,
) -> SchemaAttemptEvidence:
    """Perform and score exactly one provider call for one schema variant."""
    selected = SchemaVariant(variant)
    response_model = response_model_for(selected)
    corpus = None
    if bundle is None or section_context is None or gate_requirements is None:
        corpus = load_corpus()
    if bundle is None:
        bundle = build_typed_worker_input(section_role, contract_path=DEFAULT_CONTRACT_PATH)
    if section_context is None:
        source_corpus = load_corpus() if corpus is None else corpus
        section_context = _context_for_role(source_corpus, section_role)
    if gate_requirements is None:
        gate_corpus = load_corpus() if corpus is None else corpus
        gate_requirements = gate_corpus.gate_a["section_requirements"][section_role]

    request = structured_request(bundle, config)
    common = {
        "schema_variant": selected,
        "section_role": section_role,
        "attempt_index": attempt_index,
        "provider_id": provider_id,
        "model_id": model_id,
        "provider_input_sha256": provider_input_sha256(bundle),
        "response_schema_sha256": schema_sha256(response_model),
        "request": config,
    }
    try:
        result = await backend.generate_structured(request, response_model=response_model)
    except ProviderRequestError as error:
        outcome = (
            AttemptOutcome.STRUCTURED_OUTPUT_FAILURE
            if error.category
            in {ProviderFailureCategory.INVALID_RESPONSE, ProviderFailureCategory.VALIDATION}
            else AttemptOutcome.PROVIDER_FAILURE
        )
        return SchemaAttemptEvidence(
            **common,
            outcome=outcome,
            provider_failure=ProviderFailureEvidence(**error.public_metadata()),
        )

    metrics = (
        _attempt_metrics(result.metrics) if isinstance(result, StructuredGenerationResult) else None
    )
    if not isinstance(result, StructuredGenerationResult) or not isinstance(
        result.value, response_model
    ):
        return SchemaAttemptEvidence(
            **common,
            outcome=AttemptOutcome.STRUCTURED_OUTPUT_FAILURE,
            metrics=metrics,
            provider_failure=ProviderFailureEvidence(
                category=ProviderFailureCategory.INVALID_RESPONSE,
                safe_message=(
                    "The provider returned no validated response for the requested schema."
                ),
                retryable=False,
                status_code=None,
            ),
        )

    validated = result.value
    gate = GateAEvidence.model_validate(
        validate_gate_a(
            validated.model_dump(mode="json"),
            section_key=section_role,
            section_context=section_context,
            requirements=gate_requirements,
        )
    )
    outcome = AttemptOutcome.SUCCESS if gate.semantic_usable else AttemptOutcome.GATE_A_FAILURE
    return SchemaAttemptEvidence(
        **common,
        outcome=outcome,
        metrics=metrics,
        normalized_output=_normalized_output(validated),
        gate_a=gate,
    )


async def run_schema_section_attempts(
    section_role: SectionRole,
    variant: SchemaVariant | str,
    backend_factory: Callable[[], ModelBackendProtocol],
    *,
    provider_id: str,
    model_id: str,
    config: AttemptConfig,
    attempt_count: int = 10,
    bundle: TypedWorkerInputBundle | None = None,
    section_context: ResolvedSectionContext | None = None,
    gate_requirements: Mapping[str, object] | None = None,
    attempt_sink: Callable[[SchemaAttemptEvidence], None] | None = None,
) -> SchemaSectionSummary:
    """Run independent first attempts for one variant and section."""
    if attempt_count < 1:
        raise ValueError("attempt_count must be at least one.")
    attempts: list[SchemaAttemptEvidence] = []
    for index in range(1, attempt_count + 1):
        attempt = await run_schema_attempt(
            section_role,
            variant,
            backend_factory(),
            provider_id=provider_id,
            model_id=model_id,
            config=config,
            attempt_index=index,
            bundle=bundle,
            section_context=section_context,
            gate_requirements=gate_requirements,
        )
        attempts.append(attempt)
        if attempt_sink is not None:
            attempt_sink(attempt)
    return summarize_schema_section(tuple(attempts))


def summarize_schema_section(
    attempts: Sequence[SchemaAttemptEvidence],
) -> SchemaSectionSummary:
    """Aggregate one variant/section without inferring unavailable metrics."""
    if not attempts:
        raise ValueError("attempts must contain at least one result.")
    variants = {attempt.schema_variant for attempt in attempts}
    roles = {attempt.section_role for attempt in attempts}
    if len(variants) != 1 or len(roles) != 1:
        raise ValueError("Attempts must share one schema variant and section role.")
    metrics = [attempt.metrics for attempt in attempts if attempt.metrics is not None]
    return SchemaSectionSummary(
        schema_variant=attempts[0].schema_variant,
        section_role=attempts[0].section_role,
        attempts=tuple(attempts),
        total_attempts=len(attempts),
        provider_call_successes=sum(
            attempt.outcome is not AttemptOutcome.PROVIDER_FAILURE for attempt in attempts
        ),
        structurally_valid_outputs=sum(
            attempt.normalized_output is not None for attempt in attempts
        ),
        structured_output_failures=sum(
            attempt.outcome is AttemptOutcome.STRUCTURED_OUTPUT_FAILURE for attempt in attempts
        ),
        provider_failures=sum(
            attempt.outcome is AttemptOutcome.PROVIDER_FAILURE for attempt in attempts
        ),
        gate_a_successes=sum(attempt.outcome is AttemptOutcome.SUCCESS for attempt in attempts),
        input_tokens_total=_sum_metric(metrics, "input_tokens"),
        output_tokens_total=_sum_metric(metrics, "output_tokens"),
        total_tokens_total=_sum_metric(metrics, "total_tokens"),
        latency_ms_total=_sum_metric(metrics, "latency_ms"),
    )


def summarize_schema_variant(
    spec: SchemaVariantSpec,
    sections: Sequence[SchemaSectionSummary],
) -> SchemaVariantSummary:
    """Aggregate both section roles for one schema variant."""
    if not sections:
        raise ValueError("sections must contain at least one summary.")
    if any(section.schema_variant is not spec.variant for section in sections):
        raise ValueError("Section summaries must match the schema variant.")
    return SchemaVariantSummary(
        schema_variant=spec.variant,
        feature=spec.feature,
        response_schema_sha256=schema_sha256(spec.response_model),
        sections=tuple(sections),
        total_attempts=sum(section.total_attempts for section in sections),
        provider_call_successes=sum(section.provider_call_successes for section in sections),
        structurally_valid_outputs=sum(section.structurally_valid_outputs for section in sections),
        structured_output_failures=sum(section.structured_output_failures for section in sections),
        provider_failures=sum(section.provider_failures for section in sections),
        gate_a_successes=sum(section.gate_a_successes for section in sections),
    )


async def run_schema_ladder(
    backend_factory: Callable[[], ModelBackendProtocol],
    *,
    provider_id: str,
    model_id: str,
    config: AttemptConfig,
    attempt_count: int = 10,
    output_jsonl: str | Path | None = None,
    schema_output: str | Path | None = None,
    through_variant: SchemaVariant | str | None = None,
) -> tuple[SchemaVariantSummary, ...]:
    """Run S0-to-S5 sequentially, stopping if the S0 control fails."""
    stop_variant = SchemaVariant(through_variant) if through_variant is not None else None
    output_path = Path(output_jsonl) if output_jsonl is not None else None
    if output_path is not None:
        output_path.write_text("", encoding="utf-8")
    if schema_output is not None:
        Path(schema_output).write_text(
            json.dumps(ladder_schema_artifact(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    results: list[SchemaVariantSummary] = []
    for spec in _VARIANTS:
        section_summaries = []
        for section_role in ("main_pass", "repeat_pass"):
            section_summary = await run_schema_section_attempts(
                section_role,
                spec.variant,
                backend_factory,
                provider_id=provider_id,
                model_id=model_id,
                config=config,
                attempt_count=attempt_count,
                attempt_sink=(
                    (lambda attempt: _append_attempt_record(output_path, attempt))
                    if output_path is not None
                    else None
                ),
            )
            section_summaries.append(section_summary)
            if output_path is not None:
                _append_records(output_path, section_summary)
        variant_summary = summarize_schema_variant(spec, section_summaries)
        results.append(variant_summary)
        if output_path is not None:
            _append_records(output_path, variant_summary)
        if spec.variant is SchemaVariant.S0 and (
            any(
                section.structurally_valid_outputs != attempt_count for section in section_summaries
            )
        ):
            break
        if stop_variant is not None and spec.variant is stop_variant:
            break
    return tuple(results)


def serialize_evidence(value: BaseModel) -> str:
    """Serialize one evidence model with deterministic JSON ordering."""
    return json.dumps(value.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def _append_records(path: Path, value: SchemaSectionSummary | SchemaVariantSummary) -> None:
    """Append an aggregate record without retaining raw provider responses."""
    if isinstance(value, SchemaSectionSummary):
        records = [{"record_type": "section_summary", **value.model_dump(mode="json")}]
    else:
        records = [{"record_type": "variant_summary", **value.model_dump(mode="json")}]
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(json.dumps(record, sort_keys=True) for record in records) + "\n")
        handle.flush()


def _append_attempt_record(path: Path, attempt: SchemaAttemptEvidence) -> None:
    """Flush one completed attempt before the next provider call begins."""
    record = {"record_type": "attempt", **attempt.model_dump(mode="json")}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
        handle.flush()


def _attempt_metrics(metrics: ProviderMetrics) -> AttemptMetrics:
    """Copy provider-neutral metrics into experiment evidence."""
    return AttemptMetrics(**metrics.public_metadata())


def _normalized_output(value: BaseModel) -> str:
    """Return one validated output in deterministic review form."""
    return json.dumps(value.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


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


def _flatten_json_paths(value: object, prefix: tuple[str, ...] = ()) -> dict[str, object]:
    """Flatten JSON values to paths for structural, non-semantic diffing."""
    if isinstance(value, Mapping):
        flattened: dict[str, object] = {}
        for key in sorted(value):
            flattened.update(_flatten_json_paths(value[key], prefix + (str(key),)))
        return flattened
    if isinstance(value, list):
        flattened = {}
        for index, item in enumerate(value):
            flattened.update(_flatten_json_paths(item, prefix + (str(index),)))
        return flattened
    return {".".join(prefix): value}


def _sum_metric(metrics: Sequence[AttemptMetrics], field_name: str) -> int | float | None:
    """Sum available metrics while preserving unavailable-all semantics."""
    values = [getattr(metric, field_name) for metric in metrics]
    present = [value for value in values if value is not None]
    return sum(present) if present else None


def _sha256_text(value: str) -> str:
    """Hash one deterministic UTF-8 representation."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _parse_args() -> argparse.Namespace:
    """Parse local llama.cpp experiment settings."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://192.168.2.142:8888/v1")
    parser.add_argument("--model", default="qwen3.6-35b-a3b")
    parser.add_argument("--api-key-file", type=Path, default=Path("LLAMA_CPP_API_KEY.txt"))
    parser.add_argument("--provider-id", default="llama_cpp")
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--max-output-tokens", type=int, default=16384)
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--attempts", type=int, default=10)
    parser.add_argument(
        "--through-variant",
        choices=[item.value for item in SchemaVariant],
        help="Stop after this variant instead of continuing the ladder.",
    )
    parser.add_argument("--output-jsonl", type=Path, required=True)
    parser.add_argument("--schema-output", type=Path, required=True)
    return parser.parse_args()


def _configured_backend_factory(args: argparse.Namespace) -> Callable[[], ModelBackendProtocol]:
    """Build the existing async OpenAI-compatible backend for local Qwen."""
    from openai import AsyncOpenAI

    from wellplot.agent.providers.openai_compat_v2 import OpenAICompatibleBackendV2

    api_key = args.api_key_file.read_text(encoding="utf-8").strip()

    def factory() -> ModelBackendProtocol:
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=args.base_url,
            timeout=args.timeout,
        )
        return OpenAICompatibleBackendV2(
            model=args.model,
            client=_ConfiguredClient(client),
            structured_output="json_schema",
            max_tokens_parameter="max_tokens",
        )

    return factory


class _ConfiguredCompletions:
    """Add the local llama.cpp no-thinking request option."""

    def __init__(self, delegate: object) -> None:
        self._delegate = delegate

    async def create(self, **arguments: object) -> object:
        """Forward one request with local Qwen reasoning disabled."""
        arguments.setdefault(
            "extra_body",
            {"chat_template_kwargs": {"enable_thinking": False}},
        )
        return await self._delegate.create(**arguments)  # type: ignore[attr-defined]


class _ConfiguredChat:
    """Proxy the async chat resource used by the existing backend."""

    def __init__(self, delegate: object) -> None:
        self.completions = _ConfiguredCompletions(delegate.completions)  # type: ignore[attr-defined]


class _ConfiguredClient:
    """Proxy an async client without changing the production adapter."""

    def __init__(self, delegate: object) -> None:
        self.chat = _ConfiguredChat(delegate.chat)  # type: ignore[attr-defined]


async def _main_async(args: argparse.Namespace) -> None:
    """Run the staged local compatibility ladder."""
    summaries = await run_schema_ladder(
        _configured_backend_factory(args),
        provider_id=args.provider_id,
        model_id=args.model,
        config=AttemptConfig(
            temperature=args.temperature,
            max_output_tokens=args.max_output_tokens,
            timeout_seconds=args.timeout,
        ),
        attempt_count=args.attempts,
        output_jsonl=args.output_jsonl,
        schema_output=args.schema_output,
        through_variant=args.through_variant,
    )
    print(
        json.dumps(
            [item.model_dump(mode="json") for item in summaries],
            indent=2,
            sort_keys=True,
        )
    )


def main() -> None:
    """Run the local llama.cpp schema compatibility experiment."""
    import asyncio

    asyncio.run(_main_async(_parse_args()))


__all__ = [
    "ArrayTrackDraftS1",
    "ArrayTrackDraftS2",
    "ArrayTrackDraftS3",
    "ArrayTrackDraftS4",
    "BASELINE_SHA",
    "DEFAULT_SYSTEM_PROMPT",
    "EXPERIMENT_VERSION",
    "NormalTrackDraftS1",
    "NormalTrackDraftS2",
    "NormalTrackDraftS3",
    "NormalTrackDraftS4",
    "ReferenceTrackDraftS1",
    "ReferenceTrackDraftS2",
    "ReferenceTrackDraftS3",
    "ReferenceTrackDraftS4",
    "SchemaAttemptEvidence",
    "SchemaSectionSummary",
    "SchemaVariant",
    "SchemaVariantSpec",
    "SchemaVariantSummary",
    "SectionDraftS1",
    "SectionDraftS2",
    "SectionDraftS3",
    "SectionDraftS4",
    "ladder_schema_artifact",
    "provider_input_sha256",
    "response_model_for",
    "run_schema_attempt",
    "run_schema_ladder",
    "run_schema_section_attempts",
    "schema_diff_summary",
    "schema_projection",
    "schema_sha256",
    "schema_variant_specs",
    "serialize_evidence",
    "structured_request",
    "summarize_schema_section",
    "summarize_schema_variant",
]


if __name__ == "__main__":
    main()
