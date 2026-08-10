###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Generic asset-backed defaults for typed authoring intents."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from re import sub
from typing import Any

from .mcp.authoring_defaults import style_preset_catalog, track_archetype_catalog
from .model.intent import (
    AuthoringCurveBindingIntent,
    AuthoringDocumentIntent,
    AuthoringRasterBindingIntent,
    AuthoringTrackIntent,
)


@dataclass(frozen=True)
class AuthoringDefaultsResolution:
    """Selected defaults and diagnostics for one typed desired state."""

    defaults: dict[str, Any]
    matched_families: dict[str, str]
    warnings: tuple[str, ...] = ()


def _normalize(value: object) -> str:
    """Normalize one catalog or intent token for family matching."""
    return sub(r"[^a-z0-9]+", "", str(value).strip().lower())


def _normalized_values(values: object) -> set[str]:
    """Return normalized non-empty values from one optional catalog list."""
    if not isinstance(values, list):
        return set()
    return {_normalize(value) for value in values if _normalize(value)}


def _canonical_scale(value: object) -> dict[str, Any] | None:
    """Convert legacy or canonical scale keys into intent keys."""
    if not isinstance(value, Mapping):
        return None
    minimum = value.get("minimum", value.get("min"))
    maximum = value.get("maximum", value.get("max"))
    kind = str(value.get("kind", "linear")).strip().lower()
    if minimum is None or maximum is None or kind not in {"linear", "log", "tangential"}:
        return None
    return {
        "kind": kind,
        "minimum": minimum,
        "maximum": maximum,
        **({"reverse": bool(value["reverse"])} if "reverse" in value else {}),
        **({"unit": value["unit"]} if value.get("unit") else {}),
    }


def _canonical_style(value: object) -> dict[str, Any] | None:
    """Keep only style fields owned by the canonical intent contract."""
    if not isinstance(value, Mapping):
        return None
    allowed = {
        "color",
        "line_style",
        "line_width",
        "alpha",
        "fill_color",
        "fill_alpha",
        "colormap",
    }
    return {key: deepcopy(item) for key, item in value.items() if key in allowed}


def _grid_display(value: object) -> str | None:
    """Convert the boolean display shorthand used by the YAML catalog."""
    if isinstance(value, bool):
        return "below" if value else "none"
    if isinstance(value, str) and value in {"below", "above", "none"}:
        return value
    return None


def _canonical_grid(value: object) -> dict[str, Any] | None:
    """Flatten nested catalog grid settings into canonical intent fields."""
    if not isinstance(value, Mapping):
        return None
    result: dict[str, Any] = {}
    direct_fields = {
        "display",
        "major",
        "minor",
        "major_alpha",
        "minor_alpha",
        "horizontal_display",
        "horizontal_major_visible",
        "horizontal_minor_visible",
        "horizontal_major_color",
        "horizontal_minor_color",
        "horizontal_major_thickness",
        "horizontal_minor_thickness",
        "horizontal_major_alpha",
        "horizontal_minor_alpha",
        "vertical_display",
        "vertical_main_visible",
        "vertical_main_line_count",
        "vertical_main_thickness",
        "vertical_main_color",
        "vertical_main_alpha",
        "vertical_main_scale",
        "vertical_main_spacing_mode",
        "vertical_secondary_visible",
        "vertical_secondary_line_count",
        "vertical_secondary_thickness",
        "vertical_secondary_color",
        "vertical_secondary_alpha",
        "vertical_secondary_scale",
        "vertical_secondary_spacing_mode",
    }
    for field_name in direct_fields:
        if field_name not in value:
            continue
        field_value = value[field_name]
        if field_name in {"display", "horizontal_display", "vertical_display"}:
            field_value = _grid_display(field_value)
        if field_value is not None:
            result[field_name] = field_value

    nested_axes = {
        "horizontal": "horizontal",
        "vertical": "vertical",
    }
    nested_layers = {
        "main": "main",
        "secondary": "secondary",
    }
    nested_fields = {
        "visible": "visible",
        "line_count": "line_count",
        "thickness": "thickness",
        "color": "color",
        "alpha": "alpha",
        "scale": "scale",
        "spacing_mode": "spacing_mode",
    }
    for axis, axis_prefix in nested_axes.items():
        axis_value = value.get(axis)
        if not isinstance(axis_value, Mapping):
            continue
        for layer, layer_prefix in nested_layers.items():
            layer_value = axis_value.get(layer)
            if not isinstance(layer_value, Mapping):
                continue
            for field_name, field_value in layer_value.items():
                canonical_suffix = nested_fields.get(field_name)
                if canonical_suffix is None:
                    continue
                result[f"{axis_prefix}_{layer_prefix}_{canonical_suffix}"] = field_value
    return result or None


