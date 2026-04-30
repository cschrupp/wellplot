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

"""Pure-Python service helpers backing the optional wellplot MCP server."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from dataclasses import dataclass
from importlib.resources import as_file, files
from pathlib import Path

import yaml

from ..api.builder import ProgrammaticLogSpec
from ..api.render import (
    render_png_bytes,
    render_section_png,
    render_track_png,
    render_window_png,
)
from ..api.serialize import report_to_dict, report_to_yaml
from ..errors import DependencyUnavailableError, PathAccessError, TemplateValidationError
from ..logfile import (
    LogFileSpec,
    build_documents_for_logfile,
    load_datasets_for_logfile,
    load_logfile,
    load_logfile_text,
    logfile_from_mapping,
    resolve_section_data_sources_for_logfile,
)
from ..logfile_schema import get_logfile_json_schema
from ..pipeline import prepare_logfile_render, render_prepared_logfile

ASSET_PACKAGE = "wellplot.mcp.assets"
PRODUCTION_EXAMPLE_IDS = ("cbl_log_example", "forge16b_porosity_example")
PRODUCTION_EXAMPLE_FILES = (
    "README.md",
    "base.template.yaml",
    "full_reconstruction.log.yaml",
    "data-notes.md",
)
RESOURCE_MIME_TYPES = {
    "README.md": "text/markdown",
    "base.template.yaml": "text/yaml",
    "full_reconstruction.log.yaml": "text/yaml",
    "data-notes.md": "text/markdown",
}


@dataclass(slots=True)
class LogfileValidationResult:
    """Structured logfile validation result for MCP clients."""

    valid: bool
    message: str
    name: str
    render_backend: str
    section_ids: list[str]


@dataclass(slots=True)
class LogfileSectionSummary:
    """Structured per-section report metadata for MCP inspection."""

    id: str
    title: str
    source_path: str
    source_format: str
    depth_range: list[float] | None
    track_ids: list[str]
    track_kinds: list[str]


@dataclass(slots=True)
class LogfileInspectionResult:
    """Structured logfile inspection payload for MCP clients."""

    name: str
    render_backend: str
    configured_output_path: str
    page_settings: dict[str, object]
    depth_settings: dict[str, object]
    has_heading: bool
    has_remarks: bool
    has_tail: bool
    section_ids: list[str]
    sections: list[LogfileSectionSummary]


@dataclass(slots=True)
class RenderToFileResult:
    """Structured file-render result for MCP clients."""

    backend: str
    page_count: int
    output_path: str


@dataclass(slots=True)
class ResourceContent:
    """Text resource payload with its declared MIME type."""

    text: str
    mime_type: str


@dataclass(slots=True)
class ExampleBundleExportResult:
    """Structured result for exporting one packaged example bundle."""

    example_id: str
    output_dir: str
    written_files: list[str]


@dataclass(slots=True)
class FormattedLogfileTextResult:
    """Structured result for normalized logfile YAML text output."""

    name: str
    render_backend: str
    section_ids: list[str]
    yaml_text: str


@dataclass(slots=True)
class SavedLogfileTextResult:
    """Structured result for saving normalized logfile YAML text."""

    name: str
    render_backend: str
    section_ids: list[str]
    output_path: str


@dataclass(slots=True)
class LogfileDraftCreateResult:
    """Structured result for creating one normalized logfile draft."""

    output_path: str
    name: str
    section_ids: list[str]
    seed_kind: str
    seed_value: str


@dataclass(slots=True)
class LogfileDraftSectionSummary:
    """Structured per-section authoring summary for one draft logfile."""

    id: str
    title: str
    source_path: str
    source_format: str
    depth_range: list[float] | None
    track_ids: list[str]
    track_kinds: list[str]
    curve_binding_count: int
    raster_binding_count: int
    available_channels: list[str]
    dataset_loaded: bool
    dataset_message: str


@dataclass(slots=True)
class LogfileDraftSummaryResult:
    """Structured authoring summary for one draft logfile."""

    name: str
    render_backend: str
    configured_output_path: str
    has_heading: bool
    has_remarks: bool
    has_tail: bool
    section_count: int
    section_ids: list[str]
    sections: list[LogfileDraftSectionSummary]


@dataclass(slots=True)
class AddedTrackResult:
    """Structured result for appending one track to a draft logfile."""

    logfile_path: str
    section_id: str
    track_id: str
    track_ids: list[str]
    track_count: int


@dataclass(slots=True)
class BoundCurveResult:
    """Structured result for adding one curve binding to a draft logfile."""

    logfile_path: str
    section_id: str
    track_id: str
    channel: str
    binding_kind: str
    binding_count: int


@dataclass(slots=True)
class UpdatedCurveBindingResult:
    """Structured result for updating one curve binding in a draft logfile."""

    logfile_path: str
    section_id: str
    track_id: str
    channel: str
    binding: dict[str, object]


@dataclass(slots=True)
class MovedTrackResult:
    """Structured result for reordering one track inside a draft logfile."""

    logfile_path: str
    section_id: str
    track_id: str
    track_ids: list[str]
    track_count: int


@dataclass(slots=True)
class HeadingContentResult:
    """Structured result for updating heading content in a draft logfile."""

    logfile_path: str
    has_heading: bool
    has_tail: bool
    heading: dict[str, object]


@dataclass(slots=True)
class RemarksContentResult:
    """Structured result for replacing first-page remark content."""

    logfile_path: str
    remarks_count: int
    remarks: list[dict[str, object]]


def resolve_server_root(root: str | Path | None = None) -> Path:
    """Resolve the effective MCP server root."""
    return Path.cwd().resolve() if root is None else Path(root).expanduser().resolve()


def _resolve_user_path(path_value: str | Path, *, root: Path, context: str) -> Path:
    path = Path(path_value).expanduser()
    path = (root / path).resolve() if not path.is_absolute() else path.resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise PathAccessError(f"{context} must resolve inside the server root {root}.") from exc
    return path


def _section_ids_from_spec(spec: LogFileSpec) -> list[str]:
    layout = dict(spec.document.get("layout", {}))
    sections = list(layout.get("log_sections", []))
    return [str(section.get("id", "")) for section in sections]


def _section_map_from_spec(spec: LogFileSpec) -> dict[str, dict[str, object]]:
    layout = dict(spec.document.get("layout", {}))
    sections = list(layout.get("log_sections", []))
    return {str(section.get("id", "")): dict(section) for section in sections}


def _track_to_sections(spec: LogFileSpec) -> dict[str, list[str]]:
    track_sections: dict[str, list[str]] = {}
    for section_id, section in _section_map_from_spec(spec).items():
        for track in list(section.get("tracks", [])):
            if isinstance(track, dict):
                track_id = str(track.get("id", ""))
                track_sections.setdefault(track_id, []).append(section_id)
    return track_sections


def _resolve_base_dir(
    base_dir: str | Path | None,
    *,
    root: Path,
    fallback: Path | None = None,
) -> Path:
    if base_dir is None:
        return root if fallback is None else fallback.resolve()
    return _resolve_user_path(base_dir, root=root, context="base_dir")


def _document_default_depth_range(spec: LogFileSpec) -> list[float] | None:
    depth_range = spec.document.get("depth_range")
    if not isinstance(depth_range, list) or len(depth_range) != 2:
        return None
    return [float(depth_range[0]), float(depth_range[1])]


def _section_depth_range(
    section: dict[str, object],
    *,
    default_depth_range: list[float] | None,
) -> list[float] | None:
    depth_range = section.get("depth_range")
    if isinstance(depth_range, list) and len(depth_range) == 2:
        return [float(depth_range[0]), float(depth_range[1])]
    return deepcopy(default_depth_range)


def _report_mapping_from_spec(
    spec: LogFileSpec,
    *,
    backend_override: str | None = None,
) -> dict[str, object]:
    render_mapping: dict[str, object] = {
        "backend": backend_override or spec.render_backend,
        "output_path": spec.render_output_path,
        "dpi": spec.render_dpi,
    }
    if spec.render_continuous_strip_page_height_mm is not None:
        render_mapping["continuous_strip_page_height_mm"] = (
            spec.render_continuous_strip_page_height_mm
        )
    if spec.render_matplotlib:
        render_mapping["matplotlib"] = deepcopy(spec.render_matplotlib)

    mapping: dict[str, object] = {
        "version": 1,
        "name": spec.name,
        "render": render_mapping,
        "document": deepcopy(spec.document),
    }
    if spec.data_source_path is not None:
        mapping["data"] = {
            "source_path": spec.data_source_path,
            "source_format": spec.data_source_format,
        }
    return mapping


def _preview_report(prepared: object) -> ProgrammaticLogSpec:
    mapping = _report_mapping_from_spec(prepared.spec, backend_override="matplotlib")
    preview_spec = logfile_from_mapping(mapping)
    return ProgrammaticLogSpec(
        spec=preview_spec,
        mapping=mapping,
        datasets_by_section=prepared.datasets_by_section,
        source_paths_by_section=prepared.source_paths_by_section,
    )


def _binding_target_section_id(
    spec: LogFileSpec,
    binding: dict[str, object],
) -> str | None:
    section_value = binding.get("section")
    if isinstance(section_value, str) and section_value.strip():
        return section_value

    candidates = _track_to_sections(spec).get(str(binding.get("track_id", "")), [])
    if len(candidates) == 1:
        return candidates[0]

    section_ids = _section_ids_from_spec(spec)
    if len(section_ids) == 1:
        return section_ids[0]
    return None


def _binding_counts_by_section(spec: LogFileSpec) -> dict[str, dict[str, int]]:
    counts = {section_id: {"curve": 0, "raster": 0} for section_id in _section_ids_from_spec(spec)}
    bindings = dict(spec.document.get("bindings", {}))
    for binding in list(bindings.get("channels", [])):
        if not isinstance(binding, dict):
            continue
        section_id = _binding_target_section_id(spec, binding)
        if section_id is None:
            continue
        kind = str(binding.get("kind", "curve")).strip().lower()
        if kind == "curve":
            counts[section_id]["curve"] += 1
        elif kind == "raster":
            counts[section_id]["raster"] += 1
    return counts


def _normalize_logfile_mapping_from_path(
    logfile_path: Path,
    *,
    allowed_root: Path | None = None,
) -> tuple[LogFileSpec, dict[str, object]]:
    spec = load_logfile(logfile_path, allowed_root=allowed_root)
    return spec, report_to_dict(spec)


def _persist_rebased_logfile_mapping(
    mapping: dict[str, object],
    *,
    from_base_dir: Path,
    output_path: Path,
) -> LogFileSpec:
    rebased_mapping = _rebase_report_paths(
        deepcopy(mapping),
        from_base_dir=from_base_dir,
        to_base_dir=output_path.parent,
    )
    normalized_yaml = report_to_yaml(rebased_mapping)
    if not isinstance(normalized_yaml, str):
        raise RuntimeError("Expected canonical YAML text from report_to_yaml().")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(normalized_yaml, encoding="utf-8")
    return logfile_from_mapping(rebased_mapping)


def _logfile_mapping_sections(mapping: dict[str, object]) -> list[dict[str, object]]:
    layout = _logfile_mapping_layout(mapping)
    sections = layout.get("log_sections")
    if not isinstance(sections, list):
        raise TemplateValidationError(
            "Logfile mapping is missing document.layout.log_sections configuration."
        )
    return sections


def _logfile_mapping_layout(mapping: dict[str, object]) -> dict[str, object]:
    document = mapping.get("document")
    if not isinstance(document, dict):
        raise TemplateValidationError("Logfile mapping is missing document configuration.")
    layout = document.get("layout")
    if not isinstance(layout, dict):
        raise TemplateValidationError("Logfile mapping is missing document.layout configuration.")
    return layout


def _logfile_mapping_bindings(mapping: dict[str, object]) -> list[dict[str, object]]:
    document = mapping.get("document")
    if not isinstance(document, dict):
        raise TemplateValidationError("Logfile mapping is missing document configuration.")
    bindings = document.get("bindings")
    if not isinstance(bindings, dict):
        raise TemplateValidationError("Logfile mapping is missing document.bindings configuration.")
    channels = bindings.get("channels")
    if not isinstance(channels, list):
        raise TemplateValidationError(
            "Logfile mapping is missing document.bindings.channels configuration."
        )
    return channels


def _logfile_mapping_section(
    mapping: dict[str, object],
    section_id: str,
) -> dict[str, object]:
    sections = _logfile_mapping_sections(mapping)
    available: list[str] = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        current_id = str(section.get("id", ""))
        available.append(current_id)
        if current_id == section_id:
            return section
    raise TemplateValidationError(
        f"Unknown section_id {section_id!r}. Available sections: {available}."
    )


def _logfile_mapping_section_tracks(
    section: dict[str, object],
    *,
    section_id: str,
) -> list[dict[str, object]]:
    tracks = section.get("tracks")
    if not isinstance(tracks, list):
        raise TemplateValidationError(f"Section {section_id!r} is missing a tracks list.")
    return tracks


def _persist_validated_logfile_mapping(
    mapping: dict[str, object],
    *,
    logfile_path: Path,
    root: Path,
) -> LogFileSpec:
    spec = logfile_from_mapping(mapping)
    _validate_logfile_spec_renderable(
        spec,
        base_dir=logfile_path.parent,
        allowed_root=root,
    )
    normalized_yaml = report_to_yaml(spec)
    if not isinstance(normalized_yaml, str):
        raise RuntimeError("Expected canonical YAML text from report_to_yaml().")
    logfile_path.write_text(normalized_yaml, encoding="utf-8")
    return spec


def _renumber_section_track_positions(tracks: list[dict[str, object]]) -> None:
    for index, track in enumerate(tracks, start=1):
        if isinstance(track, dict):
            track["position"] = index


def _resolve_section_channel_name(
    spec: LogFileSpec,
    *,
    logfile_path: Path,
    root: Path,
    section_id: str,
    channel: str,
) -> str:
    datasets_by_section, _ = load_datasets_for_logfile(
        spec,
        base_dir=logfile_path.parent,
        allowed_root=root,
    )
    dataset = datasets_by_section.get(section_id)
    if dataset is None:
        raise TemplateValidationError(f"Missing dataset for section {section_id!r}.")
    for mnemonic in dataset.channels:
        if mnemonic.upper() == channel.upper():
            return mnemonic
    raise TemplateValidationError(
        f"Channel {channel!r} was not found in section {section_id!r}. "
        f"Available channels: {sorted(dataset.channels)}."
    )


def _find_curve_binding_index(
    bindings: list[dict[str, object]],
    *,
    spec: LogFileSpec,
    section_id: str,
    track_id: str,
    channel: str,
) -> int:
    for index, binding in enumerate(bindings):
        if not isinstance(binding, dict):
            continue
        if str(binding.get("kind", "curve")).strip().lower() != "curve":
            continue
        if _binding_target_section_id(spec, binding) != section_id:
            continue
        if str(binding.get("track_id", "")) != track_id:
            continue
        if str(binding.get("channel", "")).upper() == channel.upper():
            return index
    raise TemplateValidationError(
        f"Curve binding for channel {channel!r} was not found on track {track_id!r} "
        f"in section {section_id!r}."
    )


def _merge_optional_patch(
    target: dict[str, object],
    patch: dict[str, object],
) -> dict[str, object]:
    merged = deepcopy(target)
    for key, value in patch.items():
        if value is None:
            merged.pop(key, None)
            continue
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _merge_optional_patch(existing, value)
            continue
        merged[key] = deepcopy(value)
    return merged


def _layout_has_tail(layout: dict[str, object]) -> bool:
    heading = layout.get("heading")
    if isinstance(heading, dict) and bool(heading.get("tail_enabled")):
        return True
    return bool(layout.get("tail"))


def _validate_preview_parameters(
    *,
    page_index: int,
    dpi: int,
    section_id: str | None,
    track_ids: list[str] | None,
    depth_range: tuple[float, float] | None,
) -> None:
    if page_index < 0:
        raise ValueError("page_index must be zero or greater.")
    if dpi <= 0:
        raise ValueError("dpi must be positive.")
    if track_ids is not None and not track_ids:
        raise ValueError("track_ids must contain at least one track identifier.")
    if track_ids is not None and section_id is None:
        raise ValueError("track_ids filtering requires a section_id.")
    if depth_range is not None and float(depth_range[0]) == float(depth_range[1]):
        raise ValueError("depth_range values must differ.")


def _validate_logfile_spec_renderable(
    spec: LogFileSpec,
    *,
    base_dir: Path,
    allowed_root: Path,
) -> None:
    datasets_by_section, source_paths_by_section = load_datasets_for_logfile(
        spec,
        base_dir=base_dir,
        allowed_root=allowed_root,
    )
    if not datasets_by_section:
        raise TemplateValidationError("No datasets were resolved for the configured log sections.")
    _ = build_documents_for_logfile(
        spec,
        datasets_by_section,
        source_path=source_paths_by_section,
    )


def _load_validated_logfile_text_spec(
    yaml_text: str,
    *,
    base_dir: Path,
    root: Path,
) -> LogFileSpec:
    spec = load_logfile_text(
        yaml_text,
        base_dir=base_dir,
        allowed_root=root,
    )
    _validate_logfile_spec_renderable(spec, base_dir=base_dir, allowed_root=root)
    return spec


def _ensure_known_section(spec: LogFileSpec, section_id: str) -> None:
    available = _section_ids_from_spec(spec)
    if section_id not in available:
        raise TemplateValidationError(
            f"Unknown section_id {section_id!r}. Available sections: {available}."
        )


def _ensure_known_section_ids(spec: LogFileSpec, section_ids: list[str]) -> None:
    if not section_ids:
        raise ValueError("section_ids must contain at least one section identifier.")
    available = set(_section_ids_from_spec(spec))
    missing = [section_id for section_id in section_ids if section_id not in available]
    if missing:
        raise TemplateValidationError(
            f"Unknown section_ids {missing}. Available sections: {sorted(available)}."
        )


def _ensure_known_track_ids(spec: LogFileSpec, section_id: str, track_ids: list[str]) -> None:
    _ensure_known_section(spec, section_id)
    section = _section_map_from_spec(spec)[section_id]
    tracks = list(section.get("tracks", []))
    available = {str(track.get("id", "")) for track in tracks if isinstance(track, dict)}
    missing = [track_id for track_id in track_ids if track_id not in available]
    if missing:
        raise TemplateValidationError(
            f"Unknown track_ids {missing} for section {section_id!r}. "
            f"Available tracks: {sorted(available)}."
        )


def _force_agg_preview_backend() -> None:
    """Force a non-GUI matplotlib backend for MCP PNG previews."""
    os.environ.setdefault("MPLBACKEND", "Agg")
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
    except ImportError:
        return


def _production_asset_path(example_id: str, filename: str) -> object:
    if example_id not in PRODUCTION_EXAMPLE_IDS:
        raise TemplateValidationError(f"Unknown production example {example_id!r}.")
    if filename not in RESOURCE_MIME_TYPES:
        raise TemplateValidationError(f"Unsupported production example resource {filename!r}.")
    return files(ASSET_PACKAGE).joinpath("production", example_id, filename)


def _production_readme_title(example_id: str) -> str:
    readme = read_production_example_text(example_id, "README.md")
    for line in readme.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return example_id


def read_production_example_text(example_id: str, filename: str) -> str:
    """Return one packaged production example resource as UTF-8 text."""
    asset_path = _production_asset_path(example_id, filename)
    return asset_path.read_text(encoding="utf-8")


def schema_resource() -> ResourceContent:
    """Return the JSON schema resource payload."""
    payload = json.dumps(get_logfile_json_schema(), indent=2, sort_keys=True)
    return ResourceContent(text=payload, mime_type="application/json")


def production_example_manifest() -> dict[str, object]:
    """Return the curated production example manifest."""
    examples: list[dict[str, object]] = []
    for example_id in PRODUCTION_EXAMPLE_IDS:
        examples.append(
            {
                "id": example_id,
                "title": _production_readme_title(example_id),
                "files": list(PRODUCTION_EXAMPLE_FILES),
            }
        )
    return {"examples": examples}


def production_example_manifest_resource() -> ResourceContent:
    """Return the curated production example manifest as JSON text."""
    payload = json.dumps(production_example_manifest(), indent=2, sort_keys=True)
    return ResourceContent(text=payload, mime_type="application/json")


def production_example_resource(example_id: str, filename: str) -> ResourceContent:
    """Return one packaged production example resource and its MIME type."""
    return ResourceContent(
        text=read_production_example_text(example_id, filename),
        mime_type=RESOURCE_MIME_TYPES[filename],
    )


def validate_logfile(
    logfile_path: str,
    *,
    root: str | Path | None = None,
) -> LogfileValidationResult:
    """Validate one logfile path under the configured server root."""
    server_root = resolve_server_root(root)
    resolved_logfile = _resolve_user_path(logfile_path, root=server_root, context="logfile_path")
    try:
        spec = load_logfile(resolved_logfile, allowed_root=server_root)
    except (TemplateValidationError, yaml.YAMLError) as exc:
        return LogfileValidationResult(
            valid=False,
            message=str(exc),
            name="",
            render_backend="",
            section_ids=[],
        )
    section_ids = _section_ids_from_spec(spec)
    try:
        prepare_logfile_render(resolved_logfile, allowed_root=server_root)
    except (TemplateValidationError, yaml.YAMLError) as exc:
        return LogfileValidationResult(
            valid=False,
            message=str(exc),
            name=spec.name,
            render_backend=spec.render_backend,
            section_ids=section_ids,
        )
    return LogfileValidationResult(
        valid=True,
        message="Valid logfile.",
        name=spec.name,
        render_backend=spec.render_backend,
        section_ids=section_ids,
    )


def validate_logfile_text(
    yaml_text: str,
    *,
    base_dir: str | Path | None = None,
    root: str | Path | None = None,
) -> LogfileValidationResult:
    """Validate unsaved logfile YAML text under the configured server root."""
    server_root = resolve_server_root(root)
    resolved_base_dir = _resolve_base_dir(base_dir, root=server_root)
    try:
        spec = load_logfile_text(
            yaml_text,
            base_dir=resolved_base_dir,
            allowed_root=server_root,
        )
    except (TemplateValidationError, yaml.YAMLError) as exc:
        return LogfileValidationResult(
            valid=False,
            message=str(exc),
            name="",
            render_backend="",
            section_ids=[],
        )
    section_ids = _section_ids_from_spec(spec)
    try:
        _validate_logfile_spec_renderable(
            spec,
            base_dir=resolved_base_dir,
            allowed_root=server_root,
        )
    except (TemplateValidationError, yaml.YAMLError) as exc:
        return LogfileValidationResult(
            valid=False,
            message=str(exc),
            name=spec.name,
            render_backend=spec.render_backend,
            section_ids=section_ids,
        )
    return LogfileValidationResult(
        valid=True,
        message="Valid logfile.",
        name=spec.name,
        render_backend=spec.render_backend,
        section_ids=section_ids,
    )


def inspect_logfile(
    logfile_path: str,
    *,
    root: str | Path | None = None,
) -> LogfileInspectionResult:
    """Inspect one logfile path and return structured report metadata."""
    server_root = resolve_server_root(root)
    resolved_logfile = _resolve_user_path(logfile_path, root=server_root, context="logfile_path")
    prepared = prepare_logfile_render(resolved_logfile, allowed_root=server_root)
    spec = prepared.spec
    resolved_sources = resolve_section_data_sources_for_logfile(
        spec,
        base_dir=resolved_logfile.parent,
        allowed_root=server_root,
    )
    layout = dict(spec.document.get("layout", {}))
    sections = list(layout.get("log_sections", []))
    default_depth_range = _document_default_depth_range(spec)
    section_summaries: list[LogfileSectionSummary] = []
    for section in sections:
        section_id = str(section.get("id", ""))
        tracks = list(section.get("tracks", []))
        source_path, source_format = resolved_sources[section_id]
        section_summaries.append(
            LogfileSectionSummary(
                id=section_id,
                title=str(section.get("title", "")),
                source_path=str(source_path),
                source_format=source_format,
                depth_range=_section_depth_range(
                    section,
                    default_depth_range=default_depth_range,
                ),
                track_ids=[str(track.get("id", "")) for track in tracks],
                track_kinds=[str(track.get("kind", "")) for track in tracks],
            )
        )

    return LogfileInspectionResult(
        name=spec.name,
        render_backend=spec.render_backend,
        configured_output_path=spec.render_output_path,
        page_settings=deepcopy(dict(spec.document.get("page", {}))),
        depth_settings=deepcopy(dict(spec.document.get("depth", {}))),
        has_heading=bool(layout.get("heading")),
        has_remarks=bool(layout.get("remarks")),
        has_tail=_layout_has_tail(layout),
        section_ids=[summary.id for summary in section_summaries],
        sections=section_summaries,
    )


def preview_logfile_png(
    logfile_path: str,
    *,
    page_index: int = 0,
    dpi: int = 144,
    section_id: str | None = None,
    track_ids: list[str] | None = None,
    depth_range: tuple[float, float] | None = None,
    depth_range_unit: str | None = None,
    include_report_pages: bool = True,
    root: str | Path | None = None,
) -> bytes:
    """Render one logfile preview as in-memory PNG bytes."""
    _validate_preview_parameters(
        page_index=page_index,
        dpi=dpi,
        section_id=section_id,
        track_ids=track_ids,
        depth_range=depth_range,
    )
    server_root = resolve_server_root(root)
    resolved_logfile = _resolve_user_path(logfile_path, root=server_root, context="logfile_path")
    prepared = prepare_logfile_render(resolved_logfile, allowed_root=server_root)
    if section_id is not None:
        _ensure_known_section(prepared.spec, section_id)
    if track_ids is not None:
        _ensure_known_track_ids(prepared.spec, section_id, track_ids)
    report = _preview_report(prepared)
    _force_agg_preview_backend()
    section_ids = None if section_id is None else [section_id]
    track_ids_by_section = None
    if track_ids is not None:
        track_ids_by_section = {section_id: track_ids}
    return render_png_bytes(
        report,
        page_index=page_index,
        dpi=dpi,
        section_ids=section_ids,
        track_ids_by_section=track_ids_by_section,
        depth_range=depth_range,
        depth_range_unit=depth_range_unit,
        include_report_pages=include_report_pages,
    )


def preview_section_png(
    logfile_path: str,
    *,
    section_id: str,
    page_index: int = 0,
    dpi: int = 144,
    root: str | Path | None = None,
) -> bytes:
    """Render one section preview as in-memory PNG bytes."""
    _validate_preview_parameters(
        page_index=page_index,
        dpi=dpi,
        section_id=section_id,
        track_ids=None,
        depth_range=None,
    )
    server_root = resolve_server_root(root)
    resolved_logfile = _resolve_user_path(logfile_path, root=server_root, context="logfile_path")
    prepared = prepare_logfile_render(resolved_logfile, allowed_root=server_root)
    _ensure_known_section(prepared.spec, section_id)
    report = _preview_report(prepared)
    _force_agg_preview_backend()
    return render_section_png(
        report,
        section_id=section_id,
        page_index=page_index,
        dpi=dpi,
    )


def preview_track_png(
    logfile_path: str,
    *,
    section_id: str,
    track_ids: list[str],
    page_index: int = 0,
    dpi: int = 144,
    depth_range: tuple[float, float] | None = None,
    depth_range_unit: str | None = None,
    root: str | Path | None = None,
) -> bytes:
    """Render selected tracks from one section as in-memory PNG bytes."""
    _validate_preview_parameters(
        page_index=page_index,
        dpi=dpi,
        section_id=section_id,
        track_ids=track_ids,
        depth_range=depth_range,
    )
    server_root = resolve_server_root(root)
    resolved_logfile = _resolve_user_path(logfile_path, root=server_root, context="logfile_path")
    prepared = prepare_logfile_render(resolved_logfile, allowed_root=server_root)
    _ensure_known_track_ids(prepared.spec, section_id, track_ids)
    report = _preview_report(prepared)
    _force_agg_preview_backend()
    return render_track_png(
        report,
        section_id=section_id,
        track_ids=track_ids,
        page_index=page_index,
        dpi=dpi,
        depth_range=depth_range,
        depth_range_unit=depth_range_unit,
    )


def preview_window_png(
    logfile_path: str,
    *,
    depth_range: tuple[float, float],
    depth_range_unit: str | None = None,
    page_index: int = 0,
    dpi: int = 144,
    section_ids: list[str] | None = None,
    root: str | Path | None = None,
) -> bytes:
    """Render a depth-windowed preview as in-memory PNG bytes."""
    _validate_preview_parameters(
        page_index=page_index,
        dpi=dpi,
        section_id=None,
        track_ids=None,
        depth_range=depth_range,
    )
    server_root = resolve_server_root(root)
    resolved_logfile = _resolve_user_path(logfile_path, root=server_root, context="logfile_path")
    prepared = prepare_logfile_render(resolved_logfile, allowed_root=server_root)
    if section_ids is not None:
        _ensure_known_section_ids(prepared.spec, section_ids)
    report = _preview_report(prepared)
    _force_agg_preview_backend()
    return render_window_png(
        report,
        depth_range=depth_range,
        depth_range_unit=depth_range_unit,
        page_index=page_index,
        dpi=dpi,
        section_ids=section_ids,
    )


def render_logfile_to_file(
    logfile_path: str,
    output_path: str,
    *,
    overwrite: bool = False,
    root: str | Path | None = None,
) -> RenderToFileResult:
    """Render one logfile to an explicit output path under the server root."""
    server_root = resolve_server_root(root)
    resolved_logfile = _resolve_user_path(logfile_path, root=server_root, context="logfile_path")
    resolved_output = _resolve_user_path(output_path, root=server_root, context="output_path")
    if resolved_output.exists() and not overwrite:
        raise FileExistsError(f"Output path already exists: {resolved_output}")
    prepared = prepare_logfile_render(resolved_logfile, allowed_root=server_root)
    result = render_prepared_logfile(prepared, output_path=resolved_output)
    output_text = "" if result.output_path is None else str(result.output_path)
    return RenderToFileResult(
        backend=result.backend,
        page_count=result.page_count,
        output_path=output_text,
    )


def _rebase_relative_path(
    path_value: str,
    *,
    from_base_dir: Path,
    to_base_dir: Path,
) -> str:
    original_path = Path(path_value).expanduser()
    if original_path.is_absolute():
        return str(original_path.resolve())
    resolved_path = (from_base_dir / original_path).resolve()
    return Path(os.path.relpath(resolved_path, start=to_base_dir)).as_posix()


def _rebase_report_paths(
    mapping: dict[str, object],
    *,
    from_base_dir: Path,
    to_base_dir: Path,
) -> dict[str, object]:
    render = mapping.get("render")
    if isinstance(render, dict):
        output_path = render.get("output_path")
        if isinstance(output_path, str) and output_path.strip():
            render["output_path"] = _rebase_relative_path(
                output_path,
                from_base_dir=from_base_dir,
                to_base_dir=to_base_dir,
            )

    data = mapping.get("data")
    if isinstance(data, dict):
        source_path = data.get("source_path")
        if isinstance(source_path, str) and source_path.strip():
            data["source_path"] = _rebase_relative_path(
                source_path,
                from_base_dir=from_base_dir,
                to_base_dir=to_base_dir,
            )

    document = mapping.get("document")
    if not isinstance(document, dict):
        return mapping
    layout = document.get("layout")
    if not isinstance(layout, dict):
        return mapping
    sections = layout.get("log_sections")
    if not isinstance(sections, list):
        return mapping
    for section in sections:
        if not isinstance(section, dict):
            continue
        section_data = section.get("data")
        if not isinstance(section_data, dict):
            continue
        source_path = section_data.get("source_path")
        if isinstance(source_path, str) and source_path.strip():
            section_data["source_path"] = _rebase_relative_path(
                source_path,
                from_base_dir=from_base_dir,
                to_base_dir=to_base_dir,
            )
    return mapping


def export_example_bundle(
    example_id: str,
    output_dir: str,
    *,
    overwrite: bool = False,
    root: str | Path | None = None,
) -> ExampleBundleExportResult:
    """Export one packaged example bundle into a writable server-root directory."""
    server_root = resolve_server_root(root)
    resolved_output_dir = _resolve_user_path(output_dir, root=server_root, context="output_dir")
    if resolved_output_dir.exists() and not resolved_output_dir.is_dir():
        raise NotADirectoryError(f"Output directory path is not a directory: {resolved_output_dir}")

    targets = [resolved_output_dir / filename for filename in PRODUCTION_EXAMPLE_FILES]
    if not overwrite:
        for target in targets:
            if target.exists():
                raise FileExistsError(f"Example bundle target already exists: {target}")

    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    written_files: list[str] = []
    for filename in PRODUCTION_EXAMPLE_FILES:
        target = resolved_output_dir / filename
        target.write_text(
            read_production_example_text(example_id, filename),
            encoding="utf-8",
        )
        written_files.append(str(target))
    return ExampleBundleExportResult(
        example_id=example_id,
        output_dir=str(resolved_output_dir),
        written_files=written_files,
    )


def create_logfile_draft(
    output_path: str,
    *,
    example_id: str | None = None,
    source_logfile_path: str | None = None,
    overwrite: bool = False,
    root: str | Path | None = None,
) -> LogfileDraftCreateResult:
    """Create one normalized draft logfile from an example or existing logfile."""
    if (example_id is None) == (source_logfile_path is None):
        raise ValueError(
            "Provide exactly one of example_id or source_logfile_path when creating a draft."
        )

    server_root = resolve_server_root(root)
    resolved_output_path = _resolve_user_path(output_path, root=server_root, context="output_path")
    if resolved_output_path.exists() and not overwrite:
        raise FileExistsError(f"Output path already exists: {resolved_output_path}")

    if example_id is not None:
        asset = _production_asset_path(example_id, "full_reconstruction.log.yaml")
        with as_file(asset) as asset_path:
            spec = load_logfile_text(
                asset_path.read_text(encoding="utf-8"),
                base_dir=asset_path.parent,
            )
            normalized_spec = _persist_rebased_logfile_mapping(
                report_to_dict(spec),
                from_base_dir=asset_path.parent,
                output_path=resolved_output_path,
            )
        return LogfileDraftCreateResult(
            output_path=str(resolved_output_path),
            name=normalized_spec.name,
            section_ids=_section_ids_from_spec(normalized_spec),
            seed_kind="example",
            seed_value=example_id,
        )

    resolved_source_logfile = _resolve_user_path(
        source_logfile_path,
        root=server_root,
        context="source_logfile_path",
    )
    _, mapping = _normalize_logfile_mapping_from_path(
        resolved_source_logfile,
        allowed_root=server_root,
    )
    normalized_spec = _persist_rebased_logfile_mapping(
        mapping,
        from_base_dir=resolved_source_logfile.parent,
        output_path=resolved_output_path,
    )
    return LogfileDraftCreateResult(
        output_path=str(resolved_output_path),
        name=normalized_spec.name,
        section_ids=_section_ids_from_spec(normalized_spec),
        seed_kind="logfile",
        seed_value=str(resolved_source_logfile),
    )


def summarize_logfile_draft(
    logfile_path: str,
    *,
    root: str | Path | None = None,
) -> LogfileDraftSummaryResult:
    """Summarize one draft logfile for deterministic authoring workflows."""
    server_root = resolve_server_root(root)
    resolved_logfile = _resolve_user_path(logfile_path, root=server_root, context="logfile_path")
    spec = load_logfile(resolved_logfile, allowed_root=server_root)
    resolved_sources = resolve_section_data_sources_for_logfile(
        spec,
        base_dir=resolved_logfile.parent,
        allowed_root=server_root,
    )
    default_depth_range = _document_default_depth_range(spec)
    binding_counts = _binding_counts_by_section(spec)

    available_channels_by_section = {section_id: [] for section_id in _section_ids_from_spec(spec)}
    dataset_loaded = False
    dataset_message = ""
    try:
        datasets_by_section, _ = load_datasets_for_logfile(
            spec,
            base_dir=resolved_logfile.parent,
            allowed_root=server_root,
        )
    except (DependencyUnavailableError, FileNotFoundError, OSError, TemplateValidationError) as exc:
        dataset_message = str(exc)
    else:
        dataset_loaded = True
        for section_id, dataset in datasets_by_section.items():
            available_channels_by_section[section_id] = list(dataset.channels)

    layout = dict(spec.document.get("layout", {}))
    sections = list(layout.get("log_sections", []))
    section_summaries: list[LogfileDraftSectionSummary] = []
    for section in sections:
        section_id = str(section.get("id", ""))
        tracks = [track for track in list(section.get("tracks", [])) if isinstance(track, dict)]
        source_path, source_format = resolved_sources[section_id]
        counts = binding_counts.get(section_id, {"curve": 0, "raster": 0})
        section_summaries.append(
            LogfileDraftSectionSummary(
                id=section_id,
                title=str(section.get("title", "")),
                source_path=str(source_path),
                source_format=source_format,
                depth_range=_section_depth_range(
                    section,
                    default_depth_range=default_depth_range,
                ),
                track_ids=[str(track.get("id", "")) for track in tracks],
                track_kinds=[str(track.get("kind", "")) for track in tracks],
                curve_binding_count=counts["curve"],
                raster_binding_count=counts["raster"],
                available_channels=available_channels_by_section[section_id],
                dataset_loaded=dataset_loaded,
                dataset_message=dataset_message,
            )
        )

    return LogfileDraftSummaryResult(
        name=spec.name,
        render_backend=spec.render_backend,
        configured_output_path=spec.render_output_path,
        has_heading=bool(layout.get("heading")),
        has_remarks=bool(layout.get("remarks")),
        has_tail=_layout_has_tail(layout),
        section_count=len(section_summaries),
        section_ids=[summary.id for summary in section_summaries],
        sections=section_summaries,
    )


def add_track(
    logfile_path: str,
    *,
    section_id: str,
    id: str,
    title: str,
    kind: str,
    width_mm: float,
    x_scale: dict[str, object] | None = None,
    grid: dict[str, object] | None = None,
    track_header: dict[str, object] | None = None,
    reference: dict[str, object] | None = None,
    annotations: list[dict[str, object]] | None = None,
    root: str | Path | None = None,
) -> AddedTrackResult:
    """Append one track to a draft logfile and persist the validated result."""
    server_root = resolve_server_root(root)
    resolved_logfile = _resolve_user_path(logfile_path, root=server_root, context="logfile_path")
    current_spec, mapping = _normalize_logfile_mapping_from_path(
        resolved_logfile,
        allowed_root=server_root,
    )
    _ensure_known_section(current_spec, section_id)
    section = _logfile_mapping_section(mapping, section_id)
    tracks = _logfile_mapping_section_tracks(section, section_id=section_id)
    track_id = str(id).strip()
    if not track_id:
        raise TemplateValidationError("Track id must be non-empty.")
    existing_track_ids = [str(track.get("id", "")) for track in tracks if isinstance(track, dict)]
    if track_id in existing_track_ids:
        raise TemplateValidationError(
            f"Track id {track_id!r} already exists in section {section_id!r}."
        )

    track_mapping: dict[str, object] = {
        "id": track_id,
        "title": str(title),
        "kind": str(kind),
        "width_mm": float(width_mm),
        "position": len(existing_track_ids) + 1,
    }
    if x_scale is not None:
        track_mapping["x_scale"] = deepcopy(x_scale)
    if grid is not None:
        track_mapping["grid"] = deepcopy(grid)
    if track_header is not None:
        track_mapping["track_header"] = deepcopy(track_header)
    if reference is not None:
        track_mapping["reference"] = deepcopy(reference)
    if annotations is not None:
        track_mapping["annotations"] = deepcopy(annotations)
    tracks.append(track_mapping)

    saved_spec = _persist_validated_logfile_mapping(
        mapping,
        logfile_path=resolved_logfile,
        root=server_root,
    )
    saved_section = _section_map_from_spec(saved_spec)[section_id]
    saved_track_ids = [
        str(track.get("id", ""))
        for track in list(saved_section.get("tracks", []))
        if isinstance(track, dict)
    ]
    return AddedTrackResult(
        logfile_path=str(resolved_logfile),
        section_id=section_id,
        track_id=track_id,
        track_ids=saved_track_ids,
        track_count=len(saved_track_ids),
    )


def bind_curve(
    logfile_path: str,
    *,
    section_id: str,
    track_id: str,
    channel: str,
    label: str | None = None,
    style: dict[str, object] | None = None,
    scale: dict[str, object] | None = None,
    header_display: dict[str, object] | None = None,
    root: str | Path | None = None,
) -> BoundCurveResult:
    """Add one curve binding to a draft logfile and persist the validated result."""
    server_root = resolve_server_root(root)
    resolved_logfile = _resolve_user_path(logfile_path, root=server_root, context="logfile_path")
    current_spec, mapping = _normalize_logfile_mapping_from_path(
        resolved_logfile,
        allowed_root=server_root,
    )
    _ensure_known_track_ids(current_spec, section_id, [track_id])
    resolved_channel = _resolve_section_channel_name(
        current_spec,
        logfile_path=resolved_logfile,
        root=server_root,
        section_id=section_id,
        channel=channel,
    )
    bindings = _logfile_mapping_bindings(mapping)
    try:
        _ = _find_curve_binding_index(
            bindings,
            spec=current_spec,
            section_id=section_id,
            track_id=track_id,
            channel=resolved_channel,
        )
    except TemplateValidationError:
        pass
    else:
        raise TemplateValidationError(
            f"Curve binding for channel {resolved_channel!r} already exists on "
            f"track {track_id!r} in section {section_id!r}."
        )

    binding: dict[str, object] = {
        "section": section_id,
        "track_id": track_id,
        "channel": resolved_channel,
        "kind": "curve",
    }
    if label is not None:
        binding["label"] = label
    if style is not None:
        binding["style"] = deepcopy(style)
    if scale is not None:
        binding["scale"] = deepcopy(scale)
    if header_display is not None:
        binding["header_display"] = deepcopy(header_display)
    bindings.append(binding)

    saved_spec = _persist_validated_logfile_mapping(
        mapping,
        logfile_path=resolved_logfile,
        root=server_root,
    )
    binding_count = _binding_counts_by_section(saved_spec)[section_id]["curve"]
    return BoundCurveResult(
        logfile_path=str(resolved_logfile),
        section_id=section_id,
        track_id=track_id,
        channel=resolved_channel,
        binding_kind="curve",
        binding_count=binding_count,
    )


def update_curve_binding(
    logfile_path: str,
    *,
    section_id: str,
    track_id: str,
    channel: str,
    patch: dict[str, object],
    root: str | Path | None = None,
) -> UpdatedCurveBindingResult:
    """Patch one curve binding in a draft logfile and persist the validated result."""
    allowed_keys = {
        "label",
        "style",
        "scale",
        "header_display",
        "fill",
        "reference_overlay",
        "value_labels",
        "wrap",
        "render_mode",
    }
    invalid = sorted(key for key in patch if key not in allowed_keys)
    if invalid:
        raise TemplateValidationError(
            f"Unsupported curve-binding patch keys {invalid}. Allowed keys: {sorted(allowed_keys)}."
        )

    server_root = resolve_server_root(root)
    resolved_logfile = _resolve_user_path(logfile_path, root=server_root, context="logfile_path")
    current_spec, mapping = _normalize_logfile_mapping_from_path(
        resolved_logfile,
        allowed_root=server_root,
    )
    _ensure_known_track_ids(current_spec, section_id, [track_id])
    bindings = _logfile_mapping_bindings(mapping)
    binding_index = _find_curve_binding_index(
        bindings,
        spec=current_spec,
        section_id=section_id,
        track_id=track_id,
        channel=channel,
    )
    binding = bindings[binding_index]
    if not isinstance(binding, dict):
        raise RuntimeError("Expected a mapping curve binding entry.")
    bindings[binding_index] = _merge_optional_patch(binding, patch)

    saved_spec = _persist_validated_logfile_mapping(
        mapping,
        logfile_path=resolved_logfile,
        root=server_root,
    )
    saved_bindings = _logfile_mapping_bindings(report_to_dict(saved_spec))
    saved_binding_index = _find_curve_binding_index(
        saved_bindings,
        spec=saved_spec,
        section_id=section_id,
        track_id=track_id,
        channel=channel,
    )
    saved_binding = saved_bindings[saved_binding_index]
    if not isinstance(saved_binding, dict):
        raise RuntimeError("Expected a mapping curve binding entry.")
    return UpdatedCurveBindingResult(
        logfile_path=str(resolved_logfile),
        section_id=section_id,
        track_id=track_id,
        channel=str(saved_binding.get("channel", channel)),
        binding=deepcopy(saved_binding),
    )


def move_track(
    logfile_path: str,
    *,
    section_id: str,
    track_id: str,
    before_track_id: str | None = None,
    after_track_id: str | None = None,
    position: int | None = None,
    root: str | Path | None = None,
) -> MovedTrackResult:
    """Reorder one track inside a draft logfile and persist the validated result."""
    target_count = sum(value is not None for value in (before_track_id, after_track_id, position))
    if target_count != 1:
        raise ValueError("Provide exactly one of before_track_id, after_track_id, or position.")

    server_root = resolve_server_root(root)
    resolved_logfile = _resolve_user_path(logfile_path, root=server_root, context="logfile_path")
    current_spec, mapping = _normalize_logfile_mapping_from_path(
        resolved_logfile,
        allowed_root=server_root,
    )
    _ensure_known_track_ids(current_spec, section_id, [track_id])
    section = _logfile_mapping_section(mapping, section_id)
    tracks = _logfile_mapping_section_tracks(section, section_id=section_id)
    track_ids = [str(track.get("id", "")) for track in tracks if isinstance(track, dict)]
    source_index = track_ids.index(track_id)
    moving_track = tracks.pop(source_index)
    remaining_track_ids = [str(track.get("id", "")) for track in tracks if isinstance(track, dict)]

    insert_index: int
    if before_track_id is not None:
        if before_track_id == track_id:
            raise TemplateValidationError("before_track_id must differ from track_id.")
        if before_track_id not in remaining_track_ids:
            raise TemplateValidationError(
                "Unknown before_track_id "
                f"{before_track_id!r}. Available tracks: {remaining_track_ids}."
            )
        insert_index = remaining_track_ids.index(before_track_id)
    elif after_track_id is not None:
        if after_track_id == track_id:
            raise TemplateValidationError("after_track_id must differ from track_id.")
        if after_track_id not in remaining_track_ids:
            raise TemplateValidationError(
                "Unknown after_track_id "
                f"{after_track_id!r}. Available tracks: {remaining_track_ids}."
            )
        insert_index = remaining_track_ids.index(after_track_id) + 1
    else:
        assert position is not None
        if position < 1 or position > len(track_ids):
            raise ValueError(f"position must be between 1 and {len(track_ids)}.")
        insert_index = position - 1

    tracks.insert(insert_index, moving_track)
    _renumber_section_track_positions(tracks)

    saved_spec = _persist_validated_logfile_mapping(
        mapping,
        logfile_path=resolved_logfile,
        root=server_root,
    )
    saved_section = _section_map_from_spec(saved_spec)[section_id]
    saved_track_ids = [
        str(track.get("id", ""))
        for track in list(saved_section.get("tracks", []))
        if isinstance(track, dict)
    ]
    return MovedTrackResult(
        logfile_path=str(resolved_logfile),
        section_id=section_id,
        track_id=track_id,
        track_ids=saved_track_ids,
        track_count=len(saved_track_ids),
    )


def set_heading_content(
    logfile_path: str,
    *,
    patch: dict[str, object],
    root: str | Path | None = None,
) -> HeadingContentResult:
    """Patch the report heading block inside a draft logfile."""
    allowed_keys = {
        "enabled",
        "provider_name",
        "general_fields",
        "service_titles",
        "detail",
        "tail_enabled",
    }
    invalid = sorted(key for key in patch if key not in allowed_keys)
    if invalid:
        raise TemplateValidationError(
            f"Unsupported heading patch keys {invalid}. Allowed keys: {sorted(allowed_keys)}."
        )

    server_root = resolve_server_root(root)
    resolved_logfile = _resolve_user_path(logfile_path, root=server_root, context="logfile_path")
    _, mapping = _normalize_logfile_mapping_from_path(
        resolved_logfile,
        allowed_root=server_root,
    )
    layout = _logfile_mapping_layout(mapping)
    current_heading = layout.get("heading")
    if not isinstance(current_heading, dict):
        current_heading = {}
    updated_heading = _merge_optional_patch(current_heading, patch)
    if "enabled" not in updated_heading:
        updated_heading["enabled"] = True
    layout["heading"] = updated_heading

    saved_spec = _persist_validated_logfile_mapping(
        mapping,
        logfile_path=resolved_logfile,
        root=server_root,
    )
    saved_layout = dict(saved_spec.document.get("layout", {}))
    saved_heading = deepcopy(dict(saved_layout.get("heading", {})))
    return HeadingContentResult(
        logfile_path=str(resolved_logfile),
        has_heading=bool(saved_heading),
        has_tail=_layout_has_tail(saved_layout),
        heading=saved_heading,
    )


def set_remarks_content(
    logfile_path: str,
    *,
    remarks: list[dict[str, object]],
    root: str | Path | None = None,
) -> RemarksContentResult:
    """Replace the first-page remarks block inside a draft logfile."""
    server_root = resolve_server_root(root)
    resolved_logfile = _resolve_user_path(logfile_path, root=server_root, context="logfile_path")
    _, mapping = _normalize_logfile_mapping_from_path(
        resolved_logfile,
        allowed_root=server_root,
    )
    layout = _logfile_mapping_layout(mapping)
    layout["remarks"] = deepcopy(remarks)

    saved_spec = _persist_validated_logfile_mapping(
        mapping,
        logfile_path=resolved_logfile,
        root=server_root,
    )
    saved_layout = dict(saved_spec.document.get("layout", {}))
    saved_remarks = deepcopy(list(saved_layout.get("remarks", [])))
    return RemarksContentResult(
        logfile_path=str(resolved_logfile),
        remarks_count=len(saved_remarks),
        remarks=saved_remarks,
    )


def format_logfile_text(
    yaml_text: str,
    *,
    base_dir: str | Path | None = None,
    root: str | Path | None = None,
) -> FormattedLogfileTextResult:
    """Normalize valid logfile YAML text through the canonical serializer path."""
    server_root = resolve_server_root(root)
    resolved_base_dir = _resolve_base_dir(base_dir, root=server_root)
    spec = _load_validated_logfile_text_spec(
        yaml_text,
        base_dir=resolved_base_dir,
        root=server_root,
    )
    normalized_yaml = report_to_yaml(spec)
    if not isinstance(normalized_yaml, str):
        raise RuntimeError("Expected canonical YAML text from report_to_yaml().")
    return FormattedLogfileTextResult(
        name=spec.name,
        render_backend=spec.render_backend,
        section_ids=_section_ids_from_spec(spec),
        yaml_text=normalized_yaml,
    )


def save_logfile_text(
    yaml_text: str,
    output_path: str,
    *,
    overwrite: bool = False,
    base_dir: str | Path | None = None,
    root: str | Path | None = None,
) -> SavedLogfileTextResult:
    """Validate, normalize, and save logfile YAML text under the server root."""
    server_root = resolve_server_root(root)
    resolved_output_path = _resolve_user_path(output_path, root=server_root, context="output_path")
    if resolved_output_path.exists() and not overwrite:
        raise FileExistsError(f"Output path already exists: {resolved_output_path}")

    resolved_base_dir = _resolve_base_dir(
        base_dir,
        root=server_root,
        fallback=resolved_output_path.parent,
    )
    spec = _load_validated_logfile_text_spec(
        yaml_text,
        base_dir=resolved_base_dir,
        root=server_root,
    )
    normalized_mapping = report_to_dict(spec)
    rebased_mapping = _rebase_report_paths(
        normalized_mapping,
        from_base_dir=resolved_base_dir,
        to_base_dir=resolved_output_path.parent,
    )
    normalized_yaml = report_to_yaml(rebased_mapping)
    if not isinstance(normalized_yaml, str):
        raise RuntimeError("Expected canonical YAML text from report_to_yaml().")
    resolved_output_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_output_path.write_text(normalized_yaml, encoding="utf-8")
    return SavedLogfileTextResult(
        name=spec.name,
        render_backend=spec.render_backend,
        section_ids=_section_ids_from_spec(spec),
        output_path=str(resolved_output_path),
    )


def review_logfile_prompt(logfile_path: str) -> str:
    """Return the guided prompt text for logfile review workflows."""
    return (
        "Review this wellplot logfile under the current MCP server root.\n\n"
        f"Logfile path: {logfile_path}\n\n"
        "Workflow:\n"
        "1. Call validate_logfile(logfile_path) first.\n"
        "2. If valid is true, call inspect_logfile(logfile_path).\n"
        "3. Summarize any issues, notable section/source layout facts, and the next sensible "
        "render or preview step.\n"
        "4. If validation fails, explain the returned message before proposing fixes.\n"
    )


def preview_logfile_prompt(logfile_path: str, focus: str | None = None) -> str:
    """Return the guided prompt text for logfile preview workflows."""
    focus_text = "Preview focus: full report." if focus is None else f"Preview focus: {focus}"
    return (
        "Preview this wellplot logfile under the current MCP server root.\n\n"
        f"Logfile path: {logfile_path}\n"
        f"{focus_text}\n\n"
        "Workflow:\n"
        "1. Call validate_logfile(logfile_path).\n"
        "2. Call inspect_logfile(logfile_path) to identify relevant sections or tracks.\n"
        "3. Call preview_logfile_png(logfile_path, ...) with the most relevant section, track, "
        "page, or depth window for the stated focus.\n"
        "4. Briefly explain what the preview shows and any next refinement you recommend.\n"
    )


def start_from_example_prompt(example_id: str, goal: str) -> str:
    """Return the guided prompt text for adapting a packaged production example."""
    readme = read_production_example_text(example_id, "README.md")
    template_yaml = read_production_example_text(example_id, "base.template.yaml")
    logfile_yaml = read_production_example_text(example_id, "full_reconstruction.log.yaml")
    return (
        f"Adapt the packaged wellplot production example `{example_id}` for this goal:\n"
        f"{goal}\n\n"
        "Use the bundled example resources below as the starting point.\n\n"
        "README.md\n"
        "```markdown\n"
        f"{readme}\n"
        "```\n\n"
        "base.template.yaml\n"
        "```yaml\n"
        f"{template_yaml}\n"
        "```\n\n"
        "full_reconstruction.log.yaml\n"
        "```yaml\n"
        f"{logfile_yaml}\n"
        "```\n\n"
        "Preserve wellplot schema compatibility, explain the main edits you make, and prefer "
        "changing only the sections that are necessary for the stated goal.\n"
    )
