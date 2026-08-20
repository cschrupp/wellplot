###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Small deterministic recovery planner for stalled stable authoring requests."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..authoring_defaults import form_default_catalog, style_preset_catalog, track_archetype_catalog


@dataclass(frozen=True)
class StableFallbackOperation:
    """One stable MCP operation produced by the catalog planner."""

    tool_name: str
    arguments: dict[str, object]


@dataclass(frozen=True)
class StableFallbackPlan:
    """A generic track construction plan resolved from catalogs and source data."""

    section_id: str
    track_id: str
    operations: tuple[StableFallbackOperation, ...]
    expected_channels: tuple[str, ...]
    expected_scale: dict[str, object] | None
    family_id: str | None
    preset_id: str | None
    skipped_channels: tuple[str, ...]
    expected_fill: dict[str, object] | None
    expected_binding_scales: dict[str, dict[str, object]]
    expected_binding_labels: dict[str, str]


def _norm(value: object) -> str:
    """Normalize catalog and request text for matching."""
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()


def _words(value: object) -> set[str]:
    """Return normalized words from one value."""
    return {word for word in _norm(value).split() if len(word) > 1}


def _request_family(goal: str) -> str | None:
    """Extract an explicit family from a track creation or revision request."""
    match = re.search(
        r"\b(?:add|create|insert)\s+(?:(?:one|a|an|new)\s+)?"
        r"(?P<family>[a-z][a-z0-9 _/-]*?)\s+track\b",
        goal,
        re.IGNORECASE,
    )
    if match is None:
        match = re.search(
            r"\b(?:revise|update|modify|change)\s+(?:the\s+)?(?:existing\s+)?"
            r"[`\"'](?P<family>[a-z][a-z0-9_./-]*)[`\"']"
            r"(?:\s+[a-z][a-z0-9_/-]*){0,2}\s+track\b",
            goal,
            re.IGNORECASE,
        )
    if match is None:
        match = re.search(
            r"\b(?:in|on)\s+the\s+"
            r"(?P<family>[a-z][a-z0-9 _/-]*?)\s+track\b",
            goal,
            re.IGNORECASE,
        )
    if match is None:
        match = re.search(
            r"\b(?:revise|update|modify|change)\s+(?:the\s+)?(?:existing\s+)?"
            r"(?P<family>[a-z][a-z0-9 _/-]*?)\s+track\b",
            goal,
            re.IGNORECASE,
        )
    if match is None:
        return None
    family = re.sub(
        r"\b(?:existing|new|wide|narrow|standard|overview)\b",
        " ",
        match.group("family"),
    )
    return re.sub(r"\s+", " ", family).strip() or None


def is_track_request(goal: str) -> bool:
    """Return whether the request explicitly creates or revises a track."""
    return _request_family(goal) is not None


def _score(query: str, entry: Mapping[str, Any], goal: str = "") -> int:
    """Score one catalog entry against a request family and its wording."""
    identity = " ".join(str(entry.get(key, "")) for key in ("id", "label", "summary"))
    identity_words = _words(query) & _words(identity)
    score = 4 * len(identity_words)
    if _norm(query).replace(" ", "") in _norm(identity).replace(" ", ""):
        score += 8
    if score == 0:
        return 0
    use_cases = entry.get("use_cases", [])
    if isinstance(use_cases, list):
        score += 5 * len(_words(goal) & _words(" ".join(map(str, use_cases))))
    return score


def _match(
    query: str,
    entries: Sequence[Mapping[str, Any]],
    goal: str = "",
) -> Mapping[str, Any] | None:
    """Return one unique best catalog match."""
    scored = [(_score(query, entry, goal), entry) for entry in entries]
    scored = [(score, entry) for score, entry in scored if score > 0]
    if not scored:
        return None
    best = max(score for score, _entry in scored)
    winners = [entry for score, entry in scored if score == best]
    return winners[0] if len(winners) == 1 else None


def _scale(value: object) -> dict[str, object] | None:
    """Normalize a scale mapping to stable-tool keys."""
    if not isinstance(value, Mapping):
        return None
    minimum = value.get("min", value.get("minimum"))
    maximum = value.get("max", value.get("maximum"))
    if minimum is None or maximum is None:
        return None
    kind = str(value.get("kind", value.get("type", "linear"))).lower()
    kind = {"logarithmic": "log", "tangent": "tangential"}.get(kind, kind)
    return {"kind": kind, "min": float(minimum), "max": float(maximum)}