def _canonical_patch(value: object) -> dict[str, Any]:
    """Normalize one catalog patch while preserving supported canonical fields."""
    if not isinstance(value, Mapping):
        return {}
    patch: dict[str, Any] = {}
    for field_name, field_value in value.items():
        if field_name in {"scale", "x_scale"}:
            normalized = _canonical_scale(field_value)
            if normalized is not None:
                patch[field_name] = normalized
        elif field_name == "grid":
            normalized = _canonical_grid(field_value)
            if normalized is not None:
                patch[field_name] = normalized
        elif field_name == "style":
            normalized = _canonical_style(field_value)
            if normalized:
                patch[field_name] = normalized
        elif field_name == "header_display":
            if isinstance(field_value, Mapping):
                allowed = {
                    "show_name",
                    "show_unit",
                    "show_limits",
                    "show_color",
                    "wrap_name",
                }
                normalized = {
                    key: deepcopy(item) for key, item in field_value.items() if key in allowed
                }
                if normalized:
                    patch[field_name] = normalized
        elif field_name in {
            "kind",
            "title",
            "label",
            "width_mm",
            "profile",
            "normalization",
            "waveform_normalization",
            "interpolation",
            "show_raster",
            "alpha",
            "color_limits",
            "colorbar",
            "sample_axis",
            "waveform",
        }:
            patch[field_name] = deepcopy(field_value)
    return patch


def _flatten_defaults(
    defaults: dict[str, Any],
    path: str,
    value: object,
) -> None:
    """Store a default at its object path and at nested field paths."""
    if isinstance(value, Mapping):
        normalized = deepcopy(dict(value))
        defaults[path] = normalized
        for field_name, field_value in normalized.items():
            _flatten_defaults(defaults, f"{path}.{field_name}", field_value)
        return
    defaults[path] = deepcopy(value)


def _binding_channels(track: AuthoringTrackIntent) -> list[str]:
    """Return explicit source mnemonics present on one intent track."""
    if not isinstance(track.bindings, list):
        return []
    channels: list[str] = []
    for binding in track.bindings:
        if not isinstance(binding, (AuthoringCurveBindingIntent, AuthoringRasterBindingIntent)):
            continue
        if isinstance(binding.channel, str) and binding.channel.strip():
            channels.append(binding.channel.strip())
    return channels


def _recommended_channels(entry: Mapping[str, Any]) -> set[str]:
    """Return normalized channel-family members from one catalog entry."""
    return _normalized_values(entry.get("recommended_channels"))


def _binding_template_channels(
    template: Mapping[str, Any],
    preset: Mapping[str, Any] | None = None,
) -> set[str]:
    """Return normalized channel members from catalog-only family metadata."""
    alias_id = template.get("alias_id")
    if not isinstance(alias_id, str) or not isinstance(preset, Mapping):
        return set()
    families = preset.get("channel_families")
    if not isinstance(families, Mapping):
        return set()
    return _normalized_values(families.get(alias_id))


def _track_name_matches(track: AuthoringTrackIntent, entry: Mapping[str, Any]) -> bool:
    """Return whether a track identity names one catalog family."""
    title = track.title if isinstance(track.title, str) else ""
    identity = f"{_normalize(track.track_id)} {_normalize(title)}"
    family_tokens = (
        _normalize(entry.get("id", "")),
        _normalize(entry.get("label", "")),
    )
    return any(token and (token in identity or identity in token) for token in family_tokens)


def _entry_channels(entry: Mapping[str, Any]) -> set[str]:
    """Return all channels advertised by a track or style family."""
    channels = _recommended_channels(entry)
    for template in entry.get("binding_templates", []):
        if isinstance(template, Mapping):
            channels.update(_binding_template_channels(template, entry))
    return channels


def _track_match_score(
    track: AuthoringTrackIntent,
    entry: Mapping[str, Any],
) -> int:
    """Score one generic family without selecting ties."""
    entry_kind = str(entry.get("kind", "")).strip()
    if isinstance(track.kind, str) and entry_kind and track.kind != entry_kind:
        return 0
    channels = {_normalize(channel) for channel in _binding_channels(track)}
    family_channels = _entry_channels(entry)
    if channels and (not family_channels or not channels.issubset(family_channels)):
        return 0
    score = 0
    if isinstance(track.kind, str) and track.kind == entry_kind:
        score += 20
    if _track_name_matches(track, entry):
        score += 30
    if channels and family_channels:
        score += 25 + len(channels & family_channels)
    if not channels and not _track_name_matches(track, entry):
        return 0
    return score


