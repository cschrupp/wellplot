"""EXP-TW-06 native Pydantic union-form compatibility bisect."""

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
from scripts.exp_tw05_schema_bisect import SectionDraftS1
from wellplot.agent.code_mode.enrichment import ResolvedSectionContext
from wellplot.agent.providers.base import (
    ModelBackendProtocol,
    ProviderFailureCategory,
    ProviderMetrics,
    ProviderRequestError,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)

BASELINE_SHA = "2e317e1"
EXPERIMENT_VERSION = "exp-tw-06.union-bisect.v1"
DEFAULT_SYSTEM_PROMPT = (
    "Return exactly one SectionDraft that matches the typed input bundle. "
    "Use no fields outside the SectionDraft schema."
)
SectionRole = Literal["main_pass", "repeat_pass"]
TrackRole = Literal["combo", "depth", "cbl", "vdl"]


class _UnionModel(BaseModel):
    """Strict immutable base for TW-06 response models."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class TrackDraftU1(_UnionModel):
    """Historical track shape with a field-level literal union for kind."""

    role: TrackRole
    kind: Literal["normal"] | Literal["reference"] | Literal["array"]
    title: str = Field(min_length=1)
    x_scale: ScaleDraft | None = None
    bindings: tuple[CurveBindingDraft | RasterBindingDraft, ...] = Field(min_length=1)


class SectionDraftU1(_UnionModel):
    """U1 section with only the field-level kind representation changed."""

    title: str = Field(min_length=1)
    source_candidate: str = Field(min_length=1)
    tracks: tuple[TrackDraftU1, ...] = Field(min_length=1)


class NormalTrackU(_UnionModel):
    """U2/U3 normal branch with historical binding permissiveness."""

    role: TrackRole
    kind: Literal["normal"]
    title: str = Field(min_length=1)
    x_scale: ScaleDraft | None = None
    bindings: tuple[CurveBindingDraft | RasterBindingDraft, ...] = Field(min_length=1)


class ReferenceTrackU(_UnionModel):
    """U2/U3 reference branch with historical binding permissiveness."""

    role: TrackRole
    kind: Literal["reference"]
    title: str = Field(min_length=1)
    x_scale: ScaleDraft | None = None
    bindings: tuple[CurveBindingDraft | RasterBindingDraft, ...] = Field(min_length=1)


class ArrayTrackU(_UnionModel):
    """U2/U3 array branch with historical binding permissiveness."""

    role: TrackRole
    kind: Literal["array"]
    title: str = Field(min_length=1)
    x_scale: ScaleDraft | None = None
    bindings: tuple[CurveBindingDraft | RasterBindingDraft, ...] = Field(min_length=1)


TrackUnionU2 = NormalTrackU | ReferenceTrackU | ArrayTrackU
TrackUnionU3 = Annotated[TrackUnionU2, Field(discriminator="kind")]


class SectionDraftU2(_UnionModel):
    """U2 section with an ordinary union of branch track models."""

    title: str = Field(min_length=1)
    source_candidate: str = Field(min_length=1)
    tracks: tuple[TrackUnionU2, ...] = Field(min_length=1)


class SectionDraftU3(_UnionModel):
    """U3 section with the U2 branches wrapped in a discriminator."""

    title: str = Field(min_length=1)
    source_candidate: str = Field(min_length=1)
    tracks: tuple[TrackUnionU3, ...] = Field(min_length=1)


class UnionVariant(StrEnum):
    """Ordered U0-to-U4 response-model variants."""

    U0 = "U0"
    U1 = "U1"
    U2 = "U2"
    U3 = "U3"
    U4 = "U4"


@dataclass(frozen=True, slots=True)
class UnionVariantSpec:
    """Static metadata for one TW-06 response model."""

    variant: UnionVariant
    feature: str
    response_model: type[BaseModel]


_VARIANTS = (
    UnionVariantSpec(UnionVariant.U0, "historical control", SectionDraft),
    UnionVariantSpec(UnionVariant.U1, "field-level literal union", SectionDraftU1),
    UnionVariantSpec(UnionVariant.U2, "ordinary track model union", SectionDraftU2),
    UnionVariantSpec(
        UnionVariant.U3,
        "discriminated union over the U2 branches",
        SectionDraftU3,
    ),
    UnionVariantSpec(UnionVariant.U4, "exact TW-05 S1 control", SectionDraftS1),
)
_VARIANT_BY_ID = {item.variant: item for item in _VARIANTS}


class UnionAttemptEvidence(BaseModel):
    """One redacted provider attempt for one U variant."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    experiment_version: str = EXPERIMENT_VERSION
    baseline_sha: str = BASELINE_SHA
    schema_variant: UnionVariant
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


