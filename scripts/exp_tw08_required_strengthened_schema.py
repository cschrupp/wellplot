"""EXP-TW-08 required-tag remediation validation for SectionDraftS."""

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
    compile_section_draft,
    load_golden_drafts,
    validate_gate_a,
)
from scripts.exp_tw03_provider import (
    AttemptConfig,
    AttemptMetrics,
    AttemptOutcome,
    GateAEvidence,
    ProviderFailureEvidence,
)
from scripts.exp_tw03s_schema import (
    ArrayTrackDraftS,
    NormalTrackDraftS,
    ReferenceTrackDraftS,
    SectionDraftS,
)
from wellplot.agent.code_mode.enrichment import ResolvedSectionContext
from wellplot.agent.providers.base import (
    ModelBackendProtocol,
    ProviderFailureCategory,
    ProviderMetrics,
    ProviderRequestError,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)

BASELINE_SHA = "79f3173"
EXPERIMENT_VERSION = "exp-tw-08.required-strengthened-schema.v1"
DEFAULT_SYSTEM_PROMPT = (
    "Return exactly one SectionDraftS matching the typed input bundle. "
    "Use no fields outside the SectionDraftS schema."
)
SectionRole = Literal["main_pass", "repeat_pass"]
TrackRole = Literal["combo", "depth", "cbl", "vdl"]
TrackKind = Literal["normal", "reference", "array"]


class _RequiredModel(BaseModel):
    """Strict immutable base for the R1 native models."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


@dataclass(frozen=True, slots=True)
class RequiredModelSet:
    """The R1 branches and response model built through one factory."""

    response_model: type[BaseModel]
    normal_track: type[BaseModel]
    reference_track: type[BaseModel]
    array_track: type[BaseModel]


def _set_doc(model: type[BaseModel], source: type[BaseModel]) -> type[BaseModel]:
    """Align dynamic model documentation with the frozen R0 model."""
    model.__doc__ = source.__doc__
    return model


def _required_track_fields(kind: TrackKind) -> dict[str, tuple[object, object]]:
    """Build one R1 branch with a required literal discriminator tag."""
    bindings: object
    x_scale: tuple[object, object]
    if kind == "array":
        bindings = tuple[RasterBindingDraft, ...]
        x_scale = (ScaleDraft, ...)
    elif kind == "normal":
        bindings = tuple[CurveBindingDraft, ...]
        x_scale = (ScaleDraft | None, None)
    else:
        bindings = tuple[CurveBindingDraft, ...]
        x_scale = (ScaleDraft | None, None)
    return {
        "role": (TrackRole, ...),
        "kind": (Literal[kind], ...),
        "title": (str, Field(min_length=1)),
        "x_scale": x_scale,
        "bindings": (bindings, Field(min_length=1)),
    }


def build_required_section_draft_s() -> RequiredModelSet:
    """Build R1 with R0 names and required track discriminator tags."""
    normal_fields = _required_track_fields("normal")
    reference_fields = _required_track_fields("reference")
    array_fields = _required_track_fields("array")

    normal_track = create_model(
        "NormalTrackDraftS",
        __base__=_RequiredModel,
        __module__=__name__,
        **normal_fields,
    )
    reference_track = create_model(
        "ReferenceTrackDraftS",
        __base__=_RequiredModel,
        __module__=__name__,
        **reference_fields,
    )
    array_track = create_model(
        "ArrayTrackDraftS",
        __base__=_RequiredModel,
        __module__=__name__,
        **array_fields,
    )
    _set_doc(normal_track, NormalTrackDraftS)
    _set_doc(reference_track, ReferenceTrackDraftS)
    _set_doc(array_track, ArrayTrackDraftS)
    track_union = Annotated[
        normal_track | reference_track | array_track,
        Field(discriminator="kind"),
    ]
    response_model = create_model(
        "SectionDraftS",
        __base__=_RequiredModel,
        __module__=__name__,
        title=(str, Field(min_length=1)),
        source_candidate=(str, Field(min_length=1)),
        tracks=(tuple[track_union, ...], Field(min_length=1)),
    )
    _set_doc(response_model, SectionDraftS)
    return RequiredModelSet(
        response_model=response_model,
        normal_track=normal_track,
        reference_track=reference_track,
        array_track=array_track,
    )


R1 = build_required_section_draft_s()


class RemediationVariant(StrEnum):
    """The only two authorized TW-08 response variants."""

    R0 = "R0"
    R1 = "R1"


@dataclass(frozen=True, slots=True)
class RemediationVariantSpec:
    """Static metadata for one remediation response model."""

    variant: RemediationVariant
    feature: str
    required_discriminator: bool
    response_model: type[BaseModel]


_VARIANTS = (
    RemediationVariantSpec(
        RemediationVariant.R0, "exact strengthened control", False, SectionDraftS
    ),
    RemediationVariantSpec(
        RemediationVariant.R1,
        "required strengthened track tags",
        True,
        R1.response_model,
    ),
)
_VARIANT_BY_ID = {item.variant: item for item in _VARIANTS}


class RemediationAttemptEvidence(BaseModel):
    """One redacted provider attempt for one remediation variant."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    experiment_version: str = EXPERIMENT_VERSION
    baseline_sha: str = BASELINE_SHA
    schema_variant: RemediationVariant
    required_discriminator: bool
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


