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

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any, TextIO

import yaml

from ..errors import TemplateValidationError
from ..logfile import LogFileSpec, load_logfile, logfile_from_mapping
from ..model import (
    AnnotationArrowSpec,
    AnnotationGlyphSpec,
    AnnotationIntervalSpec,
    AnnotationMarkerSpec,
    AnnotationTextSpec,
    CurveCalloutSpec,
    CurveElement,
    CurveFillSpec,
    CurveHeaderDisplaySpec,
    CurveValueLabelsSpec,
    DepthAxisSpec,
    FooterSpec,
    GridSpec,
    HeaderField,
    HeaderSpec,
    LogDocument,
    MarkerSpec,
    PageSpec,
    RasterElement,
    RasterWaveformSpec,
    ReferenceCurveOverlaySpec,
    ReferenceEventSpec,
    ReferenceTrackSpec,
    ReportBlockSpec,
    ReportDetailCellSpec,
    ReportDetailColumnSpec,
    ReportDetailRowSpec,
    ReportDetailSpec,
    ReportFieldSpec,
    ReportServiceTitleSpec,
    ReportValueSpec,
    ScaleSpec,
    StyleSpec,
    TrackHeaderSpec,
    TrackSpec,
    ZoneSpec,
)
from ..templates import document_from_mapping, load_document
from .builder import LogBuilder, ProgrammaticLogSpec


def _set_if_not_none(target: dict[str, Any], key: str, value: Any) -> None:
    if value is not None:
        target[key] = value


