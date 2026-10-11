"""Versioned typed semantic workers for the supported delivery route.

This module is deliberately separate from the historical CM-55/56 section
contract.  The delivery contract lets the model describe scientific meaning;
the compiler allocates canonical identities and emits only
``AuthoringDocumentIntent``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ...authoring_program.ids import IdAllocator
from ...authoring_program.models import ProgramDiagnostic, ProgramMetrics
from ...model.authoring import (
    AuthoringDataSource,
    AuthoringRasterColorbarSpec,
    AuthoringRasterSampleAxisSpec,
    AuthoringScale,
)
from ...model.intent import (
    AuthoringCurveBindingIntent,
    AuthoringDepthIntent,
    AuthoringDocumentIntent,
    AuthoringFillIntent,
    AuthoringHeaderFieldIntent,
    AuthoringHeaderIntent,
    AuthoringPageIntent,
    AuthoringRasterBindingIntent,
    AuthoringRemarkIntent,
    AuthoringReportValueIntent,
    AuthoringSectionIntent,
    AuthoringServiceTitleIntent,
    AuthoringStyleIntent,
    AuthoringTailIntent,
    AuthoringTrackIntent,
)
from ..providers.base import (
    ModelBackendProtocol,
    ProviderRequestError,
    StructuredGenerationRequest,
)
from .enrichment import ExistingCurveContext, ReportContext, ResolvedSectionContext
from .planner import ReportTask

DELIVERY_TYPED_WORKER_VERSION = "cm58.typed-delivery-worker.v1"


class _DeliveryModel(BaseModel):
    """Strict immutable model for one provider-facing delivery response."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class DeliveryScale(_DeliveryModel):
    """Explicit scale semantics owned by the scientist request."""

    kind: Literal["linear", "log", "tangential"] = "linear"
    minimum: float
    maximum: float
    reverse: bool = False
    unit: str | None = Field(default=None, min_length=1)


class DeliveryStyle(_DeliveryModel):
    """Explicit binding presentation, with no renderer-specific fields."""

    color: str | None = Field(default=None, min_length=1)
    line_style: str | None = Field(default=None, min_length=1)
    line_width: float | None = Field(default=None, gt=0)
    alpha: float | None = Field(default=None, ge=0, le=1)
    colormap: str | None = Field(default=None, min_length=1)


class DeliverySampleAxis(_DeliveryModel):
    """Explicit array sample-axis semantics."""

    unit: str | None = Field(default=None, min_length=1)
    minimum: float | None = None
    maximum: float | None = None
    tick_count: int | None = Field(default=None, ge=2)
    source_origin: float | None = None
    source_step: float | None = None


class DeliveryCurve(_DeliveryModel):
    """One scalar binding with a request-local semantic handle."""

    semantic_id: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    label: str | None = Field(default=None, min_length=1)
    scale: DeliveryScale | None = None
    style: DeliveryStyle | None = None


class DeliveryRaster(_DeliveryModel):
    """One array binding with bounded raster presentation semantics."""

    semantic_id: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    label: str | None = Field(default=None, min_length=1)
    profile: Literal["generic", "vdl", "waveform"] = "generic"
    colormap: str | None = Field(default=None, min_length=1)
    alpha: float | None = Field(default=None, ge=0, le=1)
    colorbar_enabled: bool | None = None
    colorbar_label: str | None = Field(default=None, min_length=1)
    colorbar_position: Literal["right", "header"] | None = None
    sample_axis: DeliverySampleAxis | None = None


class DeliveryFill(_DeliveryModel):
    """One fill relation using request-local binding handles only."""

    semantic_id: str = Field(min_length=1)
    target_binding: str = Field(min_length=1)
    kind: Literal[
        "between_curves",
        "between_instances",
        "to_lower_limit",
        "to_upper_limit",
        "baseline_split",
    ]
    other_binding: str | None = Field(default=None, min_length=1)
    color: str | None = Field(default=None, min_length=1)
    alpha: float | None = Field(default=None, ge=0, le=1)


