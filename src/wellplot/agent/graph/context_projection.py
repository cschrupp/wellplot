###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Semantic prompt-context projections for graph planning."""

from __future__ import annotations

from collections.abc import Mapping, Sequence


def _without_extensions(value: object) -> object:
    """Keep canonical state while excluding opaque renderer/legacy payloads."""
    if isinstance(value, Mapping):
        return {
            key: _without_extensions(item) for key, item in value.items() if key != "extensions"
        }
    if isinstance(value, list):
        return [_without_extensions(item) for item in value]
    return value


def report_document_context(document: Mapping[str, object]) -> dict[str, object]:
    """Expose editable report values without a full header-layout template.

    Absent optional settings retain canonical automatic sizing. Detail slots
    are flattened into the same collection used for partial value updates;
    row/column identity remains available as read-only targeting context.
    """
    context = {
        key: _report_values(document[key])
        for key in ("title", "subtitle", "header", "remarks", "tail", "page", "depth", "output")
        if document.get(key) is not None
    }
    header = context.get("header")
    if isinstance(header, dict) and isinstance(header.get("detail"), dict):
        detail = header["detail"]
        slots = []
        for row in detail.get("rows", []):
            identity = _selected_values(
                row, ("row_id", "key", "keys", "label", "label_cells", "aliases")
            )
            for index, cell in enumerate(row.get("values", [])):
                slots.append({**identity, **cell, "cell_index": index})
            for column_index, column in enumerate(row.get("columns", [])):
                for index, cell in enumerate(column.get("cells", [])):
                    slots.append(
                        {**identity, **cell, "column_index": column_index, "cell_index": index}
                    )
        header["detail_fields"] = slots
        header["detail"] = _selected_values(detail, ("kind", "title", "column_titles"))
    return context


def _report_values(value: object) -> object:
    """Exclude automatic/unset properties and opaque renderer extensions."""
    if isinstance(value, Mapping):
        return {
            key: _report_values(item)
            for key, item in value.items()
            if key != "extensions" and item is not None
        }
    if isinstance(value, list):
        return [_report_values(item) for item in value]
    return value


def report_source_context(manifest: Mapping[str, object]) -> dict[str, object]:
    """Expose source-backed header metadata without unrelated sampled channels."""
    return {
        section_id: {
            key: source[key]
            for key in ("source_path", "source_format", "well_metadata")
            if key in source
        }
        for section_id, source in manifest.items()
        if isinstance(source, Mapping)
    }


def section_document_context(document: Mapping[str, object], section_id: str) -> dict[str, object]:
    """Expose the selected section plus shared axis and page geometry."""
    context = {
        key: _without_extensions(document[key]) for key in ("page", "depth") if key in document
    }
    context["sections"] = [
        _without_extensions(section)
        for section in _mapping_sequence(document.get("sections"))
        if section.get("id") == section_id
    ]
    return context


def section_source_context(manifest: Mapping[str, object], section_id: str) -> dict[str, object]:
    """Expose the selected source channels without other passes or provenance."""
    source = manifest.get(section_id)
    if not isinstance(source, Mapping):
        return {}
    return {
        section_id: {
            key: source[key]
            for key in ("source_path", "source_format", "dataset_name", "channels")
            if key in source
        }
    }


def planner_document_summary(document: Mapping[str, object]) -> dict[str, object]:
    """Return the existing document facts needed by the semantic planner.

    Planning needs stable identities, ordering, source routing, and the broad
    shape of existing report content. It does not need renderer settings,
    header values, styles, extensions, or other presentation detail. Those
    remain available to the typed report and section compilers that own the
    corresponding artifacts.
    """
    summary = _selected_values(document, ("name", "title", "subtitle"))

    depth = _mapping(document.get("depth"))
    if depth:
        summary["depth"] = _selected_values(
            depth,
            ("unit", "scale", "major_step", "minor_step"),
        )

    header = _mapping(document.get("header"))
    if header:
        summary["header"] = _header_summary(header)

    remarks = _mapping_sequence(document.get("remarks"))
    if remarks:
        summary["remarks"] = [
            _selected_values(remark, ("remark_id", "title")) for remark in remarks
        ]

    sections = _mapping_sequence(document.get("sections"))
    summary["sections"] = [_section_summary(section) for section in sections]
    return summary


def planner_source_manifest_summary(
    source_manifest: Mapping[str, object],
) -> dict[str, object]:
    """Return the source-channel facts needed to choose semantic capabilities.

    Source values, well metadata, provenance, array shapes, and repeated
    per-channel source paths are intentionally excluded. The planner needs to
    know what channels exist and how they are described, not to compile header
    values or render a channel.
    """
    summary: dict[str, object] = {}
    for section_id in sorted(source_manifest):
        source = _mapping(source_manifest[section_id])
        entry = _selected_values(
            source,
            ("source_path", "source_format", "dataset_name"),
        )
        channels = _mapping_sequence(source.get("channels"))
        entry["channels"] = [
            _channel_summary(channel) for channel in sorted(channels, key=_channel_sort_key)
        ]
        summary[str(section_id)] = entry
    return summary


