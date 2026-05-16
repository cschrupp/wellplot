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

"""Deterministic header archetype assets shared by MCP authoring and notebook helpers."""

from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from importlib.resources import files

import yaml

ASSET_PACKAGE = "wellplot.mcp.assets"
HEADER_ARCHETYPE_DIR = "header_archetypes"

STARTER_KIND_TO_SERVICE_TITLE = {
    "open_hole_quicklook": "Open Hole Quicklook",
    "cased_hole_quicklook": "Cased Hole Quicklook",
}
HEADER_ARCHETYPE_ORDER = (
    "open_hole",
    "cased_hole",
)


def _require_mapping(raw: object, *, context: str) -> dict[str, object]:
    """Return one validated mapping object."""
    if not isinstance(raw, dict):
        raise ValueError(f"{context} must be a mapping.")
    return dict(raw)


def _require_non_empty_string(value: object, *, field_name: str, context: str) -> str:
    """Return one stripped non-empty string field."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context} field {field_name!r} must be a non-empty string.")
    return value.strip()


def _require_string_list(value: object, *, field_name: str, context: str) -> list[str]:
    """Return one list of stripped non-empty strings."""
    if not isinstance(value, list):
        raise ValueError(f"{context} field {field_name!r} must be a list of strings.")
    items: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{context} field {field_name!r}[{index}] must be a non-empty string.")
        items.append(item.strip())
    return items


def _validate_general_fields(
    heading: dict[str, object],
    *,
    context: str,
) -> None:
    """Validate the general-field collection for duplicate or malformed keys."""
    fields = heading.get("general_fields")
    if fields is None:
        return
    if not isinstance(fields, list):
        raise ValueError(f"{context} heading.general_fields must be a list.")
    seen_keys: set[str] = set()
    for index, item in enumerate(fields):
        if not isinstance(item, dict):
            raise ValueError(f"{context} heading.general_fields[{index}] must be a mapping.")
        key = _require_non_empty_string(
            item.get("key"),
            field_name="key",
            context=f"{context} heading.general_fields[{index}]",
        )
        if key in seen_keys:
            raise ValueError(f"{context} heading.general_fields contains duplicate key {key!r}.")
        seen_keys.add(key)


def _validate_service_titles(
    heading: dict[str, object],
    *,
    context: str,
) -> None:
    """Validate one service-title list shape."""
    service_titles = heading.get("service_titles")
    if service_titles is None:
        return
    if not isinstance(service_titles, list):
        raise ValueError(f"{context} heading.service_titles must be a list.")
    for index, item in enumerate(service_titles):
        if isinstance(item, str):
            if not item.strip():
                raise ValueError(
                    f"{context} heading.service_titles[{index}] must not be empty when string."
                )
            continue
        if not isinstance(item, dict):
            raise ValueError(
                f"{context} heading.service_titles[{index}] must be a string or mapping."
            )
        if "value" in item and not isinstance(item["value"], str):
            raise ValueError(
                f"{context} heading.service_titles[{index}].value must be a string when set."
            )


def _validate_detail_rows(
    heading: dict[str, object],
    *,
    detail_kind: str,
    context: str,
) -> None:
    """Validate the detail-table structure of one archetype heading."""
    detail = heading.get("detail")
    if detail is None:
        return
    if not isinstance(detail, dict):
        raise ValueError(f"{context} heading.detail must be a mapping.")
    detail_mapping = dict(detail)
    if "kind" in detail_mapping:
        normalized_kind = _require_non_empty_string(
            detail_mapping.get("kind"),
            field_name="kind",
            context=f"{context} heading.detail",
        )
        if normalized_kind != detail_kind:
            raise ValueError(
                f"{context} heading.detail.kind {normalized_kind!r} must match "
                f"detail_kind {detail_kind!r}."
            )
    rows = detail_mapping.get("rows")
    if rows is None:
        return
    if not isinstance(rows, list):
        raise ValueError(f"{context} heading.detail.rows must be a list.")
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"{context} heading.detail.rows[{index}] must be a mapping.")
        has_label = isinstance(row.get("label"), str) and bool(str(row.get("label")).strip())
        label_cells = row.get("label_cells")
        has_label_cells = isinstance(label_cells, list) and bool(label_cells)
        if not has_label and not has_label_cells:
            raise ValueError(
                f"{context} heading.detail.rows[{index}] must define label or label_cells."
            )
        if has_label and has_label_cells:
            raise ValueError(
                f"{context} heading.detail.rows[{index}] cannot define both label and label_cells."
            )


def _validate_header_archetype_entry(raw: object, *, source_name: str) -> dict[str, object]:
    """Validate one loaded archetype asset and return a normalized mapping."""
    context = f"Header archetype asset {source_name!r}"
    entry = _require_mapping(raw, context=context)
    entry["id"] = _require_non_empty_string(entry.get("id"), field_name="id", context=context)
    entry["label"] = _require_non_empty_string(
        entry.get("label"),
        field_name="label",
        context=context,
    )
    entry["detail_kind"] = _require_non_empty_string(
        entry.get("detail_kind"),
        field_name="detail_kind",
        context=context,
    )
    entry["starter_kinds"] = _require_string_list(
        entry.get("starter_kinds", []),
        field_name="starter_kinds",
        context=context,
    )
    entry["notes"] = _require_string_list(
        entry.get("notes", []),
        field_name="notes",
        context=context,
    )
    heading = _require_mapping(entry.get("heading"), context=f"{context} heading")
    _validate_general_fields(heading, context=context)
    _validate_service_titles(heading, context=context)
    _validate_detail_rows(heading, detail_kind=entry["detail_kind"], context=context)
    entry["heading"] = heading
    return entry


@lru_cache(maxsize=1)
def _load_header_archetypes() -> tuple[dict[str, object], ...]:
    """Load and validate packaged header-archetype YAML assets."""
    archetype_dir = files(ASSET_PACKAGE).joinpath(HEADER_ARCHETYPE_DIR)
    entries: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    seen_starter_kinds: dict[str, str] = {}
    for asset in sorted(archetype_dir.iterdir(), key=lambda item: item.name):
        if asset.name.startswith("_") or asset.suffix.lower() not in {".yaml", ".yml"}:
            continue
        loaded = yaml.safe_load(asset.read_text(encoding="utf-8"))
        entry = _validate_header_archetype_entry(loaded, source_name=asset.name)
        normalized_id = str(entry["id"]).strip().lower()
        if normalized_id in seen_ids:
            raise ValueError(f"Duplicate header archetype id {entry['id']!r}.")
        seen_ids.add(normalized_id)
        for starter_kind in entry["starter_kinds"]:
            normalized_kind = starter_kind.strip().lower()
            existing = seen_starter_kinds.get(normalized_kind)
            if existing is not None and existing != normalized_id:
                raise ValueError(
                    f"Starter kind {starter_kind!r} is assigned to multiple header "
                    f"archetypes: {existing!r} and {normalized_id!r}."
                )
            seen_starter_kinds[normalized_kind] = normalized_id
        entries.append(entry)
    if not entries:
        raise RuntimeError("No header archetype assets were found.")
    order_map = {value: index for index, value in enumerate(HEADER_ARCHETYPE_ORDER)}
    entries.sort(
        key=lambda entry: (
            order_map.get(str(entry["id"]).strip().lower(), len(order_map)),
            str(entry["label"]).strip().lower(),
        )
    )
    return tuple(entries)


def header_archetype_catalog() -> list[dict[str, object]]:
    """Return the public catalog metadata for deterministic header archetypes."""
    catalog: list[dict[str, object]] = []
    for entry in _load_header_archetypes():
        heading = dict(entry["heading"])
        detail = dict(heading.get("detail", {}))
        rows = list(detail.get("rows", []))
        catalog.append(
            {
                "id": str(entry["id"]),
                "label": str(entry["label"]),
                "detail_kind": str(entry["detail_kind"]),
                "starter_kinds": list(entry.get("starter_kinds", [])),
                "general_field_keys": [
                    str(item.get("key", ""))
                    for item in heading.get("general_fields", [])
                    if isinstance(item, dict) and str(item.get("key", "")).strip()
                ],
                "service_title_count": len(
                    [
                        item
                        for item in heading.get("service_titles", [])
                        if isinstance(item, dict | str)
                    ]
                ),
                "detail_row_labels": [
                    str(row.get("label", "")).strip()
                    if isinstance(row, dict) and str(row.get("label", "")).strip()
                    else " / ".join(
                        str(value).strip()
                        for value in row.get("label_cells", [])
                        if str(value).strip()
                    )
                    for row in rows
                    if isinstance(row, dict)
                ],
                "notes": list(entry.get("notes", [])),
            }
        )
    return catalog


def header_archetype_heading(archetype_id: str) -> dict[str, object]:
    """Return one deep-copied heading mapping for the requested archetype id."""
    normalized = str(archetype_id).strip().lower()
    for entry in _load_header_archetypes():
        if str(entry["id"]).strip().lower() == normalized:
            return deepcopy(dict(entry["heading"]))
    available = [str(entry["id"]) for entry in _load_header_archetypes()]
    raise ValueError(
        f"Unknown header archetype {archetype_id!r}. Available archetypes: {available}."
    )


def header_archetype_ids() -> list[str]:
    """Return the supported header archetype ids."""
    return [str(entry["id"]) for entry in _load_header_archetypes()]


def default_header_archetype_for_starter_kind(kind: str) -> str:
    """Return the deterministic default header archetype for one starter kind."""
    normalized = str(kind).strip().lower()
    for entry in _load_header_archetypes():
        starter_kinds = [str(item).strip().lower() for item in entry.get("starter_kinds", [])]
        if normalized in starter_kinds:
            return str(entry["id"])
    available = sorted(
        {
            str(item).strip().lower()
            for entry in _load_header_archetypes()
            for item in entry.get("starter_kinds", [])
        }
    )
    raise ValueError(f"Supported starter kinds: {available}.")


def default_service_title_for_starter_kind(kind: str) -> str:
    """Return the starter service-title text paired with one shipped starter kind."""
    normalized = str(kind).strip().lower()
    try:
        return STARTER_KIND_TO_SERVICE_TITLE[normalized]
    except KeyError as exc:
        available = sorted(STARTER_KIND_TO_SERVICE_TITLE)
        raise ValueError(f"Supported starter kinds: {available}.") from exc
