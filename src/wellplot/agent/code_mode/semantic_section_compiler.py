"""Deterministic compiler for typed semantic section drafts."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from ...model.authoring import (
    AuthoringDataSource,
    AuthoringDocumentSpec,
    AuthoringRasterColorbarSpec,
    AuthoringRasterSampleAxisSpec,
    AuthoringScale,
)
from ...model.intent import (
    AuthoringCurveBindingIntent,
    AuthoringDocumentIntent,
    AuthoringGridIntent,
    AuthoringRasterBindingIntent,
    AuthoringSectionIntent,
    AuthoringStyleIntent,
    AuthoringTrackIntent,
)
from ..identity import IdAllocator
from .enrichment import ResolvedSectionContext
from .section_semantics import (
    ArrayTrackSemanticDraft,
    CurveBindingSemanticDraft,
    RasterBindingSemanticDraft,
    SectionSemanticDraft,
    SemanticGrid,
    SemanticSampleAxis,
    SemanticScale,
    TrackSemanticDraft,
    validate_section_semantics,
)


class SectionSemanticCompilationErrorCode(StrEnum):
    """Stable failures raised while compiling a validated semantic draft."""

    SECTION_ID_HINT_INVALID = "section_id_hint_invalid"
    IDENTITY_ALLOCATION_FAILED = "identity_allocation_failed"


class SectionSemanticCompilationError(ValueError):
    """Safe deterministic failure at the semantic compiler boundary."""

    def __init__(self, code: SectionSemanticCompilationErrorCode, message: str) -> None:
        """Store a stable code without exposing substrate exceptions."""
        self.code = code
        super().__init__(message)


def compile_section_semantics(
    draft: SectionSemanticDraft | Mapping[str, object],
    *,
    section_context: ResolvedSectionContext,
    document: AuthoringDocumentSpec,
    section_id_hint: str,
    allocator: IdAllocator | None = None,
    allow_existing_section: bool = False,
) -> AuthoringDocumentIntent:
    """Validate and compile one typed draft into a sparse section intent.

    ``document`` is used only to seed host identity reservations. No document
    mutation service or renderer is involved in this compiler.
    """
    if not isinstance(document, AuthoringDocumentSpec):
        raise TypeError("Typed section compilation requires an AuthoringDocumentSpec.")
    if (
        not isinstance(section_id_hint, str)
        or not section_id_hint
        or section_id_hint != section_id_hint.strip()
    ):
        raise SectionSemanticCompilationError(
            SectionSemanticCompilationErrorCode.SECTION_ID_HINT_INVALID,
            "Host section_id_hint must be a non-empty trimmed string.",
        )
    validated = validate_section_semantics(
        draft,
        section_context=section_context,
        allow_existing_section=allow_existing_section,
    )
    source = next(
        candidate
        for candidate in section_context.sources
        if candidate.candidate_id == validated.source_candidate
    )
    try:
        host_allocator = allocator if allocator is not None else _allocator_for(document)
        section_id = section_context.section_id or host_allocator.allocate_section(section_id_hint)
        existing_tracks = {
            track.id: track
            for section in document.sections
            if section.id == section_id
            for track in section.tracks
        }
        used_track_ids: set[str] = set()
        tracks = []
        for track in validated.tracks:
            compiled_track = _compile_track(
                track,
                allocator=host_allocator,
                section_id=section_id,
                existing_tracks=existing_tracks,
                used_track_ids=used_track_ids,
                section_context=section_context,
            )
            tracks.append(compiled_track)
            used_track_ids.add(compiled_track.track_id)
        section = AuthoringSectionIntent(
            section_id=section_id,
            title=validated.title,
            data_source=AuthoringDataSource(
                source_path=source.canonical_path,
                source_format=source.source_format,
            ),
            tracks=tracks,
        )
        return AuthoringDocumentIntent(sections=[section])
    except SectionSemanticCompilationError:
        raise
    except Exception:
        raise SectionSemanticCompilationError(
            SectionSemanticCompilationErrorCode.IDENTITY_ALLOCATION_FAILED,
            "Host identity allocation failed during semantic compilation.",
        ) from None


def _allocator_for(document: AuthoringDocumentSpec) -> IdAllocator:
    """Seed host identity allocation from the existing canonical document."""
    sections = document.sections
    return IdAllocator(
        section_ids=[section.id for section in sections],
        track_ids_by_section={
            section.id: [track.id for track in section.tracks] for section in sections
        },
        binding_ids=[
            binding.binding_id
            for section in sections
            for track in section.tracks
            for binding in getattr(track, "bindings", ())
        ],
        leaf_ids=[
            leaf_id
            for section in sections
            for track in section.tracks
            for leaf_id in _track_leaf_ids(track)
        ],
    )


def _track_leaf_ids(track: object) -> tuple[str, ...]:
    """Reserve existing fill and annotation IDs during new-section allocation."""
    fill_ids = tuple(
        fill.fill_id for fill in getattr(track, "fills", ()) if fill.fill_id is not None
    )
    annotation_ids = tuple(
        annotation.annotation_id
        for annotation in getattr(track, "annotations", ())
        if annotation.annotation_id is not None
    )
    return fill_ids + annotation_ids


def _compile_track(
    track: TrackSemanticDraft,
    *,
    allocator: IdAllocator,
    section_id: str,
    existing_tracks: dict[str, object],
    used_track_ids: set[str],
    section_context: ResolvedSectionContext,
) -> AuthoringTrackIntent:
    """Allocate one canonical track and preserve its ordered semantic children."""
    existing = next(
        (
            candidate
            for candidate in existing_tracks.values()
            if str(getattr(candidate, "id", "")) not in used_track_ids
            if str(getattr(candidate, "id", "")) == track.semantic_id
            and getattr(candidate, "kind", None) == track.kind
        ),
        None,
    )
    if existing is None:
        existing = next(
            (
                candidate
                for candidate in existing_tracks.values()
                if str(getattr(candidate, "id", "")) not in used_track_ids
                if getattr(candidate, "kind", None) == track.kind
                and str(getattr(candidate, "title", "")).casefold() == track.title.casefold()
            ),
            None,
        )
    track_id = (
        str(existing.id)
        if existing is not None
        else allocator.allocate_track(section_id, track.semantic_id)
    )
    bindings = [
        _compile_binding(
            binding,
            allocator=allocator,
            section_id=section_id,
            track_id=track_id,
            existing_bindings=list(getattr(existing, "bindings", ())),
            section_context=section_context,
        )
        for binding in track.bindings
    ]
    fields: dict[str, object] = {
        "track_id": track_id,
        "section_id": section_id,
        "title": track.title,
        "kind": track.kind,
        "bindings": bindings,
    }
    if track.width_mm is not None:
        fields["width_mm"] = track.width_mm
    if track.grid is not None:
        fields["grid"] = _compile_grid(track.grid)
    if isinstance(track, ArrayTrackSemanticDraft) or track.x_scale is not None:
        fields["x_scale"] = _compile_scale(track.x_scale)
    return AuthoringTrackIntent(**fields)


def _compile_binding(
    binding: CurveBindingSemanticDraft | RasterBindingSemanticDraft,
    *,
    allocator: IdAllocator,
    section_id: str,
    track_id: str,
    existing_bindings: list[object],
    section_context: ResolvedSectionContext,
) -> AuthoringCurveBindingIntent | AuthoringRasterBindingIntent:
    """Allocate one binding and preserve its channel, kind, and order."""
    _require_channel(
        binding.channel,
        section_context,
        expected_kind="array" if isinstance(binding, RasterBindingSemanticDraft) else "scalar",
    )
    existing = next(
        (
            candidate
            for candidate in existing_bindings
            if candidate.channel == binding.channel
            and (binding.label is None or candidate.label == binding.label)
        ),
        None,
    )
    binding_id = (
        str(existing.binding_id)
        if existing is not None
        else allocator.allocate_binding(
            section_id,
            track_id,
            id_hint=f"binding-{binding.semantic_id}",
            channel=binding.channel,
        )
    )
    common = {
        "binding_id": binding_id,
        "section_id": section_id,
        "track_id": track_id,
        "channel": binding.channel,
    }
    if binding.label is not None:
        common["label"] = binding.label
    if isinstance(binding, CurveBindingSemanticDraft) and binding.style is not None:
        common["style"] = binding.style
    if isinstance(binding, CurveBindingSemanticDraft):
        if binding.scale is not None:
            common["scale"] = _compile_scale(binding.scale)
        return AuthoringCurveBindingIntent(kind="curve", **common)

    if binding.profile is not None:
        common["profile"] = binding.profile
    if binding.colormap is not None:
        common["style"] = AuthoringStyleIntent(colormap=binding.colormap)
    if binding.alpha is not None:
        common["alpha"] = binding.alpha
    if any(
        value is not None
        for value in (
            binding.colorbar_enabled,
            binding.colorbar_label,
            binding.colorbar_position,
        )
    ):
        common["colorbar"] = AuthoringRasterColorbarSpec(
            enabled=bool(binding.colorbar_enabled),
            label=binding.colorbar_label,
            position=binding.colorbar_position or "right",
        )
    if binding.sample_axis is not None:
        common["sample_axis"] = _compile_sample_axis(binding.sample_axis)
    return AuthoringRasterBindingIntent(kind="raster", **common)


def _compile_scale(scale: SemanticScale) -> AuthoringScale:
    """Translate one explicit semantic scale without adding presentation policy."""
    return AuthoringScale(
        kind=scale.kind,
        minimum=scale.minimum,
        maximum=scale.maximum,
        reverse=scale.reverse,
        unit=scale.unit,
    )


def _compile_grid(grid: SemanticGrid) -> AuthoringGridIntent:
    """Translate explicit semantic grid visibility into a sparse intent."""
    values: dict[str, object] = {}
    if grid.vertical_main_visible is not None:
        values["vertical_main_visible"] = grid.vertical_main_visible
    if grid.vertical_secondary_visible is not None:
        values["vertical_secondary_visible"] = grid.vertical_secondary_visible
    return AuthoringGridIntent(**values)


def _compile_sample_axis(axis: SemanticSampleAxis) -> AuthoringRasterSampleAxisSpec:
    """Translate an explicit sample axis into the canonical raster contract."""
    return AuthoringRasterSampleAxisSpec(
        enabled=True,
        unit=axis.unit,
        source_origin=axis.source_origin,
        source_step=axis.source_step,
        minimum=axis.minimum,
        maximum=axis.maximum,
        tick_count=axis.tick_count if axis.tick_count is not None else 5,
    )


def _require_channel(
    channel: str,
    context: ResolvedSectionContext,
    *,
    expected_kind: str,
) -> None:
    """Require an exact inspected channel without alias substitution."""
    available = [
        item for source in context.sources for item in source.channels if item.mnemonic == channel
    ]
    if not available:
        raise SectionSemanticCompilationError(
            SectionSemanticCompilationErrorCode.IDENTITY_ALLOCATION_FAILED,
            f"No source channel matches '{channel}'.",
        )
    if not any(item.kind == expected_kind for item in available):
        raise SectionSemanticCompilationError(
            SectionSemanticCompilationErrorCode.IDENTITY_ALLOCATION_FAILED,
            f"Source channel '{channel}' is not {expected_kind}.",
        )


__all__ = [
    "SectionSemanticCompilationError",
    "SectionSemanticCompilationErrorCode",
    "compile_section_semantics",
]
