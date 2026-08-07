###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
###############################################################################

"""Compatibility adapters for the canonical authoring contract.

The adapters deliberately sit outside the renderer and MCP layers.  Legacy
logfile YAML is normalized into typed authoring objects, while the original
layout is retained in an explicit compatibility extension until every legacy
render property has a first-class authoring field.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any, TextIO

import yaml
from pydantic import ValidationError

from .errors import TemplateValidationError
from .logfile import load_logfile, load_logfile_text
from .model import LogDocument
from .model.authoring import (
    AnnotationArrowSpec,
    AnnotationGlyphSpec,
    AnnotationIntervalSpec,
    AnnotationMarkerSpec,
    AnnotationTextSpec,
    ArrayTrackSpec,
    AuthoringCurveFillKind,
    AuthoringDataSource,
    AuthoringDepthSpec,
    AuthoringDocumentSpec,
    AuthoringGridDisplayMode,
    AuthoringGridScaleKind,
    AuthoringGridSpacingMode,
    AuthoringGridSpec,
    AuthoringPageSpec,
    AuthoringRasterNormalizationKind,
    AuthoringRasterProfileKind,
    AuthoringReferenceAxisKind,
    AuthoringRemarkSpec,
    AuthoringScale,
    AuthoringScaleKind,
    AuthoringSectionSpec,
    AuthoringStyle,
    AuthoringTrackHeaderObjectKind,
    AuthoringTrackHeaderObjectSpec,
    AuthoringTrackHeaderSpec,
    CurveBindingSpec,
    CurveFillSpec,
    NormalTrackSpec,
    RasterBindingSpec,
    ReferenceTrackSpec,
    TrackSpec,
)
from .templates import document_from_mapping


def _mapping(value: object, *, context: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TemplateValidationError(
            f"Expected a mapping for {context}, got {type(value).__name__}."
        )
    return dict(value)


def _sequence(value: object, *, context: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, Mapping)):
        raise TemplateValidationError(
            f"Expected a sequence for {context}, got {type(value).__name__}."
        )
    return list(value)


def _as_text(value: object, *, context: str, default: str | None = None) -> str | None:
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    return text


def _scale_from_mapping(value: object, *, context: str) -> AuthoringScale | None:
    if value is None:
        return None
    data = _mapping(value, context=context)
    kind = str(data.get("kind", "linear")).strip().lower()
    if kind == "logarithmic":
        kind = "log"
    if kind == "tangent":
        kind = "tangential"
    try:
        return AuthoringScale(
            kind=AuthoringScaleKind(kind),
            minimum=float(data.get("minimum", data.get("min", 0.0))),
            maximum=float(data.get("maximum", data.get("max", 1.0))),
            reverse=bool(data.get("reverse", False)),
            unit=_as_text(data.get("unit"), context=f"{context}.unit"),
        )
    except (TypeError, ValueError, ValidationError) as exc:
        raise TemplateValidationError(f"Invalid {context}.") from exc


def _style_from_mapping(value: object, *, context: str) -> AuthoringStyle:
    if value is None:
        return AuthoringStyle()
    data = _mapping(value, context=context)
    try:
        return AuthoringStyle(
            color=_as_text(data.get("color"), context=f"{context}.color"),
            line_style=str(data.get("line_style", "-")),
            line_width=float(data.get("line_width", 0.8)),
            alpha=float(data.get("alpha", data.get("opacity", 1.0))),
            fill_color=_as_text(data.get("fill_color"), context=f"{context}.fill_color"),
            fill_alpha=float(data.get("fill_alpha", 0.2)),
            colormap=str(data.get("colormap", "viridis")),
        )
    except (TypeError, ValueError, ValidationError) as exc:
        raise TemplateValidationError(f"Invalid {context}.") from exc


def _grid_display_mode(value: object, *, default: AuthoringGridDisplayMode) -> str:
    """Normalize legacy boolean and textual grid display values."""
    if value is None:
        return default.value
    if isinstance(value, bool):
        return (
            AuthoringGridDisplayMode.BELOW.value if value else AuthoringGridDisplayMode.NONE.value
        )
    aliases = {
        "below": AuthoringGridDisplayMode.BELOW.value,
        "under": AuthoringGridDisplayMode.BELOW.value,
        "above": AuthoringGridDisplayMode.ABOVE.value,
        "over": AuthoringGridDisplayMode.ABOVE.value,
        "none": AuthoringGridDisplayMode.NONE.value,
        "off": AuthoringGridDisplayMode.NONE.value,
        "hidden": AuthoringGridDisplayMode.NONE.value,
        "false": AuthoringGridDisplayMode.NONE.value,
    }
    normalized = aliases.get(str(value).strip().lower())
    if normalized is None:
        raise TemplateValidationError("Grid display must be below, above, or none.")
    return normalized


def _grid_scale_kind(value: object) -> str:
    """Normalize legacy aliases to one canonical grid scale value."""
    aliases = {
        "linear": AuthoringGridScaleKind.LINEAR.value,
        "log": AuthoringGridScaleKind.LOGARITHMIC.value,
        "logarithmic": AuthoringGridScaleKind.LOGARITHMIC.value,
        "exponential": AuthoringGridScaleKind.LOGARITHMIC.value,
        "tangent": AuthoringGridScaleKind.TANGENTIAL.value,
        "tangential": AuthoringGridScaleKind.TANGENTIAL.value,
    }
    normalized = aliases.get(str(value or "linear").strip().lower())
    if normalized is None:
        raise TemplateValidationError(
            "Grid scale must be linear, logarithmic/exponential, or tangential."
        )
    return normalized


def _grid_spacing_mode(value: object) -> str:
    """Normalize legacy count/manual and scale/auto spacing aliases."""
    aliases = {
        "count": AuthoringGridSpacingMode.COUNT.value,
        "manual": AuthoringGridSpacingMode.COUNT.value,
        "scale": AuthoringGridSpacingMode.SCALE.value,
        "auto": AuthoringGridSpacingMode.SCALE.value,
    }
    normalized = aliases.get(str(value or "count").strip().lower())
    if normalized is None:
        raise TemplateValidationError("Grid spacing must be count/manual or scale/auto.")
    return normalized


def _grid_from_legacy(value: object, *, context: str) -> AuthoringGridSpec:
    """Normalize the nested legacy grid envelope into canonical flat fields."""
    data = _mapping(value or {}, context=context)
    horizontal = _mapping(data.get("horizontal", {}), context=f"{context}.horizontal")
    vertical = _mapping(data.get("vertical", {}), context=f"{context}.vertical")
    horizontal_main = _mapping(horizontal.get("main", {}), context=f"{context}.horizontal.main")
    horizontal_secondary = _mapping(
        horizontal.get("secondary", {}), context=f"{context}.horizontal.secondary"
    )
    vertical_main = _mapping(vertical.get("main", {}), context=f"{context}.vertical.main")
    vertical_secondary = _mapping(
        vertical.get("secondary", {}), context=f"{context}.vertical.secondary"
    )

    major = bool(data.get("major", True))
    minor = bool(data.get("minor", True))
    major_alpha = float(data.get("major_alpha", 0.35))
    minor_alpha = float(data.get("minor_alpha", 0.15))
    global_display = _grid_display_mode(data.get("display"), default=AuthoringGridDisplayMode.BELOW)
    horizontal_display = _grid_display_mode(
        horizontal.get("display", global_display),
        default=AuthoringGridDisplayMode(global_display),
    )
    vertical_display = _grid_display_mode(
        vertical.get("display", global_display),
        default=AuthoringGridDisplayMode(global_display),
    )

    try:
        return AuthoringGridSpec(
            display=global_display,
            major=major,
            minor=minor,
            major_alpha=major_alpha,
            minor_alpha=minor_alpha,
            horizontal_display=horizontal_display,
            horizontal_major_visible=bool(horizontal_main.get("visible", major)),
            horizontal_minor_visible=bool(horizontal_secondary.get("visible", minor)),
            horizontal_major_color=_as_text(
                horizontal_main.get("color"), context=f"{context}.horizontal.main.color"
            ),
            horizontal_minor_color=_as_text(
                horizontal_secondary.get("color"),
                context=f"{context}.horizontal.secondary.color",
            ),
            horizontal_major_thickness=(
                float(horizontal_main["thickness"]) if "thickness" in horizontal_main else None
            ),
            horizontal_minor_thickness=(
                float(horizontal_secondary["thickness"])
                if "thickness" in horizontal_secondary
                else None
            ),
            horizontal_major_alpha=float(horizontal_main.get("alpha", major_alpha)),
            horizontal_minor_alpha=float(horizontal_secondary.get("alpha", minor_alpha)),
            vertical_display=vertical_display,
            vertical_main_visible=bool(vertical_main.get("visible", major)),
            vertical_main_line_count=int(vertical_main.get("line_count", 4)),
            vertical_main_thickness=(
                float(vertical_main["thickness"]) if "thickness" in vertical_main else None
            ),
            vertical_main_color=_as_text(
                vertical_main.get("color"), context=f"{context}.vertical.main.color"
            ),
            vertical_main_alpha=float(vertical_main.get("alpha", major_alpha)),
            vertical_main_scale=_grid_scale_kind(vertical_main.get("scale")),
            vertical_main_spacing_mode=_grid_spacing_mode(vertical_main.get("spacing_mode")),
            vertical_secondary_visible=bool(vertical_secondary.get("visible", minor)),
            vertical_secondary_line_count=int(vertical_secondary.get("line_count", 4)),
            vertical_secondary_thickness=(
                float(vertical_secondary["thickness"])
                if "thickness" in vertical_secondary
                else None
            ),
            vertical_secondary_color=_as_text(
                vertical_secondary.get("color"),
                context=f"{context}.vertical.secondary.color",
            ),
            vertical_secondary_alpha=float(vertical_secondary.get("alpha", minor_alpha)),
            vertical_secondary_scale=_grid_scale_kind(vertical_secondary.get("scale")),
            vertical_secondary_spacing_mode=_grid_spacing_mode(
                vertical_secondary.get("spacing_mode")
            ),
        )
    except (TypeError, ValueError, ValidationError) as exc:
        raise TemplateValidationError(f"Invalid {context}.") from exc


def authoring_grid_to_mapping(grid: AuthoringGridSpec) -> dict[str, Any]:
    """Project canonical grid fields to the renderer's nested YAML envelope."""
    values = grid.model_dump(mode="json", exclude_none=True)

    def horizontal_line(prefix: str) -> dict[str, Any]:
        return {
            "visible": values[f"{prefix}_visible"],
            **({"color": values[f"{prefix}_color"]} if f"{prefix}_color" in values else {}),
            **(
                {"thickness": values[f"{prefix}_thickness"]}
                if f"{prefix}_thickness" in values
                else {}
            ),
            **({"alpha": values[f"{prefix}_alpha"]} if f"{prefix}_alpha" in values else {}),
        }

    def vertical_line(prefix: str) -> dict[str, Any]:
        return {
            "visible": values[f"{prefix}_visible"],
            "line_count": values[f"{prefix}_line_count"],
            **({"color": values[f"{prefix}_color"]} if f"{prefix}_color" in values else {}),
            **(
                {"thickness": values[f"{prefix}_thickness"]}
                if f"{prefix}_thickness" in values
                else {}
            ),
            "alpha": values[f"{prefix}_alpha"],
            "scale": values[f"{prefix}_scale"],
            "spacing_mode": values[f"{prefix}_spacing_mode"],
        }

    return {
        "display": values["display"],
        "major": values["major"],
        "minor": values["minor"],
        "major_alpha": values["major_alpha"],
        "minor_alpha": values["minor_alpha"],
        "horizontal": {
            "display": values["horizontal_display"],
            "main": horizontal_line("horizontal_major"),
            "secondary": horizontal_line("horizontal_minor"),
        },
        "vertical": {
            "display": values["vertical_display"],
            "main": vertical_line("vertical_main"),
            "secondary": vertical_line("vertical_secondary"),
        },
    }


