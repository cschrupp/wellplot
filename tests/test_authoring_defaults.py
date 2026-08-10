"""Tests for the asset-backed authoring defaults catalog."""

from __future__ import annotations

from wellplot.authoring_context import AuthoringResolutionSource, resolve_authoring_context
from wellplot.authoring_defaults import generic_authoring_defaults
from wellplot.authoring_reconciler import reconcile_authoring
from wellplot.mcp.authoring_defaults import (
    form_default_catalog,
    style_preset_catalog,
    track_archetype_catalog,
)
from wellplot.model.intent import AuthoringDocumentIntent


def test_defaults_catalog_loads_generic_track_and_style_entries() -> None:
    """Expose track families and style families from packaged YAML assets."""
    tracks = track_archetype_catalog()
    presets = style_preset_catalog()

    assert {entry["id"] for entry in tracks} == {
        "reference_depth",
        "gamma_ray",
        "porosity_overlay",
        "resistivity_log",
        "vdl_array",
    }
    assert {entry["id"] for entry in presets} == {
        "density_neutron_overlay",
        "gamma_ray_clean_print",
        "triple_combo_resistivity",
        "cbl_vdl_high_contrast",
        "cbl_vdl_print_safe",
        "report_header_clean",
    }
    assert {entry["id"] for entry in form_default_catalog()} == {
        "normal",
        "reference",
        "array",
        "annotation",
    }


def test_defaults_catalog_returns_defensive_copies() -> None:
    """Mutating a catalog response must not change the packaged defaults."""
    tracks = track_archetype_catalog()
    tracks[0]["label"] = "Changed locally"

    assert track_archetype_catalog()[0]["label"] == "Reference Depth"


def test_generic_defaults_select_unique_family_and_nested_binding_values() -> None:
    """Resolve generic track, grid, and curve defaults from channel families."""
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "main",
                "tracks": [
                    {
                        "track_id": "resistivity",
                        "kind": "normal",
                        "bindings": [{"kind": "curve", "binding_id": "deep", "channel": "RT"}],
                    }
                ],
            }
        ]
    )

    result = generic_authoring_defaults(intent)

    track_path = "sections[main].tracks[resistivity]"
    binding_path = f"{track_path}.bindings[deep]"
    assert result.matched_families[f"{track_path}.archetype"] == "resistivity_log"
    assert result.matched_families[f"{track_path}.preset"] == "triple_combo_resistivity"
    assert result.defaults[f"{track_path}.x_scale"] == {
        "kind": "log",
        "minimum": 0.2,
        "maximum": 2000.0,
    }
    assert result.defaults[f"{track_path}.grid.vertical_main_scale"] == "logarithmic"
    assert result.defaults[f"{binding_path}.style.color"] == "#111827"


def test_generic_defaults_do_not_override_explicit_values() -> None:
    """Keep explicit typed values ahead of catalog defaults."""
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "main",
                "tracks": [
                    {
                        "track_id": "resistivity",
                        "kind": "normal",
                        "title": "Explicit Resistivity",
                        "width_mm": 11.0,
                        "x_scale": {"kind": "linear", "minimum": 2, "maximum": 200},
                        "bindings": [{"kind": "curve", "binding_id": "deep", "channel": "RT"}],
                    }
                ],
            }
        ]
    )
    defaults = generic_authoring_defaults(intent)

    result = resolve_authoring_context(intent, defaults=defaults.defaults)

    assert result.resolved_values["sections[main].tracks[resistivity].x_scale.kind"] == "linear"
    assert result.resolved_values["sections[main].tracks[resistivity].x_scale.minimum"] == 2.0
    assert result.resolved_values["sections[main].tracks[resistivity].x_scale.maximum"] == 200.0
    assert result.resolved_values["sections[main].tracks[resistivity].title"] == (
        "Explicit Resistivity"
    )
    assert result.resolved_values["sections[main].tracks[resistivity].width_mm"] == 11.0
    assert any(
        decision.path == "sections[main].tracks[resistivity].x_scale.kind"
        and decision.source == AuthoringResolutionSource.EXPLICIT
        for decision in result.decisions
    )


