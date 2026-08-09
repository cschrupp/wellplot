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
    AuthoringCurveCalloutSpec,
    AuthoringCurveFillBaselineSpec,
    AuthoringCurveFillCrossoverSpec,
    AuthoringCurveFillKind,
    AuthoringCurveHeaderDisplaySpec,
    AuthoringCurveValueLabelsSpec,
    AuthoringDataSource,
    AuthoringDepthSpec,
    AuthoringDocumentSpec,
    AuthoringGridDisplayMode,
    AuthoringGridScaleKind,
    AuthoringGridSpacingMode,
    AuthoringGridSpec,
    AuthoringHeaderDetailCellSpec,
    AuthoringHeaderDetailColumnSpec,
    AuthoringHeaderDetailRowSpec,
    AuthoringHeaderDetailSpec,
    AuthoringHeaderFieldSpec,
    AuthoringHeaderSpec,
    AuthoringNumberFormatKind,
    AuthoringOutputSpec,
    AuthoringPageSpec,
    AuthoringRasterColorbarSpec,
    AuthoringRasterNormalizationKind,
    AuthoringRasterProfileKind,
    AuthoringRasterSampleAxisSpec,
    AuthoringRasterWaveformSpec,
    AuthoringReferenceAxisKind,
    AuthoringReferenceEventSpec,
    AuthoringReferenceOverlaySpec,
    AuthoringRemarkSpec,
    AuthoringReportValueSpec,
    AuthoringScale,
    AuthoringScaleKind,
    AuthoringSectionSpec,
    AuthoringServiceTitleSpec,
    AuthoringStyle,
    AuthoringTailSpec,
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


def _reference_overlay_from_legacy(
    value: object,
    *,
    context: str,
) -> AuthoringReferenceOverlaySpec | None:
    """Normalize one legacy reference-overlay mapping into a typed object."""
    if value is None:
        return None
    data = _mapping(value, context=context)
    try:
        return AuthoringReferenceOverlaySpec.model_validate(data)
    except ValidationError as exc:
        raise TemplateValidationError(f"Invalid {context}.") from exc


def authoring_reference_overlay_to_mapping(
    overlay: AuthoringReferenceOverlaySpec,
) -> dict[str, Any]:
    """Project a canonical reference overlay to its legacy YAML envelope."""
    return overlay.model_dump(mode="json", exclude_none=True)


def _reference_events_from_legacy(
    value: object,
    *,
    context: str,
) -> list[AuthoringReferenceEventSpec]:
    """Normalize legacy reference events into typed canonical objects."""
    if value is None:
        return []
    items = _sequence(value, context=context)
    try:
        return [AuthoringReferenceEventSpec.model_validate(item) for item in items]
    except ValidationError as exc:
        raise TemplateValidationError(f"Invalid {context}.") from exc


def authoring_reference_events_to_mapping(
    events: Sequence[AuthoringReferenceEventSpec],
) -> list[dict[str, Any]]:
    """Project typed reference events to the renderer's event list."""
    return [event.model_dump(mode="json", exclude_none=True) for event in events]


def authoring_reference_track_to_mapping(track: ReferenceTrackSpec) -> dict[str, Any]:
    """Project a typed reference track to the renderer's nested envelope."""
    return {
        "axis": track.axis.value,
        "define_layout": track.define_layout,
        **({"unit": track.unit} if track.unit is not None else {}),
        **({"scale_ratio": track.scale_ratio} if track.scale_ratio is not None else {}),
        **({"major_step": track.major_step} if track.major_step is not None else {}),
        **({"minor_step": track.minor_step} if track.minor_step is not None else {}),
        "secondary_grid": {
            "display": track.secondary_grid_display,
            "line_count": track.secondary_grid_line_count,
        },
        "header": {
            "display_unit": track.display_unit_in_header,
            "display_scale": track.display_scale_in_header,
            "display_annotations": track.display_annotations_in_header,
        },
        "number_format": {
            "format": track.number_format.value,
            "precision": track.precision,
        },
        "values_orientation": track.values_orientation,
        "events": authoring_reference_events_to_mapping(track.events),
    }


def _curve_callouts_from_legacy(
    value: object,
    *,
    context: str,
) -> list[AuthoringCurveCalloutSpec]:
    """Normalize legacy curve callouts into typed binding-owned objects."""
    if value is None:
        return []
    items = _sequence(value, context=context)
    try:
        return [AuthoringCurveCalloutSpec.model_validate(item) for item in items]
    except ValidationError as exc:
        raise TemplateValidationError(f"Invalid {context}.") from exc


def authoring_curve_callouts_to_mapping(
    callouts: Sequence[AuthoringCurveCalloutSpec],
) -> list[dict[str, Any]]:
    """Project typed curve callouts to the legacy binding envelope."""
    return [item.model_dump(mode="json", exclude_none=True) for item in callouts]