def _track_header_from_legacy(value: object, *, context: str) -> AuthoringTrackHeaderSpec:
    """Normalize legacy track-header rows into the canonical object list."""
    if value is None:
        return AuthoringTrackHeaderSpec()
    data = _mapping(value, context=context)
    objects_value = data.get("objects")
    if objects_value is not None:
        items = _sequence(objects_value, context=f"{context}.objects")
        objects: list[AuthoringTrackHeaderObjectSpec] = []
        for index, item in enumerate(items):
            object_data = _mapping(item, context=f"{context}.objects[{index}]")
            try:
                objects.append(
                    AuthoringTrackHeaderObjectSpec(
                        kind=AuthoringTrackHeaderObjectKind(str(object_data["kind"])),
                        enabled=bool(object_data.get("enabled", True)),
                        reserve_space=bool(object_data.get("reserve_space", True)),
                        line_units=int(object_data.get("line_units", 1)),
                    )
                )
            except (KeyError, TypeError, ValueError, ValidationError) as exc:
                raise TemplateValidationError(f"Invalid {context}.objects[{index}].") from exc
        try:
            return AuthoringTrackHeaderSpec(objects=objects)
        except ValidationError as exc:
            raise TemplateValidationError(f"Invalid {context}.") from exc

    defaults = AuthoringTrackHeaderSpec().objects
    by_kind = {item.kind: item for item in defaults}
    for kind in AuthoringTrackHeaderObjectKind:
        if kind.value not in data:
            continue
        object_data = _mapping(data[kind.value], context=f"{context}.{kind.value}")
        default = by_kind[kind]
        try:
            by_kind[kind] = AuthoringTrackHeaderObjectSpec(
                kind=kind,
                enabled=bool(object_data.get("enabled", default.enabled)),
                reserve_space=bool(object_data.get("reserve_space", default.reserve_space)),
                line_units=int(object_data.get("line_units", default.line_units)),
            )
        except (TypeError, ValueError, ValidationError) as exc:
            raise TemplateValidationError(f"Invalid {context}.{kind.value}.") from exc
    return AuthoringTrackHeaderSpec(objects=[by_kind[item.kind] for item in defaults])


