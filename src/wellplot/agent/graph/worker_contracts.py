"""Worker schemas derived from canonical intents and explicit target inventory."""

from __future__ import annotations

from copy import deepcopy
from functools import cache
from types import UnionType
from typing import ClassVar, Literal, Union, get_args, get_origin

from pydantic import BaseModel, Field, create_model

from ...capabilities import CapabilityRegistry
from ...capabilities.builtins import LogPlotSectionArtifact, ReportArtifact
from ...model.authoring import AuthoringDataSource
from ...model.intent import (
    AuthoringAnnotationIntent,
    AuthoringClearIntent,
    AuthoringCurveBindingIntent,
    AuthoringFillIntent,
    AuthoringHeaderFieldIntent,
    AuthoringHeaderIntent,
    AuthoringRasterBindingIntent,
    AuthoringRemarkIntent,
    AuthoringReportIntent,
    AuthoringSectionIntent,
    AuthoringServiceTitleIntent,
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
        component_id = component.component_id if component is not None else None
        children = (
            [item for item in plan.components if item.parent_component_id == component_id]
            if component_id is not None
            else []
        )
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
            canonical_model=AuthoringCurveBindingIntent | AuthoringRasterBindingIntent,
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
            canonical_model=AuthoringFillIntent,
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
            canonical_model=AuthoringAnnotationIntent,
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
    canonical_model: object,
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
        item_type = _construction_type(canonical_model) if reconstruct else canonical_model
        annotation = list[item_type] if reconstruct else list[item_type] | AuthoringClearIntent
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
    """Build exact curve/raster binding variants for one planned track."""
    grouped: dict[tuple[str, bool], list[SemanticComponentPlan]] = {}
    for item in children:
        if item.capability_id not in {"binding.curve", "binding.raster"}:
            continue
        identity = (item.capability_id, item.target_id not in existing_ids)
        grouped.setdefault(identity, []).append(item)

    models = []
    for (capability_id, requires_channel), items in grouped.items():
        base: type[BaseModel]
        base = (
            AuthoringCurveBindingIntent
            if capability_id == "binding.curve"
            else AuthoringRasterBindingIntent
        )
        if reconstruct:
            base = construction_model(base)
        fields: dict[str, object] = {
            "binding_id": (Literal[tuple(item.target_id for item in items)], ...),
            "section_id": (Literal[section_id], None),
            "track_id": (Literal[track_id], None),
        }
        if requires_channel:
            fields["channel"] = (str, Field(min_length=1))
        suffix = "New" if requires_channel else "Existing"
        models.append(
            create_model(
                f"{track_id}{capability_id.replace('.', '_')}{suffix}BindingIntent",
                __base__=base,
                **fields,
            )
        )
    return models


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
