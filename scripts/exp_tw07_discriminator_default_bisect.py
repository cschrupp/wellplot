"""EXP-TW-07 required-versus-defaulted discriminator compatibility bisect."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

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
from scripts.exp_tw06_union_bisect import SectionDraftU3
from wellplot.agent.code_mode.enrichment import ResolvedSectionContext
from wellplot.agent.providers.base import (
    ModelBackendProtocol,
    ProviderFailureCategory,
    ProviderMetrics,
    ProviderRequestError,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)

BASELINE_SHA = "1f5da6e"
EXPERIMENT_VERSION = "exp-tw-07.discriminator-default-bisect.v1"
DEFAULT_SYSTEM_PROMPT = (
    "Return exactly one SectionDraft that matches the typed input bundle. "
    "Use no fields outside the SectionDraft schema."
)
SectionRole = Literal["main_pass", "repeat_pass"]
TrackRole = Literal["combo", "depth", "cbl", "vdl"]
TrackKind = Literal["normal", "reference", "array"]


class _TaggedModel(BaseModel):
    """Strict immutable base shared by both factory outputs."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


@dataclass(frozen=True, slots=True)
class TaggedModelSet:
    """The four same-named native Pydantic models for one D variant."""

    response_model: type[BaseModel]
    normal_track: type[BaseModel]
    reference_track: type[BaseModel]
    array_track: type[BaseModel]


def _track_fields(
    kind: TrackKind, *, default_discriminator: bool
) -> dict[str, tuple[object, object]]:
    """Build one branch field map, varying only the discriminator default."""
    kind_field = (Literal[kind], kind) if default_discriminator else (Literal[kind], ...)
    return {
        "role": (TrackRole, ...),
        "kind": kind_field,
        "title": (str, Field(min_length=1)),
        "x_scale": (ScaleDraft | None, None),
        "bindings": (
            tuple[CurveBindingDraft | RasterBindingDraft, ...],
            Field(min_length=1),
        ),
    }


def build_model_set(*, default_discriminator: bool) -> TaggedModelSet:
    """Build one D0/D1 model set with identical native model names."""
    normal_track = create_model(
        "NormalTrackTag",
        __base__=_TaggedModel,
        __module__=__name__,
        **_track_fields("normal", default_discriminator=default_discriminator),
    )
    reference_track = create_model(
        "ReferenceTrackTag",
        __base__=_TaggedModel,
        __module__=__name__,
        **_track_fields("reference", default_discriminator=default_discriminator),
    )
    array_track = create_model(
        "ArrayTrackTag",
        __base__=_TaggedModel,
        __module__=__name__,
        **_track_fields("array", default_discriminator=default_discriminator),
    )
    track_union = Annotated[
        normal_track | reference_track | array_track,
        Field(discriminator="kind"),
    ]
    response_model = create_model(
        "SectionDraftTag",
        __base__=_TaggedModel,
        __module__=__name__,
        title=(str, Field(min_length=1)),
        source_candidate=(str, Field(min_length=1)),
        tracks=(tuple[track_union, ...], Field(min_length=1)),
    )
    return TaggedModelSet(
        response_model=response_model,
        normal_track=normal_track,
        reference_track=reference_track,
        array_track=array_track,
    )


_D0 = build_model_set(default_discriminator=False)
_D1 = build_model_set(default_discriminator=True)


class DefaultVariant(StrEnum):
    """The only two live TW-07 variants."""

    D0 = "D0"
    D1 = "D1"


@dataclass(frozen=True, slots=True)
class DefaultVariantSpec:
    """Static metadata for one required/defaulted response model."""

    variant: DefaultVariant
    feature: str
    default_discriminator: bool
    model_set: TaggedModelSet

    @property
    def response_model(self) -> type[BaseModel]:
        """Return the response model for this variant."""
        return self.model_set.response_model


