"""Provider-facing typed section shadow worker for CM-56."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ...capabilities import CapabilityRegistry
from ...capabilities.base import CapabilitySpec
from ...model.authoring import AuthoringDocumentSpec
from ...model.intent import AuthoringDocumentIntent
from ..providers.base import ModelBackendProtocol, ProviderMetrics, StructuredGenerationRequest
from .enrichment import ResolvedSectionContext
from .planner import CompilationMode, SectionTask
from .section_semantics import SectionSemanticDraft, validate_section_semantics
from .semantic_section_compiler import compile_section_semantics

TYPED_SECTION_INPUT_VERSION = "cm56.typed-section-input.v1"
TYPED_SECTION_PROVIDER_INPUT_VERSION = "cm57.typed-section-provider-input.v1"
RESPONSE_SCHEMA_SHA256 = "93f1b7d26f1196a1105b733bc13a8de784da19f44eaaa990989d59abaf9fa2d4"
TYPED_SECTION_SEMANTIC_METADATA_MAX_BYTES = 8192
TYPED_SECTION_SEMANTIC_TARGET_PATHS = frozenset(
    {
        "binding.profile",
        "binding.sample_axis.unit",
        "binding.sample_axis.source_origin",
        "binding.sample_axis.source_step",
        "binding.sample_axis.tick_count",
    }
)
TYPED_SECTION_CAPABILITIES = frozenset(
    {
        "section.log_plot",
        "track.normal",
        "track.reference",
        "track.array",
        "binding.curve",
        "binding.raster",
    }
)

TYPED_SECTION_SYSTEM_PROMPT = """You are the Wellplot typed section semantic worker.

Return exactly one SectionSemanticDraft that matches the supplied section task,
selected capabilities, and bounded source/channel context. Use only fields
allowed by the SectionSemanticDraft schema.

Reconstruct one new section. Use only source candidate IDs supplied in the
input. For bindings, output only exact channel mnemonics supplied in the input;
aliases are recognition hints only.

Preserve explicit scientific semantics such as track kind, track and binding
order, scale kind and bounds, reverse direction, raster profile, and sample-axis
values. Multiple bindings may intentionally reference the same channel and must
remain distinct through different local semantic IDs.

Semantic IDs are local descriptive identifiers only. Do not generate canonical
Wellplot IDs, filesystem paths, SDK calls, programs, renderer settings, styles,
widths, grids, or unsupported fields. Do not invent semantics that were not
requested."""

REQUEST_INSTRUCTION = (
    "\n\nInput authority:\n"
    "The authoritative_request field contains the user's original request and is "
    "the authoritative source of requested semantics. The section task provides "
    "scoped decomposition and routing. The bounded source/channel context provides "
    "available inputs. Preserve explicit semantics requested by the authoritative "
    "request, but do not invent semantics absent from it."
)
SEMANTIC_INSTRUCTION = (
    "\n\nCapability semantic metadata:\n"
    "The semantic_contracts field contains capability-specific WellPlot meanings "
    "that require explicit clarification. Use those mappings where applicable. "
    "For semantics not documented there, interpret the section task and normal "
    "SectionSemanticDraft schema without adding extra semantics."
)

_POSIX_PATH_RE = re.compile(r"(?<![A-Za-z0-9_])/(?:[^\s\"'<>]+/)+[^\s\"'<>]+")
_WINDOWS_PATH_RE = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/][^\s\"'<>]+")


class _TypedInputModel(BaseModel):
    """Strict immutable provider-input model."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class TypedSectionTaskInput(_TypedInputModel):
    """Planner-owned semantic task fields exposed to the typed worker."""

    goal: str = Field(min_length=1)
    capability_ids: tuple[str, ...] = Field(min_length=1)
    source_hints: tuple[str, ...] = ()
    requirements: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()


class TypedSectionCapabilityInput(_TypedInputModel):
    """Selected generic capability metadata safe for provider use."""

    id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    description: str = Field(min_length=1)
    allowed_parents: tuple[str, ...] = ()
    source_kinds: tuple[str, ...] = ()
    worker_hints: tuple[str, ...] = ()


class TypedSectionChannelInput(_TypedInputModel):
    """One exact channel plus explicitly labeled recognition aliases."""

    mnemonic: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    unit: str | None = None
    description: str = ""
    recognition_aliases: tuple[str, ...] = ()


class TypedSectionSourceInput(_TypedInputModel):
    """One opaque source candidate and its bounded channel inventory."""

    candidate_id: str = Field(min_length=1)
    channels: tuple[TypedSectionChannelInput, ...] = ()