def _clean_mapping(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _clean_mapping(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_clean_mapping(item) for item in value]
    return value


def _write_yaml(payload: Mapping[str, Any], destination: str | Path | TextIO | None) -> str | None:
    text = yaml.safe_dump(dict(payload), sort_keys=False)
    if destination is None:
        return text
    if hasattr(destination, "write"):
        destination.write(text)
        return None
    Path(destination).write_text(text, encoding="utf-8")
    return None


def _read_yaml_mapping(source: str | Path | TextIO) -> dict[str, Any]:
    if hasattr(source, "read"):
        payload = yaml.safe_load(source.read()) or {}
    else:
        payload = yaml.safe_load(Path(source).read_text(encoding="utf-8")) or {}
    if not isinstance(payload, Mapping):
        raise TemplateValidationError("YAML root must be a mapping.")
    return dict(payload)


def _serialize_style(style: StyleSpec) -> dict[str, Any]:
    return {
        "color": style.color,
        "line_width": style.line_width,
        "line_style": style.line_style,
        "opacity": style.opacity,
        "fill_color": style.fill_color,
        "fill_alpha": style.fill_alpha,
        "colormap": style.colormap,
    }


def _serialize_scale(scale: ScaleSpec) -> dict[str, Any]:
    return {
        "kind": scale.kind.value,
        "min": scale.minimum,
        "max": scale.maximum,
        "reverse": scale.reverse,
    }


def _serialize_grid(grid: GridSpec) -> dict[str, Any]:
    return {
        "major": grid.major,
        "minor": grid.minor,
        "major_alpha": grid.major_alpha,
        "minor_alpha": grid.minor_alpha,
        "horizontal": {
            "display": grid.horizontal_display.value,
            "main": {
                "visible": grid.horizontal_major_visible,
                "color": grid.horizontal_major_color,
                "thickness": grid.horizontal_major_thickness,
                "alpha": grid.horizontal_major_alpha,
            },
            "secondary": {
                "visible": grid.horizontal_minor_visible,
                "color": grid.horizontal_minor_color,
                "thickness": grid.horizontal_minor_thickness,
                "alpha": grid.horizontal_minor_alpha,
            },
        },
        "vertical": {
            "display": grid.vertical_display.value,
            "main": {
                "visible": grid.vertical_main_visible,
                "line_count": grid.vertical_main_line_count,
                "thickness": grid.vertical_main_thickness,
                "color": grid.vertical_main_color,
                "alpha": grid.vertical_main_alpha,
                "scale": grid.vertical_main_scale.value,
                "spacing_mode": grid.vertical_main_spacing_mode.value,
            },
            "secondary": {
                "visible": grid.vertical_secondary_visible,
                "line_count": grid.vertical_secondary_line_count,
                "thickness": grid.vertical_secondary_thickness,
                "color": grid.vertical_secondary_color,
                "alpha": grid.vertical_secondary_alpha,
                "scale": grid.vertical_secondary_scale.value,
                "spacing_mode": grid.vertical_secondary_spacing_mode.value,
            },
        },
    }


def _serialize_track_header(header: TrackHeaderSpec) -> dict[str, Any]:
    return {
        "objects": [
            {
                "kind": item.kind.value,
                "enabled": item.enabled,
                "reserve_space": item.reserve_space,
                "line_units": item.line_units,
            }
            for item in header.objects
        ]
    }


def _serialize_curve_value_labels(spec: CurveValueLabelsSpec) -> dict[str, Any]:
    return {
        "step": spec.step,
        "format": spec.number_format.value,
        "precision": spec.precision,
        "color": spec.color,
        "font_size": spec.font_size,
        "font_family": spec.font_family,
        "font_weight": spec.font_weight,
        "font_style": spec.font_style,
        "horizontal_alignment": spec.horizontal_alignment,
        "vertical_alignment": spec.vertical_alignment,
    }


def _serialize_curve_header_display(spec: CurveHeaderDisplaySpec) -> dict[str, Any]:
    return {
        "show_name": spec.show_name,
        "show_unit": spec.show_unit,
        "show_limits": spec.show_limits,
        "show_color": spec.show_color,
        "wrap_name": spec.wrap_name,
    }


def _serialize_reference_curve_overlay(spec: ReferenceCurveOverlaySpec) -> dict[str, Any]:
    overlay = {
        "mode": spec.mode.value,
        "tick_side": spec.tick_side.value,
    }
    _set_if_not_none(overlay, "lane_start", spec.lane_start)
    _set_if_not_none(overlay, "lane_end", spec.lane_end)
    _set_if_not_none(overlay, "tick_length_ratio", spec.tick_length_ratio)
    _set_if_not_none(overlay, "threshold", spec.threshold)
    return overlay


def _serialize_curve_callout(spec: CurveCalloutSpec) -> dict[str, Any]:
    callout = {
        "depth": spec.depth,
        "side": spec.side,
        "placement": spec.placement,
        "font_weight": spec.font_weight,
        "font_style": spec.font_style,
        "arrow": spec.arrow,
    }
    _set_if_not_none(callout, "label", spec.label)
    _set_if_not_none(callout, "text_x", spec.text_x)
    _set_if_not_none(callout, "depth_offset", spec.depth_offset)
    _set_if_not_none(callout, "distance_from_top", spec.distance_from_top)
    _set_if_not_none(callout, "distance_from_bottom", spec.distance_from_bottom)
    _set_if_not_none(callout, "every", spec.every)
    _set_if_not_none(callout, "color", spec.color)
    _set_if_not_none(callout, "font_size", spec.font_size)
    _set_if_not_none(callout, "arrow_style", spec.arrow_style)
    _set_if_not_none(callout, "arrow_linewidth", spec.arrow_linewidth)
    return callout


def _serialize_curve_fill(spec: CurveFillSpec) -> dict[str, Any]:
    fill = {
        "kind": spec.kind.value,
        "crossover": {
            "enabled": spec.crossover.enabled,
            "left_color": spec.crossover.left_color,
            "right_color": spec.crossover.right_color,
            "alpha": spec.crossover.alpha,
        },
    }
    _set_if_not_none(fill, "other_channel", spec.other_channel)
    _set_if_not_none(fill, "other_element_id", spec.other_element_id)
    _set_if_not_none(fill, "label", spec.label)
    _set_if_not_none(fill, "color", spec.color)
    _set_if_not_none(fill, "alpha", spec.alpha)
    if spec.baseline is not None:
        fill["baseline"] = {
            "value": spec.baseline.value,
            "lower_color": spec.baseline.lower_color,
            "upper_color": spec.baseline.upper_color,
            "line_color": spec.baseline.line_color,
            "line_width": spec.baseline.line_width,
            "line_style": spec.baseline.line_style,
        }
    return fill


def _serialize_curve_element(element: CurveElement) -> dict[str, Any]:
    curve = {
        "kind": "curve",
        "channel": element.channel,
        "style": _serialize_style(element.style),
        "render_mode": element.render_mode,
        "value_labels": _serialize_curve_value_labels(element.value_labels),
        "header_display": _serialize_curve_header_display(element.header_display),
    }
    _set_if_not_none(curve, "id", element.id)
    _set_if_not_none(curve, "label", element.label)
    if element.scale is not None:
        curve["scale"] = _serialize_scale(element.scale)
    if element.reference_overlay is not None:
        curve["reference_overlay"] = _serialize_reference_curve_overlay(element.reference_overlay)
    if element.wrap:
        curve["wrap"] = True
    if element.wrap_color is not None:
        curve["wrap_color"] = element.wrap_color
    if element.callouts:
        curve["callouts"] = [_serialize_curve_callout(item) for item in element.callouts]
    if element.fill is not None:
        curve["fill"] = _serialize_curve_fill(element.fill)
    return curve


def _serialize_raster_waveform(spec: RasterWaveformSpec) -> dict[str, Any]:
    waveform = {
        "enabled": spec.enabled,
        "stride": spec.stride,
        "amplitude_scale": spec.amplitude_scale,
        "color": spec.color,
        "line_width": spec.line_width,
        "fill": spec.fill,
        "positive_fill_color": spec.positive_fill_color,
        "negative_fill_color": spec.negative_fill_color,
        "invert_fill_polarity": spec.invert_fill_polarity,
    }
    _set_if_not_none(waveform, "max_traces", spec.max_traces)
    return waveform


def _serialize_raster_element(element: RasterElement) -> dict[str, Any]:
    raster = {
        "kind": "raster",
        "channel": element.channel,
        "style": _serialize_style(element.style),
        "profile": element.profile.value,
        "normalization": element.normalization.value,
        "waveform_normalization": element.waveform_normalization.value,
        "interpolation": element.interpolation,
        "show_raster": element.show_raster,
        "raster_alpha": element.raster_alpha,
        "colorbar": {
            "enabled": element.colorbar_enabled,
            "label": element.colorbar_label,
            "position": element.colorbar_position.value,
        },
        "sample_axis": {
            "enabled": element.sample_axis_enabled,
            "label": element.sample_axis_label,
            "unit": element.sample_axis_unit,
            "source_origin": element.sample_axis_source_origin,
            "source_step": element.sample_axis_source_step,
            "min": element.sample_axis_min,
            "max": element.sample_axis_max,
            "ticks": element.sample_axis_tick_count,
        },
        "waveform": _serialize_raster_waveform(element.waveform),
    }
    _set_if_not_none(raster, "label", element.label)
    if element.clip_percentiles is not None:
        raster["clip_percentiles"] = list(element.clip_percentiles)
    if element.color_limits is not None:
        raster["color_limits"] = list(element.color_limits)
    return raster


def _serialize_annotation_object(
    item: AnnotationIntervalSpec
    | AnnotationTextSpec
    | AnnotationMarkerSpec
    | AnnotationArrowSpec
    | AnnotationGlyphSpec,
) -> dict[str, Any]:
    if isinstance(item, AnnotationIntervalSpec):
        return {
            "kind": "interval",
            "top": item.top,
            "base": item.base,
            "text": item.text,
            "lane_start": item.lane_start,
            "lane_end": item.lane_end,
            "fill_color": item.fill_color,
            "fill_alpha": item.fill_alpha,
            "border_color": item.border_color,
            "border_linewidth": item.border_linewidth,
            "border_style": item.border_style,
            "text_color": item.text_color,
            "text_orientation": item.text_orientation,
            "text_wrap": item.text_wrap,
            "horizontal_alignment": item.horizontal_alignment,
            "vertical_alignment": item.vertical_alignment,
            "font_size": item.font_size,
            "font_weight": item.font_weight,
            "font_style": item.font_style,
            "padding": item.padding,
        }
    if isinstance(item, AnnotationTextSpec):
        payload = {
            "kind": "text",
            "text": item.text,
            "lane_start": item.lane_start,
            "lane_end": item.lane_end,
            "color": item.color,
            "text_orientation": item.text_orientation,
            "wrap": item.wrap,
            "horizontal_alignment": item.horizontal_alignment,
            "vertical_alignment": item.vertical_alignment,
            "font_size": item.font_size,
            "font_weight": item.font_weight,
            "font_style": item.font_style,
            "padding": item.padding,
        }
        _set_if_not_none(payload, "depth", item.depth)
        _set_if_not_none(payload, "top", item.top)
        _set_if_not_none(payload, "base", item.base)
        _set_if_not_none(payload, "background_color", item.background_color)
        _set_if_not_none(payload, "border_color", item.border_color)
        _set_if_not_none(payload, "border_linewidth", item.border_linewidth)
        return payload
    if isinstance(item, AnnotationMarkerSpec):
        payload = {
            "kind": "marker",
            "depth": item.depth,
            "x": item.x,
            "shape": item.shape,
            "size": item.size,
            "color": item.color,
            "line_width": item.line_width,
            "label": item.label,
            "text_side": item.text_side,
            "font_weight": item.font_weight,
            "font_style": item.font_style,
            "arrow": item.arrow,
            "priority": item.priority,
            "label_mode": item.label_mode.value,
        }
        _set_if_not_none(payload, "fill_color", item.fill_color)
        _set_if_not_none(payload, "edge_color", item.edge_color)
        _set_if_not_none(payload, "text_x", item.text_x)
        _set_if_not_none(payload, "depth_offset", item.depth_offset)
        _set_if_not_none(payload, "font_size", item.font_size)
        _set_if_not_none(payload, "arrow_style", item.arrow_style)
        _set_if_not_none(payload, "arrow_linewidth", item.arrow_linewidth)
        _set_if_not_none(payload, "label_lane_start", item.label_lane_start)
        _set_if_not_none(payload, "label_lane_end", item.label_lane_end)
        return payload
    if isinstance(item, AnnotationArrowSpec):
        payload = {
            "kind": "arrow",
            "start_depth": item.start_depth,
            "end_depth": item.end_depth,
            "start_x": item.start_x,
            "end_x": item.end_x,
            "color": item.color,
            "line_width": item.line_width,
            "line_style": item.line_style,
            "arrow_style": item.arrow_style,
            "label": item.label,
            "font_size": item.font_size,
            "font_weight": item.font_weight,
            "font_style": item.font_style,
            "text_rotation": item.text_rotation,
            "priority": item.priority,
            "label_mode": item.label_mode.value,
        }
        _set_if_not_none(payload, "label_x", item.label_x)
        _set_if_not_none(payload, "label_depth", item.label_depth)
        _set_if_not_none(payload, "label_lane_start", item.label_lane_start)
        _set_if_not_none(payload, "label_lane_end", item.label_lane_end)
        return payload
    payload = {
        "kind": "glyph",
        "glyph": item.glyph,
        "lane_start": item.lane_start,
        "lane_end": item.lane_end,
        "color": item.color,
        "font_size": item.font_size,
        "font_weight": item.font_weight,
        "font_style": item.font_style,
        "rotation": item.rotation,
        "horizontal_alignment": item.horizontal_alignment,
        "vertical_alignment": item.vertical_alignment,
        "padding": item.padding,
    }
    _set_if_not_none(payload, "depth", item.depth)
    _set_if_not_none(payload, "top", item.top)
    _set_if_not_none(payload, "base", item.base)
    _set_if_not_none(payload, "background_color", item.background_color)
    _set_if_not_none(payload, "border_color", item.border_color)
    _set_if_not_none(payload, "border_linewidth", item.border_linewidth)
    return payload


def _serialize_reference_event(spec: ReferenceEventSpec) -> dict[str, Any]:
    payload = {
        "depth": spec.depth,
        "label": spec.label,
        "color": spec.color,
        "line_style": spec.line_style,
        "line_width": spec.line_width,
        "tick_side": spec.tick_side.value,
        "text_side": spec.text_side,
        "font_weight": spec.font_weight,
        "font_style": spec.font_style,
        "arrow": spec.arrow,
    }
    _set_if_not_none(payload, "tick_length_ratio", spec.tick_length_ratio)
    _set_if_not_none(payload, "lane_start", spec.lane_start)
    _set_if_not_none(payload, "lane_end", spec.lane_end)
    _set_if_not_none(payload, "text_x", spec.text_x)
    _set_if_not_none(payload, "depth_offset", spec.depth_offset)
    _set_if_not_none(payload, "font_size", spec.font_size)
    _set_if_not_none(payload, "arrow_style", spec.arrow_style)
    _set_if_not_none(payload, "arrow_linewidth", spec.arrow_linewidth)
    return payload


def _serialize_reference_track(reference: ReferenceTrackSpec) -> dict[str, Any]:
    payload = {
        "axis": reference.axis.value,
        "define_layout": reference.define_layout,
        "values_orientation": reference.values_orientation,
        "secondary_grid": {
            "display": reference.secondary_grid_display,
            "line_count": reference.secondary_grid_line_count,
        },
        "header": {
            "display_unit": reference.display_unit_in_header,
            "display_scale": reference.display_scale_in_header,
            "display_annotations": reference.display_annotations_in_header,
        },
        "number_format": {
            "format": reference.number_format.value,
            "precision": reference.precision,
        },
    }
    _set_if_not_none(payload, "unit", reference.unit)
    _set_if_not_none(payload, "scale_ratio", reference.scale_ratio)
    _set_if_not_none(payload, "major_step", reference.major_step)
    _set_if_not_none(payload, "minor_step", reference.minor_step)
    if reference.events:
        payload["events"] = [_serialize_reference_event(item) for item in reference.events]
    return payload


def _serialize_track(track: TrackSpec) -> dict[str, Any]:
    payload = {
        "id": track.id,
        "title": track.title,
        "kind": track.kind.value,
        "width_mm": track.width_mm,
        "elements": [
            (
                _serialize_curve_element(item)
                if isinstance(item, CurveElement)
                else _serialize_raster_element(item)
            )
            for item in track.elements
        ],
        "track_header": _serialize_track_header(track.header),
        "grid": _serialize_grid(track.grid),
    }
    if track.annotations:
        payload["annotations"] = [_serialize_annotation_object(item) for item in track.annotations]
    if track.x_scale is not None:
        payload["x_scale"] = _serialize_scale(track.x_scale)
    if track.reference is not None:
        payload["reference"] = _serialize_reference_track(track.reference)
    return payload


def _serialize_header_field(field: HeaderField) -> dict[str, Any]:
    payload = {
        "label": field.label,
        "source_key": field.source_key,
    }
    if field.default != "":
        payload["default"] = field.default
    return payload


def _serialize_report_value(value: ReportValueSpec) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    _set_if_not_none(payload, "value", value.value)
    _set_if_not_none(payload, "source_key", value.source_key)
    if value.default != "":
        payload["default"] = value.default
    return payload


def _serialize_report_field(field: ReportFieldSpec) -> dict[str, Any]:
    payload = {
        "key": field.key,
        "label": field.label,
    }
    value = _serialize_report_value(field.value)
    if value:
        payload["value"] = value
    return payload


def _serialize_report_service_title(title: ReportServiceTitleSpec) -> dict[str, Any] | str:
    value = _serialize_report_value(title.value)
    if (
        title.font_size is None
        and title.auto_adjust
        and not title.bold
        and not title.italic
        and title.alignment == "left"
        and set(value.keys()) == {"value"}
    ):
        return str(value["value"])
    payload = dict(value)
    _set_if_not_none(payload, "font_size", title.font_size)
    payload["auto_adjust"] = title.auto_adjust
    payload["bold"] = title.bold
    payload["italic"] = title.italic
    payload["alignment"] = title.alignment
    return payload


def _serialize_report_detail_cell(cell: ReportDetailCellSpec) -> dict[str, Any]:
    payload = _serialize_report_value(cell.value)
    _set_if_not_none(payload, "background_color", cell.background_color)
    _set_if_not_none(payload, "text_color", cell.text_color)
    _set_if_not_none(payload, "font_weight", cell.font_weight)
    if not cell.divider_left_visible:
        payload["divider_left_visible"] = False
    if not cell.divider_right_visible:
        payload["divider_right_visible"] = False
    return payload


def _serialize_report_detail_column(column: ReportDetailColumnSpec) -> dict[str, Any]:
    return {"cells": [_serialize_report_detail_cell(item) for item in column.cells]}


def _serialize_report_detail_row(row: ReportDetailRowSpec) -> dict[str, Any]:
    return {
        "label_cells": [_serialize_report_detail_cell(item) for item in row.label_cells],
        "columns": [_serialize_report_detail_column(item) for item in row.columns],
    }


def _serialize_report_detail(detail: ReportDetailSpec) -> dict[str, Any]:
    payload = {
        "kind": detail.kind.value,
        "rows": [_serialize_report_detail_row(item) for item in detail.rows],
    }
    _set_if_not_none(payload, "title", detail.title)
    if detail.column_titles:
        payload["column_titles"] = list(detail.column_titles)
    return payload


def _serialize_report_block(report: ReportBlockSpec) -> dict[str, Any]:
    payload = {
        "enabled": report.enabled,
        "general_fields": [_serialize_report_field(item) for item in report.general_fields],
        "service_titles": [_serialize_report_service_title(item) for item in report.service_titles],
        "tail_enabled": report.tail_enabled,
    }
    _set_if_not_none(payload, "provider_name", report.provider_name)
    if report.detail is not None:
        payload["detail"] = _serialize_report_detail(report.detail)
    return payload


def _serialize_header(header: HeaderSpec) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    _set_if_not_none(payload, "title", header.title)
    _set_if_not_none(payload, "subtitle", header.subtitle)
    if header.fields:
        payload["fields"] = [_serialize_header_field(item) for item in header.fields]
    if header.report is not None:
        payload["report"] = _serialize_report_block(header.report)
    return payload


def _serialize_footer(footer: FooterSpec) -> dict[str, Any]:
    return {"lines": list(footer.lines)}


def _serialize_page(page: PageSpec) -> dict[str, Any]:
    return {
        "width_mm": page.width_mm,
        "height_mm": page.height_mm,
        "continuous": page.continuous,
        "bottom_track_header_enabled": page.bottom_track_header_enabled,
        "margin_left_mm": page.margin_left_mm,
        "margin_right_mm": page.margin_right_mm,
        "margin_top_mm": page.margin_top_mm,
        "margin_bottom_mm": page.margin_bottom_mm,
        "header_height_mm": page.header_height_mm,
        "track_header_height_mm": page.track_header_height_mm,
        "footer_height_mm": page.footer_height_mm,
        "track_gap_mm": page.track_gap_mm,
    }


def _serialize_depth_axis(depth_axis: DepthAxisSpec) -> dict[str, Any]:
    return {
        "unit": depth_axis.unit,
        "scale": depth_axis.scale_ratio,
        "major_step": depth_axis.major_step,
        "minor_step": depth_axis.minor_step,
    }


def _serialize_marker(marker: MarkerSpec) -> dict[str, Any]:
    return {
        "depth": marker.depth,
        "label": marker.label,
        "color": marker.color,
        "line_style": marker.line_style,
    }


def _serialize_zone(zone: ZoneSpec) -> dict[str, Any]:
    return {
        "top": zone.top,
        "base": zone.base,
        "label": zone.label,
        "fill_color": zone.fill_color,
        "alpha": zone.alpha,
    }


def document_to_dict(document: LogDocument) -> dict[str, Any]:
    payload = {
        "name": document.name,
        "page": _serialize_page(document.page),
        "depth": _serialize_depth_axis(document.depth_axis),
        "tracks": [_serialize_track(item) for item in document.tracks],
        "header": _serialize_header(document.header),
        "footer": _serialize_footer(document.footer),
    }
    if document.depth_range is not None:
        payload["depth_range"] = list(document.depth_range)
    if document.markers:
        payload["markers"] = [_serialize_marker(item) for item in document.markers]
    if document.zones:
        payload["zones"] = [_serialize_zone(item) for item in document.zones]
    if document.metadata:
        payload["metadata"] = deepcopy(document.metadata)
    return _clean_mapping(payload)


def document_from_dict(data: Mapping[str, Any]) -> LogDocument:
    return document_from_mapping(dict(data))


def document_to_yaml(
    document: LogDocument,
    destination: str | Path | TextIO | None = None,
) -> str | None:
    return _write_yaml(document_to_dict(document), destination)


def save_document(document: LogDocument, destination: str | Path | TextIO) -> str | None:
    return document_to_yaml(document, destination)


def document_from_yaml(source: str | Path | TextIO) -> LogDocument:
    if hasattr(source, "read"):
        return document_from_dict(_read_yaml_mapping(source))
    return load_document(source)


def load_document_yaml(source: str | Path | TextIO) -> LogDocument:
    return document_from_yaml(source)


def _logfile_spec_to_mapping(spec: LogFileSpec) -> dict[str, Any]:
    payload = {
        "version": 1,
        "name": spec.name,
        "render": {
            "backend": spec.render_backend,
            "output_path": spec.render_output_path,
            "dpi": spec.render_dpi,
        },
        "document": deepcopy(spec.document),
    }
    if spec.data_source_path is not None:
        payload["data"] = {
            "source_path": spec.data_source_path,
            "source_format": spec.data_source_format,
        }
    if spec.render_continuous_strip_page_height_mm is not None:
        payload["render"]["continuous_strip_page_height_mm"] = (
            spec.render_continuous_strip_page_height_mm
        )
    if spec.render_matplotlib:
        payload["render"]["matplotlib"] = deepcopy(spec.render_matplotlib)
    return _clean_mapping(payload)


def report_to_dict(
    report: ProgrammaticLogSpec | LogBuilder | LogFileSpec | Mapping[str, Any],
) -> dict[str, Any]:
    if isinstance(report, ProgrammaticLogSpec):
        return report.to_mapping()
    if isinstance(report, LogBuilder):
        return report.to_mapping()
    if isinstance(report, LogFileSpec):
        return _logfile_spec_to_mapping(report)
    if isinstance(report, Mapping):
        return deepcopy(dict(report))
    raise TypeError(
        "report_to_dict expects ProgrammaticLogSpec, LogBuilder, LogFileSpec, or mapping input."
    )


def report_from_dict(data: Mapping[str, Any]) -> LogFileSpec:
    return logfile_from_mapping(dict(data))


def report_to_yaml(
    report: ProgrammaticLogSpec | LogBuilder | LogFileSpec | Mapping[str, Any],
    destination: str | Path | TextIO | None = None,
) -> str | None:
    return _write_yaml(report_to_dict(report), destination)


def save_report(
    report: ProgrammaticLogSpec | LogBuilder | LogFileSpec | Mapping[str, Any],
    destination: str | Path | TextIO,
) -> str | None:
    return report_to_yaml(report, destination)


def report_from_yaml(source: str | Path | TextIO) -> LogFileSpec:
    if hasattr(source, "read"):
        return report_from_dict(_read_yaml_mapping(source))
    return load_logfile(source)


def load_report(source: str | Path | TextIO) -> LogFileSpec:
    return report_from_yaml(source)


__all__ = [
    "document_from_dict",
    "document_from_yaml",
    "document_to_dict",
    "document_to_yaml",
    "load_document_yaml",
    "load_report",
    "report_from_dict",
    "report_from_yaml",
    "report_to_dict",
    "report_to_yaml",
    "save_document",
    "save_report",
]