def _requested_scale(goal: str) -> dict[str, object] | None:
    """Parse one explicit scale clause, including ``scale to A to B`` wording."""
    number = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"
    match = re.search(
        rf"(?P<kind>logarithmic|log|linear)?\s*scale\s+(?:(?:from|to)\s+)?"
        rf"(?P<min>{number})"
        rf"\s+to\s+(?P<max>{number})",
        goal,
        re.IGNORECASE,
    )
    if match is None:
        match = re.search(
            rf"(?P<kind>logarithmic|log|linear)?\s*"
            rf"(?:track|curve|curves?)\s+scales?(?:[^.;\n]*?)?"
            rf"(?:from|to)\s+(?P<min>{number})\s+to\s+(?P<max>{number})",
            goal,
            re.IGNORECASE,
        )
    if match is None:
        return None
    kind = (match.group("kind") or "linear").lower()
    return {
        "kind": "log" if kind in {"log", "logarithmic"} else "linear",
        "min": float(match.group("min")),
        "max": float(match.group("max")),
    }


def _requested_scale_scope(goal: str) -> tuple[bool, bool]:
    """Return whether an explicit scale request targets the track and curves."""
    track_scale = re.search(r"\btrack(?:'s)?\s+scale\b", goal, re.IGNORECASE)
    curve_scale = re.search(
        r"(?:\balong\s+with\s+all\s+(?:the\s+)?curves?\b|"
        r"\ball\s+(?:the\s+)?curves?\s+scales?\b|"
        r"\bcurves?\s+scales?\b|\bscale\s+(?:of|for)\s+(?:all\s+)?curves?\b)",
        goal,
        re.IGNORECASE,
    )
    return track_scale is not None, curve_scale is not None


def _requested_channel_scale(goal: str, channel: str) -> dict[str, object] | None:
    """Parse an explicit scale associated with one source channel."""
    number = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"
    escaped_channel = re.escape(channel)
    patterns = (
        rf"(?P<min>{number})\s+to\s+(?P<max>{number})\s+as\s+(?:the\s+)?"
        rf"{escaped_channel}\s+(?:curve\s+)?scale\b",
        rf"\b{escaped_channel}\s+(?:curve\s+)?scale(?:\s+from)?\s+"
        rf"(?P<min>{number})\s+to\s+(?P<max>{number})",
    )
    for pattern in patterns:
        match = re.search(pattern, goal, re.IGNORECASE)
        if match is not None:
            return {
                "kind": "linear",
                "min": float(match.group("min")),
                "max": float(match.group("max")),
            }
    return None


def _source_selector_matches(
    selector: object,
    summary: Mapping[str, Any] | None,
) -> bool:
    """Evaluate one asset-declared selector against inspected source statistics."""
    if not isinstance(selector, Mapping) or not isinstance(summary, Mapping):
        return False
    value_min = summary.get("value_min")
    value_max = summary.get("value_max")
    if not isinstance(value_min, (int, float)) or not isinstance(value_max, (int, float)):
        return False
    statistics = {
        "value_min": float(value_min),
        "value_max": float(value_max),
        "value_abs_max": max(abs(float(value_min)), abs(float(value_max))),
    }
    comparisons = {
        "gt": lambda actual, expected: actual > expected,
        "gte": lambda actual, expected: actual >= expected,
        "lt": lambda actual, expected: actual < expected,
        "lte": lambda actual, expected: actual <= expected,
    }
    for condition, expected in selector.items():
        match = re.fullmatch(
            r"(?P<stat>value_(?:abs_)?(?:min|max))_(?P<op>gt|gte|lt|lte)",
            str(condition),
        )
        if match is None or not isinstance(expected, (int, float)):
            return False
        actual = statistics.get(match.group("stat"))
        comparison = comparisons[match.group("op")]
        if actual is None or not comparison(actual, float(expected)):
            return False
    return bool(selector)