def _raster_colorbar_from_legacy(
    value: object,
    *,
    context: str,
) -> AuthoringRasterColorbarSpec:
    """Normalize a legacy boolean or mapping colorbar setting."""
    if value is None:
        return AuthoringRasterColorbarSpec()
    data: dict[str, Any] = (
        {"enabled": value} if isinstance(value, bool) else _mapping(value, context=context)
    )
    try:
        return AuthoringRasterColorbarSpec.model_validate(data)
    except ValidationError as exc:
        raise TemplateValidationError(f"Invalid {context}.") from exc


def authoring_raster_colorbar_to_mapping(
    colorbar: AuthoringRasterColorbarSpec,
) -> dict[str, Any]:
    """Project canonical colorbar settings to the legacy YAML envelope."""
    return colorbar.model_dump(mode="json", exclude_none=True)


def _raster_sample_axis_from_legacy(
    value: object,
    *,
    context: str,
) -> AuthoringRasterSampleAxisSpec:
    """Normalize a legacy boolean or mapping sample-axis setting."""
    if value is None:
        return AuthoringRasterSampleAxisSpec()
    if isinstance(value, bool):
        data: dict[str, Any] = {"enabled": value}
    else:
        data = _mapping(value, context=context)
        if "min" in data:
            data["minimum"] = data.pop("min")
        if "max" in data:
            data["maximum"] = data.pop("max")
        if "ticks" in data:
            data["tick_count"] = data.pop("ticks")
    try:
        return AuthoringRasterSampleAxisSpec.model_validate(data)
    except ValidationError as exc:
        raise TemplateValidationError(f"Invalid {context}.") from exc


def authoring_raster_sample_axis_to_mapping(
    sample_axis: AuthoringRasterSampleAxisSpec,
) -> dict[str, Any]:
    """Project canonical sample-axis settings to the legacy YAML envelope."""
    data = sample_axis.model_dump(mode="json", exclude_none=True)
    minimum = data.pop("minimum", None)
    maximum = data.pop("maximum", None)
    if minimum is not None:
        data["min"] = minimum
    if maximum is not None:
        data["max"] = maximum
    data["ticks"] = data.pop("tick_count")
    return data


def _raster_waveform_from_legacy(
    value: object,
    *,
    context: str,
) -> AuthoringRasterWaveformSpec:
    """Normalize a legacy boolean or mapping waveform setting."""
    if value is None:
        return AuthoringRasterWaveformSpec()
    if isinstance(value, bool):
        data: dict[str, Any] = {"enabled": value}
    else:
        data = _mapping(value, context=context)
    try:
        return AuthoringRasterWaveformSpec.model_validate(data)
    except ValidationError as exc:
        raise TemplateValidationError(f"Invalid {context}.") from exc


def authoring_raster_waveform_to_mapping(
    waveform: AuthoringRasterWaveformSpec,
) -> dict[str, Any]:
    """Project canonical waveform settings to the legacy YAML envelope."""
    return waveform.model_dump(mode="json", exclude_none=True)


def _curve_header_display_from_legacy(
    value: object,
    *,
    context: str,
) -> AuthoringCurveHeaderDisplaySpec:
    """Normalize legacy curve-header visibility settings."""
    if value is None:
        return AuthoringCurveHeaderDisplaySpec()
    data = _mapping(value, context=context)
    try:
        return AuthoringCurveHeaderDisplaySpec.model_validate(data)
    except ValidationError as exc:
        raise TemplateValidationError(f"Invalid {context}.") from exc


def _curve_value_labels_from_legacy(
    value: object,
    *,
    context: str,
) -> AuthoringCurveValueLabelsSpec:
    """Normalize legacy value-label settings and common number-format aliases."""
    if value is None:
        return AuthoringCurveValueLabelsSpec()
    data = _mapping(value, context=context)
    format_value = str(data.get("format", "automatic")).strip().lower()
    data["format"] = {
        "auto": "automatic",
        "automatic": "automatic",
        "fixed": "fixed",
        "scientific": "scientific",
        "concise": "concise",
    }.get(format_value, format_value)
    try:
        return AuthoringCurveValueLabelsSpec.model_validate(data)
    except ValidationError as exc:
        raise TemplateValidationError(f"Invalid {context}.") from exc


def authoring_curve_header_display_to_mapping(
    display: AuthoringCurveHeaderDisplaySpec,
) -> dict[str, Any]:
    """Project canonical curve-header visibility settings to YAML."""
    return display.model_dump(mode="json", exclude_none=True)