def authoring_track_header_to_mapping(
    track_header: AuthoringTrackHeaderSpec,
) -> dict[str, Any]:
    """Project canonical track-header rows to the renderer YAML envelope."""
    return {
        "objects": [
            item.model_dump(mode="json", exclude_none=True) for item in track_header.objects
        ]
    }


def _track_kind(value: object) -> str:
    kind = str(value or "normal").strip().lower()
    aliases = {"depth": "reference", "curve": "normal", "image": "array"}
    normalized = aliases.get(kind, kind)
    if normalized not in {"reference", "normal", "array", "annotation"}:
        raise TemplateValidationError(f"Unsupported track kind {kind!r}.")
    return normalized


def _binding_id(
    binding: Mapping[str, Any],
    *,
    section_id: str,
    track_id: str,
    index: int,
    used: set[str],
) -> str:
    candidate = _as_text(binding.get("id"), context="binding.id")
    if candidate is None:
        channel = _as_text(binding.get("channel"), context="binding.channel", default="channel")
        candidate = f"{section_id}.{track_id}.{channel}.{index + 1}"
    original = candidate
    suffix = 2
    while candidate in used:
        candidate = f"{original}.{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _annotation_from_mapping(
    value: object,
    *,
    annotation_id: str,
    context: str,
) -> (
    AnnotationIntervalSpec
    | AnnotationTextSpec
    | AnnotationMarkerSpec
    | AnnotationArrowSpec
    | AnnotationGlyphSpec
):
    data = _mapping(value, context=context)
    kind = str(data.get("kind", "text")).strip().lower()
    try:
        if kind == "interval":
            return AnnotationIntervalSpec(
                annotation_id=annotation_id,
                top=float(data["top"]),
                base=float(data["base"]),
                text=str(data.get("text", "")),
            )
        if kind == "text":
            depth = data.get("depth")
            if depth is None:
                raise TemplateValidationError(f"{context}.depth is required for text annotations.")
            return AnnotationTextSpec(
                annotation_id=annotation_id,
                depth=float(depth),
                text=str(data["text"]),
            )
        if kind == "marker":
            return AnnotationMarkerSpec(
                annotation_id=annotation_id,
                depth=float(data["depth"]),
                shape=str(data.get("shape", "circle")),
                label=_as_text(data.get("label"), context=f"{context}.label"),
            )
        if kind == "arrow":
            return AnnotationArrowSpec(
                annotation_id=annotation_id,
                top=float(data["top"]),
                base=float(data["base"]),
                label=_as_text(data.get("label"), context=f"{context}.label"),
            )
        if kind == "glyph":
            return AnnotationGlyphSpec(
                annotation_id=annotation_id,
                depth=float(data["depth"]),
                glyph=str(data["glyph"]),
            )
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise TemplateValidationError(f"Invalid {context}.") from exc
    raise TemplateValidationError(f"Unsupported annotation kind {kind!r} at {context}.")


