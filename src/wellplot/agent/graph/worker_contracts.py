"""Worker schemas derived from canonical intents and explicit target inventory."""

from __future__ import annotations

from copy import deepcopy
from functools import cache
from types import UnionType
from typing import ClassVar, Literal, Union, get_args, get_origin

from pydantic import BaseModel, Field, create_model

from ...capabilities import CapabilityRegistry
from ...capabilities.builtins import LogPlotSectionArtifact, ReportArtifact
from ...model.authoring import (
    AuthoringDataSource,
    AuthoringRasterColorbarSpec,
    AuthoringRasterSampleAxisSpec,
    AuthoringScale,
)
from ...model.intent import (
    AuthoringAnnotationIntent,
    AuthoringClearIntent,
    AuthoringCurveBindingIntent,
    AuthoringFillIntent,
    AuthoringGridIntent,
    AuthoringHeaderFieldIntent,
    AuthoringHeaderIntent,
    AuthoringRasterBindingIntent,
    AuthoringRemarkIntent,
    AuthoringReportIntent,
    AuthoringSectionIntent,
    AuthoringServiceTitleIntent,
    AuthoringStyleIntent,
    AuthoringTrackIntent,
    _IntentModel,
)
from .models import SectionPlan, SemanticComponentPlan


@cache
def construction_model(model: type[BaseModel]) -> type[BaseModel]:
    """Advertise and validate set-or-omit fields while preserving canonical types.

    This changes the input contract, never the submitted payload. Clear markers
    and explicit nulls are rejected for intent fields; nullable canonical values
    such as raster sample-axis labels retain their original semantics.
    """
    model.model_rebuild()
    fields = {}
    for name, original in model.model_fields.items():
        if name == "extensions":
            # Extensions preserve opaque compatibility data. Worker context
            # deliberately excludes them, so a provider cannot replace them.
            fields[name] = (ClassVar[None], None)
            continue
        field = deepcopy(original)
        annotation = _construction_type(field.annotation)
        field.annotation = annotation
        fields[name] = (annotation, field)
    return create_model(f"Construction{model.__name__}", __base__=model, **fields)


def _construction_type(annotation: object) -> object:
    origin = get_origin(annotation)
    if origin in (Union, UnionType):
        variants = tuple(
            _construction_type(item)
            for item in get_args(annotation)
            if item not in (AuthoringClearIntent, type(None))
        )
        return variants[0] if len(variants) == 1 else Union[variants]  # noqa: UP007
    if origin is list:
        return list[_construction_type(get_args(annotation)[0])]
    if isinstance(annotation, type) and issubclass(annotation, _IntentModel):
        return construction_model(annotation)
    return annotation


def report_contract(document: dict[str, object], *, reconstruct: bool) -> type[BaseModel]:
    """Limit report output to its own fields and existing header slot identities."""
    base = (
        construction_model(AuthoringReportIntent)
        if reconstruct
        else ReportArtifact.model_fields["intent"].annotation
    )
    header_base = (
        construction_model(AuthoringHeaderIntent) if reconstruct else AuthoringHeaderIntent
    )
    field_base = (
        construction_model(AuthoringHeaderFieldIntent)
        if reconstruct
        else AuthoringHeaderFieldIntent
    )
    field_base = create_model(
        "HeaderSlotValueIntent",
        __base__=field_base,
        key=(ClassVar[None], None),
        label=(ClassVar[None], None),
        aliases=(ClassVar[None], None),
        layout_path=(ClassVar[None], None),
    )
    title_base = (
        construction_model(AuthoringServiceTitleIntent)
        if reconstruct
        else AuthoringServiceTitleIntent
    )
    header = document.get("header") or {}
    overrides = {}
    for collection, item_base in (
        ("general_fields", field_base),
        ("detail_fields", field_base),
        ("service_titles", title_base),
    ):
        slots = header_slot_ids(header, collection)
        if slots:
            item = create_model(
                f"{collection}Target",
                __base__=item_base,
                slot_id=(Literal[tuple(slots)], Field(description="Existing header slot ID.")),
            )
            annotation = list[item] if reconstruct else list[item] | AuthoringClearIntent
            overrides[collection] = (annotation, None)
        else:
            # No slot can be edited before its header archetype exists.
            overrides[collection] = (list[item_base], Field(default=None, max_length=0))
    scoped_header = create_model("ScopedHeaderIntent", __base__=header_base, **overrides)
    header_type = scoped_header if reconstruct else scoped_header | AuthoringClearIntent
    scoped_intent = create_model("ScopedReportIntent", __base__=base, header=(header_type, None))
    return create_model(
        "ScopedReportArtifact", __base__=ReportArtifact, intent=(scoped_intent, ...)
    )