class RemediationSectionSummary(BaseModel):
    """Aggregate evidence for one response variant and section."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    schema_variant: RemediationVariant
    required_discriminator: bool
    section_role: SectionRole
    attempts: tuple[RemediationAttemptEvidence, ...] = Field(min_length=1)
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


class RemediationVariantSummary(BaseModel):
    """Aggregate evidence for both sections of one response variant."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    schema_variant: RemediationVariant
    feature: str = Field(min_length=1)
    required_discriminator: bool
    response_schema_sha256: str = Field(min_length=64, max_length=64)
    sections: tuple[RemediationSectionSummary, ...] = Field(min_length=1)
    total_attempts: int = Field(ge=1)
    provider_call_successes: int = Field(ge=0)
    structurally_valid_outputs: int = Field(ge=0)
    structured_output_failures: int = Field(ge=0)
    provider_failures: int = Field(ge=0)
    gate_a_successes: int = Field(ge=0)
    metric_bearing_calls: int = Field(ge=0)


def remediation_variant_specs() -> tuple[RemediationVariantSpec, ...]:
    """Return R0 then R1 in the required staged order."""
    return _VARIANTS


def response_model_for(variant: RemediationVariant | str) -> type[BaseModel]:
    """Return the static response model for one remediation variant."""
    return _VARIANT_BY_ID[RemediationVariant(variant)].response_model


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
    """Hash the exact TW-04 first-attempt prompt."""
    return _sha256_text(DEFAULT_SYSTEM_PROMPT)


def structured_request(
    bundle: TypedWorkerInputBundle,
    config: AttemptConfig,
) -> StructuredGenerationRequest:
    """Build the identical R0/R1 provider request."""
    return StructuredGenerationRequest(
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        user_prompt=serialize_provider_input(bundle),
        timeout_seconds=config.timeout_seconds,
        temperature=config.temperature,
        max_output_tokens=config.max_output_tokens,
    )