def _fill_from_mapping(
    value: object,
    *,
    binding_id: str,
    track_bindings: Sequence[tuple[int, Mapping[str, Any]]],
    binding_ids_by_index: Mapping[int, str],
    context: str,
) -> CurveFillSpec:
    """Normalize one legacy binding fill into a typed track-level relation."""
    data = _mapping(value, context=context)
    kind_text = str(data.get("kind", "")).strip().lower()
    try:
        kind = AuthoringCurveFillKind(kind_text)
    except ValueError as exc:
        raise TemplateValidationError(f"Unsupported fill kind {kind_text!r} at {context}.") from exc

    other_binding_id: str | None = None
    if kind in {
        AuthoringCurveFillKind.BETWEEN_CURVES,
        AuthoringCurveFillKind.BETWEEN_INSTANCES,
    }:
        other_element_id = _as_text(
            data.get("other_element_id"), context=f"{context}.other_element_id"
        )
        other_channel = _as_text(data.get("other_channel"), context=f"{context}.other_channel")
        if other_element_id is not None:
            for index, binding in track_bindings:
                if str(binding.get("id", "")).strip() == other_element_id:
                    other_binding_id = binding_ids_by_index[index]
                    break
        elif other_channel is not None:
            for index, binding in track_bindings:
                if str(binding.get("channel", "")).strip().upper() == other_channel.upper():
                    other_binding_id = binding_ids_by_index[index]
                    break
        if other_binding_id is None:
            raise TemplateValidationError(
                f"{context} must reference another binding on the same track."
            )

    baseline_value = data.get("baseline")
    baseline: float | None = None
    if kind == AuthoringCurveFillKind.BASELINE_SPLIT:
        if isinstance(baseline_value, Mapping):
            baseline_value = baseline_value.get("value")
        if baseline_value is None:
            raise TemplateValidationError(f"{context}.baseline.value is required.")
        try:
            baseline = float(baseline_value)
        except (TypeError, ValueError) as exc:
            raise TemplateValidationError(f"Invalid {context}.baseline value.") from exc

    return CurveFillSpec(
        kind=kind,
        binding_id=binding_id,
        other_binding_id=other_binding_id,
        baseline=baseline,
        extensions={"compatibility": {"legacy_fill": deepcopy(data)}},
    )


def _page_from_legacy(value: object) -> AuthoringPageSpec:
    data = _mapping(value or {}, context="document.page")
    page_kwargs: dict[str, Any] = {
        "size": _as_text(data.get("size"), context="document.page.size"),
        "orientation": str(data.get("orientation", "portrait")).strip().lower(),
        "continuous": bool(data.get("continuous", False)),
        "bottom_track_header_enabled": bool(data.get("bottom_track_header_enabled", True)),
    }
    for field in (
        "width_mm",
        "height_mm",
        "margin_left_mm",
        "margin_right_mm",
        "margin_top_mm",
        "margin_bottom_mm",
        "header_height_mm",
        "track_header_height_mm",
        "footer_height_mm",
        "track_gap_mm",
    ):
        if field in data:
            page_kwargs[field] = float(data[field])
    if page_kwargs["size"] is None and (
        "width_mm" not in page_kwargs or "height_mm" not in page_kwargs
    ):
        page_kwargs["size"] = "letter"
    try:
        return AuthoringPageSpec(**page_kwargs)
    except ValidationError as exc:
        raise TemplateValidationError("Invalid document.page.") from exc


def _remarks_from_legacy(value: object) -> list[AuthoringRemarkSpec]:
    remarks: list[AuthoringRemarkSpec] = []
    for index, item in enumerate(_sequence(value or [], context="document.layout.remarks")):
        data = _mapping(item, context=f"document.layout.remarks[{index}]")
        lines = [
            str(line)
            for line in _sequence(data.get("lines", []), context=f"remarks[{index}].lines")
        ]
        text = _as_text(data.get("text"), context=f"remarks[{index}].text")
        if text is None and not lines:
            raise TemplateValidationError(
                f"document.layout.remarks[{index}] must define text or lines."
            )
        remarks.append(
            AuthoringRemarkSpec(
                title=_as_text(data.get("title"), context=f"remarks[{index}].title"),
                text=text,
                lines=lines,
                alignment=str(data.get("alignment", "left")),
                font_size=(float(data["font_size"]) if data.get("font_size") is not None else None),
                title_font_size=(
                    float(data["title_font_size"])
                    if data.get("title_font_size") is not None
                    else None
                ),
                border=(bool(data["border"]) if "border" in data else None),
            )
        )
    return remarks


def _resolve_binding_section(
    binding: Mapping[str, Any],
    *,
    sections: dict[str, dict[str, Mapping[str, Any]]],
    track_sections: dict[str, list[str]],
    context: str,
) -> str:
    explicit = _as_text(binding.get("section"), context=f"{context}.section")
    track_id = _as_text(binding.get("track_id"), context=f"{context}.track_id")
    if track_id is None:
        raise TemplateValidationError(f"{context}.track_id must be non-empty.")
    if explicit is not None:
        if explicit not in sections or track_id not in sections[explicit]:
            raise TemplateValidationError(
                f"{context} does not identify an existing section and track."
            )
        return explicit
    candidates = track_sections.get(track_id, [])
    if len(candidates) != 1:
        joined = ", ".join(candidates) or "none"
        raise TemplateValidationError(
            f"{context}.track_id {track_id!r} is ambiguous across sections ({joined}); "
            "set section explicitly."
        )
    return candidates[0]