def header_slot_ids(header: dict[str, object], collection: str) -> list[str]:
    """Enumerate canonical general, service-title, or detail value slots."""
    if collection != "detail_fields":
        return [item["slot_id"] for item in header.get(collection, [])]
    slots = []
    for row in (header.get("detail") or {}).get("rows", []):
        slots.extend(value["slot_id"] for value in row.get("values", []))
        for column in row.get("columns", []):
            slots.extend(cell["slot_id"] for cell in column.get("cells", []))
    return slots


def section_contract(
    plan: SectionPlan,
    document: dict[str, object],
    registry: CapabilityRegistry,
    *,
    reconstruct: bool,
) -> type[BaseModel]:
    """Bind a section artifact to local track IDs and declared parent ownership."""
    AuthoringTrackIntent.model_rebuild()
    sections = {item["id"]: item for item in document.get("sections", [])}
    existing = sections.get(plan.section_id, {})
    existing_tracks = {item["id"]: item for item in existing.get("tracks", [])}
    targets = {
        item.target_id: item
        for item in plan.components
        if registry.get(item.capability_id).category == "track"
    }
    variants = []
    for target_id in targets:
        creating = target_id not in existing_tracks
        track_base = (
            construction_model(AuthoringTrackIntent)
            if reconstruct or creating
            else AuthoringTrackIntent
        )
        component = targets[target_id]
        component_id = component.component_id if component is not None else None
        children = (
            [item for item in plan.components if item.parent_component_id == component_id]
            if component_id is not None
            else []
        )
        fields = {
            "track_id": (Literal[target_id], ...),
            "section_id": (Literal[plan.section_id], None),
        }
        component = targets.get(target_id)
        if component is not None:
            kind = registry.get(component.capability_id).metadata.get("track_kind")
            if kind is not None:
                fields["kind"] = (Literal[kind], ... if creating else None)
            if kind in {"reference", "annotation"}:
                # Remove the inherited field from both wire schema and accepted input.
                fields["x_scale"] = (ClassVar[None], None)
        if creating:
            fields["title"] = (str, Field(min_length=1))
            fields["width_mm"] = (float, Field(gt=0))
        fields.update(_planned_track_value_fields(children))
        existing_binding_ids = {
            item["binding_id"] for item in existing_tracks.get(target_id, {}).get("bindings", [])
        }
        fields["bindings"] = _child_collection_field(
            children=children,
            category="binding",
            item_models=_binding_models(
                children=children,
                section_id=plan.section_id,
                track_id=target_id,
                existing_ids=existing_binding_ids,
                reconstruct=reconstruct or creating,
            ),
            reconstruct=reconstruct or creating,
        )
        fields["fills"] = _child_collection_field(
            children=children,
            category="fill",
            item_models=_fill_models(
                children=children,
                section_id=plan.section_id,
                track_id=target_id,
                reconstruct=reconstruct or creating,
            ),
            reconstruct=reconstruct or creating,
        )
        fields["annotations"] = _child_collection_field(
            children=children,
            category="annotation",
            item_models=_annotation_models(
                children=children,
                section_id=plan.section_id,
                track_id=target_id,
                reconstruct=reconstruct or creating,
            ),
            reconstruct=reconstruct or creating,
        )
        variants.append(create_model(f"{target_id}TrackIntent", __base__=track_base, **fields))
    section_base = (
        construction_model(AuthoringSectionIntent)
        if reconstruct or not existing
        else AuthoringSectionIntent
    )
    fields = {"section_id": (Literal[plan.section_id], ...)}
    if not existing:
        fields["title"] = (str, Field(min_length=1))
    if plan.data_source is not None:
        source = create_model(
            f"{plan.section_id}DataSource",
            __base__=AuthoringDataSource,
            source_path=(Literal[plan.data_source.source_path], ...),
            source_format=(Literal[plan.data_source.source_format], ...),
        )
        fields["data_source"] = (source, ...)
    if variants:
        tracks = list[Union[tuple(variants)]]  # noqa: UP007
        fields["tracks"] = (
            tracks,
            Field(..., min_length=len(targets), max_length=len(targets)),
        )
    else:
        fields["tracks"] = (
            list[construction_model(AuthoringTrackIntent)],
            Field(default=None, max_length=0),
        )
    section = create_model("ScopedSectionIntent", __base__=section_base, **fields)
    remark = construction_model(AuthoringRemarkIntent) if reconstruct else AuthoringRemarkIntent
    return create_model(
        "ScopedSectionArtifact",
        __base__=LogPlotSectionArtifact,
        section=(section, ...),
        report_remarks=(list[remark], Field(default_factory=list)),
    )


