"""Canonical provider-facing semantic actions and deterministic lowering."""

from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from ...model.authoring import AuthoringScale
from ...model.intent import (
    AuthoringCurveBindingIntent,
    AuthoringDocumentIntent,
    AuthoringFillIntent,
    AuthoringSectionIntent,
    AuthoringTrackIntent,
)
from ..identity import IdAllocator
from .enrichment import ExistingCurveContext, ResolvedSectionContext
from .section_semantics import SectionSemanticDraft, SemanticScale, TrackSemanticDraft
from .semantic_section_compiler import compile_section_semantics


class _SemanticActionModel(BaseModel):
    """Strict immutable base for provider-facing semantic actions."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class ExistingCurveSelector(_SemanticActionModel):
    """Request-local existing-curve identity; canonical IDs stay host-owned."""

    handle: str = Field(min_length=1)


class BetweenCurvesFill(_SemanticActionModel):
    """Fill between two request-local curve handles."""

    kind: Literal["between_curves"]
    semantic_id: str = Field(min_length=1)
    target_binding: str = Field(min_length=1)
    other_binding: str = Field(min_length=1)
    color: str | None = Field(default=None, min_length=1)
    alpha: float | None = Field(default=None, ge=0, le=1)


class BetweenInstancesFill(_SemanticActionModel):
    """Fill between two instances of a curve."""

    kind: Literal["between_instances"]
    semantic_id: str = Field(min_length=1)
    target_binding: str = Field(min_length=1)
    other_binding: str = Field(min_length=1)
    color: str | None = Field(default=None, min_length=1)
    alpha: float | None = Field(default=None, ge=0, le=1)


class LimitFill(_SemanticActionModel):
    """Fill one request-local curve to a lower or upper limit."""

    kind: Literal["to_lower_limit", "to_upper_limit"]
    semantic_id: str = Field(min_length=1)
    target_binding: str = Field(min_length=1)
    color: str | None = Field(default=None, min_length=1)
    alpha: float | None = Field(default=None, ge=0, le=1)


class BaselineSplitFill(_SemanticActionModel):
    """Fill one request-local curve around an explicit baseline."""

    kind: Literal["baseline_split"]
    semantic_id: str = Field(min_length=1)
    target_binding: str = Field(min_length=1)
    baseline: float
    color: str | None = Field(default=None, min_length=1)
    alpha: float | None = Field(default=None, ge=0, le=1)


FillSemanticDraft: TypeAlias = Annotated[
    BetweenCurvesFill | BetweenInstancesFill | LimitFill | BaselineSplitFill,
    Field(discriminator="kind"),
]


class ReconstructSectionAction(_SemanticActionModel):
    """Construct one new section from the canonical CM semantic vocabulary."""

    action: Literal["reconstruct"]
    section: SectionSemanticDraft


class UpdateCurveScaleAction(_SemanticActionModel):
    """Update one grounded existing curve scale."""

    action: Literal["update_curve_scale"]
    target: ExistingCurveSelector
    scale: SemanticScale


class AddTrackAction(_SemanticActionModel):
    """Add one track and its grounded semantic bindings."""

    action: Literal["add_track"]
    track: TrackSemanticDraft


class AddFillAction(_SemanticActionModel):
    """Add one bounded fill relation to a grounded existing track."""

    action: Literal["add_fill"]
    target: ExistingCurveSelector
    fill: FillSemanticDraft


SectionSemanticAction: TypeAlias = Annotated[
    ReconstructSectionAction | UpdateCurveScaleAction | AddTrackAction | AddFillAction,
    Field(discriminator="action"),
]


class SemanticActionError(ValueError):
    """Safe deterministic failure while lowering one semantic action."""

    def __init__(self, code: str, message: str) -> None:
        """Store a stable code without provider payloads or host paths."""
        self.code = code
        super().__init__(message)


def lower_section_action(
    action: SectionSemanticAction,
    *,
    context: ResolvedSectionContext,
    document: object,
) -> AuthoringDocumentIntent:
    """Lower one validated action into a provider-neutral authoring intent."""
    if action.action == "reconstruct":
        return compile_section_semantics(
            action.section,
            section_context=context,
            document=document,
            section_id_hint=context.section_id or "section",
            allow_existing_section=True,
        )

    section_id = context.section_id
    if section_id is None:
        raise SemanticActionError(
            "section_missing",
            "Existing-section actions require a grounded section.",
        )

    if action.action == "update_curve_scale":
        target = resolve_existing_curve(action.target, context)
        return AuthoringDocumentIntent(
            curve_bindings=[
                AuthoringCurveBindingIntent(
                    kind="curve",
                    binding_id=target.binding_id,
                    section_id=section_id,
                    track_id=target.track_id,
                    scale=_scale(action.scale),
                )
            ]
        )

    if action.action == "add_track":
        return _lower_added_track(action.track, context=context, document=document)

    target = resolve_existing_curve(action.target, context)
    fill = action.fill
    other_binding_id = None
    if hasattr(fill, "other_binding"):
        other_binding_id = resolve_existing_curve(
            ExistingCurveSelector(handle=fill.other_binding), context
        ).binding_id
    values: dict[str, object] = {
        "fill_id": _allocator(document).allocate_leaf(
            section_id,
            target.track_id,
            leaf_kind="fill",
            id_hint=fill.semantic_id,
        ),
        "section_id": section_id,
        "track_id": target.track_id,
        "kind": fill.kind,
        "binding_id": target.binding_id,
    }
    if other_binding_id is not None:
        values["other_binding_id"] = other_binding_id
    if getattr(fill, "baseline", None) is not None:
        values["baseline"] = {"value": fill.baseline}
    if fill.color is not None:
        values["color"] = fill.color
    if fill.alpha is not None:
        values["alpha"] = fill.alpha
    return AuthoringDocumentIntent(fills=[AuthoringFillIntent(**values)])


def resolve_existing_curve(
    selector: ExistingCurveSelector,
    context: ResolvedSectionContext,
) -> ExistingCurveContext:
    """Resolve one request-local handle without fuzzy substitution."""
    if not selector.handle.startswith("curve-"):
        raise SemanticActionError("target_invalid", "The existing-curve handle is invalid.")
    try:
        index = int(selector.handle.removeprefix("curve-")) - 1
    except ValueError as error:
        raise SemanticActionError(
            "target_invalid", "The existing-curve handle is invalid."
        ) from error
    if index < 0 or index >= len(context.existing_curves):
        raise SemanticActionError(
            "target_missing", "No grounded existing curve matches the handle."
        )
    return context.existing_curves[index]


def _lower_added_track(
    track: TrackSemanticDraft,
    *,
    context: ResolvedSectionContext,
    document: object,
) -> AuthoringDocumentIntent:
    """Lower one new track while retaining host-owned identities."""
    section_id = context.section_id
    if section_id is None:
        raise SemanticActionError("section_missing", "Adding a track requires a grounded section.")
    allocator = _allocator(document)
    track_id = allocator.allocate_track(section_id, f"track-{track.semantic_id}")
    bindings: list[object] = []
    for binding in track.bindings:
        expected_kind = "array" if binding.kind == "raster" else "scalar"
        _require_channel(binding.channel, context, expected_kind=expected_kind)
        binding_id = allocator.allocate_binding(
            section_id,
            track_id,
            channel=binding.channel,
            id_hint=f"binding-{binding.semantic_id}",
        )
        if binding.kind == "curve":
            binding_values: dict[str, object] = {
                "kind": "curve",
                "binding_id": binding_id,
                "section_id": section_id,
                "track_id": track_id,
                "channel": binding.channel,
            }
            if binding.label is not None:
                binding_values["label"] = binding.label
            if binding.scale is not None:
                binding_values["scale"] = _scale(binding.scale)
            if binding.style is not None:
                binding_values["style"] = binding.style
            bindings.append(AuthoringCurveBindingIntent(**binding_values))
        else:
            raise SemanticActionError(
                "raster_add_unsupported",
                "The canonical add-track action currently supports scalar bindings only.",
            )
    if not bindings:
        raise SemanticActionError("track_empty", "A new track requires at least one binding.")
    return AuthoringDocumentIntent(
        sections=[
            AuthoringSectionIntent(
                section_id=section_id,
                tracks=[
                    AuthoringTrackIntent(
                        **{
                            **{
                                "track_id": track_id,
                                "section_id": section_id,
                                "title": track.title,
                                "kind": track.kind,
                                "bindings": bindings,
                            },
                            **({"width_mm": track.width_mm} if track.width_mm is not None else {}),
                            **(
                                {"x_scale": _scale(track.x_scale)}
                                if track.x_scale is not None
                                else {}
                            ),
                        }
                    )
                ],
            )
        ]
    )


def _require_channel(
    channel: str,
    context: ResolvedSectionContext,
    *,
    expected_kind: str,
) -> None:
    """Require an exact inspected channel kind with no substitution."""
    available = [
        item for source in context.sources for item in source.channels if item.mnemonic == channel
    ]
    if not available:
        raise SemanticActionError("channel_missing", f"No source channel matches '{channel}'.")
    if not any(item.kind == expected_kind for item in available):
        raise SemanticActionError(
            "channel_kind_mismatch",
            f"Source channel '{channel}' is not {expected_kind}.",
        )


def _allocator(document: object) -> IdAllocator:
    """Seed identity allocation from the existing canonical document."""
    return IdAllocator(
        section_ids=[section.id for section in document.sections],
        track_ids_by_section={
            section.id: [track.id for track in section.tracks] for section in document.sections
        },
        binding_ids=[
            binding.binding_id
            for section in document.sections
            for track in section.tracks
            for binding in getattr(track, "bindings", ())
        ],
        leaf_ids=[
            leaf_id
            for section in document.sections
            for track in section.tracks
            for leaf_id in (
                [fill.fill_id for fill in getattr(track, "fills", ()) if fill.fill_id]
                + [
                    annotation.annotation_id
                    for annotation in getattr(track, "annotations", ())
                    if annotation.annotation_id
                ]
            )
        ],
    )


def _scale(value: SemanticScale) -> AuthoringScale:
    """Translate the canonical semantic scale to the lower authoring model."""
    return AuthoringScale(
        kind=value.kind,
        minimum=value.minimum,
        maximum=value.maximum,
        reverse=value.reverse,
        unit=value.unit,
    )


__all__ = [
    "AddFillAction",
    "AddTrackAction",
    "BaselineSplitFill",
    "BetweenCurvesFill",
    "BetweenInstancesFill",
    "ExistingCurveSelector",
    "FillSemanticDraft",
    "LimitFill",
    "ReconstructSectionAction",
    "SectionSemanticAction",
    "SemanticActionError",
    "UpdateCurveScaleAction",
    "lower_section_action",
    "resolve_existing_curve",
]