def _legacy_to_authoring(
    root: Mapping[str, Any], document: Mapping[str, Any]
) -> AuthoringDocumentSpec:
    layout = _mapping(document.get("layout"), context="document.layout")
    section_items = _sequence(
        layout.get("log_sections", []), context="document.layout.log_sections"
    )
    if not section_items:
        raise TemplateValidationError("document.layout.log_sections cannot be empty.")

    sections: dict[str, dict[str, Mapping[str, Any]]] = {}
    track_sections: dict[str, list[str]] = {}
    for index, item in enumerate(section_items):
        section = _mapping(item, context=f"document.layout.log_sections[{index}]")
        section_id = _as_text(section.get("id"), context=f"sections[{index}].id")
        if section_id is None:
            raise TemplateValidationError(f"document.layout.log_sections[{index}].id is required.")
        tracks = _sequence(section.get("tracks", []), context=f"sections[{section_id}].tracks")
        track_map: dict[str, Mapping[str, Any]] = {}
        for track_item in tracks:
            track = _mapping(track_item, context=f"sections[{section_id}].tracks")
            track_id = _as_text(track.get("id"), context="track.id")
            if track_id is None:
                raise TemplateValidationError(
                    f"Section {section_id!r} contains a track without id."
                )
            if track_id in track_map:
                raise TemplateValidationError(
                    f"Section {section_id!r} contains duplicate track ids."
                )
            track_map[track_id] = track
            track_sections.setdefault(track_id, []).append(section_id)
        sections[section_id] = track_map

    bindings_by_track: dict[tuple[str, str], list[tuple[int, Mapping[str, Any]]]] = {}
    binding_items = _sequence(
        _mapping(document.get("bindings", {}), context="document.bindings").get("channels", []),
        context="document.bindings.channels",
    )
    for index, item in enumerate(binding_items):
        binding = _mapping(item, context=f"document.bindings.channels[{index}]")
        section_id = _resolve_binding_section(
            binding,
            sections=sections,
            track_sections=track_sections,
            context=f"document.bindings.channels[{index}]",
        )
        track_id = str(binding["track_id"])
        bindings_by_track.setdefault((section_id, track_id), []).append((index, binding))

    used_binding_ids: set[str] = set()
    authoring_sections: list[AuthoringSectionSpec] = []
    for section_index, item in enumerate(section_items):
        section = _mapping(item, context=f"document.layout.log_sections[{section_index}]")
        section_id = str(section["id"])
        authoring_tracks: list[TrackSpec] = []
        for track_index, track_item in enumerate(
            _sequence(section["tracks"], context="section.tracks")
        ):
            track = _mapping(track_item, context=f"section {section_id} track {track_index}")
            track_id = str(track["id"])
            kind = _track_kind(track.get("kind", "normal"))
            canonical_bindings: list[CurveBindingSpec | RasterBindingSpec] = []
            track_bindings = bindings_by_track.get((section_id, track_id), [])
            binding_ids_by_index: dict[int, str] = {}
            for binding_index, binding in track_bindings:
                channel = _as_text(binding.get("channel"), context="binding.channel")
                if channel is None:
                    raise TemplateValidationError("Binding channel must be non-empty.")
                binding_id = _binding_id(
                    binding,
                    section_id=section_id,
                    track_id=track_id,
                    index=binding_index,
                    used=used_binding_ids,
                )
                binding_ids_by_index[binding_index] = binding_id
                extension = {"compatibility": {"legacy_binding": deepcopy(binding)}}
                element_kind = str(binding.get("kind", "curve")).strip().lower()
                if element_kind == "curve":
                    canonical_bindings.append(
                        CurveBindingSpec(
                            binding_id=binding_id,
                            channel=channel,
                            label=_as_text(binding.get("label"), context="binding.label"),
                            scale=_scale_from_mapping(
                                binding.get("scale"), context="binding.scale"
                            ),
                            style=_style_from_mapping(
                                binding.get("style"), context="binding.style"
                            ),
                            extensions=extension,
                        )
                    )
                elif element_kind == "raster":
                    try:
                        profile = AuthoringRasterProfileKind(
                            str(binding.get("profile", "generic")).strip().lower()
                        )
                        normalization = AuthoringRasterNormalizationKind(
                            str(binding.get("normalization", "auto")).strip().lower()
                        )
                        canonical_bindings.append(
                            RasterBindingSpec(
                                binding_id=binding_id,
                                channel=channel,
                                label=_as_text(binding.get("label"), context="binding.label"),
                                style=_style_from_mapping(
                                    binding.get("style"), context="binding.style"
                                ),
                                profile=profile,
                                normalization=normalization,
                                alpha=float(binding.get("raster_alpha", 1.0)),
                                extensions=extension,
                            )
                        )
                    except (TypeError, ValueError, ValidationError) as exc:
                        raise TemplateValidationError(
                            "Invalid raster binding at "
                            f"document.bindings.channels[{binding_index}]."
                        ) from exc
                else:
                    raise TemplateValidationError(f"Unsupported binding kind {element_kind!r}.")

            annotation_models = []
            for annotation_index, annotation in enumerate(
                _sequence(track.get("annotations", []), context=f"track {track_id}.annotations")
            ):
                annotation_models.append(
                    _annotation_from_mapping(
                        annotation,
                        annotation_id=f"{section_id}.{track_id}.annotation.{annotation_index + 1}",
                        context=f"track {track_id}.annotations[{annotation_index}]",
                    )
                )
            canonical_fills: list[CurveFillSpec] = []
            if kind == "normal":
                for binding_index, binding in track_bindings:
                    fill = binding.get("fill")
                    if fill is None:
                        continue
                    canonical_fills.append(
                        _fill_from_mapping(
                            fill,
                            binding_id=binding_ids_by_index[binding_index],
                            track_bindings=track_bindings,
                            binding_ids_by_index=binding_ids_by_index,
                            context=(f"document.bindings.channels[{binding_index}].fill"),
                        )
                    )

            extensions = {"compatibility": {"legacy_track": deepcopy(track)}}
            common = {
                "id": track_id,
                "title": _as_text(track.get("title"), context="track.title", default=track_id),
                "width_mm": float(track["width_mm"]),
                "grid": _grid_from_legacy(track.get("grid"), context=f"track {track_id}.grid"),
                "track_header": _track_header_from_legacy(
                    track.get("track_header"), context=f"track {track_id}.track_header"
                ),
                "extensions": extensions,
            }
            x_scale = _scale_from_mapping(track.get("x_scale"), context=f"track {track_id}.x_scale")
            if kind == "normal":
                authoring_tracks.append(
                    NormalTrackSpec(
                        **common,
                        x_scale=x_scale,
                        fills=canonical_fills,
                        bindings=[
                            item
                            for item in canonical_bindings
                            if isinstance(item, CurveBindingSpec)
                        ],
                    )
                )
            elif kind == "reference":
                reference = _mapping(
                    track.get("reference", {}), context=f"track {track_id}.reference"
                )
                axis = AuthoringReferenceAxisKind(str(reference.get("axis", "depth")).lower())
                authoring_tracks.append(
                    ReferenceTrackSpec(
                        **common,
                        axis=axis,
                        bindings=[
                            item
                            for item in canonical_bindings
                            if isinstance(item, CurveBindingSpec)
                        ],
                    )
                )
            elif kind == "array":
                authoring_tracks.append(ArrayTrackSpec(**common, bindings=canonical_bindings))
            else:
                from .model.authoring import AnnotationTrackSpec

                authoring_tracks.append(
                    AnnotationTrackSpec(**common, annotations=annotation_models)
                )

        data = _mapping(section.get("data", {}), context=f"section {section_id}.data")
        source_path = _as_text(
            data.get("source_path"), context=f"section {section_id}.data.source_path"
        )
        data_source = (
            AuthoringDataSource(
                source_path=source_path,
                source_format=str(data.get("source_format", "auto")).lower(),
            )
            if source_path is not None
            else None
        )
        depth_range_value = section.get("depth_range")
        depth_range = None
        if depth_range_value is not None:
            values = _sequence(depth_range_value, context=f"section {section_id}.depth_range")
            if len(values) != 2:
                raise TemplateValidationError(
                    f"Section {section_id!r} depth_range must contain two values."
                )
            depth_range = (float(values[0]), float(values[1]))
        authoring_sections.append(
            AuthoringSectionSpec(
                id=section_id,
                title=_as_text(section.get("title"), context="section.title", default=section_id),
                subtitle=_as_text(section.get("subtitle"), context="section.subtitle"),
                depth_range=depth_range,
                data_source=data_source,
                tracks=authoring_tracks,
            )
        )

    depth = _mapping(document.get("depth", {}), context="document.depth")
    page = _page_from_legacy(document.get("page", {}))
    heading = _mapping(layout.get("heading", {}), context="document.layout.heading")
    title = _as_text(heading.get("title"), context="heading.title")
    subtitle = _as_text(heading.get("subtitle"), context="heading.subtitle")
    extension = {
        "compatibility": {
            "format": "wellplot-logfile-v1",
            "legacy_document": deepcopy(document),
            "legacy_render": deepcopy(root.get("render", {})),
            "legacy_data": deepcopy(root.get("data")),
        }
    }
    try:
        return AuthoringDocumentSpec(
            name=str(root.get("name", "well-log")),
            title=title,
            subtitle=subtitle,
            page=page,
            depth=AuthoringDepthSpec(
                unit=str(depth.get("unit", "m")),
                scale=depth.get("scale", depth.get("scale_ratio", 200)),
                major_step=(
                    float(depth["major_step"]) if depth.get("major_step") is not None else None
                ),
                minor_step=(
                    float(depth["minor_step"]) if depth.get("minor_step") is not None else None
                ),
            ),
            sections=authoring_sections,
            remarks=_remarks_from_legacy(layout.get("remarks", [])),
            extensions=extension,
        )
    except ValidationError as exc:
        raise TemplateValidationError(
            "Legacy logfile could not be normalized to the authoring contract."
        ) from exc


