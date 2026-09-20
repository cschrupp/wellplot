"""Deterministic compiler for typed semantic section drafts."""

from __future__ import annotations

from collections.abc import Mapping

from ...authoring_program.ids import IdAllocator
from ...model.authoring import (
    AuthoringDataSource,
    AuthoringDocumentSpec,
    AuthoringRasterSampleAxisSpec,
    AuthoringScale,
)
from ...model.intent import (
    AuthoringCurveBindingIntent,
    AuthoringDocumentIntent,
    AuthoringRasterBindingIntent,
    AuthoringSectionIntent,
    AuthoringTrackIntent,
)
from .enrichment import ResolvedSectionContext
from .section_semantics import (
    ArrayTrackSemanticDraft,
    CurveBindingSemanticDraft,
    RasterBindingSemanticDraft,
    SectionSemanticDraft,
    SemanticSampleAxis,
    SemanticScale,
    TrackSemanticDraft,
    validate_section_semantics,
)


def compile_section_semantics(
    draft: SectionSemanticDraft | Mapping[str, object],
    *,
    section_context: ResolvedSectionContext,
    document: AuthoringDocumentSpec,
) -> AuthoringDocumentIntent:
    """Validate and compile one typed draft into a sparse section intent.

    ``document`` is used only to seed host identity reservations. No document
    mutation service or renderer is involved in this compiler.
    """
    if not isinstance(document, AuthoringDocumentSpec):
        raise TypeError("Typed section compilation requires an AuthoringDocumentSpec.")
    validated = validate_section_semantics(draft, section_context=section_context)
    source = next(
        candidate
        for candidate in section_context.sources
        if candidate.candidate_id == validated.source_candidate
    )
    allocator = _allocator_for(document)
    section_id = allocator.allocate_section(validated.title)
    tracks = [
        _compile_track(
            track,
            allocator=allocator,
            section_id=section_id,
        )
        for track in validated.tracks
    ]
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


def _allocator_for(document: object) -> IdAllocator:
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
) -> AuthoringTrackIntent:
    """Allocate one canonical track and preserve its ordered semantic children."""
    track_id = allocator.allocate_track(section_id, f"track-{track.semantic_id}")
    bindings = [
        _compile_binding(
            binding,
            allocator=allocator,
            section_id=section_id,
            track_id=track_id,
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
    if isinstance(track, ArrayTrackSemanticDraft) or track.x_scale is not None:
        fields["x_scale"] = _compile_scale(track.x_scale)
    return AuthoringTrackIntent(**fields)


def _compile_binding(
    binding: CurveBindingSemanticDraft | RasterBindingSemanticDraft,
    *,
    allocator: IdAllocator,
    section_id: str,
    track_id: str,
) -> AuthoringCurveBindingIntent | AuthoringRasterBindingIntent:
    """Allocate one binding and preserve its channel, kind, and order."""
    binding_id = allocator.allocate_binding(
        section_id,
        track_id,
        id_hint=f"binding-{binding.semantic_id}",
    )
    common = {
        "binding_id": binding_id,
        "section_id": section_id,
        "track_id": track_id,
        "channel": binding.channel,
    }
    if isinstance(binding, CurveBindingSemanticDraft):
        if binding.scale is not None:
            common["scale"] = _compile_scale(binding.scale)
        return AuthoringCurveBindingIntent(kind="curve", **common)

    if binding.profile is not None:
        common["profile"] = binding.profile
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


__all__ = ["compile_section_semantics"]
