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
RESPONSE_SCHEMA_SHA256 = "93f1b7d26f1196a1105b733bc13a8de784da19f44eaaa990989d59abaf9fa2d4"
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


class TypedSectionRepresentabilityError(ValueError):
    """A selected capability cannot be expressed by the initial typed contract."""

    code: Literal["representability_gap"] = "representability_gap"

    def __init__(self, message: str) -> None:
        """Store a stable safe message."""
        super().__init__(message)


class TypedSectionWorkerErrorCode(StrEnum):
    """Stable preflight failures owned by the typed worker boundary."""

    REVISION_UNSUPPORTED = "revision_unsupported"


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
        worker_input = build_typed_section_input(
            task,
            section_context=section_context,
            registry=self.registry,
        )
        serialized = serialize_typed_section_input(worker_input)
        schema_digest = response_schema_sha256()
        generated = await self.backend.generate_structured(
            StructuredGenerationRequest(
                system_prompt=TYPED_SECTION_SYSTEM_PROMPT,
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
            system_prompt_sha256=_sha256(TYPED_SECTION_SYSTEM_PROMPT),
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
    "TYPED_SECTION_SYSTEM_PROMPT",
    "TypedSectionCapabilityInput",
    "TypedSectionChannelInput",
    "TypedSectionCompiler",
    "TypedSectionGenerationResult",
    "TypedSectionRepresentabilityError",
    "TypedSectionSourceInput",
    "TypedSectionTaskInput",
    "TypedSectionWorkerInput",
    "TypedSectionWorkerError",
    "TypedSectionWorkerErrorCode",
    "build_typed_section_input",
    "response_schema_sha256",
    "serialize_typed_section_input",
]