def authoring_document_from_mapping(data: Mapping[str, object]) -> AuthoringDocumentSpec:
    """Normalize canonical or legacy logfile mappings into an authoring model."""
    root = _mapping(data, context="authoring document")
    document_value = root.get("document")
    if document_value is not None:
        document = _mapping(document_value, context="document")
        if "sections" in document:
            canonical = deepcopy(document)
            canonical.setdefault("name", root.get("name", "well-log"))
            try:
                return AuthoringDocumentSpec.model_validate(canonical)
            except ValidationError as exc:
                raise TemplateValidationError("Invalid canonical authoring document.") from exc
        if "layout" in document:
            return _legacy_to_authoring(root, document)
    if "sections" in root:
        try:
            return AuthoringDocumentSpec.model_validate(root)
        except ValidationError as exc:
            raise TemplateValidationError("Invalid canonical authoring document.") from exc
    if "layout" in root:
        return _legacy_to_authoring(root, root)
    raise TemplateValidationError("Authoring document must define sections or a legacy layout.")


def _is_canonical_mapping(data: Mapping[str, Any]) -> bool:
    """Return whether a YAML envelope contains canonical authoring sections."""
    document = data.get("document")
    return "sections" in data or (isinstance(document, Mapping) and "sections" in document)


def authoring_document_to_mapping(document: AuthoringDocumentSpec) -> dict[str, object]:
    """Serialize an authoring model to normalized version-1 YAML data."""
    document_payload = document.model_dump(mode="json", exclude_none=True)
    name = str(document_payload.pop("name"))
    payload: dict[str, object] = {"version": 1, "name": name, "document": document_payload}
    compatibility = document.extensions.get("compatibility")
    if isinstance(compatibility, Mapping):
        for key in ("legacy_render", "legacy_data"):
            value = compatibility.get(key)
            if value is not None:
                payload[key.removeprefix("legacy_")] = deepcopy(value)
    return payload