_VARIANTS = (
    DefaultVariantSpec(DefaultVariant.D0, "required literal tag", False, _D0),
    DefaultVariantSpec(DefaultVariant.D1, "defaulted literal tag", True, _D1),
)
_VARIANT_BY_ID = {item.variant: item for item in _VARIANTS}


class DefaultAttemptEvidence(BaseModel):
    """One redacted provider attempt for one D variant."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    experiment_version: str = EXPERIMENT_VERSION
    baseline_sha: str = BASELINE_SHA
    schema_variant: DefaultVariant
    default_discriminator: bool
    section_role: SectionRole
    attempt_index: int = Field(ge=1)
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    provider_input_sha256: str = Field(min_length=64, max_length=64)
    system_prompt_sha256: str = Field(min_length=64, max_length=64)
    response_schema_sha256: str = Field(min_length=64, max_length=64)
    request: AttemptConfig
    outcome: AttemptOutcome
    provider_failure: ProviderFailureEvidence | None = None
    metrics: AttemptMetrics | None = None
    normalized_output: str | None = None
    gate_a: GateAEvidence | None = None


class DefaultSectionSummary(BaseModel):
    """Aggregate evidence for one D variant and section."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    schema_variant: DefaultVariant
    default_discriminator: bool
    section_role: SectionRole
    attempts: tuple[DefaultAttemptEvidence, ...] = Field(min_length=1)
    total_attempts: int = Field(ge=1)
    provider_call_successes: int = Field(ge=0)
    structurally_valid_outputs: int = Field(ge=0)
    structured_output_failures: int = Field(ge=0)
    provider_failures: int = Field(ge=0)
    gate_a_successes: int = Field(ge=0)
    metric_bearing_calls: int = Field(ge=0)
    input_tokens_total: int | None = None
    output_tokens_total: int | None = None
    total_tokens_total: int | None = None
    latency_ms_total: float | None = None