def schema_comparison() -> dict[str, object]:
    """Audit that R0/R1 differ only in track discriminator defaults."""
    r0 = SectionDraftS.model_json_schema()
    r1 = R1.response_model.model_json_schema()
    branch_names = ["NormalTrackDraftS", "ReferenceTrackDraftS", "ArrayTrackDraftS"]
    branch_results: dict[str, object] = {}
    for branch_name in branch_names:
        r0_branch = r0["$defs"][branch_name]
        r1_branch = r1["$defs"][branch_name]
        r0_kind = r0_branch["properties"]["kind"]
        r1_kind = r1_branch["properties"]["kind"]
        r0_required = set(r0_branch["required"])
        r1_required = set(r1_branch["required"])
        branch_results[branch_name] = {
            "r0_kind_default": r0_kind.get("default"),
            "r1_kind_has_default": "default" in r1_kind,
            "r0_kind_required": "kind" in r0_required,
            "r1_kind_required": "kind" in r1_required,
            "required_removed_from_r0": sorted(r0_required - r1_required),
            "required_added_to_r1": sorted(r1_required - r0_required),
            "non_kind_fields_equivalent": _without_kind(r0_branch) == _without_kind(r1_branch),
        }
    normalized_r0 = _normalize_tag_difference(r0, required=True, default=True)
    normalized_r1 = _normalize_tag_difference(r1, required=True, default=False)
    return {
        "branch_names_identical": set(r0["$defs"]) == set(r1["$defs"]),
        "branch_count_identical": len(branch_names) == 3,
        "one_of_identical": _track_refs(r0) == _track_refs(r1),
        "ref_targets_identical": _track_refs(r0) == _track_refs(r1),
        "discriminator_property_identical": _discriminator_property(r0)
        == _discriminator_property(r1),
        "discriminator_mapping_identical": _discriminator_mapping(r0) == _discriminator_mapping(r1),
        "non_tag_schema_identical": normalized_r0 == normalized_r1,
        "branches": branch_results,
        "raw_diff": _schema_diff(r0, r1),
    }


def structural_invariant_audit() -> dict[str, bool]:
    """Exercise all four TW-03S structural guarantees on R1."""
    model = R1.response_model
    curve = {
        "kind": "curve",
        "semantic_id": "curve",
        "channel": "CURVE",
        "scale": {"minimum": 0, "maximum": 1},
    }
    raster = {
        "kind": "raster",
        "semantic_id": "raster",
        "channel": "ARRAY",
        "profile": "vdl",
        "sample_axis": {
            "unit": "samples",
            "minimum": 0,
            "maximum": 1,
            "tick_count": 2,
            "source_origin": 0,
            "source_step": 1,
        },
    }

    def section(track: dict[str, object]) -> dict[str, object]:
        return {"title": "Section", "source_candidate": "source-1", "tracks": [track]}

    def track(kind: str, binding: dict[str, object], *, role: str = "combo") -> dict[str, object]:
        value: dict[str, object] = {
            "role": role,
            "kind": kind,
            "title": "Track",
            "bindings": [binding],
        }
        if kind == "array":
            value["x_scale"] = {"minimum": 0, "maximum": 1}
        return value

    return {
        "normal_curve_only": _accepts(model, section(track("normal", curve))),
        "reference_curve_only": _accepts(model, section(track("reference", curve))),
        "array_raster_with_x_scale": _accepts(model, section(track("array", raster, role="vdl"))),
        "normal_rejects_raster": _rejects(model, section(track("normal", raster))),
        "reference_rejects_raster": _rejects(model, section(track("reference", raster))),
        "array_rejects_curve": _rejects(model, section(track("array", curve))),
        "array_requires_x_scale": _rejects(
            model,
            {
                "title": "Section",
                "source_candidate": "source-1",
                "tracks": [track("array", raster, role="vdl") | {"x_scale": None}],
            },
        ),
        "role_domain_rejects_unknown": _rejects(
            model, section(track("normal", curve, role="anything"))
        ),
        "role_kind_not_coupled": _accepts(model, section(track("normal", curve, role="vdl"))),
    }