def authoring_document_to_yaml(
    document: AuthoringDocumentSpec,
    destination: str | Path | TextIO | None = None,
) -> str | None:
    """Serialize an authoring model to YAML text or a destination."""
    text = yaml.safe_dump(authoring_document_to_mapping(document), sort_keys=False)
    if destination is None:
        return text
    if hasattr(destination, "write"):
        destination.write(text)
        return None
    Path(destination).write_text(text, encoding="utf-8")
    return None


def _legacy_track(
    document: AuthoringDocumentSpec, section_id: str, track_id: str
) -> dict[str, Any]:
    compatibility = document.extensions.get("compatibility", {})
    legacy_document = (
        compatibility.get("legacy_document") if isinstance(compatibility, Mapping) else None
    )
    if not isinstance(legacy_document, Mapping):
        return {}
    layout = legacy_document.get("layout")
    if not isinstance(layout, Mapping):
        return {}
    for item in layout.get("log_sections", []):
        if not isinstance(item, Mapping) or str(item.get("id")) != section_id:
            continue
        for track in item.get("tracks", []):
            if isinstance(track, Mapping) and str(track.get("id")) == track_id:
                return deepcopy(dict(track))
    return {}


def _binding_legacy_data(binding: CurveBindingSpec | RasterBindingSpec) -> dict[str, Any]:
    compatibility = binding.extensions.get("compatibility")
    if isinstance(compatibility, Mapping) and isinstance(
        compatibility.get("legacy_binding"), Mapping
    ):
        return deepcopy(dict(compatibility["legacy_binding"]))
    return {}


def _binding_element(binding: CurveBindingSpec | RasterBindingSpec) -> dict[str, Any]:
    element = _binding_legacy_data(binding)
    element.update(
        {
            "kind": binding.kind,
            "id": binding.binding_id,
            "channel": binding.channel,
            "label": binding.label or binding.channel,
            "style": binding.style.model_dump(mode="json", exclude_none=True),
        }
    )
    if isinstance(binding, CurveBindingSpec):
        if binding.scale is not None:
            element["scale"] = binding.scale.model_dump(mode="json", exclude_none=True)
    else:
        element.update(
            {
                "profile": binding.profile.value,
                "normalization": binding.normalization.value,
                "raster_alpha": binding.alpha,
            }
        )
    return element


def _fill_element(fill: CurveFillSpec) -> dict[str, Any]:
    """Project one canonical fill to the legacy binding-level shape."""
    compatibility = fill.extensions.get("compatibility")
    legacy_fill = (
        deepcopy(dict(compatibility["legacy_fill"]))
        if isinstance(compatibility, Mapping)
        and isinstance(compatibility.get("legacy_fill"), Mapping)
        else {}
    )
    legacy_fill["kind"] = fill.kind.value
    if fill.other_binding_id is not None:
        legacy_fill.setdefault("other_element_id", fill.other_binding_id)
    if fill.baseline is not None:
        baseline = legacy_fill.get("baseline")
        if isinstance(baseline, Mapping):
            baseline = deepcopy(dict(baseline))
            baseline["value"] = fill.baseline
            legacy_fill["baseline"] = baseline
        else:
            legacy_fill["baseline"] = {"value": fill.baseline}
    return legacy_fill


def _render_track(
    document: AuthoringDocumentSpec, section_id: str, track: TrackSpec
) -> dict[str, Any]:
    payload = _legacy_track(document, section_id, track.id)
    payload.update(
        {
            "id": track.id,
            "title": track.title,
            "kind": track.kind,
            "width_mm": track.width_mm,
            "grid": authoring_grid_to_mapping(track.grid),
            "track_header": authoring_track_header_to_mapping(track.track_header),
            "elements": [],
        }
    )
    if getattr(track, "x_scale", None) is not None:
        payload["x_scale"] = track.x_scale.model_dump(mode="json", exclude_none=True)
    bindings = getattr(track, "bindings", ())
    payload["elements"] = [_binding_element(binding) for binding in bindings]
    if isinstance(track, NormalTrackSpec):
        elements_by_id = {
            str(element.get("id")): element
            for element in payload["elements"]
            if isinstance(element, dict)
        }
        for fill in track.fills:
            target = elements_by_id.get(fill.binding_id)
            if target is not None:
                target["fill"] = _fill_element(fill)
    if hasattr(track, "annotations"):
        payload["annotations"] = [
            annotation.model_dump(mode="json", exclude={"annotation_id"}, exclude_none=True)
            for annotation in track.annotations
        ]
    return payload