class DefaultVariantSummary(BaseModel):
    """Aggregate evidence for both sections of one D variant."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    schema_variant: DefaultVariant
    feature: str = Field(min_length=1)
    default_discriminator: bool
    response_schema_sha256: str = Field(min_length=64, max_length=64)
    sections: tuple[DefaultSectionSummary, ...] = Field(min_length=1)
    total_attempts: int = Field(ge=1)
    provider_call_successes: int = Field(ge=0)
    structurally_valid_outputs: int = Field(ge=0)
    structured_output_failures: int = Field(ge=0)
    provider_failures: int = Field(ge=0)
    gate_a_successes: int = Field(ge=0)
    metric_bearing_calls: int = Field(ge=0)


def default_variant_specs() -> tuple[DefaultVariantSpec, ...]:
    """Return D0 then D1 in live execution order."""
    return _VARIANTS


def response_model_for(variant: DefaultVariant | str) -> type[BaseModel]:
    """Return one static D0/D1 response model."""
    return _VARIANT_BY_ID[DefaultVariant(variant)].response_model


def schema_sha256(response_model: type[BaseModel]) -> str:
    """Hash an untouched native Pydantic JSON Schema."""
    payload = json.dumps(
        response_model.model_json_schema(),
        sort_keys=True,
        separators=(",", ":"),
    )
    return _sha256_text(payload)


def provider_input_sha256(bundle: TypedWorkerInputBundle) -> str:
    """Hash the exact deterministic TW-02I provider payload."""
    return _sha256_text(serialize_provider_input(bundle))


def system_prompt_sha256() -> str:
    """Hash the fixed historical system prompt."""
    return _sha256_text(DEFAULT_SYSTEM_PROMPT)


def structured_request(
    bundle: TypedWorkerInputBundle,
    config: AttemptConfig,
) -> StructuredGenerationRequest:
    """Build the identical D0/D1 provider request."""
    return StructuredGenerationRequest(
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        user_prompt=serialize_provider_input(bundle),
        timeout_seconds=config.timeout_seconds,
        temperature=config.temperature,
        max_output_tokens=config.max_output_tokens,
    )


def schema_comparison() -> dict[str, object]:
    """Audit that D0/D1 differ only in discriminator defaults/requiredness."""
    d0 = _D0.response_model.model_json_schema()
    d1 = _D1.response_model.model_json_schema()
    d0_defs = d0["$defs"]
    d1_defs = d1["$defs"]
    branch_names = ["NormalTrackTag", "ReferenceTrackTag", "ArrayTrackTag"]
    branch_results: dict[str, object] = {}
    for branch_name in branch_names:
        d0_branch = d0_defs[branch_name]
        d1_branch = d1_defs[branch_name]
        d0_kind = d0_branch["properties"]["kind"]
        d1_kind = d1_branch["properties"]["kind"]
        d0_required = set(d0_branch["required"])
        d1_required = set(d1_branch["required"])
        d0_without_kind = _without_kind_difference(d0_branch)
        d1_without_kind = _without_kind_difference(d1_branch)
        branch_results[branch_name] = {
            "d0_kind_has_default": "default" in d0_kind,
            "d1_kind_default": d1_kind.get("default"),
            "d0_kind_required": "kind" in d0_required,
            "d1_kind_required": "kind" in d1_required,
            "required_removed_from_d0": sorted(d0_required - d1_required),
            "required_added_to_d1": sorted(d1_required - d0_required),
            "non_kind_fields_equivalent": d0_without_kind == d1_without_kind,
        }

    d0_normalized = _normalize_default_difference(d0, default_discriminator=False)
    d1_normalized = _normalize_default_difference(d1, default_discriminator=True)
    return {
        "branch_names_identical": set(d0_defs) == set(d1_defs),
        "branch_count_identical": len(branch_names) == 3,
        "tracks_one_of_identical": _tracks_one_of(d0) == _tracks_one_of(d1),
        "discriminator_property_name_identical": _discriminator_property(d0)
        == _discriminator_property(d1),
        "discriminator_mapping_identical": _discriminator_mapping(d0) == _discriminator_mapping(d1),
        "non_kind_schema_identical": d0_normalized == d1_normalized,
        "branches": branch_results,
        "raw_diff": _schema_diff(d0, d1),
    }


def tag_representation(response_model: type[BaseModel]) -> dict[str, object]:
    """Project required/defaulted tag facts for U3/U4 review linkage."""
    schema = response_model.model_json_schema()
    branches: list[dict[str, object]] = []
    for reference in _tracks_one_of(schema):
        if not isinstance(reference, Mapping) or not isinstance(reference.get("$ref"), str):
            raise ValueError("Expected a local track branch reference.")
        name = reference["$ref"].rsplit("/", 1)[-1]
        branch = schema["$defs"][name]
        kind = branch["properties"]["kind"]
        branches.append(
            {
                "branch": name,
                "kind_const": kind.get("const"),
                "kind_default": kind.get("default"),
                "kind_required": "kind" in branch["required"],
            }
        )
    return {
        "branch_count": len(branches),
        "discriminator_property_name": _discriminator_property(schema),
        "branches": branches,
    }


def d1_accepts_omitted_kind() -> bool:
    """Report native Pydantic behavior for an omitted discriminator tag."""
    payload = {
        "role": "combo",
        "title": "Combo",
        "bindings": [
            {
                "kind": "curve",
                "semantic_id": "synthetic",
                "channel": "SYNTHETIC",
                "scale": {"minimum": 0, "maximum": 1},
            }
        ],
    }
    try:
        _D1.normal_track.model_validate(payload)
    except ValidationError:
        return False
    return True


def schema_artifact() -> dict[str, object]:
    """Build compact native D0/D1 and U3/U4 comparison evidence."""
    return {
        "baseline_sha": BASELINE_SHA,
        "experiment_version": EXPERIMENT_VERSION,
        "variants": [
            {
                "schema_variant": spec.variant.value,
                "default_discriminator": spec.default_discriminator,
                "response_model": spec.response_model.__name__,
                "response_schema_sha256": schema_sha256(spec.response_model),
                "schema": spec.response_model.model_json_schema(),
            }
            for spec in _VARIANTS
        ],
        "d0_d1_comparison": schema_comparison(),
        "u3_representation": tag_representation(SectionDraftU3),
        "u4_representation": tag_representation(SectionDraftS1),
        "d1_omitted_kind_accepts_on_branch": d1_accepts_omitted_kind(),
    }


async def run_default_attempt(
    section_role: SectionRole,
    variant: DefaultVariant | str,
    backend: ModelBackendProtocol,
    *,
    provider_id: str,
    model_id: str,
    config: AttemptConfig,
    attempt_index: int,
    bundle: TypedWorkerInputBundle | None = None,
    section_context: ResolvedSectionContext | None = None,
    gate_requirements: Mapping[str, object] | None = None,
) -> DefaultAttemptEvidence:
    """Perform and score exactly one provider call."""
    selected = DefaultVariant(variant)
    spec = _VARIANT_BY_ID[selected]
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
        "default_discriminator": spec.default_discriminator,
        "section_role": section_role,
        "attempt_index": attempt_index,
        "provider_id": provider_id,
        "model_id": model_id,
        "provider_input_sha256": provider_input_sha256(bundle),
        "system_prompt_sha256": system_prompt_sha256(),
        "response_schema_sha256": schema_sha256(spec.response_model),
        "request": config,
    }
    try:
        result = await backend.generate_structured(
            structured_request(bundle, config),
            response_model=spec.response_model,
        )
    except ProviderRequestError as error:
        outcome = (
            AttemptOutcome.STRUCTURED_OUTPUT_FAILURE
            if error.category
            in {ProviderFailureCategory.INVALID_RESPONSE, ProviderFailureCategory.VALIDATION}
            else AttemptOutcome.PROVIDER_FAILURE
        )
        return DefaultAttemptEvidence(
            **common,
            outcome=outcome,
            provider_failure=ProviderFailureEvidence(**error.public_metadata()),
        )

    metrics = (
        _attempt_metrics(result.metrics) if isinstance(result, StructuredGenerationResult) else None
    )
    if not isinstance(result, StructuredGenerationResult) or not isinstance(
        result.value, spec.response_model
    ):
        return DefaultAttemptEvidence(
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
    return DefaultAttemptEvidence(
        **common,
        outcome=outcome,
        metrics=metrics,
        normalized_output=_normalized_output(validated),
        gate_a=gate,
    )


async def run_default_section_attempts(
    section_role: SectionRole,
    variant: DefaultVariant | str,
    backend_factory: Callable[[], ModelBackendProtocol],
    *,
    provider_id: str,
    model_id: str,
    config: AttemptConfig,
    attempt_count: int = 10,
    attempt_sink: Callable[[DefaultAttemptEvidence], None] | None = None,
) -> DefaultSectionSummary:
    """Run independent first attempts for one D variant and section."""
    if attempt_count < 1:
        raise ValueError("attempt_count must be at least one.")
    attempts: list[DefaultAttemptEvidence] = []
    for index in range(1, attempt_count + 1):
        attempt = await run_default_attempt(
            section_role,
            variant,
            backend_factory(),
            provider_id=provider_id,
            model_id=model_id,
            config=config,
            attempt_index=index,
        )
        attempts.append(attempt)
        if attempt_sink is not None:
            attempt_sink(attempt)
    return summarize_default_section(tuple(attempts))


def summarize_default_section(
    attempts: Sequence[DefaultAttemptEvidence],
) -> DefaultSectionSummary:
    """Aggregate one D variant/section without inventing failed-call metrics."""
    if not attempts:
        raise ValueError("attempts must contain at least one result.")
    metrics = [attempt.metrics for attempt in attempts if attempt.metrics is not None]
    return DefaultSectionSummary(
        schema_variant=attempts[0].schema_variant,
        default_discriminator=attempts[0].default_discriminator,
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
        metric_bearing_calls=len(metrics),
        input_tokens_total=_sum_metric(metrics, "input_tokens"),
        output_tokens_total=_sum_metric(metrics, "output_tokens"),
        total_tokens_total=_sum_metric(metrics, "total_tokens"),
        latency_ms_total=_sum_metric(metrics, "latency_ms"),
    )


def summarize_default_variant(
    spec: DefaultVariantSpec,
    sections: Sequence[DefaultSectionSummary],
) -> DefaultVariantSummary:
    """Aggregate both sections for one D variant."""
    return DefaultVariantSummary(
        schema_variant=spec.variant,
        feature=spec.feature,
        default_discriminator=spec.default_discriminator,
        response_schema_sha256=schema_sha256(spec.response_model),
        sections=tuple(sections),
        total_attempts=sum(section.total_attempts for section in sections),
        provider_call_successes=sum(section.provider_call_successes for section in sections),
        structurally_valid_outputs=sum(section.structurally_valid_outputs for section in sections),
        structured_output_failures=sum(section.structured_output_failures for section in sections),
        provider_failures=sum(section.provider_failures for section in sections),
        gate_a_successes=sum(section.gate_a_successes for section in sections),
        metric_bearing_calls=sum(section.metric_bearing_calls for section in sections),
    )


async def run_default_stage(
    variant: DefaultVariant | str,
    backend_factory: Callable[[], ModelBackendProtocol],
    *,
    provider_id: str,
    model_id: str,
    config: AttemptConfig,
    attempt_count: int = 10,
    output_jsonl: str | Path | None = None,
    schema_output: str | Path | None = None,
    append_output: bool = False,
) -> DefaultVariantSummary:
    """Run one complete D0 or D1 stage with immediate evidence flushing."""
    selected = DefaultVariant(variant)
    spec = _VARIANT_BY_ID[selected]
    output_path = Path(output_jsonl) if output_jsonl is not None else None
    if output_path is not None and not append_output:
        output_path.write_text("", encoding="utf-8")
    if schema_output is not None:
        Path(schema_output).write_text(
            json.dumps(schema_artifact(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    sections = []
    for section_role in ("main_pass", "repeat_pass"):
        section = await run_default_section_attempts(
            section_role,
            selected,
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
        sections.append(section)
        if output_path is not None:
            _append_record(output_path, "section_summary", section)
    summary = summarize_default_variant(spec, sections)
    if output_path is not None:
        _append_record(output_path, "variant_summary", summary)
    return summary


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


def _without_kind_difference(branch: Mapping[str, object]) -> dict[str, object]:
    """Remove only the discriminator property and required entry for comparison."""
    result = copy.deepcopy(dict(branch))
    properties = result.get("properties")
    if isinstance(properties, dict):
        properties.pop("kind", None)
    required = result.get("required")
    if isinstance(required, list):
        result["required"] = sorted(item for item in required if item != "kind")
    return result


def _normalize_default_difference(
    schema: Mapping[str, object], *, default_discriminator: bool
) -> dict[str, object]:
    """Normalize D0/D1 to compare all non-discriminator schema structure."""
    result = copy.deepcopy(dict(schema))
    definitions = result.get("$defs")
    if isinstance(definitions, dict):
        for branch_name in ("NormalTrackTag", "ReferenceTrackTag", "ArrayTrackTag"):
            branch = definitions[branch_name]
            properties = branch["properties"]
            properties["kind"].pop("default", None)
            required = branch["required"]
            if default_discriminator:
                required.append("kind")
            branch["required"] = sorted(required)
    return result


def _tracks_one_of(schema: Mapping[str, object]) -> list[object]:
    """Return the native track union references in emitted order."""
    items = schema["properties"]["tracks"]["items"]
    return list(items["oneOf"])


def _discriminator_property(schema: Mapping[str, object]) -> object:
    """Return the native discriminator property name."""
    return schema["properties"]["tracks"]["items"]["discriminator"]["propertyName"]


def _discriminator_mapping(schema: Mapping[str, object]) -> object:
    """Return the native discriminator mapping."""
    return schema["properties"]["tracks"]["items"]["discriminator"]["mapping"]


def _schema_diff(before: Mapping[str, object], after: Mapping[str, object]) -> dict[str, object]:
    """Return deterministic raw schema path differences."""
    before_paths = _flatten_json_paths(before)
    after_paths = _flatten_json_paths(after)
    before_keys = set(before_paths)
    after_keys = set(after_paths)
    return {
        "added_paths": sorted(after_keys - before_keys),
        "removed_paths": sorted(before_keys - after_keys),
        "changed_paths": sorted(
            path for path in before_keys & after_keys if before_paths[path] != after_paths[path]
        ),
    }


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


def _attempt_metrics(metrics: ProviderMetrics) -> AttemptMetrics:
    """Copy provider-neutral metrics into experiment evidence."""
    return AttemptMetrics(**metrics.public_metadata())


def _normalized_output(value: BaseModel) -> str:
    """Return one validated output in deterministic review form."""
    return json.dumps(value.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def _sum_metric(metrics: Sequence[AttemptMetrics], field_name: str) -> int | float | None:
    """Sum available metrics while preserving unavailable-all semantics."""
    values = [getattr(metric, field_name) for metric in metrics]
    present = [value for value in values if value is not None]
    return sum(present) if present else None


def _sha256_text(value: str) -> str:
    """Hash deterministic text for redacted evidence identity."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _append_attempt_record(path: Path, attempt: DefaultAttemptEvidence) -> None:
    """Flush one completed attempt before the next provider call."""
    _append_record(path, "attempt", attempt)