def _template_scale(
    template: Mapping[str, Any] | None,
    summary: Mapping[str, Any] | None,
) -> dict[str, object] | None:
    """Resolve an asset scale variant from deterministic source statistics."""
    if not isinstance(template, Mapping):
        return None
    variants = template.get("scale_variants", [])
    if isinstance(variants, list):
        for variant in variants:
            if not isinstance(variant, Mapping):
                continue
            if _source_selector_matches(variant.get("when"), summary):
                selected = _scale(variant.get("scale"))
                if selected is not None:
                    return selected
    return _scale(template.get("scale"))


def _template_label(template: Mapping[str, Any] | None, channel: str) -> str | None:
    """Render one asset-backed semantic label without hiding its mnemonic."""
    if not isinstance(template, Mapping):
        return None
    label = template.get("label")
    if not isinstance(label, str) or not label.strip():
        return None
    label_template = template.get("label_template")
    if not isinstance(label_template, str) or not label_template.strip():
        return label
    return label_template.replace("{label}", label).replace("{channel}", channel)


def _requested_width(goal: str, default_width: float) -> float:
    """Resolve generic width modifiers without requiring a family catalog entry."""
    number = r"(?:\d+(?:\.\d*)?|\.\d+)"
    explicit = re.search(
        rf"\bwidth(?:_mm)?\s*(?:of|=|:)?\s*(?P<width>{number})\s*mm\b",
        goal,
        re.IGNORECASE,
    )
    if explicit is not None:
        return float(explicit.group("width"))
    if re.search(r"\b(?:half[- ]width|narrow)\b", goal, re.IGNORECASE):
        return default_width / 2.0
    if re.search(r"\bwide\b", goal, re.IGNORECASE):
        return default_width * 1.5
    return default_width


def _requested_channels(goal: str, available_channels: Sequence[str]) -> tuple[str, ...]:
    """Return explicitly named source channels in the order used by the request."""
    matches: list[tuple[int, str]] = []
    for channel in dict.fromkeys(str(item) for item in available_channels):
        if not channel.strip():
            continue
        match = re.search(rf"(?<![A-Za-z0-9]){re.escape(channel)}(?![A-Za-z0-9])", goal, re.I)
        if match is not None:
            matches.append((match.start(), channel))
    return tuple(channel for _position, channel in sorted(matches))


def _requested_move(
    goal: str,
    tracks: Sequence[Mapping[str, Any]],
    target_track_id: str,
) -> StableFallbackOperation | None:
    """Build a relative move operation for an explicitly named anchor track."""
    match = re.search(
        r"\b(?P<relation>after|before)\s+(?:the\s+)?[`\"']?"
        r"(?P<anchor>[A-Za-z][A-Za-z0-9 _/-]*?)[`\"']?\s+track\b",
        goal,
        re.IGNORECASE,
    )
    if match is None:
        return None
    relation = match.group("relation").lower()
    anchor_query = _norm(match.group("anchor")).replace(" ", "")
    remaining = [
        item
        for item in tracks
        if isinstance(item, Mapping) and str(item.get("id")) != target_track_id
    ]
    anchor_index = next(
        (
            index
            for index, item in enumerate(remaining)
            if anchor_query
            in _norm(f"{item.get('id', '')} {item.get('title', '')}").replace(" ", "")
        ),
        None,
    )
    if anchor_index is None:
        return None
    position = anchor_index + (2 if relation == "after" else 1)
    return StableFallbackOperation(
        "edit_track",
        {
            "operation": "move",
            "track_id": target_track_id,
            "new_index": position,
        },
    )


def _generic_style(goal: str) -> dict[str, object] | None:
    """Apply only an explicitly requested generic lightweight style modifier."""
    if re.search(r"\blight(?:er)?[- ]weight\b|\blightweight\b", goal, re.IGNORECASE):
        return {"line_width": 0.8}
    return None


def _context(goal: str) -> tuple[str | None, Mapping[str, Any] | None, Mapping[str, Any] | None]:
    """Resolve the request family, track archetype, and optional style preset."""
    family = _request_family(goal)
    if family is None:
        return None, None, None
    return (
        family,
        _match(family, track_archetype_catalog(), goal),
        _match(family, style_preset_catalog(), goal),
    )


