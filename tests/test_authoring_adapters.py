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
                        "raster_alpha": 0.8,
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
    assert gr_track.grid.vertical_main_line_count == 5
    assert gr_track.grid.vertical_main_scale.value == "logarithmic"
    assert gr_track.grid.vertical_main_spacing_mode.value == "scale"
    assert gr_track.grid.vertical_main_color == "#222222"

    rendered = authoring_document_to_render(document)
    assert rendered.page.width_mm == 297
    assert rendered.page.height_mm == 210
    rendered_gr = rendered.tracks[0]
    assert len(rendered_gr.elements) == 2
    assert rendered_gr.elements[0].style.color == "black"
    assert rendered_gr.elements[1].style.line_style == "--"
    assert rendered_gr.grid.vertical_main_line_count == 5
    assert rendered_gr.grid.vertical_main_color == "#222222"
    assert rendered.tracks[1].elements[0].profile.value == "vdl"


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


def test_canonical_yaml_loads_without_legacy_logfile_validation() -> None:
    """Canonical YAML uses the adapter directly rather than legacy schema rules."""
    document = authoring_document_from_mapping(_legacy_mapping())
    yaml_text = authoring_document_to_yaml(document)
    assert isinstance(yaml_text, str)
    loaded = load_authoring_document_text(yaml_text)

    assert loaded == document
    assert yaml.safe_load(yaml_text)["document"]["sections"][0]["id"] == "main"


def test_production_template_inheritance_loads_through_adapter() -> None:
    """A production logfile with a template is normalized through one entry point."""
    path = Path("examples/production/cbl_log_example/full_reconstruction.log.yaml")
    document = load_authoring_document(path)

    assert [section.id for section in document.sections] == ["main_pass", "repeat_pass"]
    assert document.sections[0].data_source is not None
    assert document.sections[0].data_source.source_format == "dlis"
    assert len(document.sections[0].tracks[2].bindings) == 2
    assert len(authoring_document_to_render(document).tracks) == 4


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