class DeliveryTrack(_DeliveryModel):
    """One ordered track and its typed binding children."""

    semantic_id: str = Field(min_length=1)
    kind: Literal["normal", "reference", "array"]
    title: str = Field(min_length=1)
    width_mm: float | None = Field(default=None, gt=0)
    scale: DeliveryScale | None = None
    grid_vertical_main_visible: bool | None = None
    grid_vertical_secondary_visible: bool | None = None
    curves: tuple[DeliveryCurve, ...] = ()
    rasters: tuple[DeliveryRaster, ...] = ()
    fills: tuple[DeliveryFill, ...] = ()

    @model_validator(mode="after")
    def validate_children(self) -> DeliveryTrack:
        """Keep the typed child vocabulary aligned with the track kind."""
        if self.kind == "array" and self.curves:
            raise ValueError("Array tracks cannot contain scalar curve children.")
        if self.kind != "array" and self.rasters:
            raise ValueError("Only array tracks may contain raster children.")
        binding_ids = [item.semantic_id for item in (*self.curves, *self.rasters)]
        if len(binding_ids) != len(set(binding_ids)):
            raise ValueError("Binding semantic IDs must be unique within a track.")
        return self


class DeliverySection(_DeliveryModel):
    """One complete section reconstruction fragment."""

    title: str = Field(min_length=1)
    source_candidate: str = Field(min_length=1)
    tracks: tuple[DeliveryTrack, ...] = Field(min_length=1)


class DeliveryTarget(_DeliveryModel):
    """Request-local existing-curve selector; canonical IDs never enter output."""

    handle: str | None = Field(default=None, min_length=1)
    channel: str | None = Field(default=None, min_length=1)
    label: str | None = Field(default=None, min_length=1)
    track_title: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_selector(self) -> DeliveryTarget:
        """Require at least one bounded selection fact."""
        if not any((self.handle, self.channel, self.label, self.track_title)):
            raise ValueError("A delivery target requires a selection fact.")
        return self


class DeliverySectionResponse(_DeliveryModel):
    """Union-like response for reconstruction and the three bounded revisions."""

    mode: Literal[
        "reconstruct",
        "update_curve_scale",
        "add_track_curve",
        "add_fill",
    ]
    section: DeliverySection | None = None
    target: DeliveryTarget | None = None
    scale: DeliveryScale | None = None
    track: DeliveryTrack | None = None
    fill: DeliveryFill | None = None

    @model_validator(mode="after")
    def validate_mode(self) -> DeliverySectionResponse:
        """Reject incomplete or cross-operation semantic responses."""
        if self.mode == "reconstruct" and self.section is None:
            raise ValueError("Reconstruction requires a section response.")
        if self.mode == "update_curve_scale" and (self.target is None or self.scale is None):
            raise ValueError("Scale revision requires target and scale.")
        if self.mode == "add_track_curve" and self.track is None:
            raise ValueError("Track revision requires a track response.")
        if self.mode == "add_fill" and (self.target is None or self.fill is None):
            raise ValueError("Fill revision requires target and fill.")
        return self


class DeliverySlotValue(_DeliveryModel):
    """One host-approved report slot value."""

    slot_id: str = Field(min_length=1)
    value: str | float | int
    unit: str | None = Field(default=None, min_length=1)


class DeliveryRemark(_DeliveryModel):
    """One report remark with a request-local identity."""

    semantic_id: str = Field(min_length=1)
    title: str | None = Field(default=None, min_length=1)
    text: str | None = None
    lines: tuple[str, ...] = ()
    alignment: Literal["left", "center", "right"] = "left"

    @model_validator(mode="after")
    def validate_content(self) -> DeliveryRemark:
        """Require content without allowing an empty mutation."""
        if self.text is None and not self.lines:
            raise ValueError("A report remark requires text or lines.")
        return self


class DeliveryReportResponse(_DeliveryModel):
    """Sparse typed report semantics; omitted fields remain preserved."""

    title: str | None = Field(default=None, min_length=1)
    subtitle: str | None = Field(default=None, min_length=1)
    general_fields: tuple[DeliverySlotValue, ...] = ()
    service_titles: tuple[DeliverySlotValue, ...] = ()
    detail_fields: tuple[DeliverySlotValue, ...] = ()
    remarks: tuple[DeliveryRemark, ...] = ()
    page_size: str | None = Field(default=None, min_length=1)
    page_orientation: Literal["portrait", "landscape"] | None = None
    depth_unit: str | None = Field(default=None, min_length=1)
    depth_scale: str | float | None = None
    tail_enabled: bool | None = None

    @model_validator(mode="after")
    def validate_nonempty(self) -> DeliveryReportResponse:
        """Require at least one explicitly requested report semantic."""
        if not any(
            (
                self.title,
                self.subtitle,
                self.general_fields,
                self.service_titles,
                self.detail_fields,
                self.remarks,
                self.page_size,
                self.page_orientation,
                self.depth_unit,
                self.depth_scale is not None,
                self.tail_enabled is not None,
            )
        ):
            raise ValueError("Typed report response contains no report mutation.")
        return self