class TypedSectionWorkerInput(_TypedInputModel):
    """Complete path-free provider payload for one section task."""

    section_task: TypedSectionTaskInput
    capabilities: tuple[TypedSectionCapabilityInput, ...]
    sources: tuple[TypedSectionSourceInput, ...]


class TypedSectionSemanticTargetInput(_TypedInputModel):
    """One provider-safe semantic target and its interpretation cue."""

    path: str = Field(min_length=1)
    value_cue: str = Field(min_length=1)


class TypedSectionSemanticMappingInput(_TypedInputModel):
    """One provider-safe capability semantic mapping."""

    concept: str = Field(min_length=1)
    language_patterns: tuple[str, ...] = Field(min_length=1)
    targets: tuple[TypedSectionSemanticTargetInput, ...] = Field(min_length=1)


class TypedSectionSemanticContractInput(_TypedInputModel):
    """One provider-safe semantic contract projected from a capability spec."""

    capability_id: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    mappings: tuple[TypedSectionSemanticMappingInput, ...] = ()
    distinctions: tuple[str, ...] = ()


class TypedSectionProviderInput(TypedSectionWorkerInput):
    """Validated production provider payload extending the historical base input."""

    authoritative_request: str = Field(min_length=1)
    semantic_contracts: tuple[TypedSectionSemanticContractInput, ...] | None = None


class TypedSectionRepresentabilityError(ValueError):
    """A selected capability cannot be expressed by the initial typed contract."""

    code: Literal["representability_gap"] = "representability_gap"

    def __init__(self, message: str) -> None:
        """Store a stable safe message."""
        super().__init__(message)


class TypedSectionWorkerErrorCode(StrEnum):
    """Stable preflight failures owned by the typed worker boundary."""

    REVISION_UNSUPPORTED = "revision_unsupported"
    INPUT_CONTRACT_INVALID = "input_contract_invalid"


class TypedSectionWorkerError(ValueError):
    """A deterministic typed-worker preflight failure."""

    def __init__(self, code: TypedSectionWorkerErrorCode, message: str) -> None:
        """Store a stable error code without provider or host details."""
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class TypedSectionGenerationResult:
    """Validated typed draft and sparse intent produced by one provider call."""

    draft: SectionSemanticDraft
    intent_fragment: AuthoringDocumentIntent
    metrics: ProviderMetrics
    provider_input_sha256: str
    provider_input_chars: int
    system_prompt_sha256: str
    response_schema_sha256: str


@dataclass(frozen=True, slots=True)
class TypedSectionCompiler:
    """Generate one typed semantic section without graph or fallback behavior."""

    backend: ModelBackendProtocol
    registry: CapabilityRegistry

    async def compile(
        self,
        *,
        task: SectionTask,
        section_context: ResolvedSectionContext,
        document: AuthoringDocumentSpec,
        section_id_hint: str,
        authoritative_request: str,
        timeout_seconds: float,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        mode: CompilationMode = "reconstruct",
    ) -> TypedSectionGenerationResult:
        """Run one structured generation, validation, and deterministic compilation."""
        if mode != "reconstruct" or section_context.section_id is not None:
            raise TypedSectionWorkerError(
                TypedSectionWorkerErrorCode.REVISION_UNSUPPORTED,
                "Typed section shadow compilation supports reconstruction only.",
            )
        _validate_schema_digest()
        _validate_representability(task, self.registry)
        worker_input = build_typed_section_provider_input(
            task,
            authoritative_request=authoritative_request,
            section_context=section_context,
            registry=self.registry,
        )
        serialized = serialize_typed_section_provider_input(worker_input)
        schema_digest = response_schema_sha256()
        system_prompt = build_typed_section_system_prompt(
            has_semantic_contracts=bool(worker_input.semantic_contracts)
        )
        generated = await self.backend.generate_structured(
            StructuredGenerationRequest(
                system_prompt=system_prompt,
                user_prompt=serialized,
                timeout_seconds=timeout_seconds,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            ),
            response_model=SectionSemanticDraft,
        )
        draft = SectionSemanticDraft.model_validate(generated.value)
        validate_section_semantics(draft, section_context=section_context)
        intent = compile_section_semantics(
            draft,
            section_context=section_context,
            document=document,
            section_id_hint=section_id_hint,
        )
        return TypedSectionGenerationResult(
            draft=draft,
            intent_fragment=intent,
            metrics=generated.metrics,
            provider_input_sha256=_sha256(serialized),
            provider_input_chars=len(serialized),
            system_prompt_sha256=_sha256(system_prompt),
            response_schema_sha256=schema_digest,
        )