def _select_family(
    track: AuthoringTrackIntent,
    entries: list[dict[str, object]],
) -> tuple[dict[str, object] | None, str | None, str | None]:
    """Select one unique family or return an ambiguity warning."""
    scored = [
        (score, entry) for entry in entries if (score := _track_match_score(track, entry)) > 0
    ]
    if not scored:
        return None, None, None
    highest = max(score for score, _entry in scored)
    winners = [entry for score, entry in scored if score == highest]
    if len(winners) != 1:
        ids = ", ".join(str(entry.get("id", "")) for entry in winners)
        return None, None, f"Ambiguous defaults for track {track.track_id!r}: {ids}."
    selected = winners[0]
    return selected, str(selected.get("id", "")).strip() or None, None


def _template_for_binding(
    binding: AuthoringCurveBindingIntent | AuthoringRasterBindingIntent,
    preset: Mapping[str, Any] | None,
) -> Mapping[str, Any] | None:
    """Select one style template by explicit channel-family metadata."""
    if preset is None or not isinstance(binding.channel, str):
        return None
    channel = _normalize(binding.channel)
    matches = [
        template
        for template in preset.get("binding_templates", [])
        if isinstance(template, Mapping) and channel in _binding_template_channels(template, preset)
    ]
    return matches[0] if len(matches) == 1 else None


def _add_binding_defaults(
    defaults: dict[str, Any],
    *,
    binding_path: str,
    template: Mapping[str, Any] | None,
    fallback: Mapping[str, Any] | None,
) -> None:
    """Add specific template values, then generic family fallback values."""
    for candidate in (fallback, template):
        if not isinstance(candidate, Mapping):
            continue
        patch = _canonical_patch(candidate)
        for field_name, field_value in patch.items():
            _flatten_defaults(defaults, f"{binding_path}.{field_name}", field_value)


def _add_track_defaults(
    defaults: dict[str, Any],
    *,
    track_path: str,
    track: AuthoringTrackIntent,
    archetype: Mapping[str, Any] | None,
    preset: Mapping[str, Any] | None,
) -> None:
    """Add generic track, binding, and presentation defaults."""
    track_patches: list[Mapping[str, Any]] = []
    if isinstance(archetype, Mapping):
        archetype_patch = {
            "kind": archetype.get("kind"),
            "title": archetype.get("label"),
            "width_mm": archetype.get("default_width_mm"),
        }
        if isinstance(archetype.get("recommended_track_patch"), Mapping):
            archetype_patch.update(archetype["recommended_track_patch"])
        track_patches.append(archetype_patch)
    if isinstance(preset, Mapping) and isinstance(preset.get("track_patch"), Mapping):
        track_patches.insert(0, preset["track_patch"])

    for patch in track_patches:
        for field_name, field_value in _canonical_patch(patch).items():
            _flatten_defaults(defaults, f"{track_path}.{field_name}", field_value)

    fallback_binding = (
        archetype.get("recommended_binding") if isinstance(archetype, Mapping) else None
    )
    if not isinstance(track.bindings, list):
        return
    for binding in track.bindings:
        if not isinstance(binding, (AuthoringCurveBindingIntent, AuthoringRasterBindingIntent)):
            continue
        binding_path = f"{track_path}.bindings[{binding.binding_id}]"
        template = _template_for_binding(binding, preset)
        _add_binding_defaults(
            defaults,
            binding_path=binding_path,
            template=template,
            fallback=fallback_binding,
        )


def generic_authoring_defaults(
    intent: AuthoringDocumentIntent,
) -> AuthoringDefaultsResolution:
    """Return generic defaults for omitted fields in one typed desired state."""
    defaults: dict[str, Any] = {}
    matched_families: dict[str, str] = {}
    warnings: list[str] = []
    archetypes = track_archetype_catalog()
    presets = style_preset_catalog()
    if not isinstance(intent.sections, list):
        return AuthoringDefaultsResolution(defaults, matched_families)

    for section in intent.sections:
        if not hasattr(section, "tracks") or not isinstance(section.tracks, list):
            continue
        for track in section.tracks:
            if not isinstance(track, AuthoringTrackIntent):
                continue
            track_path = f"sections[{section.section_id}].tracks[{track.track_id}]"
            archetype, archetype_id, archetype_warning = _select_family(track, archetypes)
            preset, preset_id, preset_warning = _select_family(track, presets)
            if archetype_id:
                matched_families[f"{track_path}.archetype"] = archetype_id
            if preset_id:
                matched_families[f"{track_path}.preset"] = preset_id
            for warning in (archetype_warning, preset_warning):
                if warning:
                    warnings.append(warning)
            if archetype is None and preset is None:
                continue
            _add_track_defaults(
                defaults,
                track_path=track_path,
                track=track,
                archetype=archetype,
                preset=preset,
            )

    return AuthoringDefaultsResolution(
        defaults=defaults,
        matched_families=matched_families,
        warnings=tuple(dict.fromkeys(warnings)),
    )


__all__ = ["AuthoringDefaultsResolution", "generic_authoring_defaults"]
