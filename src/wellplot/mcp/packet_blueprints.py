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

"""Asset-backed packet blueprints shared by agent planning workflows."""

from __future__ import annotations

import re
from copy import deepcopy
from functools import lru_cache
from importlib.resources import files

import yaml

ASSET_PACKAGE = "wellplot.mcp.assets"
PACKET_BLUEPRINT_DIR = "packet_blueprints"


def _require_mapping(raw: object, *, context: str) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise ValueError(f"{context} must be a mapping.")
    return dict(raw)


def _require_non_empty_string(value: object, *, field_name: str, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context} field {field_name!r} must be a non-empty string.")
    return value.strip()


def _require_string_list(value: object, *, field_name: str, context: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{context} field {field_name!r} must be a list of strings.")
    items: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{context} field {field_name!r}[{index}] must be a non-empty string.")
        items.append(item.strip())
    return items


def _validate_track_templates(section: dict[str, object], *, context: str) -> None:
    track_templates = section.get("track_templates", [])
    if not isinstance(track_templates, list) or not track_templates:
        raise ValueError(f"{context} track_templates must be a non-empty list.")
    seen_track_ids: set[str] = set()
    for index, item in enumerate(track_templates):
        track_context = f"{context} track_templates[{index}]"
        track = _require_mapping(item, context=track_context)
        track_id = _require_non_empty_string(
            track.get("id"), field_name="id", context=track_context
        )
        if track_id in seen_track_ids:
            raise ValueError(f"{context} contains duplicate track template id {track_id!r}.")
        seen_track_ids.add(track_id)
        _require_non_empty_string(track.get("kind"), field_name="kind", context=track_context)


def _validate_section_templates(entry: dict[str, object], *, context: str) -> None:
    section_templates = entry.get("section_templates")
    if not isinstance(section_templates, list) or not section_templates:
        raise ValueError(f"{context} field 'section_templates' must be a non-empty list.")
    seen_section_ids: set[str] = set()
    for index, item in enumerate(section_templates):
        section_context = f"{context} section_templates[{index}]"
        section = _require_mapping(item, context=section_context)
        section_id = _require_non_empty_string(
            section.get("id"), field_name="id", context=section_context
        )
        if section_id in seen_section_ids:
            raise ValueError(f"{context} contains duplicate section template id {section_id!r}.")
        seen_section_ids.add(section_id)
        _require_non_empty_string(section.get("title"), field_name="title", context=section_context)
        _require_non_empty_string(
            section.get("source_slot"),
            field_name="source_slot",
            context=section_context,
        )
        _validate_track_templates(section, context=section_context)
        expected_bindings = section.get("expected_bindings_by_track", {})
        if not isinstance(expected_bindings, dict):
            raise ValueError(f"{section_context} expected_bindings_by_track must be a mapping.")
        for track_id, channels in expected_bindings.items():
            if not isinstance(track_id, str) or not track_id.strip():
                raise ValueError(
                    f"{section_context} expected_bindings_by_track keys must be non-empty strings."
                )
            _require_string_list(
                channels,
                field_name=f"expected_bindings_by_track.{track_id}",
                context=section_context,
            )


def _validate_plan_phases(entry: dict[str, object], *, context: str) -> None:
    phases = entry.get("plan_phases")
    if not isinstance(phases, list) or not phases:
        raise ValueError(f"{context} field 'plan_phases' must be a non-empty list.")
    seen_phase_ids: set[str] = set()
    for index, item in enumerate(phases):
        phase_context = f"{context} plan_phases[{index}]"
        phase = _require_mapping(item, context=phase_context)
        phase_id = _require_non_empty_string(
            phase.get("id"), field_name="id", context=phase_context
        )
        if phase_id in seen_phase_ids:
            raise ValueError(f"{context} contains duplicate phase id {phase_id!r}.")
        seen_phase_ids.add(phase_id)
        _require_non_empty_string(phase.get("kind"), field_name="kind", context=phase_context)
        _require_non_empty_string(phase.get("summary"), field_name="summary", context=phase_context)
        _require_non_empty_string(
            phase.get("instructions"),
            field_name="instructions",
            context=phase_context,
        )
        _require_string_list(
            phase.get("tool_families", []), field_name="tool_families", context=phase_context
        )
        _require_string_list(
            phase.get("preconditions", []), field_name="preconditions", context=phase_context
        )
        _require_string_list(
            phase.get("success_checks", []), field_name="success_checks", context=phase_context
        )
        success_check_specs = phase.get("success_check_specs", [])
        if success_check_specs:
            if not isinstance(success_check_specs, list):
                raise ValueError(f"{phase_context} field 'success_check_specs' must be a list.")
            for spec_index, raw_spec in enumerate(success_check_specs):
                spec_context = f"{phase_context} success_check_specs[{spec_index}]"
                spec = _require_mapping(raw_spec, context=spec_context)
                kind = _require_non_empty_string(
                    spec.get("kind"), field_name="kind", context=spec_context
                )
                if kind in {"section_exists", "track_exists", "binding_channel_exists"}:
                    _require_non_empty_string(
                        spec.get("section_id"), field_name="section_id", context=spec_context
                    )
                if kind in {"track_exists", "binding_channel_exists"}:
                    _require_non_empty_string(
                        spec.get("track_id"), field_name="track_id", context=spec_context
                    )
                if kind == "binding_channel_exists":
                    _require_non_empty_string(
                        spec.get("channel"), field_name="channel", context=spec_context
                    )
                    if "min_count" in spec and not isinstance(spec.get("min_count"), int):
                        raise ValueError(
                            f"{spec_context} field 'min_count' must be an integer when present."
                        )


def _validate_packet_blueprint_entry(raw: object, *, source_name: str) -> dict[str, object]:
    context = f"Packet blueprint asset {source_name!r}"
    entry = _require_mapping(raw, context=context)
    entry["id"] = _require_non_empty_string(entry.get("id"), field_name="id", context=context)
    entry["label"] = _require_non_empty_string(
        entry.get("label"), field_name="label", context=context
    )
    entry["starter_kind"] = _require_non_empty_string(
        entry.get("starter_kind"),
        field_name="starter_kind",
        context=context,
    )
    entry["header_archetype"] = _require_non_empty_string(
        entry.get("header_archetype"),
        field_name="header_archetype",
        context=context,
    )
    entry["source_formats"] = _require_string_list(
        entry.get("source_formats", []),
        field_name="source_formats",
        context=context,
    )
    entry["use_cases"] = _require_string_list(
        entry.get("use_cases", []),
        field_name="use_cases",
        context=context,
    )
    entry["notes"] = _require_string_list(
        entry.get("notes", []), field_name="notes", context=context
    )
    entry["unsupported_features"] = _require_string_list(
        entry.get("unsupported_features", []),
        field_name="unsupported_features",
        context=context,
    )
    if "example_id" in entry and entry["example_id"] is not None:
        entry["example_id"] = _require_non_empty_string(
            entry.get("example_id"),
            field_name="example_id",
            context=context,
        )
    remarks_templates = entry.get("remarks_templates", [])
    if remarks_templates:
        if not isinstance(remarks_templates, list):
            raise ValueError(f"{context} field 'remarks_templates' must be a list.")
        for index, item in enumerate(remarks_templates):
            remark_context = f"{context} remarks_templates[{index}]"
            remark = _require_mapping(item, context=remark_context)
            _require_non_empty_string(
                remark.get("title"), field_name="title", context=remark_context
            )
    _validate_section_templates(entry, context=context)
    _validate_plan_phases(entry, context=context)
    return entry


@lru_cache(maxsize=1)
def _load_packet_blueprints() -> tuple[dict[str, object], ...]:
    blueprint_dir = files(ASSET_PACKAGE).joinpath(PACKET_BLUEPRINT_DIR)
    entries: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for asset in sorted(blueprint_dir.iterdir(), key=lambda item: item.name):
        if asset.name.startswith("_") or asset.suffix.lower() not in {".yaml", ".yml"}:
            continue
        loaded = yaml.safe_load(asset.read_text(encoding="utf-8"))
        entry = _validate_packet_blueprint_entry(loaded, source_name=asset.name)
        normalized_id = str(entry["id"]).strip().lower()
        if normalized_id in seen_ids:
            raise ValueError(f"Duplicate packet blueprint id {entry['id']!r}.")
        seen_ids.add(normalized_id)
        entries.append(entry)
    if not entries:
        raise RuntimeError("No packet blueprint assets were found.")
    entries.sort(key=lambda entry: str(entry["label"]).strip().lower())
    return tuple(entries)


def packet_blueprint_catalog() -> list[dict[str, object]]:
    """Return shallow catalog entries for all shipped packet blueprints."""
    catalog: list[dict[str, object]] = []
    for entry in _load_packet_blueprints():
        section_templates = list(entry.get("section_templates", []))
        catalog.append(
            {
                "id": str(entry["id"]),
                "label": str(entry["label"]),
                "starter_kind": str(entry["starter_kind"]),
                "header_archetype": str(entry["header_archetype"]),
                "example_id": entry.get("example_id"),
                "source_formats": list(entry.get("source_formats", [])),
                "use_cases": list(entry.get("use_cases", [])),
                "section_ids": [str(section.get("id", "")) for section in section_templates],
                "track_ids_by_section": {
                    str(section.get("id", "")): [
                        str(track.get("id", ""))
                        for track in section.get("track_templates", [])
                        if isinstance(track, dict)
                    ]
                    for section in section_templates
                    if isinstance(section, dict)
                },
                "unsupported_features": list(entry.get("unsupported_features", [])),
                "notes": list(entry.get("notes", [])),
            }
        )
    return catalog


def packet_blueprint_spec(blueprint_id: str) -> dict[str, object]:
    """Return one full packet blueprint specification by identifier."""
    normalized = str(blueprint_id).strip().lower()
    for entry in _load_packet_blueprints():
        if str(entry["id"]).strip().lower() == normalized:
            return deepcopy(entry)
    available = [str(entry["id"]) for entry in _load_packet_blueprints()]
    raise ValueError(f"Unknown packet blueprint {blueprint_id!r}. Available: {available}.")


def packet_blueprint_ids() -> list[str]:
    """Return the identifiers for all shipped packet blueprints."""
    return [str(entry["id"]) for entry in _load_packet_blueprints()]


def match_packet_blueprint(text: str) -> str | None:
    """Return the best-matching packet blueprint id for one freeform request."""
    normalized_text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    best_match: tuple[int, str] | None = None
    for entry in _load_packet_blueprints():
        blueprint_id = str(entry["id"]).strip().lower()
        blueprint_label = str(entry.get("label", "")).strip().lower()
        direct_keywords = [blueprint_id, blueprint_label]
        use_case_keywords = [str(item).strip().lower() for item in entry.get("use_cases", [])]
        score = 0
        matched_direct = False
        for keyword in direct_keywords:
            normalized_keyword = re.sub(r"[^a-z0-9]+", " ", keyword).strip()
            if normalized_keyword and normalized_keyword in normalized_text:
                matched_direct = True
                score += 1
        for keyword in use_case_keywords:
            normalized_keyword = re.sub(r"[^a-z0-9]+", " ", keyword).strip()
            if normalized_keyword and normalized_keyword in normalized_text:
                score += 1
        if score <= 0:
            continue
        if not matched_direct and score < 2:
            continue
        blueprint_id_value = str(entry["id"])
        if best_match is None or score > best_match[0]:
            best_match = (score, blueprint_id_value)
    return None if best_match is None else best_match[1]