class UnionSectionSummary(BaseModel):
    """Aggregate evidence for one U variant and section role."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    schema_variant: UnionVariant
    section_role: SectionRole
    attempts: tuple[UnionAttemptEvidence, ...] = Field(min_length=1)
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


class UnionVariantSummary(BaseModel):
    """Aggregate evidence for both sections of one U variant."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    schema_variant: UnionVariant
    feature: str = Field(min_length=1)
    response_schema_sha256: str = Field(min_length=64, max_length=64)
    sections: tuple[UnionSectionSummary, ...] = Field(min_length=1)
    total_attempts: int = Field(ge=1)
    provider_call_successes: int = Field(ge=0)
    structurally_valid_outputs: int = Field(ge=0)
    structured_output_failures: int = Field(ge=0)
    provider_failures: int = Field(ge=0)
    gate_a_successes: int = Field(ge=0)


def union_variant_specs() -> tuple[UnionVariantSpec, ...]:
    """Return the fixed U0-to-U4 response-model ladder."""
    return _VARIANTS


def response_model_for(variant: UnionVariant | str) -> type[BaseModel]:
    """Return one static TW-06 response model."""
    return _VARIANT_BY_ID[UnionVariant(variant)].response_model


def schema_sha256(response_model: type[BaseModel]) -> str:
    """Hash a response model's canonical JSON Schema."""
    payload = json.dumps(
        response_model.model_json_schema(),
        sort_keys=True,
        separators=(",", ":"),
    )
    return _sha256_text(payload)


def schema_projection(variant: UnionVariant | str) -> dict[str, object]:
    """Return raw and normalized review projections for one variant."""
    selected = UnionVariant(variant)
    model = response_model_for(selected)
    return {
        "schema_variant": selected.value,
        "response_model": model.__name__,
        "response_schema_sha256": schema_sha256(model),
        "schema": model.model_json_schema(),
        "normalized_track_schema": normalized_track_schema(model),
    }


def normalized_track_schema(response_model: type[BaseModel]) -> dict[str, object]:
    """Resolve and normalize the schema for one track item."""
    schema = response_model.model_json_schema()
    tracks = schema["properties"]["tracks"]
    item_schema = tracks["items"]
    return _normalize_schema(_resolve_schema(item_schema, schema))


def normalized_branch_schema(branch: type[BaseModel]) -> dict[str, object]:
    """Resolve and normalize one U2/U3 branch definition."""
    schema = branch.model_json_schema()
    return _normalize_schema(schema)


def u2_u3_branch_equivalence() -> dict[str, bool]:
    """Compare the exact reused U2/U3 branch classes by normalized schema."""
    u2_schema = SectionDraftU2.model_json_schema()
    u3_schema = SectionDraftU3.model_json_schema()
    return {
        branch.__name__: _normalize_schema(
            _resolve_schema({"$ref": f"#/$defs/{branch.__name__}"}, u2_schema)
        )
        == _normalize_schema(_resolve_schema({"$ref": f"#/$defs/{branch.__name__}"}, u3_schema))
        for branch in (NormalTrackU, ReferenceTrackU, ArrayTrackU)
    }


def schemas_equivalent_for_track_field(before: type[BaseModel], after: type[BaseModel]) -> bool:
    """Compare track-item schemas after native reference resolution."""
    return normalized_track_schema(before) == normalized_track_schema(after)


def schema_diff_summary(
    before: type[BaseModel] | Mapping[str, object],
    after: type[BaseModel] | Mapping[str, object],
) -> dict[str, object]:
    """Summarize adjacent raw JSON-Schema changes by JSON path."""
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
        "track_schema_equivalent": schemas_equivalent_for_track_field(before, after)
        if isinstance(before, type) and isinstance(after, type)
        else None,
    }


def union_schema_artifact() -> dict[str, object]:
    """Build deterministic U0-to-U4 schema review evidence."""
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
        "u2_u3_branch_equivalence": u2_u3_branch_equivalence(),
    }


def provider_input_sha256(bundle: TypedWorkerInputBundle) -> str:
    """Hash the exact deterministic TW-02I provider payload."""
    return _sha256_text(serialize_provider_input(bundle))


def structured_request(
    bundle: TypedWorkerInputBundle,
    config: AttemptConfig,
) -> StructuredGenerationRequest:
    """Build the identical provider request used for every U variant."""
    return StructuredGenerationRequest(
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        user_prompt=serialize_provider_input(bundle),
        timeout_seconds=config.timeout_seconds,
        temperature=config.temperature,
        max_output_tokens=config.max_output_tokens,
    )