def build_typed_section_input(
    task: SectionTask,
    *,
    section_context: ResolvedSectionContext,
    registry: CapabilityRegistry,
) -> TypedSectionWorkerInput:
    """Project existing task/context contracts into a redacted worker payload."""
    _validate_representability(task, registry)
    task_input = TypedSectionTaskInput(
        goal=_safe_text(task.goal),
        capability_ids=tuple(_safe_text(value) for value in task.capability_ids),
        source_hints=tuple(_safe_text(value) for value in task.source_hints),
        requirements=tuple(_safe_text(value) for value in task.requirements),
        constraints=tuple(_safe_text(value) for value in task.constraints),
    )
    capabilities = tuple(
        TypedSectionCapabilityInput(
            id=_safe_text(spec.capability_id),
            category=_safe_text(spec.category),
            description=_safe_text(spec.description),
            allowed_parents=tuple(_safe_text(value) for value in spec.allowed_parents),
            source_kinds=tuple(_safe_text(value) for value in spec.source_kinds),
            worker_hints=tuple(_safe_text(value) for value in spec.worker_hints),
        )
        for spec in _selected_specs(task, registry)
    )
    sources = tuple(
        TypedSectionSourceInput(
            candidate_id=_safe_text(source.candidate_id),
            channels=tuple(
                TypedSectionChannelInput(
                    mnemonic=_safe_text(channel.mnemonic),
                    kind=_safe_text(channel.kind),
                    unit=_safe_optional_text(channel.unit),
                    description=_safe_text(channel.description),
                    recognition_aliases=tuple(_safe_text(alias) for alias in channel.aliases),
                )
                for channel in source.channels
            ),
        )
        for source in section_context.sources
    )
    return TypedSectionWorkerInput(
        section_task=task_input,
        capabilities=capabilities,
        sources=sources,
    )