def _child_collection_field(
    *,
    children: list[SemanticComponentPlan],
    category: str,
    item_models: list[type[BaseModel]],
    reconstruct: bool,
) -> tuple[object, Field]:
    """Restrict one nested collection to the planned child targets.

    An omitted collection preserves prior state. Once a collection is supplied,
    reconstruction may only contain the targets declared by the planner. This
    keeps target ownership in the advertised schema rather than in execution
    recovery logic.
    """
    count = sum(1 for item in children if item.capability_id.split(".", maxsplit=1)[0] == category)
    if not item_models:
        # No item is legal here. Advertising its full model suggests unsupported
        # work and pulls unrelated capability definitions into the tool schema.
        annotation = list[object] if reconstruct else list[object] | AuthoringClearIntent
        return annotation, Field(default=None, max_length=0)
    item_type = Union[tuple(item_models)]  # noqa: UP007
    annotation = list[item_type] if reconstruct else list[item_type] | AuthoringClearIntent
    return annotation, Field(..., min_length=count, max_length=count)


def _binding_models(
    *,
    children: list[SemanticComponentPlan],
    section_id: str,
    track_id: str,
    existing_ids: set[str],
    reconstruct: bool,
) -> list[type[BaseModel]]:
    """Build binding contracts that preserve every explicit semantic value.

    A planner's component values are the hand-off between semantic planning and
    typed authoring. Constraining them here prevents a section compiler from
    silently replacing a requested style or raster-axis value with a default.
    """
    models = []
    for index, item in enumerate(children):
        if item.capability_id not in {"binding.curve", "binding.raster"}:
            continue
        base: type[BaseModel] = (
            AuthoringCurveBindingIntent
            if item.capability_id == "binding.curve"
            else AuthoringRasterBindingIntent
        )
        if reconstruct:
            base = construction_model(base)
        fields: dict[str, object] = {
            "binding_id": (Literal[item.target_id], ...),
            "section_id": (Literal[section_id], None),
            "track_id": (Literal[track_id], None),
        }
        channel = _planned_text(item, "channel")
        if channel is not None:
            fields["channel"] = (Literal[channel], ...)
        elif item.target_id not in existing_ids:
            fields["channel"] = (str, Field(min_length=1))
        fields.update(_planned_binding_value_fields(item))
        models.append(
            create_model(
                f"{track_id}{index}{item.capability_id.replace('.', '_')}BindingIntent",
                __base__=base,
                **fields,
            )
        )
    return models


def _planned_track_value_fields(
    children: list[SemanticComponentPlan],
) -> dict[str, tuple[object, object]]:
    """Require track settings explicitly carried by child semantic components."""
    values = _planned_values(children)
    fields: dict[str, tuple[object, object]] = {}
    scale_fields = _scale_value_fields(values, prefix="track_x_scale_")
    if scale_fields:
        fields["x_scale"] = (
            _constrained_model("PlannedTrackScale", AuthoringScale, scale_fields),
            ...,
        )
    if "hide_vertical_grid_lines" in values:
        visible = not bool(values["hide_vertical_grid_lines"])
        grid = create_model(
            "PlannedTrackGrid",
            __base__=construction_model(AuthoringGridIntent),
            vertical_main_visible=(Literal[visible], ...),
            vertical_secondary_visible=(Literal[visible], ...),
        )
        fields["grid"] = (grid, ...)
    return fields


def _planned_binding_value_fields(
    item: SemanticComponentPlan,
) -> dict[str, tuple[object, object]]:
    """Translate explicit semantic binding values into exact nested constraints."""
    values = item.values
    fields: dict[str, tuple[object, object]] = {}
    label = _planned_text(item, "label")
    if label is not None:
        fields["label"] = (Literal[label], ...)
    scale_fields = _scale_value_fields(values, prefix="scale_")
    if scale_fields:
        fields["scale"] = (
            _constrained_model("PlannedCurveScale", AuthoringScale, scale_fields),
            ...,
        )
    style_fields = _style_value_fields(values)
    if style_fields:
        fields["style"] = (
            _constrained_model(
                "PlannedBindingStyle",
                construction_model(AuthoringStyleIntent),
                style_fields,
            ),
            ...,
        )
    if item.capability_id == "binding.raster":
        fields.update(_planned_raster_value_fields(values))
    return fields