async def run_union_attempt(
    section_role: SectionRole,
    variant: UnionVariant | str,
    backend: ModelBackendProtocol,
    *,
    provider_id: str,
    model_id: str,
    config: AttemptConfig,
    attempt_index: int = 1,
    bundle: TypedWorkerInputBundle | None = None,
    section_context: ResolvedSectionContext | None = None,
    gate_requirements: Mapping[str, object] | None = None,
) -> UnionAttemptEvidence:
    """Perform and score exactly one provider call for one U variant."""
    selected = UnionVariant(variant)
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
        result = await backend.generate_structured(
            structured_request(bundle, config),
            response_model=response_model,
        )
    except ProviderRequestError as error:
        outcome = (
            AttemptOutcome.STRUCTURED_OUTPUT_FAILURE
            if error.category
            in {ProviderFailureCategory.INVALID_RESPONSE, ProviderFailureCategory.VALIDATION}
            else AttemptOutcome.PROVIDER_FAILURE
        )
        return UnionAttemptEvidence(
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
        return UnionAttemptEvidence(
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
    return UnionAttemptEvidence(
        **common,
        outcome=outcome,
        metrics=metrics,
        normalized_output=_normalized_output(validated),
        gate_a=gate,
    )


async def run_union_section_attempts(
    section_role: SectionRole,
    variant: UnionVariant | str,
    backend_factory: Callable[[], ModelBackendProtocol],
    *,
    provider_id: str,
    model_id: str,
    config: AttemptConfig,
    attempt_count: int = 10,
    bundle: TypedWorkerInputBundle | None = None,
    section_context: ResolvedSectionContext | None = None,
    gate_requirements: Mapping[str, object] | None = None,
    attempt_sink: Callable[[UnionAttemptEvidence], None] | None = None,
) -> UnionSectionSummary:
    """Run independent first attempts for one U variant and section."""
    if attempt_count < 1:
        raise ValueError("attempt_count must be at least one.")
    attempts: list[UnionAttemptEvidence] = []
    for index in range(1, attempt_count + 1):
        attempt = await run_union_attempt(
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
    return summarize_union_section(tuple(attempts))


def summarize_union_section(
    attempts: Sequence[UnionAttemptEvidence],
) -> UnionSectionSummary:
    """Aggregate one U variant/section without inferring unavailable metrics."""
    if not attempts:
        raise ValueError("attempts must contain at least one result.")
    variants = {attempt.schema_variant for attempt in attempts}
    roles = {attempt.section_role for attempt in attempts}
    if len(variants) != 1 or len(roles) != 1:
        raise ValueError("Attempts must share one schema variant and section role.")
    metrics = [attempt.metrics for attempt in attempts if attempt.metrics is not None]
    return UnionSectionSummary(
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


def summarize_union_variant(
    spec: UnionVariantSpec,
    sections: Sequence[UnionSectionSummary],
) -> UnionVariantSummary:
    """Aggregate both section roles for one U variant."""
    if not sections:
        raise ValueError("sections must contain at least one summary.")
    if any(section.schema_variant is not spec.variant for section in sections):
        raise ValueError("Section summaries must match the schema variant.")
    return UnionVariantSummary(
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


async def run_union_ladder(
    backend_factory: Callable[[], ModelBackendProtocol],
    *,
    provider_id: str,
    model_id: str,
    config: AttemptConfig,
    attempt_count: int = 10,
    output_jsonl: str | Path | None = None,
    schema_output: str | Path | None = None,
    through_variant: UnionVariant | str | None = None,
    from_variant: UnionVariant | str | None = None,
    append_output: bool = False,
) -> tuple[UnionVariantSummary, ...]:
    """Run staged U variants and stop after the first localization boundary."""
    stop_variant = UnionVariant(through_variant) if through_variant is not None else None
    start_variant = UnionVariant(from_variant) if from_variant is not None else UnionVariant.U0
    variant_ids = [item.variant for item in _VARIANTS]
    if variant_ids.index(start_variant) > (variant_ids.index(stop_variant) if stop_variant else 4):
        raise ValueError("through_variant must not precede from_variant.")
    output_path = Path(output_jsonl) if output_jsonl is not None else None
    if output_path is not None and not append_output:
        output_path.write_text("", encoding="utf-8")
    if schema_output is not None:
        Path(schema_output).write_text(
            json.dumps(union_schema_artifact(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    results: list[UnionVariantSummary] = []
    for spec in _VARIANTS[variant_ids.index(start_variant) :]:
        if spec.variant is UnionVariant.U1 and schemas_equivalent_for_track_field(
            SectionDraft, SectionDraftU1
        ):
            if stop_variant is UnionVariant.U1:
                break
            continue
        section_summaries = []
        for section_role in ("main_pass", "repeat_pass"):
            section_summary = await run_union_section_attempts(
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
        variant_summary = summarize_union_variant(spec, section_summaries)
        results.append(variant_summary)
        if output_path is not None:
            _append_records(output_path, variant_summary)

        if spec.variant is UnionVariant.U0 and any(
            section.structurally_valid_outputs != attempt_count for section in section_summaries
        ):
            break
        if spec.variant in {UnionVariant.U2, UnionVariant.U3} and any(
            section.structurally_valid_outputs != attempt_count for section in section_summaries
        ):
            break
        if stop_variant is not None and spec.variant is stop_variant:
            break
    return tuple(results)


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


def _resolve_schema(value: object, root: Mapping[str, object]) -> object:
    """Resolve local JSON-Schema references for review projections."""
    if isinstance(value, Mapping):
        reference = value.get("$ref")
        if isinstance(reference, str) and reference.startswith("#/$defs/"):
            name = reference.removeprefix("#/$defs/")
            definitions = root.get("$defs", {})
            if isinstance(definitions, Mapping) and name in definitions:
                return _resolve_schema(definitions[name], root)
        return {key: _resolve_schema(item, root) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_schema(item, root) for item in value]
    return value


def _normalize_schema(value: object) -> dict[str, object]:
    """Remove non-structural titles while retaining native schema keywords."""
    if not isinstance(value, Mapping):
        raise TypeError("A schema projection must be a mapping.")
    return _normalize_mapping(value)


def _normalize_mapping(value: Mapping[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key, item in value.items():
        if key in {"title", "description"}:
            continue
        if isinstance(item, Mapping):
            normalized[key] = _normalize_mapping(item)
        elif isinstance(item, list):
            normalized[key] = [
                _normalize_mapping(entry) if isinstance(entry, Mapping) else entry for entry in item
            ]
        else:
            normalized[key] = item
    return normalized


def _flatten_json_paths(value: object, prefix: tuple[str, ...] = ()) -> dict[str, object]:
    """Flatten JSON values to deterministic structural paths."""
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


def _append_records(path: Path, value: UnionSectionSummary | UnionVariantSummary) -> None:
    """Append one aggregate record to the redacted JSONL."""
    if isinstance(value, UnionSectionSummary):
        records = [{"record_type": "section_summary", **value.model_dump(mode="json")}]
    else:
        records = [{"record_type": "variant_summary", **value.model_dump(mode="json")}]
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(json.dumps(record, sort_keys=True) for record in records) + "\n")
        handle.flush()


def _append_attempt_record(path: Path, attempt: UnionAttemptEvidence) -> None:
    """Flush one completed attempt before the next provider call begins."""
    record = {"record_type": "attempt", **attempt.model_dump(mode="json")}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
        handle.flush()


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
        choices=[item.value for item in UnionVariant],
        help="Stop after this variant instead of continuing the ladder.",
    )
    parser.add_argument(
        "--from-variant",
        choices=[item.value for item in UnionVariant],
        help="Start at this variant when prior evidence is already present.",
    )
    parser.add_argument(
        "--append-output",
        action="store_true",
        help="Append evidence instead of clearing the JSONL output first.",
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
    summaries = await run_union_ladder(
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
        from_variant=args.from_variant,
        append_output=args.append_output,
    )
    print(
        json.dumps([item.model_dump(mode="json") for item in summaries], indent=2, sort_keys=True)
    )


def main() -> None:
    """Run the local llama.cpp union-form compatibility experiment."""
    import asyncio

    asyncio.run(_main_async(_parse_args()))


__all__ = [
    "ArrayTrackU",
    "BASELINE_SHA",
    "DEFAULT_SYSTEM_PROMPT",
    "EXPERIMENT_VERSION",
    "NormalTrackU",
    "ReferenceTrackU",
    "SectionDraftU1",
    "SectionDraftU2",
    "SectionDraftU3",
    "TrackDraftU1",
    "UnionAttemptEvidence",
    "UnionSectionSummary",
    "UnionVariant",
    "UnionVariantSpec",
    "UnionVariantSummary",
    "normalized_branch_schema",
    "normalized_track_schema",
    "provider_input_sha256",
    "response_model_for",
    "run_union_attempt",
    "run_union_ladder",
    "run_union_section_attempts",
    "schema_diff_summary",
    "schema_projection",
    "schema_sha256",
    "schemas_equivalent_for_track_field",
    "structured_request",
    "summarize_union_section",
    "summarize_union_variant",
    "u2_u3_branch_equivalence",
    "union_schema_artifact",
    "union_variant_specs",
]


if __name__ == "__main__":
    main()