def golden_equivalence() -> dict[str, object]:
    """Compare R0/R1 golden semantics and unchanged corrected Gate A."""
    corpus = load_corpus()
    results: dict[str, object] = {}
    for section_role, golden in load_golden_drafts().items():
        r0 = SectionDraftS.model_validate(golden.model_dump(mode="json"))
        r1 = R1.response_model.model_validate(golden.model_dump(mode="json"))
        context = _context_for_role(corpus, section_role)
        requirements = corpus.gate_a["section_requirements"][section_role]
        r0_gate = validate_gate_a(
            r0.model_dump(mode="json"),
            section_key=section_role,
            section_context=context,
            requirements=requirements,
        )
        r1_gate = validate_gate_a(
            r1.model_dump(mode="json"),
            section_key=section_role,
            section_context=context,
            requirements=requirements,
        )
        results[section_role] = {
            "r0_dump_equals_r1": r0.model_dump(mode="json") == r1.model_dump(mode="json"),
            "r1_dump_equals_golden": r1.model_dump(mode="json") == golden.model_dump(mode="json"),
            "r0_gate": r0_gate,
            "r1_gate": r1_gate,
            "gate_equal": r0_gate == r1_gate,
        }
    return results


def compiler_projection_equivalence() -> dict[str, bool]:
    """Verify the unchanged compiler sees equivalent serialized mappings."""
    corpus = load_corpus()
    results: dict[str, bool] = {}
    for index, (section_role, golden) in enumerate(load_golden_drafts().items()):
        context = corpus.sections[index]
        requirements = corpus.gate_a["section_requirements"][section_role]
        r0 = SectionDraftS.model_validate(golden.model_dump(mode="json"))
        r1 = R1.response_model.model_validate(golden.model_dump(mode="json"))
        compiled_r0 = compile_section_draft(
            r0.model_dump(mode="json"),
            section_key=section_role,
            section_context=context,
            requirements=requirements,
        )
        compiled_r1 = compile_section_draft(
            r1.model_dump(mode="json"),
            section_key=section_role,
            section_context=context,
            requirements=requirements,
        )
        results[section_role] = (
            compiled_r0.normalized_projection == compiled_r1.normalized_projection
        )
    return results


def schema_artifact() -> dict[str, object]:
    """Build deterministic schema, invariant, and semantic evidence."""
    return {
        "baseline_sha": BASELINE_SHA,
        "experiment_version": EXPERIMENT_VERSION,
        "variants": [
            {
                "schema_variant": spec.variant.value,
                "required_discriminator": spec.required_discriminator,
                "response_model": spec.response_model.__name__,
                "response_schema_sha256": schema_sha256(spec.response_model),
                "schema": spec.response_model.model_json_schema(),
            }
            for spec in _VARIANTS
        ],
        "r0_r1_comparison": schema_comparison(),
        "tw03s_invariant_audit": structural_invariant_audit(),
        "golden_equivalence": golden_equivalence(),
        "compiler_projection_equivalence": compiler_projection_equivalence(),
        "r0_full_union_omitted_kind": _full_union_omitted_kind(SectionDraftS),
        "r1_full_union_omitted_kind": _full_union_omitted_kind(R1.response_model),
    }