def _header_summary(header: Mapping[str, object]) -> dict[str, object]:
    """Keep header identities and semantic slot inventory without field values."""
    summary = _selected_values(
        header,
        ("enabled", "provider_name", "title", "subtitle", "tail_enabled"),
    )
    service_titles = _mapping_sequence(header.get("service_titles"))
    if service_titles:
        summary["service_titles"] = [
            _selected_values(service_title, ("slot_id",)) for service_title in service_titles
        ]

    general_fields = _mapping_sequence(header.get("general_fields"))
    if general_fields:
        summary["general_fields"] = [
            _selected_values(field, ("slot_id", "key", "label", "aliases"))
            for field in general_fields
        ]

    detail = _mapping(header.get("detail"))
    if detail:
        detail_summary = _selected_values(
            detail,
            ("kind", "title", "column_titles"),
        )
        rows = _mapping_sequence(detail.get("rows"))
        if rows:
            detail_summary["row_count"] = len(rows)
            detail_summary["fields"] = _planner_detail_slot_inventory(rows)
        summary["detail"] = detail_summary
    return summary


def _planner_detail_slot_inventory(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Expose stable detail slots with the row labels needed for semantic matching."""
    slots: list[dict[str, object]] = []
    for row in rows:
        identity = _selected_values(
            row, ("row_id", "key", "keys", "label", "label_cells", "aliases")
        )
        for index, value in enumerate(_mapping_sequence(row.get("values"))):
            slot = _selected_values(value, ("slot_id",))
            if slot:
                slots.append({**identity, **slot, "cell_index": index})
        for column_index, column in enumerate(_mapping_sequence(row.get("columns"))):
            for index, cell in enumerate(_mapping_sequence(column.get("cells"))):
                slot = _selected_values(cell, ("slot_id",))
                if slot:
                    slots.append(
                        {
                            **identity,
                            **slot,
                            "column_index": column_index,
                            "cell_index": index,
                        }
                    )
    return slots


def _section_summary(section: Mapping[str, object]) -> dict[str, object]:
    """Project one existing section into semantic planner inventory."""
    summary = _selected_values(
        section,
        ("id", "title", "subtitle", "depth_range"),
    )
    source = _mapping(section.get("data_source"))
    if source:
        summary["data_source"] = _selected_values(
            source,
            ("source_path", "source_format"),
        )

    tracks = _mapping_sequence(section.get("tracks"))
    summary["tracks"] = [_track_summary(track) for track in tracks]
    return summary


def _track_summary(track: Mapping[str, object]) -> dict[str, object]:
    """Project one track and its existing semantic content identities."""
    summary = _selected_values(track, ("id", "title", "kind", "width_mm", "axis", "unit"))
    x_scale = _mapping(track.get("x_scale"))
    if x_scale:
        summary["x_scale"] = _scale_summary(x_scale)

    bindings = _mapping_sequence(track.get("bindings"))
    if bindings:
        summary["bindings"] = [_binding_summary(binding) for binding in bindings]

    fills = _mapping_sequence(track.get("fills"))
    if fills:
        summary["fills"] = [
            _selected_values(
                fill,
                ("fill_id", "kind", "binding_id", "other_binding_id", "label"),
            )
            for fill in fills
        ]

    annotations = _mapping_sequence(track.get("annotations"))
    if annotations:
        summary["annotations"] = [
            _selected_values(annotation, ("annotation_id", "kind", "label"))
            for annotation in annotations
        ]
    return summary


def _binding_summary(binding: Mapping[str, object]) -> dict[str, object]:
    """Project stable binding identity and data-channel association."""
    summary = _selected_values(
        binding,
        ("binding_id", "kind", "channel", "label", "profile"),
    )
    scale = _mapping(binding.get("scale"))
    if scale:
        summary["scale"] = _scale_summary(scale)
    return summary


def _scale_summary(scale: Mapping[str, object]) -> dict[str, object]:
    """Keep the semantic scale transform and bounds while dropping styling."""
    return _selected_values(
        scale,
        ("kind", "minimum", "maximum", "reverse", "unit"),
    )


def _channel_summary(channel: Mapping[str, object]) -> dict[str, object]:
    """Project one source channel into planner-selectable semantic facts."""
    summary = _selected_values(channel, ("mnemonic", "kind", "unit", "description"))
    aliases = channel.get("aliases")
    if isinstance(aliases, Sequence) and not isinstance(aliases, (bytes, str)):
        summary["aliases"] = [alias for alias in aliases if isinstance(alias, str)]
    return summary


def _channel_sort_key(channel: Mapping[str, object]) -> tuple[str, str]:
    """Sort equivalent source manifests into a deterministic prompt ordering."""
    mnemonic = channel.get("mnemonic")
    kind = channel.get("kind")
    return (
        mnemonic if isinstance(mnemonic, str) else "",
        kind if isinstance(kind, str) else "",
    )


def _selected_values(
    source: Mapping[str, object],
    names: tuple[str, ...],
) -> dict[str, object]:
    """Copy selected JSON-scalar values without leaking nested payloads."""
    selected: dict[str, object] = {}
    for name in names:
        if name not in source:
            continue
        value = source[name]
        if value is None or isinstance(value, (str, int, float, bool)):
            selected[name] = value
        elif isinstance(value, (list, tuple)) and all(
            item is None or isinstance(item, (str, int, float, bool)) for item in value
        ):
            selected[name] = list(value)
    return selected


def _mapping(value: object) -> Mapping[str, object]:
    """Return a string-keyed mapping or an empty mapping for malformed input."""
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items() if isinstance(key, str)}


def _mapping_sequence(value: object) -> tuple[Mapping[str, object], ...]:
    """Return mapping items from a JSON sequence while ignoring malformed items."""
    if not isinstance(value, Sequence) or isinstance(value, (bytes, str)):
        return ()
    return tuple(_mapping(item) for item in value if isinstance(item, Mapping))


__all__ = [
    "planner_document_summary",
    "planner_source_manifest_summary",
    "report_document_context",
    "report_source_context",
    "section_document_context",
    "section_source_context",
]
