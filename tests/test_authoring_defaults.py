"""Tests for the asset-backed authoring defaults catalog."""

from __future__ import annotations

from wellplot.mcp.authoring_defaults import style_preset_catalog, track_archetype_catalog


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


def test_defaults_catalog_returns_defensive_copies() -> None:
    """Mutating a catalog response must not change the packaged defaults."""
    tracks = track_archetype_catalog()
    tracks[0]["label"] = "Changed locally"

    assert track_archetype_catalog()[0]["label"] == "Reference Depth"