def serialize_typed_section_input(value: TypedSectionWorkerInput) -> str:
    """Serialize one provider payload deterministically and compactly."""
    return json.dumps(
        value.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def build_typed_section_provider_input(
    task: SectionTask,
    *,
    authoritative_request: str,
    section_context: ResolvedSectionContext,
    registry: CapabilityRegistry,
) -> TypedSectionProviderInput:
    """Build the validated RS provider contract without changing the base input."""
    base = build_typed_section_input(
        task,
        section_context=section_context,
        registry=registry,
    )
    if not isinstance(authoritative_request, str) or not authoritative_request.strip():
        raise TypedSectionWorkerError(
            TypedSectionWorkerErrorCode.INPUT_CONTRACT_INVALID,
            "The authoritative request must be a non-empty string.",
        )
    safe_request = _safe_text(authoritative_request)
    contracts = _project_semantic_metadata(_selected_specs(task, registry))
    return TypedSectionProviderInput(
        section_task=base.section_task,
        capabilities=base.capabilities,
        sources=base.sources,
        authoritative_request=safe_request,
        semantic_contracts=contracts or None,
    )


def serialize_typed_section_provider_input(value: TypedSectionProviderInput) -> str:
    """Serialize the provider contract, omitting only absent semantic contracts."""
    payload = value.model_dump(mode="json")
    if value.semantic_contracts is None:
        payload.pop("semantic_contracts", None)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def build_typed_section_system_prompt(*, has_semantic_contracts: bool) -> str:
    """Compose the frozen production prompt from applicable provider factors."""
    prompt = TYPED_SECTION_SYSTEM_PROMPT + REQUEST_INSTRUCTION
    if has_semantic_contracts:
        prompt += SEMANTIC_INSTRUCTION
    return prompt


def _project_semantic_metadata(
    specs: tuple[CapabilitySpec, ...],
) -> tuple[TypedSectionSemanticContractInput, ...]:
    """Project selected capability metadata into the typed worker vocabulary."""
    contracts: list[TypedSectionSemanticContractInput] = []
    seen: set[str] = set()
    for spec in specs:
        if spec.capability_id in seen:
            continue
        seen.add(spec.capability_id)
        metadata = spec.semantic_metadata
        if metadata is None:
            continue
        mappings: list[TypedSectionSemanticMappingInput] = []
        for mapping in metadata.mappings:
            targets: list[TypedSectionSemanticTargetInput] = []
            for path, value_cue in mapping.targets:
                if path not in TYPED_SECTION_SEMANTIC_TARGET_PATHS:
                    raise TypedSectionWorkerError(
                        TypedSectionWorkerErrorCode.INPUT_CONTRACT_INVALID,
                        "Capability semantic metadata targets an unsupported typed field.",
                    )
                targets.append(TypedSectionSemanticTargetInput(path=path, value_cue=value_cue))
            mappings.append(
                TypedSectionSemanticMappingInput(
                    concept=mapping.concept,
                    language_patterns=mapping.language_patterns,
                    targets=tuple(targets),
                )
            )
        contracts.append(
            TypedSectionSemanticContractInput(
                capability_id=spec.capability_id,
                purpose=metadata.purpose,
                mappings=tuple(mappings),
                distinctions=metadata.distinctions,
            )
        )
    serialized = json.dumps(
        [contract.model_dump(mode="json") for contract in contracts],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    if len(serialized.encode("utf-8")) > TYPED_SECTION_SEMANTIC_METADATA_MAX_BYTES:
        raise TypedSectionWorkerError(
            TypedSectionWorkerErrorCode.INPUT_CONTRACT_INVALID,
            "Capability semantic metadata exceeds the typed worker size limit.",
        )
    return tuple(contracts)


def response_schema_sha256() -> str:
    """Return the canonical digest of the static production response schema."""
    schema = SectionSemanticDraft.model_json_schema()
    canonical = json.dumps(schema, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return _sha256(canonical)


def _validate_schema_digest() -> None:
    """Fail before provider use if CM-55's response schema changed."""
    actual = response_schema_sha256()
    if actual != RESPONSE_SCHEMA_SHA256:
        raise RuntimeError("CM-55 SectionSemanticDraft schema digest changed before CM-56.")


def _validate_representability(task: SectionTask, registry: CapabilityRegistry) -> None:
    """Reject unsupported selected capabilities before structured generation."""
    for spec in _selected_specs(task, registry):
        if spec.capability_id not in TYPED_SECTION_CAPABILITIES:
            raise TypedSectionRepresentabilityError(
                f"Capability {spec.capability_id!r} is outside the CM-55 typed section contract."
            )


def _selected_specs(task: SectionTask, registry: CapabilityRegistry) -> tuple[CapabilitySpec, ...]:
    """Resolve canonical selected capability descriptors without aliases."""
    specs: list[CapabilitySpec] = []
    for capability_id in task.capability_ids:
        try:
            spec = registry.get(capability_id)
        except KeyError as exc:
            raise TypedSectionRepresentabilityError(
                "Typed section capabilities must use registered identifiers."
            ) from exc
        if spec.capability_id != capability_id:
            raise TypedSectionRepresentabilityError(
                "Typed section capabilities must use canonical identifiers."
            )
        specs.append(spec)
    return tuple(specs)


def _safe_text(value: str) -> str:
    """Redact path-shaped planner text without changing ordinary semantics."""
    return _WINDOWS_PATH_RE.sub("[redacted-path]", _POSIX_PATH_RE.sub("[redacted-path]", value))


def _safe_optional_text(value: str | None) -> str | None:
    """Redact optional text while preserving an absent value."""
    return None if value is None else _safe_text(value)


def _sha256(value: str) -> str:
    """Hash UTF-8 text with the experiment's stable digest convention."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = [
    "RESPONSE_SCHEMA_SHA256",
    "TYPED_SECTION_CAPABILITIES",
    "TYPED_SECTION_INPUT_VERSION",
    "TYPED_SECTION_PROVIDER_INPUT_VERSION",
    "TYPED_SECTION_SEMANTIC_METADATA_MAX_BYTES",
    "TYPED_SECTION_SEMANTIC_TARGET_PATHS",
    "TYPED_SECTION_SYSTEM_PROMPT",
    "TypedSectionCapabilityInput",
    "TypedSectionChannelInput",
    "TypedSectionCompiler",
    "TypedSectionGenerationResult",
    "TypedSectionProviderInput",
    "TypedSectionRepresentabilityError",
    "TypedSectionSemanticContractInput",
    "TypedSectionSemanticMappingInput",
    "TypedSectionSemanticTargetInput",
    "TypedSectionSourceInput",
    "TypedSectionTaskInput",
    "TypedSectionWorkerInput",
    "TypedSectionWorkerError",
    "TypedSectionWorkerErrorCode",
    "build_typed_section_input",
    "build_typed_section_provider_input",
    "build_typed_section_system_prompt",
    "response_schema_sha256",
    "serialize_typed_section_input",
    "serialize_typed_section_provider_input",
]