@dataclass(frozen=True, slots=True)
class TypedSemanticWorkerResult:
    """Worker result projected into the existing graph evidence contract."""

    success: bool
    intent_fragment: AuthoringDocumentIntent | None
    diagnostics: tuple[ProgramDiagnostic, ...]
    metrics: ProgramMetrics


@dataclass(frozen=True, slots=True)
class TypedDeliveryReportCompiler:
    """Generate one structured report response and compile it deterministically."""

    backend: ModelBackendProtocol

    async def compile(
        self,
        *,
        task: ReportTask,
        report_context: ReportContext,
        document: object,
        timeout_seconds: float,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> TypedSemanticWorkerResult:
        """Make exactly one structured report generation call."""
        payload = {
            "report_task": task.model_dump(mode="json"),
            "report_context": report_context.model_dump(mode="json"),
            "rules": "Return only explicit report values. Do not emit sections or plot children.",
        }
        try:
            generated = await self.backend.generate_structured(
                StructuredGenerationRequest(
                    system_prompt=(
                        "You are the Wellplot typed report semantic worker. Return only "
                        "the fields declared by DeliveryReportResponse."
                    ),
                    user_prompt=_json_payload(payload),
                    timeout_seconds=timeout_seconds,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                ),
                response_model=DeliveryReportResponse,
            )
            response = DeliveryReportResponse.model_validate(generated.value)
            intent = _compile_report(response, report_context)
            return TypedSemanticWorkerResult(True, intent, (), ProgramMetrics())
        except ProviderRequestError:
            raise
        except Exception as error:
            return _typed_failure("report", error)


@dataclass(frozen=True, slots=True)
class TypedDeliverySectionCompiler:
    """Generate one structured section response for reconstruction or revision."""

    backend: ModelBackendProtocol

    async def compile(
        self,
        *,
        task_index: int,
        context: object,
        document: object,
        timeout_seconds: float,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> TypedSemanticWorkerResult:
        """Make exactly one structured section generation call."""
        section_context = ResolvedSectionContext.model_validate(context.sections[task_index])
        task = context.plan.section_tasks[task_index]
        payload = {
            "section_task": task.model_dump(mode="json"),
            "section_context": _section_provider_context(section_context),
            "rules": (
                "Return typed semantic fields only. Use request-local handles for existing "
                "targets. Never return paths, canonical IDs, SDK calls, or program source."
            ),
        }
        try:
            generated = await self.backend.generate_structured(
                StructuredGenerationRequest(
                    system_prompt=(
                        "You are the Wellplot typed section semantic worker. Return only "
                        "the fields declared by DeliverySectionResponse."
                    ),
                    user_prompt=_json_payload(payload),
                    timeout_seconds=timeout_seconds,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                ),
                response_model=DeliverySectionResponse,
            )
            response = DeliverySectionResponse.model_validate(generated.value)
            intent = _compile_section(response, section_context, document)
            return TypedSemanticWorkerResult(True, intent, (), ProgramMetrics())
        except ProviderRequestError:
            raise
        except Exception as error:
            return _typed_failure("section", error)


def _compile_report(
    response: DeliveryReportResponse, report_context: ReportContext
) -> AuthoringDocumentIntent:
    """Compile report values after checking every slot against host context."""
    allowed = {slot.slot_id: slot for slot in report_context.header_slots}

    def field(value: DeliverySlotValue) -> AuthoringHeaderFieldIntent:
        slot = allowed.get(value.slot_id)
        if slot is None:
            raise ValueError("Typed report selected an unavailable header slot.")
        report_value = {
            "value": str(value.value),
            "provenance": "user",
            "availability": "available",
        }
        if value.unit is not None:
            report_value["unit"] = value.unit
        field_values = {
            "slot_id": value.slot_id,
            "value": AuthoringReportValueIntent(**report_value),
        }
        if slot.key is not None:
            field_values["key"] = slot.key
        if slot.label is not None:
            field_values["label"] = slot.label
        return AuthoringHeaderFieldIntent(**field_values)

    def service(value: DeliverySlotValue) -> AuthoringServiceTitleIntent:
        if value.slot_id not in allowed or not value.slot_id.startswith("service_title"):
            raise ValueError("Typed report selected an unavailable service-title slot.")
        report_value = {
            "value": str(value.value),
            "provenance": "user",
            "availability": "available",
        }
        if value.unit is not None:
            report_value["unit"] = value.unit
        return AuthoringServiceTitleIntent(
            slot_id=value.slot_id,
            value=AuthoringReportValueIntent(**report_value),
        )

    fields = [field(item) for item in (*response.general_fields, *response.detail_fields)]
    header = None
    if fields or response.service_titles:
        header_values: dict[str, object] = {}
        general = [item for item in fields if item.slot_id.startswith("general.")]
        detail = [item for item in fields if item.slot_id.startswith("detail.")]
        services = [service(item) for item in response.service_titles]
        if general:
            header_values["general_fields"] = general
        if detail:
            header_values["detail_fields"] = detail
        if services:
            header_values["service_titles"] = services
        header = AuthoringHeaderIntent(**header_values)
    remarks = [
        AuthoringRemarkIntent(
            remark_id=f"typed-remark-{index + 1}",
            title=item.title,
            text=item.text,
            lines=list(item.lines) if item.text is None else None,
            alignment=item.alignment,
        )
        for index, item in enumerate(response.remarks)
    ]
    page_values: dict[str, object] = {}
    if response.page_size is not None:
        page_values["size"] = response.page_size
    if response.page_orientation is not None:
        page_values["orientation"] = response.page_orientation
    page = AuthoringPageIntent(**page_values) if page_values else None
    depth_values: dict[str, object] = {}
    if response.depth_unit is not None:
        depth_values["unit"] = response.depth_unit
    if response.depth_scale is not None:
        depth_values["scale"] = response.depth_scale
    depth = AuthoringDepthIntent(**depth_values) if depth_values else None
    tail = (
        AuthoringTailIntent(enabled=response.tail_enabled)
        if response.tail_enabled is not None
        else None
    )
    values: dict[str, object] = {}
    for name, value in (
        ("title", response.title),
        ("subtitle", response.subtitle),
        ("header", header),
        ("page", page),
        ("depth", depth),
        ("tail", tail),
    ):
        if value is not None:
            values[name] = value
    if remarks:
        values["remarks"] = remarks
    return AuthoringDocumentIntent(**values)


def _compile_section(
    response: DeliverySectionResponse,
    context: ResolvedSectionContext,
    document: object,
) -> AuthoringDocumentIntent:
    """Compile one typed response while keeping canonical identity host-owned."""
    if response.mode == "reconstruct":
        assert response.section is not None
        return _compile_reconstruction(response.section, context, document)
    if context.section_id is None:
        raise ValueError("Section revisions require a resolved existing section.")
    if response.mode == "update_curve_scale":
        assert response.target is not None and response.scale is not None
        target = _resolve_curve(response.target, context)
        return AuthoringDocumentIntent(
            curve_bindings=[
                AuthoringCurveBindingIntent(
                    kind="curve",
                    binding_id=target.binding_id,
                    section_id=context.section_id,
                    track_id=target.track_id,
                    scale=_scale(response.scale),
                )
            ]
        )
    if response.mode == "add_track_curve":
        assert response.track is not None
        return _compile_added_track(response.track, context, document)
    assert response.target is not None and response.fill is not None
    target = _resolve_curve(response.target, context)
    fill = response.fill
    if fill.target_binding != target.channel and fill.target_binding != target.label:
        raise ValueError("Fill target does not match the selected grounded curve.")
    other_id = None
    if fill.other_binding:
        other_id = _resolve_curve(DeliveryTarget(handle=fill.other_binding), context).binding_id
    fill_values: dict[str, object] = {
        "fill_id": _allocator(document).allocate_leaf(
            context.section_id or "section",
            target.track_id,
            leaf_kind="fill",
            id_hint="typed",
        ),
        "section_id": context.section_id,
        "track_id": target.track_id,
        "kind": fill.kind,
        "binding_id": target.binding_id,
    }
    if other_id is not None:
        fill_values["other_binding_id"] = other_id
    if fill.color is not None:
        fill_values["color"] = fill.color
    if fill.alpha is not None:
        fill_values["alpha"] = fill.alpha
    return AuthoringDocumentIntent(fills=[AuthoringFillIntent(**fill_values)])


def _compile_reconstruction(
    section: DeliverySection,
    context: ResolvedSectionContext,
    document: object,
) -> AuthoringDocumentIntent:
    """Compile a complete section while matching existing objects by semantics."""
    allocator = _allocator(document)
    section_id = context.section_id or allocator.allocate_section("typed-section")
    existing_tracks = _existing_tracks(document, section_id)
    used_tracks: set[str] = set()
    tracks: list[AuthoringTrackIntent] = []
    for item in section.tracks:
        existing = next(
            (
                track
                for track in existing_tracks
                if track.id not in used_tracks
                and track.kind == item.kind
                and track.title.casefold() == item.title.casefold()
            ),
            None,
        )
        track_id = (
            existing.id
            if existing is not None
            else allocator.allocate_track(section_id, f"track-{item.semantic_id}")
        )
        used_tracks.add(track_id)
        bindings = _compile_bindings(item, allocator, section_id, track_id, existing, context)
        fills = _compile_fills(
            item.fills,
            bindings,
            [child.semantic_id for child in (*item.curves, *item.rasters)],
            allocator,
            section_id,
            track_id,
        )
        tracks.append(_track_intent(item, track_id, section_id, bindings, fills))
    source = next(
        (source for source in context.sources if source.candidate_id == section.source_candidate),
        None,
    )
    if source is None:
        raise ValueError("Typed section selected an unavailable source candidate.")
    return AuthoringDocumentIntent(
        sections=[
            AuthoringSectionIntent(
                section_id=section_id,
                title=section.title,
                data_source=AuthoringDataSource(
                    source_path=source.canonical_path,
                    source_format=source.source_format,
                ),
                tracks=tracks,
            )
        ]
    )


def _compile_added_track(
    track: DeliveryTrack, context: ResolvedSectionContext, document: object
) -> AuthoringDocumentIntent:
    """Create one track and its grounded children under the selected section."""
    if track.kind == "array" or len(track.curves) != 1 or track.rasters:
        raise ValueError("Add-track delivery revisions require one scalar curve.")
    allocator = _allocator(document)
    track_id = allocator.allocate_track(
        context.section_id or "section", f"track-{track.semantic_id}"
    )
    binding = track.curves[0]
    _require_channel(binding.channel, context)
    binding_id = allocator.allocate_binding(
        context.section_id or "section",
        track_id,
        id_hint=f"binding-{binding.semantic_id}",
        channel=binding.channel,
    )
    curve = _curve_intent(binding, context.section_id, track_id, binding_id)
    return AuthoringDocumentIntent(
        sections=[
            AuthoringSectionIntent(
                section_id=context.section_id,
                tracks=[
                    _track_intent(
                        track,
                        track_id,
                        context.section_id,
                        [curve],
                        [],
                    )
                ],
            )
        ]
    )


def _compile_bindings(
    item: DeliveryTrack,
    allocator: IdAllocator,
    section_id: str,
    track_id: str,
    existing: object | None,
    context: ResolvedSectionContext,
) -> list[object]:
    """Allocate or semantically match ordered curve/raster binding children."""
    existing_bindings = list(getattr(existing, "bindings", ())) if existing is not None else []
    result: list[object] = []
    for child in (*item.curves, *item.rasters):
        _require_channel(
            child.channel,
            context,
            expected_kind="array" if isinstance(child, DeliveryRaster) else "scalar",
        )
        match = next(
            (
                binding
                for binding in existing_bindings
                if binding.channel == child.channel
                and (child.label is None or binding.label == child.label)
            ),
            None,
        )
        binding_id = (
            match.binding_id
            if match is not None
            else allocator.allocate_binding(
                section_id,
                track_id,
                id_hint=f"binding-{child.semantic_id}",
                channel=child.channel,
            )
        )
        if isinstance(child, DeliveryCurve):
            result.append(_curve_intent(child, section_id, track_id, binding_id))
        else:
            result.append(_raster_intent(child, section_id, track_id, binding_id))
    return result


def _track_intent(
    item: DeliveryTrack,
    track_id: str,
    section_id: str,
    bindings: list[object],
    fills: list[AuthoringFillIntent],
) -> AuthoringTrackIntent:
    """Build a sparse track intent with explicit requested presentation only."""
    grid = None
    if (
        item.grid_vertical_main_visible is not None
        or item.grid_vertical_secondary_visible is not None
    ):
        from ...model.intent import AuthoringGridIntent

        grid = AuthoringGridIntent(
            vertical_main_visible=item.grid_vertical_main_visible,
            vertical_secondary_visible=item.grid_vertical_secondary_visible,
        )
    values: dict[str, object] = {
        "track_id": track_id,
        "section_id": section_id,
        "title": item.title,
        "kind": item.kind,
        "bindings": bindings,
    }
    if item.width_mm is not None:
        values["width_mm"] = item.width_mm
    if item.scale is not None:
        values["x_scale"] = _scale(item.scale)
    if grid is not None:
        values["grid"] = grid
    if fills:
        values["fills"] = fills
    return AuthoringTrackIntent(**values)


def _curve_intent(
    child: DeliveryCurve, section_id: str | None, track_id: str, binding_id: str
) -> AuthoringCurveBindingIntent:
    """Build a scalar binding intent from typed semantics."""
    values: dict[str, object] = {
        "kind": "curve",
        "binding_id": binding_id,
        "section_id": section_id,
        "track_id": track_id,
        "channel": child.channel,
    }
    if child.label is not None:
        values["label"] = child.label
    if child.scale is not None:
        values["scale"] = _scale(child.scale)
    if child.style is not None:
        values["style"] = _style(child.style)
    return AuthoringCurveBindingIntent(
        **values,
    )


def _raster_intent(
    child: DeliveryRaster, section_id: str, track_id: str, binding_id: str
) -> AuthoringRasterBindingIntent:
    """Build an array binding intent from typed raster semantics."""
    colorbar = None
    if (
        child.colorbar_enabled is not None
        or child.colorbar_label is not None
        or child.colorbar_position is not None
    ):
        colorbar = AuthoringRasterColorbarSpec(
            enabled=bool(child.colorbar_enabled),
            label=child.colorbar_label,
            position=child.colorbar_position or "right",
        )
    axis = None
    if child.sample_axis is not None:
        axis = AuthoringRasterSampleAxisSpec(enabled=True, **child.sample_axis.model_dump())
    values: dict[str, object] = {
        "kind": "raster",
        "binding_id": binding_id,
        "section_id": section_id,
        "track_id": track_id,
        "channel": child.channel,
        "profile": child.profile,
    }
    for name, value in (("label", child.label), ("alpha", child.alpha)):
        if value is not None:
            values[name] = value
    if child.colormap:
        values["style"] = AuthoringStyleIntent(colormap=child.colormap)
    if colorbar is not None:
        values["colorbar"] = colorbar
    if axis is not None:
        values["sample_axis"] = axis
    return AuthoringRasterBindingIntent(**values)


def _compile_fills(
    items: tuple[DeliveryFill, ...],
    bindings: list[object],
    semantic_ids: list[str],
    allocator: IdAllocator,
    section_id: str,
    track_id: str,
) -> list[AuthoringFillIntent]:
    """Resolve fill handles against the newly compiled binding order."""
    by_semantic = dict(zip(semantic_ids, bindings, strict=True))
    result: list[AuthoringFillIntent] = []
    for item in items:
        target = by_semantic.get(item.target_binding)
        if target is None:
            target = next(
                (
                    binding
                    for binding in bindings
                    if getattr(binding, "binding_id", "") == item.target_binding
                ),
                None,
            )
        if target is None:
            raise ValueError("Fill references an unavailable binding handle.")
        values: dict[str, object] = {
            "fill_id": allocator.allocate_leaf(
                section_id,
                track_id,
                leaf_kind="fill",
                id_hint="typed",
            ),
            "section_id": section_id,
            "track_id": track_id,
            "kind": item.kind,
            "binding_id": target.binding_id,
        }
        if item.color is not None:
            values["color"] = item.color
        if item.alpha is not None:
            values["alpha"] = item.alpha
        result.append(AuthoringFillIntent(**values))
    return result


def _resolve_curve(
    target: DeliveryTarget,
    context: ResolvedSectionContext,
) -> ExistingCurveContext:
    """Resolve one target against host-grounded existing curve facts."""
    matches = list(context.existing_curves)
    if target.handle:
        try:
            index = int(target.handle.removeprefix("curve-"))
        except ValueError:
            index = -1
        matches = [
            item for item in matches if index == list(context.existing_curves).index(item) + 1
        ]
    if target.channel:
        matches = [item for item in matches if item.channel == target.channel]
    if target.label:
        matches = [item for item in matches if item.label == target.label]
    if target.track_title:
        matches = [item for item in matches if item.track_title == target.track_title]
    if len(matches) != 1:
        raise ValueError("Existing curve target is missing or ambiguous.")
    return matches[0]


def _require_channel(
    channel: str,
    context: ResolvedSectionContext,
    *,
    expected_kind: str = "scalar",
) -> None:
    """Require an exact inspected channel kind without substitution."""
    available = [
        item for source in context.sources for item in source.channels if item.mnemonic == channel
    ]
    if not available:
        raise ValueError(f"channel_missing: No source channel matches '{channel}'.")
    if not any(item.kind == expected_kind for item in available):
        raise ValueError(f"channel_kind_mismatch: '{channel}' is not {expected_kind}.")


def _section_provider_context(context: ResolvedSectionContext) -> dict[str, object]:
    """Expose bounded source and request-local target facts without paths."""
    curves = [
        {
            "handle": f"curve-{index}",
            "track_title": curve.track_title,
            "track_kind": curve.track_kind,
            "channel": curve.channel,
            "label": curve.label,
            "scale_kind": curve.scale_kind,
            "scale_minimum": curve.scale_minimum,
            "scale_maximum": curve.scale_maximum,
            "reverse": curve.reverse,
        }
        for index, curve in enumerate(context.existing_curves, start=1)
    ]
    return {
        "target": {"kind": "existing" if context.section_id else "new"},
        "sources": [
            {
                "candidate_id": source.candidate_id,
                "channels": [
                    {"mnemonic": channel.mnemonic, "kind": channel.kind, "unit": channel.unit}
                    for channel in source.channels
                ],
            }
            for source in context.sources
        ],
        "existing_curves": curves,
    }


def _allocator(document: object) -> IdAllocator:
    """Seed host identity allocation from the canonical document."""
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
            leaf.fill_id
            for section in sections
            for track in section.tracks
            for leaf in getattr(track, "fills", ())
            if leaf.fill_id
        ]
        + [
            leaf.annotation_id
            for section in sections
            for track in section.tracks
            for leaf in getattr(track, "annotations", ())
            if leaf.annotation_id
        ],
    )