def test_generic_defaults_refuse_ambiguous_style_family() -> None:
    """Do not guess between multiple catalog presets for one channel family."""
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "main",
                "tracks": [
                    {
                        "track_id": "cbl",
                        "kind": "normal",
                        "bindings": [
                            {"kind": "curve", "binding_id": "amplitude", "channel": "CBL"}
                        ],
                    }
                ],
            }
        ]
    )

    result = generic_authoring_defaults(intent)

    assert result.defaults == {}
    assert result.matched_families == {}
    assert result.warnings == (
        "Ambiguous defaults for track 'cbl': cbl_vdl_high_contrast, cbl_vdl_print_safe.",
    )


def test_generic_defaults_complete_uncatalogued_scalar_track() -> None:
    """Construct an arbitrary scalar track without a scientific family match."""
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "main",
                "title": "Main",
                "tracks": [
                    {
                        "track_id": "custom_sensor",
                        "bindings": [
                            {"kind": "curve", "binding_id": "sensor", "channel": "SENSOR_X"}
                        ],
                    }
                ],
            }
        ]
    )

    result = generic_authoring_defaults(intent)
    track_path = "sections[main].tracks[custom_sensor]"

    assert result.defaults[f"{track_path}.title"] == "Custom Sensor"
    assert result.defaults[f"{track_path}.kind"] == "normal"
    assert result.defaults[f"{track_path}.width_mm"] == 28.0
    assert result.matched_families[f"{track_path}.form"] == "normal"
    assert result.matched_families[f"{track_path}.unmatched_channels"] == "SENSOR_X"

    plan = reconcile_authoring(
        intent,
        defaults=result.defaults,
        available_channels={"main": ["SENSOR_X"]},
    )

    assert plan.ready
    section_operation = next(
        operation for operation in plan.operations if operation.object_kind.value == "section"
    )
    assert section_operation.payload["object"]["tracks"][0]["kind"] == "normal"


def test_generic_defaults_infer_reference_and_array_forms() -> None:
    """Infer compatible generic forms from track names and raster children."""
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "main",
                "tracks": [
                    {"track_id": "depth_axis"},
                    {
                        "track_id": "custom_waveform",
                        "bindings": [
                            {
                                "kind": "raster",
                                "binding_id": "waveform",
                                "channel": "WAVE_X",
                            }
                        ],
                    },
                ],
            }
        ]
    )

    result = generic_authoring_defaults(intent)

    reference_path = "sections[main].tracks[depth_axis]"
    array_path = "sections[main].tracks[custom_waveform]"
    assert result.defaults[f"{reference_path}.kind"] == "reference"
    assert result.defaults[f"{reference_path}.width_mm"] == 16.0
    assert result.defaults[f"{array_path}.kind"] == "array"
    assert result.defaults[f"{array_path}.width_mm"] == 28.0


def test_generic_defaults_infer_array_form_from_root_binding() -> None:
    """Use scoped root bindings when nested track content is omitted."""
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "main",
                "tracks": [{"track_id": "custom_waveform"}],
            }
        ],
        raster_bindings=[
            {
                "kind": "raster",
                "binding_id": "waveform",
                "section_id": "main",
                "track_id": "custom_waveform",
                "channel": "WAVE_X",
            }
        ],
    )

    result = generic_authoring_defaults(intent)
    track_path = "sections[main].tracks[custom_waveform]"

    assert result.defaults[f"{track_path}.kind"] == "array"


def test_generic_defaults_infer_annotation_form_from_root_annotation() -> None:
    """Use scoped root annotations when the track owns no nested children."""
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "main",
                "tracks": [{"track_id": "markers"}],
            }
        ],
        annotations=[
            {
                "annotation_id": "marker",
                "section_id": "main",
                "track_id": "markers",
            }
        ],
    )

    result = generic_authoring_defaults(intent)
    track_path = "sections[main].tracks[markers]"

    assert result.defaults[f"{track_path}.kind"] == "annotation"