def authoring_curve_value_labels_to_mapping(
    labels: AuthoringCurveValueLabelsSpec,
) -> dict[str, Any]:
    """Project canonical curve value-label settings to YAML."""
    return labels.model_dump(mode="json", exclude_none=True)


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
    data["kind"] = kind
    data["annotation_id"] = annotation_id
    if kind == "arrow":
        if "start_depth" not in data and "top" in data:
            data["start_depth"] = data.pop("top")
        if "end_depth" not in data and "base" in data:
            data["end_depth"] = data.pop("base")
        data.setdefault("start_x", 0.5)
        data.setdefault("end_x", 0.5)
    try:
        if kind == "interval":
            return AnnotationIntervalSpec.model_validate(data)
        if kind == "text":
            return AnnotationTextSpec.model_validate(data)
        if kind == "marker":
            return AnnotationMarkerSpec.model_validate(data)
        if kind == "arrow":
            return AnnotationArrowSpec.model_validate(data)
        if kind == "glyph":
            return AnnotationGlyphSpec.model_validate(data)
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
    baseline: AuthoringCurveFillBaselineSpec | None = None
    if kind == AuthoringCurveFillKind.BASELINE_SPLIT:
        if isinstance(baseline_value, Mapping):
            baseline_data = dict(baseline_value)
        else:
            baseline_data = {"value": baseline_value}
        baseline_value = baseline_data.get("value")
        if baseline_value is None:
            raise TemplateValidationError(f"{context}.baseline.value is required.")
        try:
            baseline = AuthoringCurveFillBaselineSpec.model_validate(baseline_data)
        except (TypeError, ValueError, ValidationError) as exc:
            raise TemplateValidationError(f"Invalid {context}.baseline value.") from exc

    try:
        crossover = AuthoringCurveFillCrossoverSpec.model_validate(data.get("crossover", {}))
    except ValidationError as exc:
        raise TemplateValidationError(f"Invalid {context}.crossover.") from exc

    return CurveFillSpec(
        kind=kind,
        binding_id=binding_id,
        other_binding_id=other_binding_id,
        baseline=baseline,
        label=_as_text(data.get("label"), context=f"{context}.label"),
        color=_as_text(data.get("color"), context=f"{context}.color"),
        alpha=(float(data["alpha"]) if data.get("alpha") is not None else None),
        crossover=crossover,
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


def _header_literal(value: object) -> str | None:
    """Preserve explicit empty header values while normalizing other literals."""
    if value is None:
        return None
    return str(value)


def _report_value_from_legacy(
    value: object,
    *,
    context: str,
    source_key: object = None,
    default: object = "",
    unit: object = None,
) -> AuthoringReportValueSpec:
    """Normalize one legacy report value into a typed authoring value."""
    data: dict[str, Any]
    if isinstance(value, Mapping):
        data = dict(value)
    elif value is None:
        data = {}
    else:
        data = {"value": value}
    resolved_source_key = data.get("source_key", source_key)
    resolved_default = data.get("default", default)
    resolved_unit = data.get("unit", unit)
    literal = _header_literal(data.get("value")) if "value" in data else None
    try:
        return AuthoringReportValueSpec(
            value=literal,
            source_key=_as_text(resolved_source_key, context=f"{context}.source_key"),
            default=str(resolved_default or ""),
            unit=_as_text(resolved_unit, context=f"{context}.unit"),
            provenance=str(
                data.get("provenance", "preserved" if literal is not None else "unknown")
            ).lower(),
            availability=str(
                data.get("availability", "available" if literal is not None else "unknown")
            ).lower(),
        )
    except (TypeError, ValueError, ValidationError) as exc:
        raise TemplateValidationError(f"Invalid {context}.") from exc


def _header_cell_from_legacy(
    value: object,
    *,
    slot_id: str,
    context: str,
) -> AuthoringHeaderDetailCellSpec:
    """Normalize one detail-table cell and assign a stable slot id."""
    data = dict(value) if isinstance(value, Mapping) else {}
    report_value = _report_value_from_legacy(value, context=context)
    if isinstance(value, Mapping):
        slot_id = str(data.get("slot_id", slot_id))
    return AuthoringHeaderDetailCellSpec(slot_id=slot_id, value=report_value)


def _header_from_legacy(value: object) -> AuthoringHeaderSpec | None:
    """Normalize a legacy heading mapping into stable typed header slots."""
    if value is None:
        return None
    heading = _mapping(value, context="document.layout.heading")
    if not heading:
        return None

    fields: list[AuthoringHeaderFieldSpec] = []
    for index, item in enumerate(
        _sequence(heading.get("general_fields", []), context="heading.general_fields")
    ):
        data = _mapping(item, context=f"heading.general_fields[{index}]")
        key = str(data.get("key", f"field_{index + 1}")).strip()
        label = str(data.get("label", key)).strip()
        fields.append(
            AuthoringHeaderFieldSpec(
                slot_id=str(data.get("slot_id", f"general.{key}")),
                key=key,
                label=label,
                value=_report_value_from_legacy(
                    data,
                    context=f"heading.general_fields[{index}]",
                ),
                aliases=[str(alias) for alias in data.get("aliases", [key, label])],
                layout_path=_as_text(
                    data.get("layout_path"),
                    context=f"heading.general_fields[{index}].layout_path",
                ),
            )
        )

    service_titles: list[AuthoringServiceTitleSpec] = []
    for index, item in enumerate(
        _sequence(heading.get("service_titles", []), context="heading.service_titles")
    ):
        data = dict(item) if isinstance(item, Mapping) else {"value": item}
        service_titles.append(
            AuthoringServiceTitleSpec(
                slot_id=str(data.get("slot_id", f"service_title.{index + 1}")),
                value=_report_value_from_legacy(
                    data,
                    context=f"heading.service_titles[{index}]",
                ),
                font_size=(float(data["font_size"]) if data.get("font_size") is not None else None),
                auto_adjust=bool(data.get("auto_adjust", True)),
                bold=bool(data.get("bold", False)),
                italic=bool(data.get("italic", False)),
                alignment=str(data.get("alignment", "left")).lower(),
            )
        )

    detail_value = heading.get("detail")
    detail: AuthoringHeaderDetailSpec | None = None
    if detail_value is not None:
        detail_data = _mapping(detail_value, context="heading.detail")
        rows: list[AuthoringHeaderDetailRowSpec] = []
        for row_index, row_value in enumerate(
            _sequence(detail_data.get("rows", []), context="heading.detail.rows")
        ):
            row = _mapping(row_value, context=f"heading.detail.rows[{row_index}]")
            label = _as_text(row.get("label"), context=f"heading.detail.rows[{row_index}].label")
            label_cells = [str(cell) for cell in row.get("label_cells", [])]
            values = [
                _header_cell_from_legacy(
                    cell,
                    slot_id=f"detail.row_{row_index + 1}.value_{cell_index + 1}",
                    context=f"heading.detail.rows[{row_index}].values[{cell_index}]",
                )
                for cell_index, cell in enumerate(
                    _sequence(
                        row.get("values", []),
                        context=f"heading.detail.rows[{row_index}].values",
                    )
                )
            ]
            columns: list[AuthoringHeaderDetailColumnSpec] = []
            for column_index, column_value in enumerate(
                _sequence(
                    row.get("columns", []),
                    context=f"heading.detail.rows[{row_index}].columns",
                )
            ):
                column = _mapping(
                    column_value,
                    context=f"heading.detail.rows[{row_index}].columns[{column_index}]",
                )
                cells = [
                    _header_cell_from_legacy(
                        cell,
                        slot_id=(
                            f"detail.row_{row_index + 1}.column_{column_index + 1}."
                            f"cell_{cell_index + 1}"
                        ),
                        context=(
                            f"heading.detail.rows[{row_index}].columns[{column_index}]"
                            f".cells[{cell_index}]"
                        ),
                    )
                    for cell_index, cell in enumerate(
                        _sequence(
                            column.get("cells", []),
                            context=(
                                f"heading.detail.rows[{row_index}].columns[{column_index}].cells"
                            ),
                        )
                    )
                ]
                columns.append(AuthoringHeaderDetailColumnSpec(cells=cells))
            rows.append(
                AuthoringHeaderDetailRowSpec(
                    row_id=str(row.get("row_id", f"detail.row_{row_index + 1}")),
                    label=label,
                    label_cells=label_cells,
                    values=values,
                    columns=columns,
                )
            )
        if rows:
            detail = AuthoringHeaderDetailSpec(
                kind=str(detail_data.get("kind", "custom")),
                title=_as_text(detail_data.get("title"), context="heading.detail.title"),
                column_titles=[str(item) for item in detail_data.get("column_titles", [])],
                rows=rows,
            )

    compatibility = {"legacy_heading": deepcopy(heading)}
    return AuthoringHeaderSpec(
        enabled=bool(heading.get("enabled", True)),
        provider_name=_as_text(heading.get("provider_name"), context="heading.provider_name"),
        title=_as_text(heading.get("title"), context="heading.title"),
        subtitle=_as_text(heading.get("subtitle"), context="heading.subtitle"),
        general_fields=fields,
        service_titles=service_titles,
        detail=detail,
        tail_enabled=bool(heading.get("tail_enabled", False)),
        extensions={"compatibility": compatibility},
    )


def _report_value_to_legacy(
    value: AuthoringReportValueSpec,
    *,
    existing: object = None,
) -> object:
    """Project one typed report value while retaining legacy scalar shapes."""
    if value.value is not None and value.source_key is None and value.unit is None:
        return value.value
    data = dict(existing) if isinstance(existing, Mapping) else {}
    if value.value is not None:
        data["value"] = value.value
    elif value.source_key is not None:
        data.pop("value", None)
    if value.source_key is not None:
        data["source_key"] = value.source_key
    if value.default:
        data["default"] = value.default
    if value.unit is not None:
        data["unit"] = value.unit
    if data:
        return data
    return value.value


def _remark_to_legacy(remark: AuthoringRemarkSpec) -> dict[str, Any]:
    """Project one canonical remark without empty alternative content fields."""
    data = remark.model_dump(mode="json", exclude={"remark_id"}, exclude_none=True)
    if not data.get("text"):
        data.pop("text", None)
    if not data.get("lines"):
        data.pop("lines", None)
    return data


def _header_field_to_legacy(
    field: AuthoringHeaderFieldSpec,
    existing_fields: Sequence[object],
) -> dict[str, Any]:
    """Project one canonical header field without leaking canonical metadata."""
    existing = next(
        (
            item
            for item in existing_fields
            if isinstance(item, Mapping) and item.get("key") == field.key
        ),
        {},
    )
    item = dict(existing) if isinstance(existing, Mapping) else {}
    for key in ("aliases", "layout_path", "slot_id"):
        item.pop(key, None)
    item["key"] = field.key
    item["label"] = field.label
    item.pop("value", None)
    item.pop("source_key", None)
    if field.value.value is not None:
        item["value"] = _report_value_to_legacy(field.value, existing=existing.get("value"))
    if field.value.source_key is not None:
        item["source_key"] = field.value.source_key
    return item


def _header_to_legacy(header: AuthoringHeaderSpec) -> dict[str, Any]:
    """Project the canonical header to the renderer's legacy heading shape."""
    compatibility = header.extensions.get("compatibility", {})
    existing = (
        deepcopy(dict(compatibility["legacy_heading"]))
        if isinstance(compatibility, Mapping)
        and isinstance(compatibility.get("legacy_heading"), Mapping)
        else {}
    )
    existing.update({"enabled": header.enabled})
    existing.pop("title", None)
    existing.pop("subtitle", None)
    if header.provider_name is not None:
        existing["provider_name"] = header.provider_name
    existing_fields = existing.get("general_fields", [])
    if not isinstance(existing_fields, Sequence) or isinstance(existing_fields, (str, bytes)):
        existing_fields = []
    existing["general_fields"] = [
        _header_field_to_legacy(field, existing_fields) for field in header.general_fields
    ]
    old_titles = existing.get("service_titles", [])
    existing["service_titles"] = []
    for index, title in enumerate(header.service_titles):
        old = (
            old_titles[index]
            if index < len(old_titles) and isinstance(old_titles[index], Mapping)
            else {}
        )
        item = dict(old)
        item["value"] = _report_value_to_legacy(
            title.value,
            existing=old.get("value"),
        )
        item.pop("font_size", None)
        if title.font_size is not None:
            item["font_size"] = title.font_size
        item.update(
            {
                "auto_adjust": title.auto_adjust,
                "bold": title.bold,
                "italic": title.italic,
                "alignment": title.alignment,
            }
        )
        existing["service_titles"].append(item)
    if header.detail is not None:
        old_detail = existing.get("detail")
        detail = dict(old_detail) if isinstance(old_detail, Mapping) else {}
        detail["kind"] = header.detail.kind
        detail.pop("title", None)
        if header.detail.title is not None:
            detail["title"] = header.detail.title
        detail.pop("column_titles", None)
        if header.detail.column_titles:
            detail["column_titles"] = list(header.detail.column_titles)
        old_rows = detail.get("rows", [])
        rows: list[dict[str, Any]] = []
        for row_index, row in enumerate(header.detail.rows):
            old_row = (
                old_rows[row_index]
                if row_index < len(old_rows) and isinstance(old_rows[row_index], Mapping)
                else {}
            )
            row_data = dict(old_row)
            if row.label is not None:
                row_data["label"] = row.label
                row_data.pop("label_cells", None)
            else:
                row_data["label_cells"] = list(row.label_cells)
                row_data.pop("label", None)
            if row.values:
                old_values = old_row.get("values", [])
                row_data["values"] = [
                    _report_value_to_legacy(
                        cell.value,
                        existing=old_values[index] if index < len(old_values) else None,
                    )
                    for index, cell in enumerate(row.values)
                ]
                row_data.pop("columns", None)
            else:
                old_columns = old_row.get("columns", [])
                row_data["columns"] = []
                for column_index, column in enumerate(row.columns):
                    old_column = (
                        old_columns[column_index]
                        if column_index < len(old_columns)
                        and isinstance(old_columns[column_index], Mapping)
                        else {}
                    )
                    old_cells = old_column.get("cells", [])
                    row_data["columns"].append(
                        {
                            "cells": [
                                _report_value_to_legacy(
                                    cell.value,
                                    existing=old_cells[cell_index]
                                    if cell_index < len(old_cells)
                                    else None,
                                )
                                for cell_index, cell in enumerate(column.cells)
                            ]
                        }
                    )
                row_data.pop("values", None)
            rows.append(row_data)
        detail["rows"] = rows
        existing["detail"] = detail
    existing["tail_enabled"] = header.tail_enabled
    return existing


def _output_from_legacy(value: object) -> AuthoringOutputSpec:
    """Normalize root render settings into the canonical output object."""
    data = _mapping(value or {}, context="render")
    try:
        return AuthoringOutputSpec(
            backend=str(data.get("backend", "matplotlib")).lower(),
            output_path=str(data.get("output_path", "wellplot.pdf")),
            dpi=int(data.get("dpi", 180)),
            continuous_strip_page_height_mm=(
                float(data["continuous_strip_page_height_mm"])
                if data.get("continuous_strip_page_height_mm") is not None
                else None
            ),
        )
    except (TypeError, ValueError, ValidationError) as exc:
        raise TemplateValidationError("Invalid render output settings.") from exc


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
                            reference_overlay=_reference_overlay_from_legacy(
                                binding.get("reference_overlay"),
                                context="binding.reference_overlay",
                            ),
                            wrap=bool(binding.get("wrap", False)),
                            render_mode=str(binding.get("render_mode", "line")),
                            value_labels=_curve_value_labels_from_legacy(
                                binding.get("value_labels"), context="binding.value_labels"
                            ),
                            header_display=_curve_header_display_from_legacy(
                                binding.get("header_display"),
                                context="binding.header_display",
                            ),
                            callouts=_curve_callouts_from_legacy(
                                binding.get("callouts"), context="binding.callouts"
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
                                waveform_normalization=AuthoringRasterNormalizationKind(
                                    str(binding.get("waveform_normalization", "auto"))
                                    .strip()
                                    .lower()
                                ),
                                clip_percentiles=(
                                    tuple(float(item) for item in binding["clip_percentiles"])
                                    if binding.get("clip_percentiles") is not None
                                    else None
                                ),
                                interpolation=str(binding.get("interpolation", "nearest")),
                                show_raster=bool(
                                    binding.get("show_raster", profile.value != "waveform")
                                ),
                                alpha=float(binding.get("raster_alpha", 1.0)),
                                color_limits=(
                                    tuple(float(item) for item in binding["color_limits"])
                                    if binding.get("color_limits") is not None
                                    else None
                                ),
                                colorbar=_raster_colorbar_from_legacy(
                                    binding.get("colorbar"), context="binding.colorbar"
                                ),
                                sample_axis=_raster_sample_axis_from_legacy(
                                    binding.get("sample_axis"), context="binding.sample_axis"
                                ),
                                waveform=_raster_waveform_from_legacy(
                                    (
                                        True
                                        if binding.get("waveform") is None
                                        and profile == AuthoringRasterProfileKind.WAVEFORM
                                        else binding.get("waveform")
                                    ),
                                    context="binding.waveform",
                                ),
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
                secondary_grid = _mapping(
                    reference.get("secondary_grid", {}),
                    context=f"track {track_id}.reference.secondary_grid",
                )
                header = _mapping(
                    reference.get("header", {}),
                    context=f"track {track_id}.reference.header",
                )
                number_format = _mapping(
                    reference.get("number_format", {}),
                    context=f"track {track_id}.reference.number_format",
                )
                number_format_value = str(number_format.get("format", "automatic")).lower()
                number_format_value = {
                    "auto": "automatic",
                    "automatic": "automatic",
                }.get(number_format_value, number_format_value)
                authoring_tracks.append(
                    ReferenceTrackSpec(
                        **common,
                        axis=axis,
                        define_layout=bool(reference.get("define_layout", True)),
                        unit=_as_text(reference.get("unit"), context="reference.unit"),
                        scale_ratio=(
                            int(reference["scale_ratio"])
                            if reference.get("scale_ratio") is not None
                            else None
                        ),
                        major_step=(
                            float(reference["major_step"])
                            if reference.get("major_step") is not None
                            else None
                        ),
                        minor_step=(
                            float(reference["minor_step"])
                            if reference.get("minor_step") is not None
                            else None
                        ),
                        secondary_grid_display=bool(secondary_grid.get("display", True)),
                        secondary_grid_line_count=int(secondary_grid.get("line_count", 4)),
                        display_unit_in_header=bool(header.get("display_unit", True)),
                        display_scale_in_header=bool(header.get("display_scale", True)),
                        display_annotations_in_header=bool(header.get("display_annotations", True)),
                        number_format=AuthoringNumberFormatKind(number_format_value),
                        precision=int(number_format.get("precision", 2)),
                        values_orientation=str(reference.get("values_orientation", "horizontal")),
                        events=_reference_events_from_legacy(
                            reference.get("events"),
                            context=f"track {track_id}.reference.events",
                        ),
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
    header = _header_from_legacy(heading)
    tail_data = _mapping(layout.get("tail", {}), context="document.layout.tail")
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
            output=_output_from_legacy(root.get("render", {})),
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
            header=header,
            tail=AuthoringTailSpec(
                enabled=bool(tail_data.get("enabled", header.tail_enabled if header else False)),
                extensions={"compatibility": {"legacy_tail": deepcopy(tail_data)}},
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
            if "output" not in canonical and root.get("render") is not None:
                canonical["output"] = _output_from_legacy(root.get("render", {})).model_dump(
                    mode="python",
                    exclude={"extensions"},
                )
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
    output_payload = document_payload.pop("output", None)
    if not isinstance(output_payload, Mapping):
        output_payload = {}
    output_payload = dict(output_payload)
    output_payload.pop("extensions", None)
    payload: dict[str, object] = {"version": 1, "name": name, "document": document_payload}
    compatibility = document.extensions.get("compatibility")
    render_payload: dict[str, Any] = {}
    if isinstance(compatibility, Mapping):
        legacy_render = compatibility.get("legacy_render")
        if isinstance(legacy_render, Mapping):
            render_payload = deepcopy(dict(legacy_render))
        for key in ("legacy_render", "legacy_data"):
            value = compatibility.get(key)
            if value is not None and key == "legacy_data":
                payload["data"] = deepcopy(value)
    render_payload.update(output_payload)
    payload["render"] = render_payload
    return payload


def authoring_document_to_logfile_mapping(
    document: AuthoringDocumentSpec,
) -> dict[str, object]:
    """Project a canonical document into the multi-section logfile envelope."""
    canonical = authoring_document_to_mapping(document)
    compatibility = document.extensions.get("compatibility", {})
    legacy_document = (
        compatibility.get("legacy_document") if isinstance(compatibility, Mapping) else None
    )
    legacy = deepcopy(dict(legacy_document)) if isinstance(legacy_document, Mapping) else {}
    legacy_layout = legacy.get("layout")
    layout = deepcopy(dict(legacy_layout)) if isinstance(legacy_layout, Mapping) else {}
    existing_sections = {
        str(section.get("id", "")): deepcopy(dict(section))
        for section in layout.get("log_sections", [])
        if isinstance(section, Mapping) and str(section.get("id", "")).strip()
    }
    rendered_sections: list[dict[str, Any]] = []
    binding_channels: list[dict[str, Any]] = []
    for section in document.sections:
        section_payload = existing_sections.get(section.id, {})
        rendered_tracks = []
        for track in section.tracks:
            rendered_track = _render_track(document, section.id, track)
            rendered_track.pop("elements", None)
            rendered_tracks.append(rendered_track)
        section_payload.update(
            {
                "id": section.id,
                "title": section.title,
                "tracks": rendered_tracks,
            }
        )
        if section.subtitle is not None:
            section_payload["subtitle"] = section.subtitle
        else:
            section_payload.pop("subtitle", None)
        if section.depth_range is not None:
            section_payload["depth_range"] = list(section.depth_range)
        elif "depth_range" in section_payload:
            section_payload.pop("depth_range")
        if section.data_source is not None:
            section_payload["data"] = section.data_source.model_dump(
                mode="json", exclude_none=True
            )
        rendered_sections.append(section_payload)
        for track in section.tracks:
            for binding in getattr(track, "bindings", ()):
                binding_payload = _binding_element(binding)
                style = binding_payload.get("style")
                if isinstance(style, Mapping):
                    style = dict(style)
                    style.pop("alpha", None)
                    binding_payload["style"] = style
                binding_payload["track_id"] = track.id
                binding_payload["section"] = section.id
                binding_channels.append(binding_payload)

    heading = _header_to_legacy(document.header) if document.header is not None else {}
    layout["heading"] = heading
    layout["remarks"] = [_remark_to_legacy(remark) for remark in document.remarks]
    layout["log_sections"] = rendered_sections
    tail = layout.get("tail", {})
    tail_payload = deepcopy(dict(tail)) if isinstance(tail, Mapping) else {}
    tail_payload["enabled"] = document.tail.enabled
    layout["tail"] = tail_payload
    legacy["layout"] = layout
    legacy_header = legacy.get("header")
    header_payload = dict(legacy_header) if isinstance(legacy_header, Mapping) else {}
    title = document.title or (document.header.title if document.header is not None else None)
    subtitle = document.subtitle or (
        document.header.subtitle if document.header is not None else None
    )
    if title is not None:
        header_payload["title"] = title
    if subtitle is not None:
        header_payload["subtitle"] = subtitle
    if header_payload:
        legacy["header"] = header_payload
    legacy["bindings"] = {"channels": binding_channels}
    legacy["page"] = document.page.model_dump(mode="json", exclude_none=True)
    legacy["depth"] = document.depth.model_dump(mode="json", exclude_none=True)
    canonical["document"] = legacy
    canonical["name"] = document.name
    render = canonical.get("render")
    if isinstance(render, Mapping):
        canonical["render"] = {
            key: value for key, value in render.items() if value is not None
        }
    return canonical


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


def _scale_to_legacy(scale: AuthoringScale) -> dict[str, Any]:
    """Project a canonical scale to the legacy min/max representation."""
    data = scale.model_dump(mode="json", exclude_none=True)
    data["min"] = data.pop("minimum")
    data["max"] = data.pop("maximum")
    data.pop("unit", None)
    return data


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
            element["scale"] = _scale_to_legacy(binding.scale)
        if binding.reference_overlay is not None:
            element["reference_overlay"] = binding.reference_overlay.model_dump(
                mode="json", exclude_none=True
            )
        element["wrap"] = binding.wrap
        element["render_mode"] = binding.render_mode
        element["value_labels"] = authoring_curve_value_labels_to_mapping(binding.value_labels)
        element["header_display"] = authoring_curve_header_display_to_mapping(
            binding.header_display
        )
        element["callouts"] = authoring_curve_callouts_to_mapping(binding.callouts)
    else:
        element.update(
            {
                "profile": binding.profile.value,
                "normalization": binding.normalization.value,
                "waveform_normalization": binding.waveform_normalization.value,
                "interpolation": binding.interpolation,
                "show_raster": binding.show_raster,
                "raster_alpha": binding.alpha,
                "colorbar": authoring_raster_colorbar_to_mapping(binding.colorbar),
                "sample_axis": authoring_raster_sample_axis_to_mapping(binding.sample_axis),
                "waveform": authoring_raster_waveform_to_mapping(binding.waveform),
            }
        )
        if binding.clip_percentiles is not None:
            element["clip_percentiles"] = list(binding.clip_percentiles)
        if binding.color_limits is not None:
            element["color_limits"] = list(binding.color_limits)
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
        baseline_values = fill.baseline.model_dump(mode="json", exclude_none=True)
        if isinstance(baseline, Mapping):
            baseline = deepcopy(dict(baseline))
            baseline.update(baseline_values)
            legacy_fill["baseline"] = baseline
        else:
            legacy_fill["baseline"] = baseline_values
    if fill.label is not None:
        legacy_fill["label"] = fill.label
    if fill.color is not None:
        legacy_fill["color"] = fill.color
    if fill.alpha is not None:
        legacy_fill["alpha"] = fill.alpha
    crossover_data = fill.crossover.model_dump(mode="json", exclude_none=True)
    if crossover_data != {"enabled": False}:
        legacy_fill["crossover"] = crossover_data
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
        payload["x_scale"] = _scale_to_legacy(track.x_scale)
    if isinstance(track, ReferenceTrackSpec):
        payload["reference"] = authoring_reference_track_to_mapping(track)
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
            layout_sections["heading"] = (
                _header_to_legacy(document.header)
                if document.header is not None
                else deepcopy(layout.get("heading", {}))
            )
            layout_sections["remarks"] = [
                _remark_to_legacy(remark) for remark in document.remarks
            ]
            layout_sections["log_sections"] = deepcopy(layout.get("log_sections", []))
            legacy_tail = layout.get("tail", {})
            tail_payload = dict(legacy_tail) if isinstance(legacy_tail, Mapping) else {}
            tail_payload["enabled"] = document.tail.enabled
            layout_sections["tail"] = tail_payload
            payload["metadata"] = {**metadata, "layout_sections": layout_sections}
            heading = layout_sections["heading"]
            if heading and "report" not in payload.get("header", {}):
                payload["header"] = {
                    **_mapping(payload.get("header", {}), context="document.header"),
                    "report": heading,
                }
    metadata = _mapping(payload.get("metadata", {}), context="document.metadata")
    layout_sections = _mapping(
        metadata.get("layout_sections", {}), context="metadata.layout_sections"
    )
    if document.header is not None:
        layout_sections["heading"] = _header_to_legacy(document.header)
    layout_sections["remarks"] = [
        _remark_to_legacy(remark) for remark in document.remarks
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
    tail_payload = layout_sections.get("tail", {})
    tail_mapping = dict(tail_payload) if isinstance(tail_payload, Mapping) else {}
    tail_mapping["enabled"] = document.tail.enabled
    layout_sections["tail"] = tail_mapping
    metadata["layout_sections"] = layout_sections
    payload["metadata"] = metadata
    if document.header is not None:
        header_payload = _header_to_legacy(document.header)
        payload["header"] = {
            **_mapping(payload.get("header", {}), context="document.header"),
            "report": header_payload,
        }
    title = document.title or (document.header.title if document.header is not None else None)
    subtitle = document.subtitle or (
        document.header.subtitle if document.header is not None else None
    )
    if title is not None or subtitle is not None:
        header = _mapping(payload.get("header", {}), context="document.header")
        if title is not None:
            header["title"] = title
        if subtitle is not None:
            header["subtitle"] = subtitle
        payload["header"] = header
    depth_payload: dict[str, Any] = {
        "unit": document.depth.unit,
        "scale": document.depth.scale,
    }
    if document.depth.major_step is not None:
        depth_payload["major_step"] = document.depth.major_step
    if document.depth.minor_step is not None:
        depth_payload["minor_step"] = document.depth.minor_step
    payload.update(
        {
            "name": document.name,
            "page": document.page.model_dump(mode="json", exclude_none=True),
            "depth": depth_payload,
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
    "authoring_document_to_logfile_mapping",
    "authoring_document_to_mapping",
    "authoring_document_to_render",
    "authoring_document_to_yaml",
    "load_authoring_document",
    "load_authoring_document_text",
]