def _planned_raster_value_fields(
    values: dict[str, object],
) -> dict[str, tuple[object, object]]:
    """Require the raster presentation values explicitly declared by the planner."""
    fields: dict[str, tuple[object, object]] = {}
    profile = _text_value(values.get("profile"))
    if profile is not None:
        fields["profile"] = (Literal[profile], ...)
    colorbar_fields = _prefixed_value_fields(
        values,
        "colorbar_",
        {
            "enabled": "enabled",
            "label": "label",
            "position": "position",
        },
    )
    if colorbar_fields:
        fields["colorbar"] = (
            _constrained_model(
                "PlannedRasterColorbar",
                AuthoringRasterColorbarSpec,
                colorbar_fields,
            ),
            ...,
        )
    sample_axis_fields = _prefixed_value_fields(
        values,
        "sample_axis_",
        {
            "enabled": "enabled",
            "unit": "unit",
            "source_origin": "source_origin",
            "source_step": "source_step",
            "min": "minimum",
            "max": "maximum",
            "ticks": "tick_count",
        },
    )
    if sample_axis_fields:
        fields["sample_axis"] = (
            _constrained_model(
                "PlannedRasterSampleAxis",
                AuthoringRasterSampleAxisSpec,
                sample_axis_fields,
            ),
            ...,
        )
    return fields


def _scale_value_fields(
    values: dict[str, object], *, prefix: str
) -> dict[str, tuple[object, object]]:
    """Build exact scale fields from the planner's semantic scale vocabulary."""
    return _prefixed_value_fields(
        values,
        prefix,
        {"min": "minimum", "max": "maximum", "reversed": "reverse"},
    )


def _style_value_fields(values: dict[str, object]) -> dict[str, tuple[object, object]]:
    """Build exact style fields when the planner specified them explicitly."""
    fields = _prefixed_value_fields(
        values,
        "style_",
        {"color": "color", "width": "line_width", "colormap": "colormap"},
    )
    dash = _text_value(values.get("style_dash"))
    if dash is not None:
        fields["line_style"] = (Literal[dash], ...)
    return fields


def _prefixed_value_fields(
    values: dict[str, object],
    prefix: str,
    mapping: dict[str, str],
) -> dict[str, tuple[object, object]]:
    """Return literal constraints for scalar values declared under one prefix."""
    fields: dict[str, tuple[object, object]] = {}
    for source_name, target_name in mapping.items():
        key = prefix + source_name
        if key in values and _is_literal_value(values[key]):
            fields[target_name] = (Literal[values[key]], ...)
    return fields


def _planned_values(children: list[SemanticComponentPlan]) -> dict[str, object]:
    """Combine only child values that describe their shared parent track."""
    values: dict[str, object] = {}
    for child in children:
        for key, value in child.values.items():
            if not (key.startswith("track_x_scale_") or key == "hide_vertical_grid_lines"):
                continue
            if key in values and values[key] != value:
                raise ValueError(f"Planned track children disagree on {key!r}.")
            values[key] = value
    return values


def _planned_text(item: SemanticComponentPlan, key: str) -> str | None:
    """Read a non-empty textual component value when present."""
    return _text_value(item.values.get(key))


def _text_value(value: object) -> str | None:
    """Return a non-empty string suitable for an exact construction constraint."""
    return value if isinstance(value, str) and value.strip() else None


def _is_literal_value(value: object) -> bool:
    """Allow only scalar semantic values in dynamic literal constraints."""
    return isinstance(value, (str, int, float, bool)) and not isinstance(value, complex)


def _constrained_model(
    name: str,
    base: type[BaseModel],
    fields: dict[str, tuple[object, object]],
) -> type[BaseModel]:
    """Create one sparse nested model with exact values required by the plan."""
    return create_model(name, __base__=base, **fields)


def _fill_models(
    *,
    children: list[SemanticComponentPlan],
    section_id: str,
    track_id: str,
    reconstruct: bool,
) -> list[type[BaseModel]]:
    """Build exact fill variants for one planned track."""
    base = construction_model(AuthoringFillIntent) if reconstruct else AuthoringFillIntent
    items = [item for item in children if item.capability_id == "fill.curve"]
    if not items:
        return []
    return [
        create_model(
            f"{track_id}FillIntent",
            __base__=base,
            fill_id=(Literal[tuple(item.target_id for item in items)], ...),
            section_id=(Literal[section_id], None),
            track_id=(Literal[track_id], None),
        )
    ]


def _annotation_models(
    *,
    children: list[SemanticComponentPlan],
    section_id: str,
    track_id: str,
    reconstruct: bool,
) -> list[type[BaseModel]]:
    """Build exact annotation variants for one planned track."""
    base = (
        construction_model(AuthoringAnnotationIntent) if reconstruct else AuthoringAnnotationIntent
    )
    items = [item for item in children if item.capability_id == "annotation.typed"]
    if not items:
        return []
    return [
        create_model(
            f"{track_id}AnnotationIntent",
            __base__=base,
            annotation_id=(Literal[tuple(item.target_id for item in items)], ...),
            section_id=(Literal[section_id], None),
            track_id=(Literal[track_id], None),
        )
    ]