def _append_record(path: Path, record_type: str, value: BaseModel) -> None:
    """Append and flush one redacted evidence record."""
    record = {"record_type": record_type, **value.model_dump(mode="json")}
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
    parser.add_argument("--variant", choices=[item.value for item in DefaultVariant], required=True)
    parser.add_argument("--append-output", action="store_true")
    parser.add_argument("--output-jsonl", type=Path, required=True)
    parser.add_argument("--schema-output", type=Path, required=True)
    return parser.parse_args()


def _configured_backend_factory(args: argparse.Namespace) -> Callable[[], ModelBackendProtocol]:
    """Build the existing async OpenAI-compatible backend for local Qwen."""
    from openai import AsyncOpenAI

    from wellplot.agent.providers.openai_compat_v2 import OpenAICompatibleBackendV2

    api_key = args.api_key_file.read_text(encoding="utf-8").strip()

    def factory() -> ModelBackendProtocol:
        client = AsyncOpenAI(api_key=api_key, base_url=args.base_url, timeout=args.timeout)
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
    """Run one staged D0 or D1 compatibility stage."""
    summary = await run_default_stage(
        args.variant,
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
        append_output=args.append_output,
    )
    print(json.dumps(summary.model_dump(mode="json"), indent=2, sort_keys=True))


def main() -> None:
    """Run the local llama.cpp discriminator-default experiment."""
    import asyncio

    asyncio.run(_main_async(_parse_args()))


__all__ = [
    "BASELINE_SHA",
    "DEFAULT_SYSTEM_PROMPT",
    "DefaultAttemptEvidence",
    "DefaultSectionSummary",
    "DefaultVariant",
    "DefaultVariantSpec",
    "DefaultVariantSummary",
    "TaggedModelSet",
    "build_model_set",
    "d1_accepts_omitted_kind",
    "default_variant_specs",
    "provider_input_sha256",
    "response_model_for",
    "run_default_attempt",
    "run_default_section_attempts",
    "run_default_stage",
    "schema_artifact",
    "schema_comparison",
    "schema_sha256",
    "system_prompt_sha256",
    "structured_request",
    "tag_representation",
]


if __name__ == "__main__":
    main()