def test_resistivity_family_accepts_known_msfl_channel() -> None:
    """Keep resistivity enrichment when all three conventional channels exist."""
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "main",
                "tracks": [
                    {
                        "track_id": "resistivity",
                        "bindings": [
                            {"kind": "curve", "binding_id": "ild", "channel": "ILD"},
                            {"kind": "curve", "binding_id": "ilm", "channel": "ILM"},
                            {"kind": "curve", "binding_id": "msfl", "channel": "MSFL"},
                        ],
                    }
                ],
            }
        ]
    )

    result = generic_authoring_defaults(intent)
    track_path = "sections[main].tracks[resistivity]"

    assert result.matched_families[f"{track_path}.archetype"] == "resistivity_log"
    assert result.matched_families[f"{track_path}.preset"] == "triple_combo_resistivity"
    assert f"{track_path}.unmatched_channels" not in result.matched_families
    assert result.defaults[f"{track_path}.x_scale"] == {
        "kind": "log",
        "minimum": 0.2,
        "maximum": 2000.0,
    }


def test_family_match_keeps_unknown_channel_as_provenance() -> None:
    """Do not discard family defaults because of one vendor mnemonic."""
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "main",
                "tracks": [
                    {
                        "track_id": "resistivity",
                        "bindings": [
                            {"kind": "curve", "binding_id": "ild", "channel": "ILD"},
                            {
                                "kind": "curve",
                                "binding_id": "vendor",
                                "channel": "VENDOR_RES",
                            },
                        ],
                    }
                ],
            }
        ]
    )

    result = generic_authoring_defaults(intent)
    track_path = "sections[main].tracks[resistivity]"

    assert result.matched_families[f"{track_path}.preset"] == "triple_combo_resistivity"
    assert result.matched_families[f"{track_path}.unmatched_channels"] == "VENDOR_RES"


def test_known_contradictory_channel_does_not_select_resistivity_family() -> None:
    """Reject resistivity conventions when the evidence is a known GR channel."""
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "main",
                "tracks": [
                    {
                        "track_id": "resistivity",
                        "bindings": [
                            {"kind": "curve", "binding_id": "gr", "channel": "GR"}
                        ],
                    }
                ],
            }
        ]
    )

    result = generic_authoring_defaults(intent)
    track_path = "sections[main].tracks[resistivity]"

    assert result.matched_families[f"{track_path}.archetype"] == "gamma_ray"
    assert result.matched_families[f"{track_path}.preset"] == "gamma_ray_clean_print"
    assert f"{track_path}.x_scale" not in result.defaults


def test_family_match_uses_scoped_root_bindings() -> None:
    """Use root-level scoped channels when selecting optional family defaults."""
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "main",
                "tracks": [{"track_id": "resistivity"}],
            }
        ],
        curve_bindings=[
            {
                "kind": "curve",
                "binding_id": "ild",
                "section_id": "main",
                "track_id": "resistivity",
                "channel": "ILD",
            },
            {
                "kind": "curve",
                "binding_id": "msfl",
                "section_id": "main",
                "track_id": "resistivity",
                "channel": "MSFL",
            },
        ],
    )

    result = generic_authoring_defaults(intent)
    track_path = "sections[main].tracks[resistivity]"

    assert result.matched_families[f"{track_path}.archetype"] == "resistivity_log"


def test_generic_defaults_are_serialized_for_new_bindings() -> None:
    """Carry resolved family defaults into deterministic create operations."""
    intent = AuthoringDocumentIntent(
        title="Gamma report",
        sections=[
            {
                "section_id": "main",
                "title": "Main",
                "tracks": [
                    {
                        "track_id": "gamma",
                        "bindings": [{"kind": "curve", "binding_id": "gr", "channel": "GR"}],
                    }
                ],
            }
        ],
    )
    defaults = generic_authoring_defaults(intent)

    plan = reconcile_authoring(
        intent,
        defaults=defaults.defaults,
        available_channels={"main": ["GR"]},
    )

    binding_operation = next(
        operation for operation in plan.operations if operation.object_kind.value == "curve_binding"
    )
    assert binding_operation.payload["object"]["scale"] == {
        "kind": "linear",
        "minimum": 0.0,
        "maximum": 150.0,
    }
    assert binding_operation.payload["object"]["style"] == {
        "color": "#166534",
        "line_width": 1.2,
    }
