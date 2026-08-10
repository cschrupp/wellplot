"""Tests for the asset-backed authoring defaults catalog."""

from __future__ import annotations

from wellplot.authoring_context import AuthoringResolutionSource, resolve_authoring_context
from wellplot.authoring_defaults import generic_authoring_defaults
from wellplot.authoring_reconciler import reconcile_authoring
from wellplot.mcp.authoring_defaults import style_preset_catalog, track_archetype_catalog
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
