"""Static semantic models for the typed Code Mode section worker."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enrichment import ResolvedSectionContext


class _SemanticModel(BaseModel):
    """Strict immutable base for transient worker semantic models."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class SemanticScaleKind(StrEnum):
    """Scale transforms exposed by the typed section contract."""

    LINEAR = "linear"
    LOG = "log"
    TANGENTIAL = "tangential"


class SemanticRasterProfile(StrEnum):
    """Raster profiles exposed by the typed section contract."""

    GENERIC = "generic"
    VDL = "vdl"
    WAVEFORM = "waveform"


class SemanticScale(_SemanticModel):
    """One explicit worker-owned numeric scale."""

    kind: SemanticScaleKind = SemanticScaleKind.LINEAR
    minimum: float
    maximum: float
    reverse: bool = False
    unit: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_bounds(self) -> SemanticScale:
        """Reuse canonical scale bounds without adding presentation defaults."""
        if self.minimum == self.maximum:
            raise ValueError("Scale minimum and maximum must differ.")
        if self.kind is SemanticScaleKind.LOG and (self.minimum <= 0 or self.maximum <= 0):
            raise ValueError("Logarithmic scales require positive bounds.")
        return self


class SemanticSampleAxis(_SemanticModel):
    """Explicit raster sample-axis semantics."""

    unit: str | None = Field(default=None, min_length=1)
    source_origin: float | None = None
    source_step: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    tick_count: int | None = Field(default=None, ge=2)

    @model_validator(mode="after")
    def validate_pairs(self) -> SemanticSampleAxis:
        """Require complete source and display bound pairs."""
        if all(
            value is None
            for value in (
                self.unit,
                self.source_origin,
                self.source_step,
                self.minimum,
                self.maximum,
                self.tick_count,
            )
        ):
            raise ValueError("Sample-axis semantics must contain at least one value.")
        if (self.source_origin is None) != (self.source_step is None):
            raise ValueError("Sample-axis source_origin and source_step must be paired.")
        if self.source_step == 0:
            raise ValueError("Sample-axis source_step must be non-zero.")
        if (self.minimum is None) != (self.maximum is None):
            raise ValueError("Sample-axis minimum and maximum must be paired.")
        if self.minimum is not None and self.minimum == self.maximum:
            raise ValueError("Sample-axis minimum and maximum must differ.")
        return self


class CurveBindingSemanticDraft(_SemanticModel):
    """One ordered scalar binding; kind is optional because no union selects it."""

    kind: Literal["curve"] = "curve"
    semantic_id: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    scale: SemanticScale | None = None


class RasterBindingSemanticDraft(_SemanticModel):
    """One ordered array binding; kind is optional because no union selects it."""

    kind: Literal["raster"] = "raster"
    semantic_id: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    profile: SemanticRasterProfile | None = None
    sample_axis: SemanticSampleAxis | None = None


class NormalTrackSemanticDraft(_SemanticModel):
    """Normal track with scalar curve bindings only."""

    semantic_id: str = Field(min_length=1)
    kind: Literal["normal"]
    title: str = Field(min_length=1)
    x_scale: SemanticScale | None = None
    bindings: tuple[CurveBindingSemanticDraft, ...] = Field(min_length=1)


class ReferenceTrackSemanticDraft(_SemanticModel):
    """Reference track with scalar curve bindings only."""

    semantic_id: str = Field(min_length=1)
    kind: Literal["reference"]
    title: str = Field(min_length=1)
    x_scale: SemanticScale | None = None
    bindings: tuple[CurveBindingSemanticDraft, ...] = Field(min_length=1)


class ArrayTrackSemanticDraft(_SemanticModel):
    """Array track with raster bindings and a required x-scale."""

    semantic_id: str = Field(min_length=1)
    kind: Literal["array"]
    title: str = Field(min_length=1)
    x_scale: SemanticScale
    bindings: tuple[RasterBindingSemanticDraft, ...] = Field(min_length=1)


TrackSemanticDraft: TypeAlias = Annotated[
    NormalTrackSemanticDraft | ReferenceTrackSemanticDraft | ArrayTrackSemanticDraft,
    Field(discriminator="kind"),
]


class SectionSemanticDraft(_SemanticModel):
    """Transient semantic intent for one new section."""

    title: str = Field(min_length=1)
    source_candidate: str = Field(min_length=1)
    tracks: tuple[TrackSemanticDraft, ...] = Field(min_length=1)