def authoring_document_to_render(document: AuthoringDocumentSpec) -> LogDocument:
    """Convert a validated authoring model into the existing render model."""
    compatibility = document.extensions.get("compatibility", {})
    legacy_document = (
        compatibility.get("legacy_document") if isinstance(compatibility, Mapping) else None
    )
    payload: dict[str, Any] = {}
    if isinstance(legacy_document, Mapping):
        for key in ("header", "footer", "markers", "zones", "metadata"):
            if key in legacy_document:
                payload[key] = deepcopy(legacy_document[key])
        layout = legacy_document.get("layout")
        if isinstance(layout, Mapping):
            metadata = _mapping(payload.get("metadata", {}), context="document.metadata")
            layout_sections = _mapping(
                metadata.get("layout_sections", {}), context="metadata.layout_sections"
            )
            layout_sections["heading"] = deepcopy(layout.get("heading", {}))
            layout_sections["remarks"] = [
                remark.model_dump(mode="json", exclude_none=True) for remark in document.remarks
            ]
            layout_sections["log_sections"] = deepcopy(layout.get("log_sections", []))
            layout_sections["tail"] = deepcopy(layout.get("tail", {}))
            payload["metadata"] = {**metadata, "layout_sections": layout_sections}
            heading = _mapping(layout.get("heading", {}), context="document.layout.heading")
            if heading and "report" not in payload.get("header", {}):
                payload["header"] = {
                    **_mapping(payload.get("header", {}), context="document.header"),
                    "report": heading,
                }
    metadata = _mapping(payload.get("metadata", {}), context="document.metadata")
    layout_sections = _mapping(
        metadata.get("layout_sections", {}), context="metadata.layout_sections"
    )
    layout_sections["remarks"] = [
        remark.model_dump(mode="json", exclude_none=True) for remark in document.remarks
    ]
    layout_sections["log_sections"] = [
        {
            "id": section.id,
            "title": section.title,
            "subtitle": section.subtitle,
            **(
                {"depth_range": list(section.depth_range)}
                if section.depth_range is not None
                else {}
            ),
        }
        for section in document.sections
    ]
    metadata["layout_sections"] = layout_sections
    payload["metadata"] = metadata
    if document.title is not None or document.subtitle is not None:
        header = _mapping(payload.get("header", {}), context="document.header")
        if document.title is not None:
            header["title"] = document.title
        if document.subtitle is not None:
            header["subtitle"] = document.subtitle
        payload["header"] = header
    payload.update(
        {
            "name": document.name,
            "page": document.page.model_dump(mode="json", exclude_none=True),
            "depth": {
                "unit": document.depth.unit,
                "scale": document.depth.scale,
                "major_step": document.depth.major_step,
                "minor_step": document.depth.minor_step,
            },
            "tracks": [
                {
                    "id": section.id,
                    "title": section.title,
                    "kind": "normal",
                    "width_mm": 1,
                    "elements": [],
                }
                for section in document.sections
            ],
        }
    )
    # A render document represents one section. Use the first section because
    # multi-section logfile rendering already owns section iteration.
    section = document.sections[0]
    payload["name"] = document.name
    payload["tracks"] = [_render_track(document, section.id, track) for track in section.tracks]
    if section.depth_range is not None:
        payload["depth_range"] = list(section.depth_range)
    return document_from_mapping(payload)


def load_authoring_document(
    path: str | Path, *, allowed_root: Path | None = None
) -> AuthoringDocumentSpec:
    """Load a canonical or legacy logfile YAML file into the authoring model."""
    file_path = Path(path).expanduser().resolve()
    if allowed_root is not None:
        try:
            file_path.relative_to(Path(allowed_root).expanduser().resolve())
        except ValueError as exc:
            raise TemplateValidationError(
                f"authoring document must resolve inside {Path(allowed_root).resolve()}."
            ) from exc
    raw = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, Mapping):
        raise TemplateValidationError("Authoring YAML root must be a mapping.")
    if _is_canonical_mapping(raw):
        return authoring_document_from_mapping(raw)
    logfile = load_logfile(path, allowed_root=allowed_root)
    root: dict[str, Any] = {
        "version": 1,
        "name": logfile.name,
        "render": {
            "backend": logfile.render_backend,
            "output_path": logfile.render_output_path,
            "dpi": logfile.render_dpi,
            "continuous_strip_page_height_mm": logfile.render_continuous_strip_page_height_mm,
            "matplotlib": logfile.render_matplotlib,
        },
        "document": logfile.document,
    }
    return authoring_document_from_mapping(root)


def load_authoring_document_text(
    yaml_text: str,
    *,
    base_dir: str | Path | None = None,
    allowed_root: Path | None = None,
) -> AuthoringDocumentSpec:
    """Load YAML text into the canonical authoring model with template support."""
    raw = yaml.safe_load(yaml_text) or {}
    if not isinstance(raw, Mapping):
        raise TemplateValidationError("Authoring YAML root must be a mapping.")
    if _is_canonical_mapping(raw):
        return authoring_document_from_mapping(raw)
    logfile = load_logfile_text(yaml_text, base_dir=base_dir, allowed_root=allowed_root)
    return authoring_document_from_mapping(
        {
            "version": 1,
            "name": logfile.name,
            "render": {
                "backend": logfile.render_backend,
                "output_path": logfile.render_output_path,
                "dpi": logfile.render_dpi,
                "continuous_strip_page_height_mm": logfile.render_continuous_strip_page_height_mm,
                "matplotlib": logfile.render_matplotlib,
            },
            "document": logfile.document,
        }
    )


__all__ = [
    "authoring_document_from_mapping",
    "authoring_document_to_mapping",
    "authoring_document_to_render",
    "authoring_document_to_yaml",
    "load_authoring_document",
    "load_authoring_document_text",
]
