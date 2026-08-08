###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Asset-backed authoring defaults and style catalogs."""

from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from importlib.resources import files
from typing import Any

import yaml

ASSET_PACKAGE = "wellplot.mcp.assets"
DEFAULTS_ASSET = "defaults/authoring_defaults.yaml"


def _require_mapping(value: object, *, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be a mapping.")
    return dict(value)


def _require_entries(value: object, *, field_name: str) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list):
        raise ValueError(f"Authoring defaults field {field_name!r} must be a list.")
    entries: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(value):
        entry = _require_mapping(item, context=f"authoring defaults {field_name}[{index}]")
        identifier = entry.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            raise ValueError(
                f"Authoring defaults {field_name}[{index}].id must be a non-empty string."
            )
        normalized_id = identifier.strip().lower()
        if normalized_id in seen_ids:
            raise ValueError(f"Duplicate authoring defaults id {identifier!r}.")
        seen_ids.add(normalized_id)
        entry["id"] = identifier.strip()
        entries.append(entry)
    if not entries:
        raise ValueError(f"Authoring defaults field {field_name!r} must not be empty.")
    return tuple(entries)


@lru_cache(maxsize=1)
def _load_defaults() -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
    """Load and validate the packaged defaults catalog once per process."""
    asset = files(ASSET_PACKAGE).joinpath(DEFAULTS_ASSET)
    payload = _require_mapping(
        yaml.safe_load(asset.read_text(encoding="utf-8")),
        context=DEFAULTS_ASSET,
    )
    if payload.get("version") != 1:
        raise ValueError(f"{DEFAULTS_ASSET} must declare version 1.")
    return (
        _require_entries(payload.get("track_archetypes"), field_name="track_archetypes"),
        _require_entries(payload.get("style_presets"), field_name="style_presets"),
    )


def track_archetype_catalog() -> list[dict[str, object]]:
    """Return defensive copies of the asset-backed track archetypes."""
    return deepcopy(list(_load_defaults()[0]))


def style_preset_catalog() -> list[dict[str, object]]:
    """Return defensive copies of the asset-backed style presets."""
    return deepcopy(list(_load_defaults()[1]))


def style_preset_by_id(preset_id: str) -> dict[str, object]:
    """Return one style preset by id or raise a catalog error."""
    normalized = str(preset_id).strip().lower()
    presets = style_preset_catalog()
    for preset in presets:
        if str(preset.get("id", "")).strip().lower() == normalized:
            return preset
    available = [str(preset.get("id", "")) for preset in presets]
    raise ValueError(f"preset_id must be one of {available}, got {preset_id!r}.")