class SectionSemanticErrorCode(StrEnum):
    """Stable context-validation failure categories."""

    REVISION_UNSUPPORTED = "revision_unsupported"
    SOURCE_CANDIDATE_MISSING = "source_candidate_missing"
    SOURCE_CANDIDATE_AMBIGUOUS = "source_candidate_ambiguous"
    CHANNEL_MISSING = "channel_missing"
    CHANNEL_AMBIGUOUS = "channel_ambiguous"
    CHANNEL_KIND_MISMATCH = "channel_kind_mismatch"
    DUPLICATE_TRACK_ID = "duplicate_track_semantic_id"
    DUPLICATE_BINDING_ID = "duplicate_binding_semantic_id"


class SectionSemanticValidationError(ValueError):
    """Deterministic failure while validating a draft against host context."""

    def __init__(self, code: SectionSemanticErrorCode, message: str) -> None:
        """Store a stable code without retaining host paths or raw exceptions."""
        self.code = code
        super().__init__(message)


def validate_section_semantics(
    draft: SectionSemanticDraft | Mapping[str, object],
    *,
    section_context: ResolvedSectionContext,
) -> SectionSemanticDraft:
    """Validate one structurally valid draft against its selected source context."""
    validated = _revalidate(draft)
    if section_context.section_id is not None:
        raise SectionSemanticValidationError(
            SectionSemanticErrorCode.REVISION_UNSUPPORTED,
            "Typed section compilation does not yet support existing-section revision.",
        )

    track_ids = [track.semantic_id for track in validated.tracks]
    if len(track_ids) != len(set(track_ids)):
        raise SectionSemanticValidationError(
            SectionSemanticErrorCode.DUPLICATE_TRACK_ID,
            "Track semantic IDs must be unique within one section.",
        )

    source_ids = [source.candidate_id for source in section_context.sources]
    if len(source_ids) != len(set(source_ids)):
        raise SectionSemanticValidationError(
            SectionSemanticErrorCode.SOURCE_CANDIDATE_AMBIGUOUS,
            "Section context contains duplicate source candidate IDs.",
        )

    matching_sources = [
        source
        for source in section_context.sources
        if source.candidate_id == validated.source_candidate
    ]
    if not matching_sources:
        raise SectionSemanticValidationError(
            SectionSemanticErrorCode.SOURCE_CANDIDATE_MISSING,
            "The selected source candidate is not available in section context.",
        )
    source = matching_sources[0]

    for track in validated.tracks:
        binding_ids = [binding.semantic_id for binding in track.bindings]
        if len(binding_ids) != len(set(binding_ids)):
            raise SectionSemanticValidationError(
                SectionSemanticErrorCode.DUPLICATE_BINDING_ID,
                f"Binding semantic IDs must be unique within track '{track.semantic_id}'.",
            )
        for binding in track.bindings:
            matching_channels = [
                channel for channel in source.channels if channel.mnemonic == binding.channel
            ]
            if not matching_channels:
                raise SectionSemanticValidationError(
                    SectionSemanticErrorCode.CHANNEL_MISSING,
                    f"Channel '{binding.channel}' is not available from the selected source.",
                )
            if len(matching_channels) > 1:
                raise SectionSemanticValidationError(
                    SectionSemanticErrorCode.CHANNEL_AMBIGUOUS,
                    f"Channel '{binding.channel}' is duplicated in the selected source.",
                )
            channel = matching_channels[0]
            expected_kind = "scalar" if binding.kind == "curve" else "array"
            if channel.kind != expected_kind:
                raise SectionSemanticValidationError(
                    SectionSemanticErrorCode.CHANNEL_KIND_MISMATCH,
                    f"Channel '{binding.channel}' must be {expected_kind} for a "
                    f"{binding.kind} binding.",
                )
    return validated


def _revalidate(
    draft: SectionSemanticDraft | Mapping[str, object],
) -> SectionSemanticDraft:
    """Revalidate mappings and model instances through the static response model."""
    raw = draft.model_dump(mode="json") if isinstance(draft, SectionSemanticDraft) else draft
    return SectionSemanticDraft.model_validate(raw)


__all__ = [
    "ArrayTrackSemanticDraft",
    "CurveBindingSemanticDraft",
    "NormalTrackSemanticDraft",
    "RasterBindingSemanticDraft",
    "ReferenceTrackSemanticDraft",
    "SectionSemanticDraft",
    "SectionSemanticErrorCode",
    "SectionSemanticValidationError",
    "SemanticRasterProfile",
    "SemanticSampleAxis",
    "SemanticScale",
    "SemanticScaleKind",
    "TrackSemanticDraft",
    "validate_section_semantics",
]