def catalog_channel_candidates(goal: str) -> tuple[str, ...]:
    """Return source channels advertised by the matching catalog families."""
    _family, archetype, preset = _context(goal)
    channels: list[str] = []
    if isinstance(archetype, Mapping):
        channels.extend(map(str, archetype.get("recommended_channels", [])))
    families = preset.get("channel_families") if isinstance(preset, Mapping) else None
    if isinstance(families, Mapping):
        for values in families.values():
            if isinstance(values, list):
                channels.extend(map(str, values))
    return tuple(dict.fromkeys(channel for channel in channels if channel.strip()))


def _track(document: Mapping[str, Any], section_id: str, family: str) -> Mapping[str, Any] | None:
    """Find one existing track representing the requested family."""
    section = next(
        (
            item
            for item in document.get("sections", [])
            if isinstance(item, Mapping) and item.get("id") == section_id
        ),
        None,
    )
    if not isinstance(section, Mapping):
        return None
    query = _norm(family).replace(" ", "")
    matches = [
        item
        for item in section.get("tracks", [])
        if isinstance(item, Mapping)
        and query in _norm(f"{item.get('id', '')} {item.get('title', '')}").replace(" ", "")
    ]
    return matches[0] if len(matches) == 1 else None


def _template(preset: Mapping[str, Any] | None, alias: str) -> Mapping[str, Any] | None:
    """Return one preset binding template by semantic alias."""
    if not isinstance(preset, Mapping):
        return None
    return next(
        (
            item
            for item in preset.get("binding_templates", [])
            if isinstance(item, Mapping) and item.get("alias_id") == alias
        ),
        None,
    )