async def run_remediation_attempt(
    section_role: SectionRole,
    variant: RemediationVariant | str,
    backend: ModelBackendProtocol,
    *,
    provider_id: str,
    model_id: str,
    config: AttemptConfig,
    attempt_index: int,
    bundle: TypedWorkerInputBundle | None = None,
    section_context: ResolvedSectionContext | None = None,
    gate_requirements: Mapping[str, object] | None = None,
) -> RemediationAttemptEvidence:
    """Perform and score exactly one R0 or R1 provider call."""
    selected = RemediationVariant(variant)
    spec = _VARIANT_BY_ID[selected]
    corpus = None
    if bundle is None or section_context is None or gate_requirements is None:
        corpus = load_corpus()
    if bundle is None:
        bundle = build_typed_worker_input(section_role, contract_path=DEFAULT_CONTRACT_PATH)
    if section_context is None:
        section_corpus = load_corpus() if corpus is None else corpus
        section_context = _context_for_role(section_corpus, section_role)
    if gate_requirements is None:
        gate_corpus = load_corpus() if corpus is None else corpus
        gate_requirements = gate_corpus.gate_a["section_requirements"][section_role]

    common = {
        "schema_variant": selected,
        "required_discriminator": spec.required_discriminator,
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
        return RemediationAttemptEvidence(
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
        return RemediationAttemptEvidence(
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

    gate = GateAEvidence.model_validate(
        validate_gate_a(
            result.value.model_dump(mode="json"),
            section_key=section_role,
            section_context=section_context,
            requirements=gate_requirements,
        )
    )
    outcome = AttemptOutcome.SUCCESS if gate.semantic_usable else AttemptOutcome.GATE_A_FAILURE
    return RemediationAttemptEvidence(
        **common,
        outcome=outcome,
        metrics=metrics,
        normalized_output=_normalized_output(result.value),
        gate_a=gate,
    )


async def run_remediation_section_attempts(
    section_role: SectionRole,
    variant: RemediationVariant | str,
    backend_factory: Callable[[], ModelBackendProtocol],
    *,
    provider_id: str,
    model_id: str,
    config: AttemptConfig,
    attempt_count: int = 10,
    attempt_sink: Callable[[RemediationAttemptEvidence], None] | None = None,
) -> RemediationSectionSummary:
    """Run independent first attempts for one variant and section."""
    if attempt_count < 1:
        raise ValueError("attempt_count must be at least one.")
    attempts: list[RemediationAttemptEvidence] = []
    for index in range(1, attempt_count + 1):
        attempt = await run_remediation_attempt(
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
    return summarize_section(tuple(attempts))


def summarize_section(
    attempts: Sequence[RemediationAttemptEvidence],
) -> RemediationSectionSummary:
    """Aggregate one section without inventing failed-call metrics."""
    if not attempts:
        raise ValueError("attempts must contain at least one result.")
    metrics = [attempt.metrics for attempt in attempts if attempt.metrics is not None]
    return RemediationSectionSummary(
        schema_variant=attempts[0].schema_variant,
        required_discriminator=attempts[0].required_discriminator,
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


def summarize_variant(
    spec: RemediationVariantSpec,
    sections: Sequence[RemediationSectionSummary],
) -> RemediationVariantSummary:
    """Aggregate both section roles for one variant."""
    return RemediationVariantSummary(
        schema_variant=spec.variant,
        feature=spec.feature,
        required_discriminator=spec.required_discriminator,
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


async def run_remediation_stage(
    variant: RemediationVariant | str,
    backend_factory: Callable[[], ModelBackendProtocol],
    *,
    provider_id: str,
    model_id: str,
    config: AttemptConfig,
    attempt_count: int = 10,
    output_jsonl: str | Path | None = None,
    schema_output: str | Path | None = None,
    append_output: bool = False,
) -> RemediationVariantSummary:
    """Run one complete R0 or R1 stage with immediate evidence flushing."""
    selected = RemediationVariant(variant)
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
        section = await run_remediation_section_attempts(
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
    summary = summarize_variant(spec, sections)
    if output_path is not None:
        _append_record(output_path, "variant_summary", summary)
    return summary


def _context_for_role(
    corpus: FrozenWorkerCorpus,
    section_role: SectionRole,
) -> ResolvedSectionContext:
    """Resolve the frozen host context by opaque source candidate."""
    candidate_id = "source-1" if section_role == "main_pass" else "source-2"
    for section in corpus.sections:
        if any(source.candidate_id == candidate_id for source in section.sources):
            return section
    raise ValueError(f"Frozen corpus has no context for {section_role!r}.")


def _accepts(model: type[BaseModel], payload: Mapping[str, object]) -> bool:
    try:
        model.model_validate(payload)
    except ValidationError:
        return False
    return True


def _rejects(model: type[BaseModel], payload: Mapping[str, object]) -> bool:
    return not _accepts(model, payload)


def _full_union_omitted_kind(model: type[BaseModel]) -> bool:
    """Record actual top-level union behavior for an omitted track tag."""
    payload = {
        "title": "Section",
        "source_candidate": "source-1",
        "tracks": [
            {
                "role": "combo",
                "title": "Combo",
                "bindings": [
                    {
                        "kind": "curve",
                        "semantic_id": "curve",
                        "channel": "CURVE",
                        "scale": {"minimum": 0, "maximum": 1},
                    }
                ],
            }
        ],
    }
    return _accepts(model, payload)


def _without_kind(branch: Mapping[str, object]) -> dict[str, object]:
    result = copy.deepcopy(dict(branch))
    properties = result.get("properties")
    if isinstance(properties, dict):
        properties.pop("kind", None)
    required = result.get("required")
    if isinstance(required, list):
        result["required"] = sorted(item for item in required if item != "kind")
    return result


def _normalize_tag_difference(
    schema: Mapping[str, object], *, required: bool, default: bool
) -> dict[str, object]:
    result = copy.deepcopy(dict(schema))
    definitions = result.get("$defs")
    if isinstance(definitions, dict):
        for branch_name in ("NormalTrackDraftS", "ReferenceTrackDraftS", "ArrayTrackDraftS"):
            branch = definitions[branch_name]
            if default:
                branch["properties"]["kind"].pop("default", None)
            if required and "kind" not in branch["required"]:
                branch["required"].append("kind")
            branch["required"] = sorted(branch["required"])
    return result


def _track_refs(schema: Mapping[str, object]) -> object:
    return schema["properties"]["tracks"]["items"]["oneOf"]


def _discriminator_property(schema: Mapping[str, object]) -> object:
    return schema["properties"]["tracks"]["items"]["discriminator"]["propertyName"]


def _discriminator_mapping(schema: Mapping[str, object]) -> object:
    return schema["properties"]["tracks"]["items"]["discriminator"]["mapping"]


def _schema_diff(before: Mapping[str, object], after: Mapping[str, object]) -> dict[str, object]:
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
    return AttemptMetrics(**metrics.public_metadata())


def _normalized_output(value: BaseModel) -> str:
    return json.dumps(value.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def _sum_metric(metrics: Sequence[AttemptMetrics], field_name: str) -> int | float | None:
    values = [getattr(metric, field_name) for metric in metrics]
    present = [value for value in values if value is not None]
    return sum(present) if present else None


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _append_attempt_record(path: Path, attempt: RemediationAttemptEvidence) -> None:
    _append_record(path, "attempt", attempt)


def _append_record(path: Path, record_type: str, value: BaseModel) -> None:
    record = {"record_type": record_type, **value.model_dump(mode="json")}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
        handle.flush()


def _parse_args() -> argparse.Namespace:
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
        "--variant", choices=[item.value for item in RemediationVariant], required=True
    )
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
    summary = await run_remediation_stage(
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
    """Run one local llama.cpp remediation-validation stage."""
    import asyncio

    asyncio.run(_main_async(_parse_args()))


__all__ = [
    "BASELINE_SHA",
    "DEFAULT_SYSTEM_PROMPT",
    "R1",
    "RemediationAttemptEvidence",
    "RemediationSectionSummary",
    "RemediationVariant",
    "RemediationVariantSpec",
    "RemediationVariantSummary",
    "build_required_section_draft_s",
    "compiler_projection_equivalence",
    "golden_equivalence",
    "remediation_variant_specs",
    "response_model_for",
    "run_remediation_attempt",
    "run_remediation_section_attempts",
    "run_remediation_stage",
    "schema_artifact",
    "schema_comparison",
    "schema_sha256",
    "structural_invariant_audit",
    "structured_request",
    "system_prompt_sha256",
]


if __name__ == "__main__":
    main()
