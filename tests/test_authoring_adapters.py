"""Tests for canonical authoring compatibility adapters."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from wellplot import (
    authoring_document_from_mapping,
    authoring_document_to_mapping,
    authoring_document_to_render,
    authoring_document_to_yaml,
    load_authoring_document,
    load_authoring_document_text,
)
from wellplot.authoring import authoring_document_to_logfile_mapping
from wellplot.errors import TemplateValidationError
from wellplot.model.authoring import ArrayTrackSpec, NormalTrackSpec


def _legacy_mapping() -> dict[str, object]:
    """Return a small legacy logfile mapping with repeated channel bindings."""
    return {
        "version": 1,
        "name": "adapter-test",
        "render": {"backend": "matplotlib", "output_path": "out.pdf", "dpi": 120},
        "document": {
            "page": {
                "size": "A4",
                "orientation": "landscape",
                "margin_right_mm": 5,
            },
            "depth": {"unit": "ft", "scale": 240, "major_step": 10, "minor_step": 2},
            "layout": {
                "heading": {"title": "Adapter Test"},
                "remarks": [{"title": "Notes", "lines": ["Preserved"]}],
                "log_sections": [
                    {
                        "id": "main",
                        "title": "Main",
                        "data": {"source_path": "data/test.las", "source_format": "las"},
                        "tracks": [
                            {
                                "id": "gr",
                                "title": "Gamma Ray",
                                "kind": "normal",
                                "width_mm": 30,
                                "grid": {
                                    "vertical": {
                                        "main": {
                                            "line_count": 5,
                                            "scale": "exponential",
                                            "spacing_mode": "scale",
                                            "color": "#222222",
                                        }
                                    }
                                },
                                "track_header": {
                                    "objects": [
                                        {"kind": "title", "enabled": True, "line_units": 1},
                                        {"kind": "scale", "enabled": False, "line_units": 1},
                                        {"kind": "legend", "enabled": True, "line_units": 2},
                                        {
                                            "kind": "divisions",
                                            "enabled": True,
                                            "reserve_space": True,
                                            "line_units": 1,
                                        },
                                    ]
                                },
                            },
                            {"id": "vdl", "title": "VDL", "kind": "image", "width_mm": 40},
                        ],
                    }
                ],
            },
            "bindings": {
                "channels": [
                    {
                        "id": "gr-1",
                        "section": "main",
                        "track_id": "gr",
                        "channel": "GR",
                        "style": {"color": "black", "line_width": 0.75},
                        "scale": {"kind": "linear", "min": 0, "max": 200},
                        "render_mode": "value_labels",
                        "value_labels": {"step": 10, "format": "fixed", "precision": 1},
                        "header_display": {"show_color": False},
                        "callouts": [
                            {
                                "depth": 1005,
                                "label": "GR Sand",
                                "side": "right",
                                "placement": "bottom",
                                "distance_from_top": 1.0,
                            }
                        ],
                    },
                    {
                        "id": "gr-2",
                        "section": "main",
                        "track_id": "gr",
                        "channel": "GR",
                        "style": {"color": "blue", "line_style": "--"},
                        "scale": {"kind": "linear", "min": 200, "max": 0},
                    },
                    {
                        "section": "main",
                        "track_id": "vdl",
                        "channel": "VDL",
                        "kind": "raster",
                        "profile": "vdl",
                        "normalization": "none",
                        "waveform_normalization": "trace_maxabs",
                        "clip_percentiles": [1, 99],
                        "interpolation": "nearest",
                        "show_raster": True,
                        "raster_alpha": 0.8,
                        "color_limits": [-1, 1],
                        "colorbar": {
                            "enabled": True,
                            "label": "Amplitude",
                            "position": "header",
                        },
                        "sample_axis": {
                            "enabled": True,
                            "unit": "us",
                            "min": 200,
                            "max": 1200,
                            "ticks": 7,
                        },
                        "waveform": {"enabled": True, "stride": 5},
                    },
                ]
            },
        },
    }


def test_legacy_mapping_normalizes_and_renders() -> None:
    """Normalize layout bindings without losing duplicate instances or styles."""
    document = authoring_document_from_mapping(_legacy_mapping())

    assert document.page.orientation == "landscape"
    assert document.remarks[0].lines == ["Preserved"]
    gr_track = document.sections[0].tracks[0]
    vdl_track = document.sections[0].tracks[1]
    assert isinstance(gr_track, NormalTrackSpec)
    assert isinstance(vdl_track, ArrayTrackSpec)
    assert [binding.binding_id for binding in gr_track.bindings] == ["gr-1", "gr-2"]
    assert [binding.channel for binding in gr_track.bindings] == ["GR", "GR"]
    assert gr_track.bindings[1].scale is not None
    assert gr_track.bindings[1].scale.minimum == 200
    assert gr_track.bindings[0].render_mode == "value_labels"
    assert gr_track.bindings[0].value_labels.precision == 1
    assert gr_track.bindings[0].header_display.show_color is False
    assert gr_track.bindings[0].callouts[0].label == "GR Sand"
    assert gr_track.bindings[0].callouts[0].placement == "bottom"
    assert gr_track.grid.vertical_main_line_count == 5
    assert gr_track.grid.vertical_main_scale.value == "logarithmic"
    assert gr_track.grid.vertical_main_spacing_mode.value == "scale"
    assert gr_track.grid.vertical_main_color == "#222222"
    assert gr_track.track_header.objects[1].enabled is False
    assert gr_track.track_header.objects[2].line_units == 2

    rendered = authoring_document_to_render(document)
    assert rendered.page.width_mm == 297
    assert rendered.page.height_mm == 210
    rendered_gr = rendered.tracks[0]
    assert len(rendered_gr.elements) == 2
    assert rendered_gr.elements[0].style.color == "black"
    assert rendered_gr.elements[1].style.line_style == "--"
    assert rendered_gr.elements[0].render_mode == "value_labels"
    assert rendered_gr.elements[0].value_labels.precision == 1
    assert rendered_gr.elements[0].callouts[0].label == "GR Sand"
    assert rendered_gr.grid.vertical_main_line_count == 5
    assert rendered_gr.grid.vertical_main_color == "#222222"
    assert rendered_gr.header.objects[3].enabled is True
    assert rendered.tracks[1].elements[0].profile.value == "vdl"
    raster = vdl_track.bindings[0]
    assert raster.waveform_normalization.value == "trace_maxabs"
    assert raster.clip_percentiles == (1.0, 99.0)
    assert raster.color_limits == (-1.0, 1.0)
    assert raster.colorbar.enabled is True
    assert raster.sample_axis.maximum == 1200.0
    assert raster.waveform.stride == 5

    normalized = authoring_document_to_mapping(document)
    raster_mapping = normalized["document"]["sections"][0]["tracks"][1]["bindings"][0]
    assert raster_mapping["sample_axis"]["maximum"] == 1200.0
    assert raster_mapping["waveform"]["stride"] == 5


def test_array_track_x_scale_round_trips_through_canonical_model() -> None:
    """Preserve the shared sample-axis scale on array tracks."""
    mapping = _legacy_mapping()
    sections = mapping["document"]["layout"]["log_sections"]
    sections[0]["tracks"][1]["x_scale"] = {
        "kind": "linear",
        "min": 200,
        "max": 1200,
    }

    document = authoring_document_from_mapping(mapping)
    vdl_track = document.sections[0].tracks[1]

    assert isinstance(vdl_track, ArrayTrackSpec)
    assert vdl_track.x_scale is not None
    assert vdl_track.x_scale.minimum == 200
    assert vdl_track.x_scale.maximum == 1200

    normalized = authoring_document_to_mapping(document)
    assert normalized["document"]["sections"][0]["tracks"][1]["x_scale"] == {
        "kind": "linear",
        "minimum": 200.0,
        "maximum": 1200.0,
        "reverse": False,
    }


def test_legacy_binding_fill_round_trips_through_canonical_track() -> None:
    """Normalize binding-level fills without losing renderer-specific fields."""
    mapping = _legacy_mapping()
    document = mapping["document"]
    assert isinstance(document, dict)
    bindings = document["bindings"]["channels"]
    assert isinstance(bindings, list)
    bindings[0]["fill"] = {
        "kind": "to_lower_limit",
        "label": "Gamma fill",
        "color": "#8fd19e",
        "alpha": 0.35,
    }

    normalized = authoring_document_from_mapping(mapping)
    track = normalized.sections[0].tracks[0]
    assert isinstance(track, NormalTrackSpec)
    assert len(track.fills) == 1
    assert track.fills[0].binding_id == "gr-1"
    assert track.fills[0].extensions["compatibility"]["legacy_fill"]["label"] == "Gamma fill"
    assert track.fills[0].label == "Gamma fill"
    assert track.fills[0].color == "#8fd19e"
    assert track.fills[0].alpha == 0.35

    rendered = authoring_document_to_render(normalized)
    assert rendered.tracks[0].elements[0].fill is not None
    assert rendered.tracks[0].elements[0].fill.label == "Gamma fill"
    assert rendered.tracks[0].elements[0].fill.color == "#8fd19e"


def test_canonical_mapping_round_trips() -> None:
    """Normalized authoring YAML can be loaded without legacy conversion."""
    document = authoring_document_from_mapping(_legacy_mapping())
    normalized = authoring_document_to_mapping(document)
    restored = authoring_document_from_mapping(normalized)

    assert normalized["version"] == 1
    assert restored == document


def test_logfile_projection_round_trips_document_title_and_subtitle() -> None:
    """Preserve root document titles through the legacy logfile envelope."""
    document = authoring_document_from_mapping(_legacy_mapping()).model_copy(
        update={
            "title": "Projected document title",
            "subtitle": "Projected document subtitle",
        }
    )

    projected = authoring_document_to_logfile_mapping(document)
    restored = authoring_document_from_mapping(projected)

    assert projected["document"]["header"] == {
        "title": "Projected document title",
        "subtitle": "Projected document subtitle",
    }
    assert restored.title == "Projected document title"
    assert restored.subtitle == "Projected document subtitle"


def test_canonical_yaml_loads_without_legacy_logfile_validation() -> None:
    """Canonical YAML uses the adapter directly rather than legacy schema rules."""
    document = authoring_document_from_mapping(_legacy_mapping())
    yaml_text = authoring_document_to_yaml(document)
    assert isinstance(yaml_text, str)
    loaded = load_authoring_document_text(yaml_text)

    assert loaded == document
    assert yaml.safe_load(yaml_text)["document"]["sections"][0]["id"] == "main"


def test_header_detail_slots_and_output_settings_round_trip() -> None:
    """Normalize first-class report slots while preserving renderer output behavior."""
    mapping = _legacy_mapping()
    document = mapping["document"]
    assert isinstance(document, dict)
    layout = document["layout"]
    assert isinstance(layout, dict)
    layout["heading"] = {
        "enabled": True,
        "provider_name": "Company",
        "title": "Adapter Test",
        "general_fields": [
            {"key": "well", "label": "Well", "value": "Demo-1", "unit": "name"},
        ],
        "service_titles": [
            {"value": "Gamma Ray", "bold": True, "alignment": "center"},
        ],
        "detail": {
            "kind": "open_hole",
            "title": "Open Hole Metadata",
            "rows": [
                {
                    "label": "Date",
                    "values": [
                        {"value": "2026-08-08", "unit": "date"},
                        {"value": ""},
                    ],
                },
                {
                    "label_cells": ["Run", "Direction"],
                    "columns": [
                        {"cells": ["ONE"]},
                        {"cells": ["Up"]},
                    ],
                },
            ],
        },
        "tail_enabled": True,
    }
    layout["tail"] = {"enabled": True}
    render = mapping["render"]
    assert isinstance(render, dict)
    render["continuous_strip_page_height_mm"] = 420

    authoring = authoring_document_from_mapping(mapping)

    assert authoring.output.continuous_strip_page_height_mm == 420
    assert authoring.header is not None
    assert authoring.header.general_fields[0].slot_id == "general.well"
    assert authoring.header.general_fields[0].value.unit == "name"
    assert authoring.header.service_titles[0].slot_id == "service_title.1"
    assert authoring.header.detail is not None
    assert authoring.header.detail.rows[0].values[0].slot_id == "detail.row_1.value_1"
    assert authoring.header.detail.rows[1].columns[1].cells[0].slot_id == (
        "detail.row_2.column_2.cell_1"
    )
    assert authoring.tail.enabled is True

    normalized = authoring_document_to_mapping(authoring)
    assert normalized["render"]["continuous_strip_page_height_mm"] == 420
    normalized_header = normalized["document"]["header"]
    assert normalized_header["general_fields"][0]["slot_id"] == "general.well"

    restored = authoring_document_from_mapping(normalized)
    assert restored == authoring
    rendered = authoring_document_to_render(authoring)
    assert rendered.header.report is not None
    assert rendered.header.report.general_fields[0].value.value == "Demo-1"
    assert rendered.header.report.detail is not None
    assert rendered.header.report.detail.rows[0].columns[0].cells[0].value.value == ("2026-08-08")


def test_production_template_inheritance_loads_through_adapter() -> None:
    """A production logfile with a template is normalized through one entry point."""
    path = Path("examples/production/cbl_log_example/full_reconstruction.log.yaml")
    document = load_authoring_document(path)

    assert [section.id for section in document.sections] == ["main_pass", "repeat_pass"]
    assert document.sections[0].data_source is not None
    assert document.sections[0].data_source.source_format == "dlis"
    assert len(document.sections[0].tracks[2].bindings) == 2
    assert len(authoring_document_to_render(document).tracks) == 4


def test_annotation_objects_preserve_renderer_geometry_and_styling() -> None:
    """Normalize every annotation kind without dropping its display controls."""
    document = load_authoring_document(Path("examples/annotation_track_objects_showcase.log.yaml"))
    track = document.sections[0].tracks[2]

    assert len(track.annotations) == 11
    interval = track.annotations[0]
    text = track.annotations[1]
    marker = track.annotations[6]
    arrow = track.annotations[9]
    glyph = track.annotations[10]
    assert interval.fill_color == "#2047a3"
    assert interval.text_orientation == "vertical"
    assert text.top == 670
    assert text.base == 688
    assert text.background_color == "#dbe7ff"
    assert marker.label_mode.value == "dedicated_lane"
    assert marker.label_lane_end == 0.98
    assert arrow.start_depth == 696
    assert arrow.end_x == 0.18
    assert glyph.border_linewidth == 0.5

    rendered = authoring_document_to_render(document)
    rendered_arrow = rendered.tracks[2].annotations[9]
    assert rendered_arrow.start_depth == 696
    assert rendered_arrow.end_x == 0.18


def test_ambiguous_legacy_binding_requires_section() -> None:
    """The adapter must not guess when a legacy track exists in two sections."""
    mapping = _legacy_mapping()
    document = mapping["document"]
    assert isinstance(document, dict)
    layout = document["layout"]
    assert isinstance(layout, dict)
    section = layout["log_sections"][0]
    assert isinstance(section, dict)
    second = dict(section)
    second["id"] = "repeat"
    layout["log_sections"] = [section, second]
    channels = document["bindings"]["channels"]
    assert isinstance(channels, list)
    channels[0] = {key: value for key, value in channels[0].items() if key != "section"}

    with pytest.raises(TemplateValidationError, match="ambiguous"):
        authoring_document_from_mapping(mapping)


def test_reference_overlay_round_trips_as_typed_binding_content() -> None:
    """Normalize reference overlay properties without treating them as freeform YAML."""
    mapping = _legacy_mapping()
    document = mapping["document"]
    assert isinstance(document, dict)
    layout = document["layout"]
    assert isinstance(layout, dict)
    tracks = layout["log_sections"][0]["tracks"]
    tracks[0]["kind"] = "reference"
    channels = document["bindings"]["channels"]
    channels[0]["reference_overlay"] = {
        "mode": "indicator",
        "lane_start": 0.2,
        "lane_end": 0.8,
        "tick_side": "right",
        "threshold": 1.5,
    }

    normalized = authoring_document_from_mapping(mapping)
    binding = normalized.sections[0].tracks[0].bindings[0]
    assert binding.reference_overlay is not None
    assert binding.reference_overlay.mode.value == "indicator"
    assert binding.reference_overlay.tick_side.value == "right"

    rendered = authoring_document_to_render(normalized)
    assert rendered.tracks[0].elements[0].reference_overlay is not None
    assert rendered.tracks[0].elements[0].reference_overlay.threshold == 1.5


def test_reference_track_presentation_round_trips_as_typed_content() -> None:
    """Normalize and render the complete reference-track presentation contract."""
    mapping = _legacy_mapping()
    document = mapping["document"]
    assert isinstance(document, dict)
    layout = document["layout"]
    assert isinstance(layout, dict)
    track = layout["log_sections"][0]["tracks"][0]
    track["kind"] = "reference"
    track["reference"] = {
        "axis": "depth",
        "define_layout": True,
        "unit": "ft",
        "scale_ratio": 500,
        "major_step": 50,
        "minor_step": 10,
        "secondary_grid": {"display": False, "line_count": 5},
        "header": {
            "display_unit": False,
            "display_scale": True,
            "display_annotations": False,
        },
        "number_format": {"format": "fixed", "precision": 1},
        "values_orientation": "vertical",
        "events": [
            {
                "depth": 1002.0,
                "label": "Casing Foot",
                "color": "#8b5a2b",
                "line_style": "--",
                "text_side": "left",
                "text_x": 0.72,
            }
        ],
    }

    normalized = authoring_document_from_mapping(mapping)
    reference = normalized.sections[0].tracks[0]
    assert reference.scale_ratio == 500
    assert reference.major_step == 50
    assert reference.secondary_grid_display is False
    assert reference.display_unit_in_header is False
    assert reference.number_format.value == "fixed"
    assert reference.values_orientation == "vertical"
    assert reference.events[0].label == "Casing Foot"

    rendered = authoring_document_to_render(normalized)
    rendered_reference = rendered.tracks[0].reference
    assert rendered_reference is not None
    assert rendered_reference.scale_ratio == 500
    assert rendered_reference.secondary_grid_display is False
    assert rendered_reference.display_unit_in_header is False
    assert rendered_reference.number_format.value == "fixed"
    assert rendered_reference.events[0].line_style == "--"