def _existing_tracks(document: object, section_id: str) -> list[object]:
    """Return canonical tracks for semantic matching without exposing them to the model."""
    for section in document.sections:
        if section.id == section_id:
            return list(section.tracks)
    return []


def _scale(value: DeliveryScale) -> AuthoringScale:
    """Translate a delivery scale into the canonical scale model."""
    return AuthoringScale(
        kind=value.kind,
        minimum=value.minimum,
        maximum=value.maximum,
        reverse=value.reverse,
        unit=value.unit,
    )


def _style(value: DeliveryStyle) -> AuthoringStyleIntent:
    """Translate explicit style semantics without adding defaults."""
    return AuthoringStyleIntent(**value.model_dump(exclude_none=True))


def _json_payload(value: object) -> str:
    """Serialize provider input with stable JSON ordering."""
    import json

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _typed_failure(kind: str, error: Exception) -> TypedSemanticWorkerResult:
    """Project typed validation failures without leaking provider payloads."""
    return TypedSemanticWorkerResult(
        success=False,
        intent_fragment=None,
        diagnostics=(
            ProgramDiagnostic(
                stage="typed_worker",
                code=f"typed.{kind}_validation_error",
                message="Typed semantic response failed deterministic validation.",
                remediation_hint="Return one response matching the typed delivery contract.",
            ),
        ),
        metrics=ProgramMetrics(),
    )


__all__ = [
    "DELIVERY_TYPED_WORKER_VERSION",
    "DeliveryCurve",
    "DeliveryFill",
    "DeliveryRaster",
    "DeliveryRemark",
    "DeliveryReportResponse",
    "DeliveryScale",
    "DeliverySection",
    "DeliverySectionResponse",
    "DeliverySlotValue",
    "DeliveryStyle",
    "DeliveryTarget",
    "DeliveryTrack",
    "TypedDeliveryReportCompiler",
    "TypedDeliverySectionCompiler",
    "TypedSemanticWorkerResult",
]