def build_catalog_fallback_plan(
    goal: str,
    *,
    section_id: str,
    document: Mapping[str, Any],
    available_channels: Sequence[str],
    channel_summaries: Mapping[str, Mapping[str, Any]] | None = None,
) -> StableFallbackPlan | None:
    """Build stable operations for a catalog-backed or open-world track request."""
    family, archetype, preset = _context(goal)
    if family is None:
        return None
    generic = archetype is None and preset is None

    current_track = _track(document, section_id, family)
    patch: dict[str, object] = {}
    if isinstance(archetype, Mapping) and isinstance(
        archetype.get("recommended_track_patch"), Mapping
    ):
        patch.update(archetype["recommended_track_patch"])
    if isinstance(preset, Mapping) and isinstance(preset.get("track_patch"), Mapping):
        patch.update(preset["track_patch"])
    kind = str(patch.get("kind") or (archetype or {}).get("kind", "normal"))
    form = next((item for item in form_default_catalog() if item.get("kind") == kind), {})
    title = str(patch.get("title") or (archetype or {}).get("label") or family)
    default_width = float(
        patch.get("width_mm")
        or (archetype or {}).get("default_width_mm")
        or form.get("default_width_mm", 28.0)
    )
    width = _requested_width(goal, default_width)
    requested_scale = _requested_scale(goal)
    explicit_track_scale, explicit_curve_scale = _requested_scale_scope(goal)
    if requested_scale is not None and not re.search(
        r"\b(?:logarithmic|log|linear)\s+scale\b",
        goal,
        re.IGNORECASE,
    ):
        existing_scale = _scale(current_track.get("x_scale")) if current_track else None
        if existing_scale is not None:
            requested_scale["kind"] = existing_scale["kind"]
    if current_track is None:
        x_scale = requested_scale or _scale(patch.get("x_scale"))
    else:
        x_scale = requested_scale if explicit_track_scale or not explicit_curve_scale else None
    if x_scale is None and current_track is None and isinstance(archetype, Mapping):
        recommended = archetype.get("recommended_binding")
        x_scale = _scale(recommended.get("scale")) if isinstance(recommended, Mapping) else None

    track_id = str(current_track.get("id")) if current_track else _norm(family).replace(" ", "_")
    section = next(
        (
            item
            for item in document.get("sections", [])
            if isinstance(item, Mapping) and item.get("id") == section_id
        ),
        {},
    )
    existing_ids = {
        str(item.get("id")) for item in section.get("tracks", []) if isinstance(item, Mapping)
    }
    base_track_id = track_id
    suffix = 2
    while current_track is None and track_id in existing_ids:
        track_id = f"{base_track_id}_{suffix}"
        suffix += 1
    operations: list[StableFallbackOperation] = []
    base = {"section_id": section_id, "track_id": track_id}
    if current_track is None:
        arguments: dict[str, object] = {
            "operation": "add",
            **base,
            "title": title,
            "kind": kind,
            "width_mm": width,
        }
        if x_scale is not None:
            arguments["x_scale"] = x_scale
        if isinstance(patch.get("grid"), Mapping):
            arguments["grid"] = dict(patch["grid"])
        operations.append(StableFallbackOperation("edit_track", arguments))
    elif x_scale is not None:
        track_patch: dict[str, object] = {}
        if x_scale is not None:
            track_patch["x_scale"] = x_scale
        operations.append(
            StableFallbackOperation(
                "edit_track", {"operation": "update", **base, "patch": track_patch}
            )
        )

    available = {str(channel).upper(): str(channel) for channel in available_channels}
    families = preset.get("channel_families") if isinstance(preset, Mapping) else None
    selected: list[tuple[str, str, Mapping[str, Any] | None]] = []
    track_axis_only_request = bool(
        current_track is not None
        and requested_scale is not None
        and explicit_track_scale
        and not explicit_curve_scale
        and not re.search(r"\b(?:add|bind|fill|overlay)\b", goal, re.IGNORECASE)
    )
    scale_only_request = bool(
        current_track is not None
        and requested_scale is not None
        and not re.search(r"\b(?:add|bind|fill|overlay)\b", goal, re.IGNORECASE)
    )
    if track_axis_only_request:
        selected = []
    elif isinstance(families, Mapping):
        groups = list(families.items())
        semantic = _words(goal) & {"deep", "medium", "shallow", "density", "neutron", "gamma"}
        overlay_requested = bool(_words(goal) & {"overlay", "crossover", "between", "both"})
        if semantic and not overlay_requested:
            groups = [(alias, values) for alias, values in groups if _words(alias) & semantic]
        for alias, values in groups:
            if not isinstance(values, list):
                continue
            channel = next(
                (
                    available.get(str(item).upper())
                    for item in values
                    if str(item).upper() in available
                ),
                None,
            )
            if channel is not None:
                selected.append((str(alias), channel, _template(preset, str(alias))))
    else:
        if generic:
            for channel in _requested_channels(goal, available_channels):
                selected.append((channel, channel, None))
        else:
            for item in (archetype or {}).get("recommended_channels", []):
                channel = available.get(str(item).upper())
                if channel is not None:
                    selected.append((str(item), channel, None))

    if generic and not selected and re.search(r"\b(?:bind|curve|channel)s?\b", goal, re.I):
        return None

    expected = (
        tuple(
            str(binding.get("channel"))
            for binding in current_track.get("bindings", [])
            if isinstance(binding, Mapping) and binding.get("channel")
        )
        if track_axis_only_request and isinstance(current_track, Mapping)
        else tuple(channel for _alias, channel, _template in selected)
    )
    skipped = (
        tuple(
            str(item)
            for values in families.values()
            for item in values
            if str(item).upper() not in available
        )
        if isinstance(families, Mapping)
        else ()
    )
    existing_bindings = {
        str(binding.get("channel", "")).upper(): binding
        for track in [current_track]
        if isinstance(current_track, Mapping)
        for binding in track.get("bindings", [])
        if isinstance(binding, Mapping)
    }
    binding_ids = {
        str(binding.get("binding_id", ""))
        for section in document.get("sections", [])
        if isinstance(section, Mapping)
        for track in section.get("tracks", [])
        if isinstance(track, Mapping)
        for binding in track.get("bindings", [])
        if isinstance(binding, Mapping)
    }
    binding_ids_by_channel: dict[str, str] = {}
    expected_binding_scales: dict[str, dict[str, object]] = {}
    expected_binding_labels: dict[str, str] = {}
    source_summaries = {
        str(channel).upper(): summary for channel, summary in (channel_summaries or {}).items()
    }
    for alias, channel, template in selected:
        existing = existing_bindings.get(channel.upper())
        requested_channel_scale = _requested_channel_scale(goal, channel)
        existing_scale = _scale(existing.get("scale")) if isinstance(existing, Mapping) else None
        requested_binding_scale = requested_channel_scale or requested_scale
        if (
            requested_binding_scale is not None
            and existing_scale is not None
            and not re.search(
                r"\b(?:logarithmic|log|linear)\s+scale\b",
                goal,
                re.IGNORECASE,
            )
        ):
            requested_binding_scale = dict(requested_binding_scale)
            requested_binding_scale["kind"] = existing_scale["kind"]
        binding_default_scale = (
            (
                requested_binding_scale
                if explicit_curve_scale or current_track is None
                else existing_scale
            )
            or _template_scale(template, source_summaries.get(channel.upper()))
        )
        scale = binding_default_scale
        if scale is None and isinstance(archetype, Mapping):
            recommended = archetype.get("recommended_binding")
            scale = _scale(recommended.get("scale")) if isinstance(recommended, Mapping) else None
        label = _template_label(template, channel)
        if label is None and generic:
            label = channel
        style = template.get("style") if template else None
        if style is None and generic:
            style = _generic_style(goal)
        if scale_only_request and isinstance(existing, Mapping):
            values = {"scale": scale} if scale is not None else {}
        else:
            values = {
                key: value
                for key, value in {
                    "label": label,
                    "style": style,
                    "scale": scale,
                }.items()
                if value is not None
            }
        if isinstance(existing, Mapping):
            existing_label = existing.get("label")
            catalog_label = template.get("label") if isinstance(template, Mapping) else None
            replaceable_labels = {
                _norm(value)
                for value in (channel, catalog_label, label)
                if isinstance(value, str) and value.strip()
            }
            if (
                isinstance(existing_label, str)
                and existing_label.strip()
                and _norm(existing_label) not in replaceable_labels
            ):
                values.pop("label", None)
                expected_binding_labels[channel.upper()] = existing_label
            elif label is not None:
                expected_binding_labels[channel.upper()] = label
            binding_id = str(existing.get("binding_id", existing.get("id", "")))
            if binding_id:
                binding_ids_by_channel[channel.upper()] = binding_id
            if scale is not None:
                expected_binding_scales[channel.upper()] = scale
            if values:
                operations.append(
                    StableFallbackOperation(
                        "edit_curve_binding",
                        {
                            "operation": "update",
                            **base,
                            "channel": channel,
                            "binding_id": existing.get("binding_id"),
                            "patch": values,
                        },
                    )
                )
            continue
        if label is not None:
            expected_binding_labels[channel.upper()] = label
        if scale is not None:
            expected_binding_scales[channel.upper()] = scale
        binding_id = f"{track_id}.{_norm(alias).replace(' ', '_')}.{channel.lower()}"
        suffix = 2
        while binding_id in binding_ids:
            binding_id = f"{track_id}.{_norm(alias).replace(' ', '_')}.{channel.lower()}.{suffix}"
            suffix += 1
        binding_ids.add(binding_id)
        binding_ids_by_channel[channel.upper()] = binding_id
        operations.append(
            StableFallbackOperation(
                "edit_curve_binding",
                {
                    "operation": "add",
                    **base,
                    "channel": channel,
                    "binding_id": binding_id,
                    **values,
                },
            )
        )

    expected_fill: dict[str, object] | None = None
    if isinstance(families, Mapping):
        selected_channels_by_catalog_name: dict[str, str] = {}
        for alias, channel, _template_value in selected:
            values = families.get(alias, [])
            if not isinstance(values, list):
                continue
            for value in values:
                selected_channels_by_catalog_name[str(value).upper()] = channel
        for _alias, channel, template in selected:
            fill = template.get("fill") if isinstance(template, Mapping) else None
            if not isinstance(fill, Mapping):
                continue
            other_channel_name = str(fill.get("other_channel", "")).strip().upper()
            other_channel = selected_channels_by_catalog_name.get(other_channel_name)
            binding_id = binding_ids_by_channel.get(channel.upper())
            other_binding_id = (
                binding_ids_by_channel.get(other_channel.upper())
                if other_channel is not None
                else None
            )
            if not binding_id or not other_binding_id:
                continue
            fill_kind = str(fill.get("kind", "")).strip().lower()
            fill_arguments: dict[str, object] = {
                "operation": "add",
                **base,
                "channel": channel,
                "binding_id": binding_id,
                "other_binding_id": other_binding_id,
                "kind": fill_kind,
            }
            for key in ("label", "color", "alpha", "crossover"):
                if fill.get(key) is not None:
                    fill_arguments[key] = fill[key]
            operations.append(StableFallbackOperation("edit_fill", fill_arguments))
            expected_fill = {
                "kind": fill_kind,
                "binding_id": binding_id,
                "other_binding_id": other_binding_id,
            }
            break

    if x_scale is not None and expected and (explicit_curve_scale or current_track is None):
        operations.append(
            StableFallbackOperation(
                "edit_track",
                {
                    "operation": "set_scales",
                    **base,
                    "x_scale": x_scale,
                    "curve_scale": x_scale,
                    "sync_grid_to_scale": True,
                },
            )
        )
    section = next(
        (
            item
            for item in document.get("sections", [])
            if isinstance(item, Mapping) and item.get("id") == section_id
        ),
        {},
    )
    tracks = section.get("tracks", []) if isinstance(section, Mapping) else []
    move_operation = _requested_move(goal, tracks, track_id)
    if move_operation is not None:
        move_operation.arguments["section_id"] = section_id
        operations.append(move_operation)
    if not operations:
        return None
    return StableFallbackPlan(
        section_id=section_id,
        track_id=track_id,
        operations=tuple(operations),
        expected_channels=expected,
        expected_scale=x_scale,
        family_id=str(archetype.get("id")) if isinstance(archetype, Mapping) else None,
        preset_id=str(preset.get("id")) if isinstance(preset, Mapping) else None,
        skipped_channels=tuple(dict.fromkeys(skipped)),
        expected_fill=expected_fill,
        expected_binding_scales=expected_binding_scales,
        expected_binding_labels=expected_binding_labels,
    )


def fallback_plan_satisfied(plan: StableFallbackPlan, document: Mapping[str, Any]) -> bool:
    """Verify the track and requested channel/scale postconditions."""
    section = next(
        (
            item
            for item in document.get("sections", [])
            if isinstance(item, Mapping) and item.get("id") == plan.section_id
        ),
        None,
    )
    track = (
        next(
            (
                item
                for item in section.get("tracks", [])
                if isinstance(item, Mapping) and item.get("id") == plan.track_id
            ),
            None,
        )
        if isinstance(section, Mapping)
        else None
    )
    if not isinstance(track, Mapping):
        return False
    expected_channels = {channel.upper() for channel in plan.expected_channels}
    bindings = [item for item in track.get("bindings", []) if isinstance(item, Mapping)]
    if not expected_channels.issubset({str(item.get("channel", "")).upper() for item in bindings}):
        return False
    if plan.expected_scale is not None:
        expected = _scale(plan.expected_scale)
        if _scale(track.get("x_scale")) != expected:
            return False
        if not all(
            _scale(item.get("scale")) == expected
            for item in bindings
            if str(item.get("channel", "")).upper() in expected_channels
        ):
            return False
    bindings_by_channel = {str(item.get("channel", "")).upper(): item for item in bindings}
    for channel, expected_scale in plan.expected_binding_scales.items():
        binding = bindings_by_channel.get(channel)
        if not isinstance(binding, Mapping) or _scale(binding.get("scale")) != _scale(
            expected_scale
        ):
            return False
    for channel, expected_label in plan.expected_binding_labels.items():
        binding = bindings_by_channel.get(channel)
        if not isinstance(binding, Mapping) or binding.get("label") != expected_label:
            return False
    if plan.expected_fill is not None:
        fills = [item for item in track.get("fills", []) if isinstance(item, Mapping)]
        if not any(
            all(fill.get(key) == value for key, value in plan.expected_fill.items())
            for fill in fills
        ):
            return False
    return True


__all__ = [
    "StableFallbackOperation",
    "StableFallbackPlan",
    "build_catalog_fallback_plan",
    "catalog_channel_candidates",
    "fallback_plan_satisfied",
    "is_track_request",
]
