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

import csv
import json
import os
from copy import deepcopy
from dataclasses import dataclass
from difflib import SequenceMatcher
from importlib.resources import as_file, files
from pathlib import Path

import numpy as np
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
from ..io import load_dlis, load_las
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
from ..model import ArrayChannel, RasterChannel, ScalarChannel, WellDataset
from ..model.document import (
    CurveFillKind,
    ReportDetailKind,
    ScaleKind,
    TrackHeaderObjectKind,
    TrackKind,
)
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
AUTHORING_HEADING_PATCH_KEYS = (
    "enabled",
    "provider_name",
    "general_fields",
    "service_titles",
    "detail",
    "tail_enabled",
)
AUTHORING_CURVE_BINDING_PATCH_KEYS = (
    "label",
    "style",
    "scale",
    "header_display",
    "fill",
    "reference_overlay",
    "value_labels",
    "wrap",
    "render_mode",
)
AUTHORING_MOVE_TRACK_SELECTORS = ("before_track_id", "after_track_id", "position")
AUTHORING_RESOURCE_URIS = (
    "wellplot://authoring/schema/patch.json",
    "wellplot://authoring/catalog/track-kinds.json",
    "wellplot://authoring/catalog/fill-kinds.json",
    "wellplot://authoring/catalog/track-archetypes.json",
    "wellplot://authoring/catalog/header-fields.json",
    "wellplot://authoring/catalog/header-key-aliases.json",
    "wellplot://authoring/catalog/channel-aliases.json",
    "wellplot://authoring/catalog/style-presets.json",
)
AUTHORING_HEADER_OVERWRITE_POLICIES = ("fill_empty", "replace", "merge_lists")
SUPPORTED_KEY_VALUE_FORMAT_HINTS = ("auto", "colon", "equals", "tsv", "csv")
AUTHORING_TRACK_ARCHETYPES = (
    {
        "id": "reference_depth",
        "label": "Reference Depth",
        "kind": "reference",
        "default_width_mm": 16.0,
        "notes": "Shared depth axis, markers, and event context.",
    },
    {
        "id": "gamma_ray",
        "label": "Gamma Ray",
        "kind": "normal",
        "default_width_mm": 28.0,
        "recommended_binding": {
            "scale": {"kind": "linear", "min": 0.0, "max": 150.0},
            "style": {"color": "#008000"},
        },
        "notes": "Single-curve scalar track for GR review.",
    },
    {
        "id": "porosity_overlay",
        "label": "Porosity Overlay",
        "kind": "normal",
        "default_width_mm": 32.0,
        "recommended_channels": ["NPHI", "RHOB"],
        "notes": "Dual-curve porosity track, often followed by crossover fill edits.",
    },
    {
        "id": "resistivity_log",
        "label": "Resistivity",
        "kind": "normal",
        "default_width_mm": 28.0,
        "recommended_binding": {
            "scale": {"kind": "log", "min": 0.2, "max": 2000.0},
        },
        "notes": "Scalar resistivity track with logarithmic scale.",
    },
    {
        "id": "vdl_array",
        "label": "VDL Array",
        "kind": "array",
        "default_width_mm": 28.0,
        "notes": "Array/raster track for waveform-style VDL presentation.",
    },
)
AUTHORING_STYLE_PRESETS = (
    {
        "family": "porosity_overlays",
        "id": "density_neutron_overlay",
        "label": "Density-Neutron Overlay",
        "summary": "Balanced overlay style for RHOB/NPHI porosity review.",
        "use_cases": ["porosity", "density-neutron", "overlay"],
        "track_patch": {
            "kind": "normal",
            "width_mm": 32.0,
            "grid": {"enabled": True, "vertical": {"minor_count": 4}},
        },
        "binding_templates": [
            {
                "alias_id": "bulk_density",
                "label": "Density",
                "scale": {"kind": "linear", "min": 1.95, "max": 2.95},
                "style": {"color": "#c2410c", "line_width": 1.3},
            },
            {
                "alias_id": "neutron_porosity",
                "label": "Neutron",
                "scale": {"kind": "linear", "min": 0.45, "max": -0.15},
                "style": {"color": "#1d4ed8", "line_width": 1.1},
                "fill": {
                    "kind": "between_curves",
                    "target_channel": "RHOB",
                    "left_color": "#bfdbfe",
                    "right_color": "#fed7aa",
                    "alpha": 0.35,
                },
            },
        ],
        "notes": [
            "Use one shared track for RHOB and NPHI.",
            "Reverse the neutron scale so low porosity plots to the right.",
        ],
    },
    {
        "family": "gamma_ray_defaults",
        "id": "gamma_ray_clean_print",
        "label": "Gamma Ray Clean Print",
        "summary": "Single-curve gamma ray styling with strong print contrast.",
        "use_cases": ["gamma ray", "gr", "print-safe"],
        "track_patch": {
            "kind": "normal",
            "width_mm": 28.0,
            "grid": {"enabled": True},
        },
        "binding_templates": [
            {
                "alias_id": "gamma_ray",
                "label": "Gamma Ray",
                "scale": {"kind": "linear", "min": 0.0, "max": 150.0},
                "style": {"color": "#166534", "line_width": 1.2},
                "header_display": {"scale_text_color": "#166534"},
            }
        ],
        "notes": [
            "Good default for single-track GR review.",
            "Keeps the scale conventional and readable on grayscale printouts.",
        ],
    },
    {
        "family": "resistivity_log_conventions",
        "id": "triple_combo_resistivity",
        "label": "Triple Combo Resistivity",
        "summary": "Log-scale resistivity convention for shallow/medium/deep overlays.",
        "use_cases": ["resistivity", "deep resistivity", "triple combo"],
        "track_patch": {
            "kind": "normal",
            "width_mm": 32.0,
            "grid": {"enabled": True, "horizontal": {"enabled": True}},
        },
        "binding_templates": [
            {
                "alias_id": "shallow_resistivity",
                "label": "RSH",
                "scale": {"kind": "log", "min": 0.2, "max": 2000.0},
                "style": {"color": "#2563eb", "line_width": 1.0},
            },
            {
                "alias_id": "medium_resistivity",
                "label": "RME",
                "scale": {"kind": "log", "min": 0.2, "max": 2000.0},
                "style": {"color": "#7c3aed", "line_width": 1.0},
            },
            {
                "alias_id": "deep_resistivity",
                "label": "RDEEP",
                "scale": {"kind": "log", "min": 0.2, "max": 2000.0},
                "style": {"color": "#dc2626", "line_width": 1.2},
            },
        ],
        "notes": [
            "Keep all resistivity curves on the same logarithmic scale.",
            "Use the deepest investigation curve with the strongest visual weight.",
        ],
    },
    {
        "family": "cbl_vdl_variants",
        "id": "cbl_vdl_high_contrast",
        "label": "CBL/VDL High Contrast",
        "summary": "High-contrast CBL/VDL presentation for screen review.",
        "use_cases": ["cbl", "vdl", "cement bond", "waveform"],
        "binding_templates": [
            {
                "alias_id": "cement_bond",
                "label": "CBL",
                "scale": {"kind": "linear", "min": 0.0, "max": 100.0},
                "style": {"color": "#111827", "line_width": 1.3},
            },
            {
                "alias_id": "variable_density_log",
                "label": "VDL",
                "render_mode": "raster",
                "style": {"colormap": "gray_r"},
            },
        ],
        "notes": [
            "Use a dark scalar CBL curve against an inverted grayscale VDL raster.",
            "Intended for screen-first diagnostics and anomaly review.",
        ],
    },
    {
        "family": "cbl_vdl_variants",
        "id": "cbl_vdl_print_safe",
        "label": "CBL/VDL Print Safe",
        "summary": "Print-oriented CBL/VDL styling with restrained grayscale choices.",
        "use_cases": ["cbl", "vdl", "print-safe"],
        "binding_templates": [
            {
                "alias_id": "cement_bond",
                "label": "CBL",
                "scale": {"kind": "linear", "min": 0.0, "max": 100.0},
                "style": {"color": "#374151", "line_width": 1.2},
            },
            {
                "alias_id": "variable_density_log",
                "label": "VDL",
                "render_mode": "raster",
                "style": {"colormap": "Greys"},
            },
        ],
        "notes": [
            "Avoids overly dark fills that collapse in office printers.",
            "Prefer this preset when the main artifact will be PDF or paper.",
        ],
    },
    {
        "family": "report_page_styles",
        "id": "report_header_clean",
        "label": "Report Header Clean",
        "summary": "Cleaner first page with fewer title rows and restrained remarks.",
        "use_cases": ["header", "report page", "clean presentation"],
        "heading_patch": {
            "service_titles": [
                {
                    "value": "Primary Interpretation",
                    "alignment": "left",
                    "bold": True,
                }
            ]
        },
        "remarks_patch": [
            {
                "title": "Notes",
                "lines": ["Condense first-page commentary to one short block."],
                "alignment": "left",
            }
        ],
        "notes": [
            "Good fit when the plot should read more like a concise report page.",
            "Use with inspect_heading_slots(...) before applying extracted header text.",
        ],
    },
)
AUTHORING_CHANNEL_ALIASES = (
    {
        "id": "gamma_ray",
        "label": "Gamma Ray",
        "aliases": ["gamma ray", "gamma"],
        "mnemonics": ["GR", "SGR", "CGR"],
    },
    {
        "id": "bulk_density",
        "label": "Bulk Density",
        "aliases": ["bulk density", "density"],
        "mnemonics": ["RHOB", "RHOZ", "ZDEN", "DEN"],
    },
    {
        "id": "neutron_porosity",
        "label": "Neutron Porosity",
        "aliases": ["neutron porosity", "porosity neutron"],
        "mnemonics": ["NPHI", "TNPH", "NPHI", "NPL"],
    },
    {
        "id": "deep_resistivity",
        "label": "Deep Resistivity",
        "aliases": ["deep resistivity", "true resistivity", "resistivity"],
        "mnemonics": ["RT", "RESD", "RDEP", "ILD", "AT90"],
    },
    {
        "id": "shallow_resistivity",
        "label": "Shallow Resistivity",
        "aliases": ["shallow resistivity", "medium resistivity"],
        "mnemonics": ["RS", "RMED", "ILM", "AT30"],
    },
    {
        "id": "caliper",
        "label": "Caliper",
        "aliases": ["caliper", "hole size"],
        "mnemonics": ["CALI", "CAL"],
    },
    {
        "id": "cement_bond",
        "label": "Cement Bond",
        "aliases": ["cement bond", "cbl"],
        "mnemonics": ["CBL", "CBLF"],
    },
    {
        "id": "variable_density_log",
        "label": "Variable Density Log",
        "aliases": ["variable density log", "vdl", "waveform"],
        "mnemonics": ["VDL"],
    },
)
SUPPORTED_SOURCE_FORMATS = ("auto", "las", "dlis")


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
class DataSourceIndexSummary:
    """Structured shared-index summary for one inspected raw data source."""

    depth_unit: str | None
    depth_min: float | None
    depth_max: float | None
    sample_count: int | None
    shared_axis: bool


@dataclass(slots=True)
class DataSourceChannelSummary:
    """Structured per-channel summary for one inspected raw data source."""

    mnemonic: str
    kind: str
    depth_unit: str
    depth_min: float
    depth_max: float
    sample_count: int
    value_unit: str | None
    description: str
    value_shape: list[int]
    value_min: float | None
    value_max: float | None
    sample_axis_count: int | None
    sample_unit: str | None
    sample_label: str | None
    metadata_keys: list[str]


@dataclass(slots=True)
class DataSourceInspectionResult:
    """Structured inspection payload for one raw LAS/DLIS source."""

    source_path: str
    source_format_detected: str
    dataset_name: str
    index: DataSourceIndexSummary
    channel_count: int
    channels: list[DataSourceChannelSummary]
    metadata_keys: list[str]
    well_metadata: dict[str, object]
    provenance: dict[str, object]
    warnings: list[str]


@dataclass(slots=True)
class RequestedChannelResolution:
    """Structured per-request channel-availability resolution."""

    requested_channel: str
    status: str
    matched_channels: list[str]
    canonical_alias_id: str | None
    matched_alias: str | None
    suggested_channels: list[str]


@dataclass(slots=True)
class ChannelAvailabilityResult:
    """Structured channel-availability result for one source or logfile target."""

    target_kind: str
    source_path: str
    source_format_detected: str
    logfile_path: str | None
    section_id: str | None
    requested_channels: list[str]
    available_channels: list[str]
    found_channels: list[str]
    missing_channels: list[str]
    alias_matches: list[dict[str, object]]
    ambiguous_matches: list[dict[str, object]]
    resolutions: list[RequestedChannelResolution]
    warnings: list[str]


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


@dataclass(slots=True)
class HeadingSlotsResult:
    """Structured heading/report slot inspection payload for MCP ingestion flows."""

    target_kind: str
    target_path: str | None
    has_heading: bool
    has_remarks: bool
    has_tail: bool
    provider_slots: list[dict[str, object]]
    general_field_slots: list[dict[str, object]]
    service_title_slots: list[dict[str, object]]
    detail_slots: dict[str, object]
    remarks_capabilities: dict[str, object]
    current_values: dict[str, object]
    resource_uris: list[str]


@dataclass(slots=True)
class HeaderMappingPreviewResult:
    """Structured dry-run result for deterministic heading-value assignment."""

    logfile_path: str
    overwrite_policy: str
    resolved_assignments: list[dict[str, object]]
    unmatched_values: list[dict[str, object]]
    conflicting_values: list[dict[str, object]]
    warnings: list[str]
    predicted_heading_patch: dict[str, object]


@dataclass(slots=True)
class AppliedHeaderValuesResult:
    """Structured result for persisted heading/report value assignment."""

    logfile_path: str
    overwrite_policy: str
    applied_assignments: list[dict[str, object]]
    skipped_assignments: list[dict[str, object]]
    warnings: list[str]
    heading_summary: dict[str, object]


@dataclass(slots=True)
class ParsedKeyValueTextResult:
    """Structured result for deterministic key-value text extraction."""

    pairs: list[dict[str, object]]
    unparsed_lines: list[dict[str, object]]
    format_detected: str
    warnings: list[str]


@dataclass(slots=True)
class StylePresetsResult:
    """Structured style-preset catalog surface for authoring workflows."""

    available_families: list[str]
    selected_family: str | None
    presets: list[dict[str, object]]
    resource_uris: list[str]


@dataclass(slots=True)
class _HeaderAssignmentTarget:
    """Internal target descriptor for one previewable heading assignment slot."""

    target_kind: str
    target_key: str
    display_label: str
    slot_path: str
    lookup_keys: list[str]
    current_mode: str
    current_value: str | None
    general_field_index: int | None = None
    service_title_index: int | None = None
    detail_row_index: int | None = None
    detail_column_index: int | None = None
    detail_cell_index: int | None = None
    detail_uses_values: bool = False


@dataclass(slots=True)
class AuthoringVocabularyResult:
    """Structured authoring vocabulary surface for MCP-guided draft edits."""

    track_kinds: list[str]
    scale_kinds: list[str]
    curve_fill_kinds: list[str]
    report_detail_kinds: list[str]
    track_header_object_kinds: list[str]
    heading_patch_keys: list[str]
    curve_binding_patch_keys: list[str]
    move_track_selectors: list[str]
    heading_field_catalog: dict[str, object]
    track_archetypes: list[dict[str, object]]
    resource_uris: list[str]
    target_summary: dict[str, object] | None


@dataclass(slots=True)
class LogfileChangeSummaryResult:
    """Structured structural-diff summary for one mutable logfile draft."""

    logfile_path: str
    changed: bool
    message: str
    section_ids: list[str]
    added_tracks_by_section: dict[str, list[str]]
    removed_tracks_by_section: dict[str, list[str]]
    reordered_tracks_by_section: dict[str, list[str]]
    added_curve_bindings: list[dict[str, str]]
    removed_curve_bindings: list[dict[str, str]]
    updated_curve_bindings: list[dict[str, str]]
    heading_changed: bool
    remarks_changed: bool
    render_output_changed: bool
    summary_lines: list[str]


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


def _normalize_source_format(source_format: str) -> str:
    normalized = str(source_format).strip().lower()
    if normalized not in SUPPORTED_SOURCE_FORMATS:
        raise ValueError(
            f"source_format must be one of {list(SUPPORTED_SOURCE_FORMATS)}, got {source_format!r}."
        )
    return normalized


def _detect_source_format(source_path: Path, source_format: str) -> str:
    normalized = _normalize_source_format(source_format)
    if normalized != "auto":
        return normalized
    suffix = source_path.suffix.strip().lower()
    if suffix == ".las":
        return "las"
    if suffix == ".dlis":
        return "dlis"
    raise TemplateValidationError(
        "Could not detect source_format from "
        f"{source_path.name!r}. Set source_format to 'las' or 'dlis' explicitly."
    )


def _load_dataset_from_source_path(
    source_path: str | Path,
    *,
    source_format: str = "auto",
    root: Path,
) -> tuple[WellDataset, Path, str]:
    resolved_source = _resolve_user_path(source_path, root=root, context="source_path")
    detected_format = _detect_source_format(resolved_source, source_format)
    if detected_format == "las":
        return load_las(resolved_source), resolved_source, detected_format
    if detected_format == "dlis":
        return load_dlis(resolved_source), resolved_source, detected_format
    raise RuntimeError(f"Unsupported source_format {detected_format!r}.")


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


def _normalized_logfile_mapping_from_text(
    yaml_text: str,
    *,
    base_dir: Path,
    root: Path,
) -> tuple[LogFileSpec, dict[str, object]]:
    spec = _load_validated_logfile_text_spec(yaml_text, base_dir=base_dir, root=root)
    return spec, report_to_dict(spec)


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


def _enum_values(enum_type: type[object]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for member in enum_type:  # type: ignore[operator]
        value = str(member.value)  # type: ignore[attr-defined]
        if value not in seen:
            seen.add(value)
            values.append(value)
    return values


def _normalize_channel_token(value: str) -> str:
    return "".join(character for character in str(value).upper() if character.isalnum())


def _safe_numeric_range(values: np.ndarray) -> tuple[float | None, float | None]:
    finite = np.asarray(values, dtype=float)[np.isfinite(values)]
    if finite.size == 0:
        return None, None
    return float(np.nanmin(finite)), float(np.nanmax(finite))


def _normalized_depth_unit_text(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text.lower() or None


def _masked_channel_values(channel: ScalarChannel | ArrayChannel | RasterChannel) -> np.ndarray:
    if isinstance(channel, ScalarChannel):
        return channel.masked_values()
    masked = np.asarray(channel.values, dtype=float).copy()
    if channel.null_value is not None:
        masked[np.isclose(masked, channel.null_value, equal_nan=False)] = np.nan
    return masked


def _channel_kind(channel: ScalarChannel | ArrayChannel | RasterChannel) -> str:
    if isinstance(channel, RasterChannel):
        return "raster"
    if isinstance(channel, ArrayChannel):
        return "array"
    return "scalar"


def _same_depth_axis(
    left: ScalarChannel | ArrayChannel | RasterChannel,
    right: ScalarChannel | ArrayChannel | RasterChannel,
) -> bool:
    if left.depth_unit != right.depth_unit:
        return False
    if left.depth.shape != right.depth.shape:
        return False
    return bool(np.allclose(left.depth, right.depth, equal_nan=True))


def _dataset_index_summary(dataset: WellDataset) -> DataSourceIndexSummary:
    channels = list(dataset.channels.values())
    if not channels:
        return DataSourceIndexSummary(
            depth_unit=None,
            depth_min=None,
            depth_max=None,
            sample_count=None,
            shared_axis=False,
        )

    first = channels[0]
    shared_axis = all(_same_depth_axis(first, channel) for channel in channels[1:])
    common_unit = (
        _normalized_depth_unit_text(first.depth_unit)
        if all(channel.depth_unit == first.depth_unit for channel in channels)
        else None
    )
    depth_min = min(channel.depth_min for channel in channels)
    depth_max = max(channel.depth_max for channel in channels)
    sample_count = int(first.depth.shape[0]) if shared_axis else None
    return DataSourceIndexSummary(
        depth_unit=common_unit,
        depth_min=float(depth_min),
        depth_max=float(depth_max),
        sample_count=sample_count,
        shared_axis=shared_axis,
    )


def _channel_summary(
    channel: ScalarChannel | ArrayChannel | RasterChannel,
) -> DataSourceChannelSummary:
    masked_values = _masked_channel_values(channel)
    value_min, value_max = _safe_numeric_range(masked_values)
    sample_axis_count: int | None = None
    sample_unit: str | None = None
    sample_label: str | None = None
    if isinstance(channel, ArrayChannel):
        sample_axis_count = int(channel.sample_axis.shape[0])
        sample_unit = channel.sample_unit
        sample_label = channel.sample_label
    return DataSourceChannelSummary(
        mnemonic=channel.mnemonic,
        kind=_channel_kind(channel),
        depth_unit=_normalized_depth_unit_text(channel.depth_unit) or channel.depth_unit,
        depth_min=channel.depth_min,
        depth_max=channel.depth_max,
        sample_count=int(channel.depth.shape[0]),
        value_unit=channel.value_unit,
        description=channel.description,
        value_shape=list(np.asarray(channel.values).shape),
        value_min=value_min,
        value_max=value_max,
        sample_axis_count=sample_axis_count,
        sample_unit=_normalized_depth_unit_text(sample_unit),
        sample_label=sample_label,
        metadata_keys=sorted(str(key) for key in channel.metadata),
    )


def _channel_alias_catalog() -> list[dict[str, object]]:
    return deepcopy(list(AUTHORING_CHANNEL_ALIASES))


def _matching_channel_alias_entry(requested_channel: str) -> dict[str, object] | None:
    normalized_request = _normalize_channel_token(requested_channel)
    for entry in AUTHORING_CHANNEL_ALIASES:
        lookup_terms = [
            entry["id"],
            entry["label"],
            *list(entry["aliases"]),
            *list(entry["mnemonics"]),
        ]
        if normalized_request in {_normalize_channel_token(str(term)) for term in lookup_terms}:
            return deepcopy(dict(entry))
    return None


def _channel_suggestions(
    requested_channel: str,
    available_channels: list[str],
    *,
    limit: int = 3,
) -> list[str]:
    normalized_request = _normalize_channel_token(requested_channel)
    scored: list[tuple[float, str]] = []
    for channel in available_channels:
        score = SequenceMatcher(
            a=normalized_request,
            b=_normalize_channel_token(channel),
            autojunk=False,
        ).ratio()
        if score >= 0.45:
            scored.append((score, channel))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [channel for _score, channel in scored[:limit]]


def _logfile_channel_target(
    logfile_path: str | Path,
    *,
    section_id: str | None,
    root: Path,
) -> tuple[WellDataset, Path, str, Path, str, list[str]]:
    resolved_logfile = _resolve_user_path(logfile_path, root=root, context="logfile_path")
    spec = load_logfile(resolved_logfile, allowed_root=root)
    section_ids = _section_ids_from_spec(spec)
    if not section_ids:
        raise TemplateValidationError("Logfile does not define any log sections.")

    resolved_section_id = section_id
    warnings: list[str] = []
    if resolved_section_id is None:
        if len(section_ids) == 1:
            resolved_section_id = section_ids[0]
        else:
            resolved_sources = resolve_section_data_sources_for_logfile(
                spec,
                base_dir=resolved_logfile.parent,
                allowed_root=root,
            )
            unique_sources = {
                (str(path), source_format) for path, source_format in resolved_sources.values()
            }
            if len(unique_sources) != 1:
                raise ValueError(
                    "section_id is required when logfile_path resolves multiple section "
                    "data sources."
                )
            resolved_section_id = section_ids[0]
            warnings.append(
                "No section_id was provided. The logfile has multiple sections, but they "
                "share the same source, so the first section was used for availability checks."
            )
    assert resolved_section_id is not None
    _ensure_known_section(spec, resolved_section_id)

    datasets_by_section, _ = load_datasets_for_logfile(
        spec,
        base_dir=resolved_logfile.parent,
        allowed_root=root,
    )
    dataset = datasets_by_section.get(resolved_section_id)
    if dataset is None:
        raise TemplateValidationError(f"Missing dataset for section {resolved_section_id!r}.")
    resolved_sources = resolve_section_data_sources_for_logfile(
        spec,
        base_dir=resolved_logfile.parent,
        allowed_root=root,
    )
    source_path, source_format_detected = resolved_sources[resolved_section_id]
    return (
        dataset,
        source_path,
        source_format_detected,
        resolved_logfile,
        resolved_section_id,
        warnings,
    )


def _heading_general_field_keys_from_layout(layout: dict[str, object]) -> list[str]:
    heading = layout.get("heading")
    if not isinstance(heading, dict):
        return []
    general_fields = heading.get("general_fields")
    if not isinstance(general_fields, list):
        return []
    keys: list[str] = []
    for entry in general_fields:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("key", "")).strip()
        if key and key not in keys:
            keys.append(key)
    return keys


def _raw_yaml_mapping_from_path(path: Path) -> dict[str, object]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TemplateValidationError(f"Expected a mapping at {path}.")
    return payload


def _section_track_ids_from_mapping(mapping: dict[str, object]) -> dict[str, list[str]]:
    track_ids_by_section: dict[str, list[str]] = {}
    for section in _logfile_mapping_sections(mapping):
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("id", "")).strip()
        if not section_id:
            continue
        tracks = _logfile_mapping_section_tracks(section, section_id=section_id)
        track_ids_by_section[section_id] = [
            str(track.get("id", ""))
            for track in tracks
            if isinstance(track, dict) and str(track.get("id", "")).strip()
        ]
    return track_ids_by_section


def _reordered_track_ids(previous_ids: list[str], current_ids: list[str]) -> list[str]:
    reordered: list[str] = []
    matcher = SequenceMatcher(a=previous_ids, b=current_ids, autojunk=False)
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        for track_id in current_ids[j1:j2]:
            if track_id in previous_ids and track_id not in reordered:
                reordered.append(track_id)
    return reordered


def _curve_bindings_by_key(spec: LogFileSpec) -> dict[tuple[str, str, str], dict[str, object]]:
    bindings = dict(spec.document.get("bindings", {})).get("channels", [])
    if not isinstance(bindings, list):
        return {}
    mapping: dict[tuple[str, str, str], dict[str, object]] = {}
    for binding in bindings:
        if not isinstance(binding, dict):
            continue
        if str(binding.get("kind", "curve")).strip().lower() != "curve":
            continue
        section_id = _binding_target_section_id(spec, binding)
        if section_id is None:
            continue
        track_id = str(binding.get("track_id", "")).strip()
        channel = str(binding.get("channel", "")).strip()
        if not track_id or not channel:
            continue
        mapping[(section_id, track_id, channel.upper())] = deepcopy(binding)
    return mapping


def _binding_ref(section_id: str, track_id: str, channel: str) -> dict[str, str]:
    return {
        "section_id": section_id,
        "track_id": track_id,
        "channel": channel,
    }


def _authoring_patch_schema() -> dict[str, object]:
    return {
        "heading_patch_keys": list(AUTHORING_HEADING_PATCH_KEYS),
        "curve_binding_patch_keys": list(AUTHORING_CURVE_BINDING_PATCH_KEYS),
        "move_track_target_selectors": list(AUTHORING_MOVE_TRACK_SELECTORS),
        "remarks_entry_fields": ["title", "lines", "alignment"],
    }


def _heading_field_catalog() -> dict[str, object]:
    general_field_keys: list[str] = []
    for example_id in PRODUCTION_EXAMPLE_IDS:
        template_mapping = yaml.safe_load(
            read_production_example_text(example_id, "base.template.yaml")
        )
        if not isinstance(template_mapping, dict):
            continue
        try:
            layout = _logfile_mapping_layout(template_mapping)
        except TemplateValidationError:
            continue
        for key in _heading_general_field_keys_from_layout(layout):
            if key not in general_field_keys:
                general_field_keys.append(key)
    return {
        "provider_fields": ["provider_name"],
        "general_field_keys": general_field_keys,
        "service_title_fields": [
            "value",
            "font_size",
            "auto_adjust",
            "bold",
            "italic",
            "alignment",
        ],
        "detail_kinds": _enum_values(ReportDetailKind),
        "detail_row_shapes": [
            "label + values",
            "label_cells + columns.cells",
        ],
        "remarks_fields": ["title", "lines", "alignment"],
    }


def _header_key_alias_catalog() -> dict[str, object]:
    return {
        "provider_aliases": ["provider_name", "provider"],
        "general_field_prefixes": ["general_field.<key>", "field.<key>"],
        "service_title_patterns": ["service_title_<1-based-index>", "title_<1-based-index>"],
        "detail_prefixes": ["detail.<row label>", "detail.row_<row-index>.col_<column-index>"],
        "overwrite_policies": list(AUTHORING_HEADER_OVERWRITE_POLICIES),
        "notes": [
            "General fields match by canonical key and visible label text.",
            "Detail rows match by label text when one target cell can be identified.",
            "When a label matches multiple slots, use an explicit prefixed key to disambiguate.",
        ],
    }


def _normalize_header_lookup(value: object) -> str:
    return _normalize_channel_token(str(value))


def _coerce_header_assignment_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        text = str(value).strip()
        return text or None
    return None


def _header_value_text(value: object) -> str | None:
    if isinstance(value, dict):
        for key in ("value", "default", "source_key"):
            text = _coerce_header_assignment_value(value.get(key))
            if text is not None:
                return text
        return None
    return _coerce_header_assignment_value(value)


def _heading_value_slot_mode(value: object) -> str:
    return str(_report_value_slot(value, slot_path=None)["mode"])


def _header_slot_is_filled(mode: str, current_value: str | None) -> bool:
    return mode in {"literal", "mixed"} and current_value not in (None, "")


def _normalize_key_value_format_hint(format_hint: str | None) -> str:
    normalized = str(format_hint or "auto").strip().lower().replace("-", "_")
    aliases = {
        "auto": "auto",
        "colon": "colon",
        "equals": "equals",
        "equal": "equals",
        "tsv": "tsv",
        "tab": "tsv",
        "tab_separated": "tsv",
        "csv": "csv",
        "comma": "csv",
        "comma_separated": "csv",
    }
    try:
        return aliases[normalized]
    except KeyError as exc:
        raise ValueError(
            f"format_hint must be one of {list(SUPPORTED_KEY_VALUE_FORMAT_HINTS)}."
        ) from exc


def _header_slot_lookup_keys(*values: object) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _coerce_header_assignment_value(value)
        if text is None:
            continue
        lookup = _normalize_header_lookup(text)
        if not lookup or lookup in seen:
            continue
        seen.add(lookup)
        normalized.append(lookup)
    return normalized


def _heading_target_descriptors(
    heading: dict[str, object],
    *,
    slot_prefix: str,
) -> list[_HeaderAssignmentTarget]:
    targets: list[_HeaderAssignmentTarget] = [
        _HeaderAssignmentTarget(
            target_kind="provider",
            target_key="provider_name",
            display_label="Provider Name",
            slot_path=f"{slot_prefix}.provider_name",
            lookup_keys=_header_slot_lookup_keys("provider_name", "provider"),
            current_mode="literal"
            if _coerce_header_assignment_value(heading.get("provider_name")) is not None
            else "empty",
            current_value=_coerce_header_assignment_value(heading.get("provider_name")),
        )
    ]

    general_fields = heading.get("general_fields")
    if isinstance(general_fields, list):
        for index, item in enumerate(general_fields):
            if not isinstance(item, dict):
                continue
            if "value" in item:
                slot_value: object = item.get("value")
            else:
                slot_value = {key: item[key] for key in ("source_key", "default") if key in item}
            key = str(item.get("key", "")).strip()
            label = str(item.get("label", key)).strip()
            targets.append(
                _HeaderAssignmentTarget(
                    target_kind="general_field",
                    target_key=key,
                    display_label=label or key,
                    slot_path=f"{slot_prefix}.general_fields[{index}].value",
                    lookup_keys=_header_slot_lookup_keys(
                        key,
                        label,
                        f"general_field.{key}",
                        f"field.{key}",
                    ),
                    current_mode=_heading_value_slot_mode(slot_value),
                    current_value=_header_value_text(slot_value),
                    general_field_index=index,
                )
            )

    service_titles = heading.get("service_titles")
    if isinstance(service_titles, list):
        for index, item in enumerate(service_titles):
            slot_value: object = item if isinstance(item, dict) else item
            targets.append(
                _HeaderAssignmentTarget(
                    target_kind="service_title",
                    target_key=f"service_title_{index + 1}",
                    display_label=f"Service Title {index + 1}",
                    slot_path=f"{slot_prefix}.service_titles[{index}].value",
                    lookup_keys=_header_slot_lookup_keys(
                        f"service_title_{index + 1}",
                        f"title_{index + 1}",
                    ),
                    current_mode=_heading_value_slot_mode(slot_value),
                    current_value=_header_value_text(slot_value),
                    service_title_index=index,
                )
            )

    detail = heading.get("detail")
    if not isinstance(detail, dict):
        return targets

    rows = detail.get("rows")
    if not isinstance(rows, list):
        return targets

    for row_index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue

        label_cells = row.get("label_cells")
        columns = row.get("columns")
        if isinstance(label_cells, list) and isinstance(columns, list):
            for column_index, label_value in enumerate(label_cells):
                if column_index >= len(columns):
                    continue
                column = columns[column_index]
                if not isinstance(column, dict):
                    continue
                cells = column.get("cells")
                if not isinstance(cells, list) or not cells:
                    continue
                label_text = _header_value_text(label_value)
                if label_text is None:
                    continue
                cell_value = cells[0]
                targets.append(
                    _HeaderAssignmentTarget(
                        target_kind="detail_field",
                        target_key=label_text,
                        display_label=label_text,
                        slot_path=(
                            f"{slot_prefix}.detail.rows[{row_index}].columns[{column_index}]"
                            ".cells[0]"
                        ),
                        lookup_keys=_header_slot_lookup_keys(
                            label_text,
                            f"detail.{label_text}",
                            f"detail.row_{row_index + 1}.col_{column_index + 1}",
                        ),
                        current_mode=_heading_value_slot_mode(cell_value),
                        current_value=_header_value_text(cell_value),
                        detail_row_index=row_index,
                        detail_column_index=column_index,
                        detail_cell_index=0,
                    )
                )
            continue

        label_text = _header_value_text(row.get("label"))
        if label_text is None:
            continue
        values = row.get("values")
        if isinstance(values, list) and values:
            cell_value = values[0]
            targets.append(
                _HeaderAssignmentTarget(
                    target_kind="detail_field",
                    target_key=label_text,
                    display_label=label_text,
                    slot_path=f"{slot_prefix}.detail.rows[{row_index}].values[0]",
                    lookup_keys=_header_slot_lookup_keys(
                        label_text,
                        f"detail.{label_text}",
                        f"detail.row_{row_index + 1}.col_1",
                    ),
                    current_mode=_heading_value_slot_mode(cell_value),
                    current_value=_header_value_text(cell_value),
                    detail_row_index=row_index,
                    detail_column_index=0,
                    detail_cell_index=0,
                    detail_uses_values=True,
                )
            )
            continue
        if isinstance(columns, list) and columns:
            column = columns[0]
            if not isinstance(column, dict):
                continue
            cells = column.get("cells")
            if not isinstance(cells, list) or not cells:
                continue
            cell_value = cells[0]
            targets.append(
                _HeaderAssignmentTarget(
                    target_kind="detail_field",
                    target_key=label_text,
                    display_label=label_text,
                    slot_path=f"{slot_prefix}.detail.rows[{row_index}].columns[0].cells[0]",
                    lookup_keys=_header_slot_lookup_keys(
                        label_text,
                        f"detail.{label_text}",
                        f"detail.row_{row_index + 1}.col_1",
                    ),
                    current_mode=_heading_value_slot_mode(cell_value),
                    current_value=_header_value_text(cell_value),
                    detail_row_index=row_index,
                    detail_column_index=0,
                    detail_cell_index=0,
                )
            )
    return targets


def _apply_header_target_value(
    heading: dict[str, object],
    target: _HeaderAssignmentTarget,
    value: str,
) -> None:
    if target.target_kind == "provider":
        heading["provider_name"] = value
        return

    if target.target_kind == "general_field":
        fields = heading.get("general_fields")
        assert isinstance(fields, list)
        assert target.general_field_index is not None
        item = fields[target.general_field_index]
        assert isinstance(item, dict)
        item["value"] = value
        item.pop("source_key", None)
        item.pop("default", None)
        return

    if target.target_kind == "service_title":
        titles = heading.get("service_titles")
        assert isinstance(titles, list)
        assert target.service_title_index is not None
        item = titles[target.service_title_index]
        if isinstance(item, dict):
            item["value"] = value
        else:
            titles[target.service_title_index] = {"value": value}
        return

    if target.target_kind != "detail_field":
        raise RuntimeError(f"Unsupported heading target kind {target.target_kind!r}.")

    detail = heading.get("detail")
    assert isinstance(detail, dict)
    rows = detail.get("rows")
    assert isinstance(rows, list)
    assert target.detail_row_index is not None
    row = rows[target.detail_row_index]
    assert isinstance(row, dict)
    assert target.detail_column_index is not None
    if target.detail_uses_values:
        values = row.get("values")
        assert isinstance(values, list)
        values[target.detail_column_index] = value
        return

    columns = row.get("columns")
    assert isinstance(columns, list)
    column = columns[target.detail_column_index]
    assert isinstance(column, dict)
    cells = column.get("cells")
    assert isinstance(cells, list)
    assert target.detail_cell_index is not None
    cells[target.detail_cell_index] = value


def _predicted_heading_patch(
    current_heading: dict[str, object],
    updated_heading: dict[str, object],
) -> dict[str, object]:
    patch: dict[str, object] = {}
    for key in (
        "enabled",
        "provider_name",
        "general_fields",
        "service_titles",
        "detail",
        "tail_enabled",
    ):
        if current_heading.get(key) != updated_heading.get(key):
            patch[key] = deepcopy(updated_heading.get(key))
    return patch


def _parseable_key_value_lines(
    source_text: str,
) -> list[tuple[int, str, str]]:
    lines: list[tuple[int, str, str]] = []
    for line_number, raw_line in enumerate(source_text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append((line_number, raw_line, stripped))
    return lines


def _parse_separator_key_value_lines(
    source_text: str,
    *,
    separator: str,
    format_name: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    pairs: list[dict[str, object]] = []
    unparsed_lines: list[dict[str, object]] = []
    for line_number, raw_line, _stripped in _parseable_key_value_lines(source_text):
        if separator not in raw_line:
            unparsed_lines.append(
                {
                    "line_number": line_number,
                    "text": raw_line,
                    "reason": f"Expected `{format_name}` key-value syntax.",
                }
            )
            continue
        key_text, value_text = raw_line.split(separator, 1)
        key = key_text.strip()
        if not key:
            unparsed_lines.append(
                {
                    "line_number": line_number,
                    "text": raw_line,
                    "reason": "Key text cannot be empty.",
                }
            )
            continue
        pairs.append(
            {
                "key": key,
                "value": value_text.strip(),
                "line_number": line_number,
            }
        )
    return pairs, unparsed_lines


def _parse_table_key_value_lines(
    source_text: str,
    *,
    delimiter: str,
    format_name: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    pairs: list[dict[str, object]] = []
    unparsed_lines: list[dict[str, object]] = []
    for line_number, raw_line, _stripped in _parseable_key_value_lines(source_text):
        try:
            row = next(csv.reader([raw_line], delimiter=delimiter))
        except csv.Error as exc:
            unparsed_lines.append(
                {
                    "line_number": line_number,
                    "text": raw_line,
                    "reason": f"{format_name.upper()} parse error: {exc}",
                }
            )
            continue
        if len(row) != 2:
            unparsed_lines.append(
                {
                    "line_number": line_number,
                    "text": raw_line,
                    "reason": f"Expected exactly two {format_name.upper()} columns.",
                }
            )
            continue
        key = row[0].strip()
        if not key:
            unparsed_lines.append(
                {
                    "line_number": line_number,
                    "text": raw_line,
                    "reason": "Key text cannot be empty.",
                }
            )
            continue
        pairs.append(
            {
                "key": key,
                "value": row[1].strip(),
                "line_number": line_number,
            }
        )
    return pairs, unparsed_lines


def _parse_key_value_text_with_format(
    source_text: str,
    *,
    format_name: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    if format_name == "colon":
        return _parse_separator_key_value_lines(
            source_text,
            separator=":",
            format_name=format_name,
        )
    if format_name == "equals":
        return _parse_separator_key_value_lines(
            source_text,
            separator="=",
            format_name=format_name,
        )
    if format_name == "tsv":
        return _parse_table_key_value_lines(
            source_text,
            delimiter="\t",
            format_name=format_name,
        )
    if format_name == "csv":
        return _parse_table_key_value_lines(
            source_text,
            delimiter=",",
            format_name=format_name,
        )
    raise ValueError(f"Unsupported key-value format {format_name!r}.")


def _report_value_slot(
    data: object,
    *,
    slot_path: str | None,
) -> dict[str, object]:
    value_mapping: dict[str, object] = {}
    if isinstance(data, dict):
        value = data.get("value")
        source_key = data.get("source_key")
        default = data.get("default")
        if value not in (None, ""):
            value_mapping["value"] = str(value)
        if source_key not in (None, ""):
            value_mapping["source_key"] = str(source_key)
        if default not in (None, ""):
            value_mapping["default"] = str(default)
    elif data not in (None, ""):
        value_mapping["value"] = str(data)

    has_value = "value" in value_mapping
    has_source_key = "source_key" in value_mapping
    if has_value and has_source_key:
        mode = "mixed"
    elif has_source_key:
        mode = "dataset"
    elif has_value:
        mode = "literal"
    elif "default" in value_mapping:
        mode = "default_only"
    else:
        mode = "empty"

    return {
        "slot_path": slot_path,
        "mode": mode,
        **value_mapping,
    }


def _heading_provider_slots(
    heading: dict[str, object],
    *,
    slot_prefix: str,
) -> list[dict[str, object]]:
    return [
        {
            "key": "provider_name",
            "slot_path": f"{slot_prefix}.provider_name",
            "current_value": heading.get("provider_name"),
        }
    ]


def _heading_general_field_slots(
    heading: dict[str, object],
    *,
    slot_prefix: str,
    target_kind: str,
) -> list[dict[str, object]]:
    fields = heading.get("general_fields")
    slots: list[dict[str, object]] = []
    if isinstance(fields, list):
        for index, item in enumerate(fields):
            if not isinstance(item, dict):
                continue
            value_data: object
            if "value" in item:
                value_data = item.get("value")
            else:
                value_data = {key: item[key] for key in ("source_key", "default") if key in item}
            slots.append(
                {
                    "index": index,
                    "key": str(item.get("key", "")),
                    "label": str(item.get("label", "")),
                    "value_slot": _report_value_slot(
                        value_data,
                        slot_path=f"{slot_prefix}.general_fields[{index}].value",
                    ),
                }
            )
        return slots

    if target_kind == "catalog":
        for index, key in enumerate(_heading_field_catalog()["general_field_keys"]):
            slots.append(
                {
                    "index": index,
                    "key": key,
                    "label": str(key).replace("_", " ").title(),
                    "value_slot": _report_value_slot(
                        None,
                        slot_path=None,
                    ),
                }
            )
    return slots


def _heading_service_title_slots(
    heading: dict[str, object],
    *,
    slot_prefix: str,
    target_kind: str,
) -> list[dict[str, object]]:
    titles = heading.get("service_titles")
    slots: list[dict[str, object]] = []
    if isinstance(titles, list):
        for index, item in enumerate(titles):
            metadata: dict[str, object] = {
                "index": index,
                "value_slot": _report_value_slot(
                    item,
                    slot_path=f"{slot_prefix}.service_titles[{index}].value",
                ),
            }
            if isinstance(item, dict):
                for key in ("font_size", "auto_adjust", "bold", "italic", "alignment"):
                    if key in item:
                        metadata[key] = deepcopy(item[key])
            slots.append(metadata)
        return slots

    if target_kind == "catalog":
        slots.append(
            {
                "index": 0,
                "value_slot": _report_value_slot(None, slot_path=None),
                "auto_adjust": True,
                "bold": False,
                "italic": False,
                "alignment": "left",
            }
        )
    return slots


def _detail_row_slot(row: object, *, row_index: int, slot_prefix: str) -> dict[str, object]:
    if not isinstance(row, dict):
        return {
            "row_index": row_index,
            "label_slots": [],
            "column_slots": [],
        }

    label_slots: list[dict[str, object]] = []
    label_cells = row.get("label_cells")
    if isinstance(label_cells, list):
        for index, item in enumerate(label_cells):
            label_slots.append(
                _report_value_slot(
                    item,
                    slot_path=f"{slot_prefix}.rows[{row_index}].label_cells[{index}]",
                )
            )
    elif "label" in row:
        label_slots.append(
            _report_value_slot(
                row.get("label"),
                slot_path=f"{slot_prefix}.rows[{row_index}].label",
            )
        )

    column_slots: list[list[dict[str, object]]] = []
    columns = row.get("columns")
    if isinstance(columns, list):
        for column_index, column in enumerate(columns):
            if not isinstance(column, dict):
                continue
            cells = column.get("cells")
            if not isinstance(cells, list):
                continue
            column_slots.append(
                [
                    _report_value_slot(
                        cell,
                        slot_path=(
                            f"{slot_prefix}.rows[{row_index}].columns[{column_index}].cells"
                            f"[{cell_index}]"
                        ),
                    )
                    for cell_index, cell in enumerate(cells)
                ]
            )
    else:
        values = row.get("values")
        if isinstance(values, list):
            for column_index, value in enumerate(values):
                column_slots.append(
                    [
                        _report_value_slot(
                            value,
                            slot_path=f"{slot_prefix}.rows[{row_index}].values[{column_index}]",
                        )
                    ]
                )

    return {
        "row_index": row_index,
        "label_slots": label_slots,
        "column_slots": column_slots,
    }


def _heading_detail_slots(heading: dict[str, object], *, slot_prefix: str) -> dict[str, object]:
    detail = heading.get("detail")
    if not isinstance(detail, dict):
        return {
            "enabled": False,
            "detail_kinds": _enum_values(ReportDetailKind),
            "rows": [],
        }

    rows = detail.get("rows")
    row_slots = []
    if isinstance(rows, list):
        row_slots = [
            _detail_row_slot(item, row_index=index, slot_prefix=f"{slot_prefix}.detail")
            for index, item in enumerate(rows)
        ]
    return {
        "enabled": True,
        "kind": detail.get("kind"),
        "title": detail.get("title"),
        "column_titles": deepcopy(list(detail.get("column_titles", [])))
        if isinstance(detail.get("column_titles"), list)
        else [],
        "row_count": len(row_slots),
        "rows": row_slots,
        "detail_kinds": _enum_values(ReportDetailKind),
    }


def _remarks_capabilities(layout: dict[str, object]) -> dict[str, object]:
    remarks = layout.get("remarks")
    remark_blocks = remarks if isinstance(remarks, list) else []
    return {
        "supports_title": True,
        "supports_lines": True,
        "supports_alignment": True,
        "alignment_values": ["left", "center", "right"],
        "entry_fields": ["title", "lines", "alignment"],
        "existing_block_count": len(remark_blocks),
    }


def _heading_slot_resource_uris() -> list[str]:
    return [
        "wellplot://authoring/catalog/header-fields.json",
        "wellplot://authoring/catalog/header-key-aliases.json",
        "wellplot://authoring/schema/patch.json",
    ]


def _track_archetypes_catalog() -> list[dict[str, object]]:
    return deepcopy(list(AUTHORING_TRACK_ARCHETYPES))


def _style_presets_catalog() -> list[dict[str, object]]:
    return deepcopy(list(AUTHORING_STYLE_PRESETS))


def _style_preset_families() -> list[str]:
    families: list[str] = []
    for preset in AUTHORING_STYLE_PRESETS:
        family = str(preset.get("family", "")).strip()
        if family and family not in families:
            families.append(family)
    return families


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


def authoring_patch_schema_resource() -> ResourceContent:
    """Return the draft-authoring patch contract as JSON text."""
    payload = json.dumps(_authoring_patch_schema(), indent=2, sort_keys=True)
    return ResourceContent(text=payload, mime_type="application/json")


def authoring_track_kinds_resource() -> ResourceContent:
    """Return supported draft-authoring track kinds as JSON text."""
    payload = json.dumps({"track_kinds": _enum_values(TrackKind)}, indent=2, sort_keys=True)
    return ResourceContent(text=payload, mime_type="application/json")


def authoring_fill_kinds_resource() -> ResourceContent:
    """Return supported curve-fill kinds as JSON text."""
    payload = json.dumps(
        {
            "curve_fill_kinds": _enum_values(CurveFillKind),
            "scale_kinds": _enum_values(ScaleKind),
        },
        indent=2,
        sort_keys=True,
    )
    return ResourceContent(text=payload, mime_type="application/json")


def authoring_track_archetypes_resource() -> ResourceContent:
    """Return curated draft-authoring track archetypes as JSON text."""
    payload = json.dumps(
        {"track_archetypes": _track_archetypes_catalog()},
        indent=2,
        sort_keys=True,
    )
    return ResourceContent(text=payload, mime_type="application/json")


def authoring_header_fields_resource() -> ResourceContent:
    """Return heading and remarks field guidance as JSON text."""
    payload = json.dumps(_heading_field_catalog(), indent=2, sort_keys=True)
    return ResourceContent(text=payload, mime_type="application/json")


def authoring_style_presets_resource() -> ResourceContent:
    """Return curated draft-authoring style presets as JSON text."""
    payload = json.dumps(
        {
            "available_families": _style_preset_families(),
            "style_presets": _style_presets_catalog(),
        },
        indent=2,
        sort_keys=True,
    )
    return ResourceContent(text=payload, mime_type="application/json")


def authoring_header_key_aliases_resource() -> ResourceContent:
    """Return deterministic header-slot lookup guidance as JSON text."""
    payload = json.dumps(_header_key_alias_catalog(), indent=2, sort_keys=True)
    return ResourceContent(text=payload, mime_type="application/json")


def authoring_channel_aliases_resource() -> ResourceContent:
    """Return curated channel-alias guidance as JSON text."""
    payload = json.dumps(
        {"channel_aliases": _channel_alias_catalog()},
        indent=2,
        sort_keys=True,
    )
    return ResourceContent(text=payload, mime_type="application/json")


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


def inspect_data_source(
    source_path: str,
    *,
    source_format: str = "auto",
    root: str | Path | None = None,
) -> DataSourceInspectionResult:
    """Inspect one raw LAS/DLIS source before draft authoring begins."""
    server_root = resolve_server_root(root)
    dataset, resolved_source, detected_format = _load_dataset_from_source_path(
        source_path,
        source_format=source_format,
        root=server_root,
    )
    channel_summaries = [_channel_summary(channel) for channel in dataset.channels.values()]
    return DataSourceInspectionResult(
        source_path=str(resolved_source),
        source_format_detected=detected_format,
        dataset_name=dataset.name,
        index=_dataset_index_summary(dataset),
        channel_count=len(channel_summaries),
        channels=channel_summaries,
        metadata_keys=sorted(str(key) for key in dataset.well_metadata),
        well_metadata=deepcopy(dataset.well_metadata),
        provenance=deepcopy(dataset.provenance),
        warnings=[],
    )


def check_channel_availability(
    requested_channels: list[str],
    *,
    source_path: str | None = None,
    logfile_path: str | None = None,
    section_id: str | None = None,
    source_format: str = "auto",
    root: str | Path | None = None,
) -> ChannelAvailabilityResult:
    """Resolve requested channel names or aliases against one source or logfile section."""
    if not requested_channels:
        raise ValueError("requested_channels must contain at least one channel name.")
    if (source_path is None) == (logfile_path is None):
        raise ValueError("Provide exactly one of source_path or logfile_path.")
    if source_path is not None and section_id is not None:
        raise ValueError("section_id is only supported when checking logfile_path targets.")

    server_root = resolve_server_root(root)
    warnings: list[str] = []
    if source_path is not None:
        dataset, resolved_source, detected_format = _load_dataset_from_source_path(
            source_path,
            source_format=source_format,
            root=server_root,
        )
        target_kind = "source"
        resolved_logfile_path: str | None = None
        resolved_section_id: str | None = None
    else:
        (
            dataset,
            resolved_source,
            detected_format,
            resolved_logfile,
            resolved_section_id,
            target_warnings,
        ) = _logfile_channel_target(
            logfile_path,
            section_id=section_id,
            root=server_root,
        )
        warnings.extend(target_warnings)
        target_kind = "logfile"
        resolved_logfile_path = str(resolved_logfile)

    available_channels = list(dataset.channels)
    available_by_token: dict[str, list[str]] = {}
    for channel in available_channels:
        available_by_token.setdefault(_normalize_channel_token(channel), []).append(channel)

    found_channels: list[str] = []
    missing_channels: list[str] = []
    alias_matches: list[dict[str, object]] = []
    ambiguous_matches: list[dict[str, object]] = []
    resolutions: list[RequestedChannelResolution] = []

    for requested_channel in requested_channels:
        exact_matches = list(
            available_by_token.get(_normalize_channel_token(requested_channel), [])
        )
        if len(exact_matches) == 1:
            matched_channel = exact_matches[0]
            if matched_channel not in found_channels:
                found_channels.append(matched_channel)
            resolutions.append(
                RequestedChannelResolution(
                    requested_channel=requested_channel,
                    status="exact",
                    matched_channels=exact_matches,
                    canonical_alias_id=None,
                    matched_alias=None,
                    suggested_channels=[],
                )
            )
            continue

        alias_entry = _matching_channel_alias_entry(requested_channel)
        if alias_entry is not None:
            alias_mnemonics = {
                _normalize_channel_token(str(value))
                for value in alias_entry.get("mnemonics", [])
                if str(value).strip()
            }
            alias_channel_matches = [
                channel
                for channel in available_channels
                if _normalize_channel_token(channel) in alias_mnemonics
            ]
            if len(alias_channel_matches) == 1:
                matched_channel = alias_channel_matches[0]
                if matched_channel not in found_channels:
                    found_channels.append(matched_channel)
                alias_matches.append(
                    {
                        "requested_channel": requested_channel,
                        "canonical_alias_id": alias_entry["id"],
                        "matched_channels": alias_channel_matches,
                    }
                )
                resolutions.append(
                    RequestedChannelResolution(
                        requested_channel=requested_channel,
                        status="alias",
                        matched_channels=alias_channel_matches,
                        canonical_alias_id=str(alias_entry["id"]),
                        matched_alias=str(alias_entry["label"]),
                        suggested_channels=[],
                    )
                )
                continue
            if len(alias_channel_matches) > 1:
                ambiguous_matches.append(
                    {
                        "requested_channel": requested_channel,
                        "canonical_alias_id": alias_entry["id"],
                        "matched_channels": alias_channel_matches,
                    }
                )
                warnings.append(
                    f"Requested channel {requested_channel!r} matched multiple available "
                    f"channels {alias_channel_matches}."
                )
                resolutions.append(
                    RequestedChannelResolution(
                        requested_channel=requested_channel,
                        status="ambiguous",
                        matched_channels=alias_channel_matches,
                        canonical_alias_id=str(alias_entry["id"]),
                        matched_alias=str(alias_entry["label"]),
                        suggested_channels=[],
                    )
                )
                continue

        suggestions = _channel_suggestions(requested_channel, available_channels)
        missing_channels.append(requested_channel)
        if suggestions:
            warnings.append(
                f"Requested channel {requested_channel!r} was not found. "
                f"Suggested channels: {suggestions}."
            )
        else:
            warnings.append(f"Requested channel {requested_channel!r} was not found.")
        resolutions.append(
            RequestedChannelResolution(
                requested_channel=requested_channel,
                status="missing",
                matched_channels=[],
                canonical_alias_id=None if alias_entry is None else str(alias_entry["id"]),
                matched_alias=None if alias_entry is None else str(alias_entry["label"]),
                suggested_channels=suggestions,
            )
        )

    return ChannelAvailabilityResult(
        target_kind=target_kind,
        source_path=str(resolved_source),
        source_format_detected=detected_format,
        logfile_path=resolved_logfile_path,
        section_id=resolved_section_id,
        requested_channels=list(requested_channels),
        available_channels=available_channels,
        found_channels=found_channels,
        missing_channels=missing_channels,
        alias_matches=alias_matches,
        ambiguous_matches=ambiguous_matches,
        resolutions=resolutions,
        warnings=warnings,
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


def inspect_heading_slots(
    *,
    logfile_path: str | None = None,
    template_path: str | None = None,
    root: str | Path | None = None,
) -> HeadingSlotsResult:
    """Inspect precise heading, detail-table, and remarks slots for one target."""
    if logfile_path is not None and template_path is not None:
        raise ValueError("Provide at most one of logfile_path or template_path.")

    server_root = resolve_server_root(root)
    target_kind = "catalog"
    target_path: str | None = None
    layout: dict[str, object] = {}
    if logfile_path is not None:
        target_kind = "logfile"
        resolved_logfile = _resolve_user_path(
            logfile_path,
            root=server_root,
            context="logfile_path",
        )
        _, mapping = _normalize_logfile_mapping_from_path(
            resolved_logfile,
            allowed_root=server_root,
        )
        layout = _logfile_mapping_layout(mapping)
        target_path = str(resolved_logfile)
    elif template_path is not None:
        target_kind = "template"
        resolved_template = _resolve_user_path(
            template_path,
            root=server_root,
            context="template_path",
        )
        layout = _logfile_mapping_layout(_raw_yaml_mapping_from_path(resolved_template))
        target_path = str(resolved_template)

    heading_raw = layout.get("heading")
    heading = dict(heading_raw) if isinstance(heading_raw, dict) else {}
    remarks_raw = layout.get("remarks")
    remarks = deepcopy(list(remarks_raw)) if isinstance(remarks_raw, list) else []
    tail_raw = layout.get("tail")
    tail = deepcopy(dict(tail_raw)) if isinstance(tail_raw, dict) else {}
    slot_prefix = "document.layout.heading"
    return HeadingSlotsResult(
        target_kind=target_kind,
        target_path=target_path,
        has_heading=bool(heading),
        has_remarks=bool(remarks),
        has_tail=_layout_has_tail(layout),
        provider_slots=_heading_provider_slots(heading, slot_prefix=slot_prefix),
        general_field_slots=_heading_general_field_slots(
            heading,
            slot_prefix=slot_prefix,
            target_kind=target_kind,
        ),
        service_title_slots=_heading_service_title_slots(
            heading,
            slot_prefix=slot_prefix,
            target_kind=target_kind,
        ),
        detail_slots=_heading_detail_slots(heading, slot_prefix=slot_prefix),
        remarks_capabilities=_remarks_capabilities(layout),
        current_values={
            "heading": deepcopy(heading),
            "remarks": remarks,
            "tail": tail,
        },
        resource_uris=_heading_slot_resource_uris(),
    )


def preview_header_mapping(
    logfile_path: str,
    *,
    values: dict[str, object],
    overwrite_policy: str = "fill_empty",
    root: str | Path | None = None,
) -> HeaderMappingPreviewResult:
    """Dry-run heading/report value assignment without mutating the draft logfile."""
    if overwrite_policy not in AUTHORING_HEADER_OVERWRITE_POLICIES:
        raise ValueError(
            f"overwrite_policy must be one of {list(AUTHORING_HEADER_OVERWRITE_POLICIES)}."
        )
    if not isinstance(values, dict):
        raise ValueError("values must be a mapping of extracted header keys to values.")

    server_root = resolve_server_root(root)
    resolved_logfile = _resolve_user_path(logfile_path, root=server_root, context="logfile_path")
    _, mapping = _normalize_logfile_mapping_from_path(
        resolved_logfile,
        allowed_root=server_root,
    )
    layout = _logfile_mapping_layout(mapping)
    current_heading_raw = layout.get("heading")
    current_heading = dict(current_heading_raw) if isinstance(current_heading_raw, dict) else {}
    predicted_heading = deepcopy(current_heading)
    targets = _heading_target_descriptors(predicted_heading, slot_prefix="document.layout.heading")
    targets_by_lookup: dict[str, list[_HeaderAssignmentTarget]] = {}
    for target in targets:
        for lookup_key in target.lookup_keys:
            targets_by_lookup.setdefault(lookup_key, []).append(target)

    warnings: list[str] = []
    if overwrite_policy == "merge_lists":
        warnings.append(
            "overwrite_policy='merge_lists' currently behaves like 'replace' for scalar "
            "heading and detail slots."
        )

    resolved_assignments: list[dict[str, object]] = []
    unmatched_values: list[dict[str, object]] = []
    conflicting_values: list[dict[str, object]] = []
    effective_policy = "replace" if overwrite_policy == "merge_lists" else overwrite_policy

    for input_key, raw_value in values.items():
        input_value = _coerce_header_assignment_value(raw_value)
        if input_value is None:
            unmatched_values.append(
                {
                    "input_key": str(input_key),
                    "input_value": raw_value,
                    "reason": "Unsupported value type. Use scalar string, number, or boolean data.",
                }
            )
            continue

        lookup_key = _normalize_header_lookup(input_key)
        matches = targets_by_lookup.get(lookup_key, [])
        if not matches:
            unmatched_values.append(
                {
                    "input_key": str(input_key),
                    "input_value": input_value,
                }
            )
            continue

        if len(matches) > 1:
            conflicting_values.append(
                {
                    "input_key": str(input_key),
                    "input_value": input_value,
                    "reason": "Ambiguous header key. Use an explicit prefixed key.",
                    "candidate_targets": [
                        {
                            "target_kind": match.target_kind,
                            "target_key": match.target_key,
                            "slot_path": match.slot_path,
                        }
                        for match in matches
                    ],
                }
            )
            continue

        target = matches[0]
        if target.current_value == input_value:
            resolved_assignments.append(
                {
                    "input_key": str(input_key),
                    "input_value": input_value,
                    "target_kind": target.target_kind,
                    "target_key": target.target_key,
                    "slot_path": target.slot_path,
                    "previous_mode": target.current_mode,
                    "previous_value": target.current_value,
                    "action": "unchanged",
                }
            )
            continue

        if effective_policy == "fill_empty" and _header_slot_is_filled(
            target.current_mode,
            target.current_value,
        ):
            conflicting_values.append(
                {
                    "input_key": str(input_key),
                    "input_value": input_value,
                    "target_kind": target.target_kind,
                    "target_key": target.target_key,
                    "slot_path": target.slot_path,
                    "existing_value": target.current_value,
                    "reason": "Target already has an explicit literal value.",
                }
            )
            continue

        action = "replace" if target.current_value not in (None, "") else "set"
        _apply_header_target_value(predicted_heading, target, input_value)
        resolved_assignments.append(
            {
                "input_key": str(input_key),
                "input_value": input_value,
                "target_kind": target.target_kind,
                "target_key": target.target_key,
                "slot_path": target.slot_path,
                "previous_mode": target.current_mode,
                "previous_value": target.current_value,
                "action": action,
            }
        )
        target.current_mode = "literal"
        target.current_value = input_value

    if not targets:
        warnings.append("The draft does not expose any heading slots that can receive values.")

    return HeaderMappingPreviewResult(
        logfile_path=str(resolved_logfile),
        overwrite_policy=overwrite_policy,
        resolved_assignments=resolved_assignments,
        unmatched_values=unmatched_values,
        conflicting_values=conflicting_values,
        warnings=warnings,
        predicted_heading_patch=_predicted_heading_patch(current_heading, predicted_heading),
    )


def _heading_summary_payload(slots: HeadingSlotsResult) -> dict[str, object]:
    return {
        "has_heading": slots.has_heading,
        "has_remarks": slots.has_remarks,
        "has_tail": slots.has_tail,
        "provider_slots": deepcopy(slots.provider_slots),
        "general_field_slots": deepcopy(slots.general_field_slots),
        "service_title_slots": deepcopy(slots.service_title_slots),
        "detail_slots": deepcopy(slots.detail_slots),
        "remarks_capabilities": deepcopy(slots.remarks_capabilities),
        "current_values": deepcopy(slots.current_values),
    }


def apply_header_values(
    logfile_path: str,
    *,
    values: dict[str, object],
    overwrite_policy: str = "fill_empty",
    root: str | Path | None = None,
) -> AppliedHeaderValuesResult:
    """Apply deterministic heading/report value assignment to a mutable draft logfile."""
    preview = preview_header_mapping(
        logfile_path,
        values=values,
        overwrite_policy=overwrite_policy,
        root=root,
    )
    warnings = list(preview.warnings)
    applied_assignments = [
        deepcopy(entry)
        for entry in preview.resolved_assignments
        if str(entry.get("action", "")).strip().lower() != "unchanged"
    ]
    skipped_assignments: list[dict[str, object]] = [
        {
            "input_key": str(entry.get("input_key", "")),
            "input_value": deepcopy(entry.get("input_value")),
            "status": "unchanged",
            "reason": "Target already contains the requested value.",
            "target_kind": entry.get("target_kind"),
            "target_key": entry.get("target_key"),
            "slot_path": entry.get("slot_path"),
        }
        for entry in preview.resolved_assignments
        if str(entry.get("action", "")).strip().lower() == "unchanged"
    ]
    skipped_assignments.extend(
        {
            "input_key": str(entry.get("input_key", "")),
            "input_value": deepcopy(entry.get("input_value")),
            "status": "unmatched",
            "reason": str(entry.get("reason", "No matching heading slot was found.")),
        }
        for entry in preview.unmatched_values
    )
    skipped_assignments.extend(
        {
            "input_key": str(entry.get("input_key", "")),
            "input_value": deepcopy(entry.get("input_value")),
            "status": "conflict",
            "reason": str(entry.get("reason", "The target could not be updated safely.")),
            "target_kind": entry.get("target_kind"),
            "target_key": entry.get("target_key"),
            "slot_path": entry.get("slot_path"),
            "existing_value": deepcopy(entry.get("existing_value")),
            "candidate_targets": deepcopy(entry.get("candidate_targets")),
        }
        for entry in preview.conflicting_values
    )

    if preview.predicted_heading_patch:
        set_heading_content(
            preview.logfile_path,
            patch=preview.predicted_heading_patch,
            root=root,
        )
    else:
        warnings.append("No header values were applied.")

    heading_slots = inspect_heading_slots(
        logfile_path=preview.logfile_path,
        root=root,
    )
    return AppliedHeaderValuesResult(
        logfile_path=preview.logfile_path,
        overwrite_policy=overwrite_policy,
        applied_assignments=applied_assignments,
        skipped_assignments=skipped_assignments,
        warnings=warnings,
        heading_summary=_heading_summary_payload(heading_slots),
    )


def parse_key_value_text(
    source_text: str,
    *,
    format_hint: str | None = None,
) -> ParsedKeyValueTextResult:
    """Parse a simple key-value text block into ordered pairs without slot mapping."""
    normalized_hint = _normalize_key_value_format_hint(format_hint)
    warnings: list[str] = []
    if normalized_hint == "auto":
        candidates = ["colon", "equals", "tsv", "csv"]
        ranked: list[
            tuple[int, int, int, str, list[dict[str, object]], list[dict[str, object]]]
        ] = []
        for rank, candidate in enumerate(candidates):
            pairs, unparsed_lines = _parse_key_value_text_with_format(
                source_text,
                format_name=candidate,
            )
            ranked.append(
                (len(pairs), -len(unparsed_lines), -rank, candidate, pairs, unparsed_lines)
            )
        best = max(ranked, key=lambda item: item[:3])
        pairs = best[4]
        unparsed_lines = best[5]
        if best[0] == 0:
            warnings.append("No supported key-value pattern was detected in the provided text.")
            return ParsedKeyValueTextResult(
                pairs=[],
                unparsed_lines=unparsed_lines,
                format_detected="unknown",
                warnings=warnings,
            )
        format_detected = best[3]
        if unparsed_lines:
            warnings.append(
                f"Auto-detected `{format_detected}` format, but {len(unparsed_lines)} "
                "non-empty lines were left unparsed."
            )
    else:
        format_detected = normalized_hint
        pairs, unparsed_lines = _parse_key_value_text_with_format(
            source_text,
            format_name=format_detected,
        )
        if unparsed_lines:
            warnings.append(
                f"{len(unparsed_lines)} non-empty lines did not match the requested "
                f"`{format_detected}` format."
            )

    normalized_keys: dict[str, int] = {}
    duplicate_keys: list[str] = []
    for pair in pairs:
        normalized_key = _normalize_header_lookup(pair["key"])
        pair["normalized_key"] = normalized_key
        count = normalized_keys.get(normalized_key, 0) + 1
        normalized_keys[normalized_key] = count
        if count == 2:
            duplicate_keys.append(str(pair["key"]))
    if duplicate_keys:
        warnings.append(
            "Duplicate keys were preserved in order: "
            + ", ".join(sorted(set(duplicate_keys), key=duplicate_keys.index))
            + "."
        )

    return ParsedKeyValueTextResult(
        pairs=pairs,
        unparsed_lines=unparsed_lines,
        format_detected=format_detected,
        warnings=warnings,
    )


def inspect_style_presets(
    *,
    preset_family: str | None = None,
) -> StylePresetsResult:
    """Return curated style presets, optionally filtered to one family."""
    available_families = _style_preset_families()
    selected_family = str(preset_family).strip() if preset_family is not None else None
    if selected_family is not None and selected_family not in available_families:
        raise ValueError(
            f"preset_family must be one of {available_families}, got {preset_family!r}."
        )
    presets = [
        preset
        for preset in _style_presets_catalog()
        if selected_family is None or str(preset.get("family", "")) == selected_family
    ]
    return StylePresetsResult(
        available_families=available_families,
        selected_family=selected_family,
        presets=presets,
        resource_uris=["wellplot://authoring/catalog/style-presets.json"],
    )


def inspect_authoring_vocab(
    *,
    logfile_path: str | None = None,
    template_path: str | None = None,
    root: str | Path | None = None,
) -> AuthoringVocabularyResult:
    """Return deterministic authoring vocabularies and optional target context."""
    if logfile_path is not None and template_path is not None:
        raise ValueError("Provide at most one of logfile_path or template_path.")

    server_root = resolve_server_root(root)
    target_summary: dict[str, object] | None = None
    if logfile_path is not None:
        resolved_logfile = _resolve_user_path(
            logfile_path, root=server_root, context="logfile_path"
        )
        summary = summarize_logfile_draft(str(resolved_logfile), root=server_root)
        _, mapping = _normalize_logfile_mapping_from_path(
            resolved_logfile,
            allowed_root=server_root,
        )
        layout = _logfile_mapping_layout(mapping)
        target_summary = {
            "target_kind": "logfile",
            "target_path": str(resolved_logfile),
            "section_ids": list(summary.section_ids),
            "track_ids_by_section": {
                section.id: list(section.track_ids) for section in summary.sections
            },
            "available_channels_by_section": {
                section.id: list(section.available_channels) for section in summary.sections
            },
            "dataset_loaded_by_section": {
                section.id: bool(section.dataset_loaded) for section in summary.sections
            },
            "heading_general_field_keys": _heading_general_field_keys_from_layout(layout),
            "has_heading": summary.has_heading,
            "has_remarks": summary.has_remarks,
            "has_tail": summary.has_tail,
        }
    elif template_path is not None:
        resolved_template = _resolve_user_path(
            template_path,
            root=server_root,
            context="template_path",
        )
        mapping = _raw_yaml_mapping_from_path(resolved_template)
        layout = _logfile_mapping_layout(mapping)
        target_summary = {
            "target_kind": "template",
            "target_path": str(resolved_template),
            "section_ids": list(_section_track_ids_from_mapping(mapping)),
            "track_ids_by_section": _section_track_ids_from_mapping(mapping),
            "heading_general_field_keys": _heading_general_field_keys_from_layout(layout),
            "has_heading": bool(layout.get("heading")),
            "has_remarks": bool(layout.get("remarks")),
            "has_tail": _layout_has_tail(layout),
        }

    return AuthoringVocabularyResult(
        track_kinds=_enum_values(TrackKind),
        scale_kinds=_enum_values(ScaleKind),
        curve_fill_kinds=_enum_values(CurveFillKind),
        report_detail_kinds=_enum_values(ReportDetailKind),
        track_header_object_kinds=_enum_values(TrackHeaderObjectKind),
        heading_patch_keys=list(AUTHORING_HEADING_PATCH_KEYS),
        curve_binding_patch_keys=list(AUTHORING_CURVE_BINDING_PATCH_KEYS),
        move_track_selectors=list(AUTHORING_MOVE_TRACK_SELECTORS),
        heading_field_catalog=_heading_field_catalog(),
        track_archetypes=_track_archetypes_catalog(),
        resource_uris=list(AUTHORING_RESOURCE_URIS),
        target_summary=target_summary,
    )


def summarize_logfile_changes(
    logfile_path: str,
    *,
    previous_text: str | None = None,
    root: str | Path | None = None,
) -> LogfileChangeSummaryResult:
    """Summarize structural draft changes relative to an optional previous YAML snapshot."""
    server_root = resolve_server_root(root)
    resolved_logfile = _resolve_user_path(
        logfile_path,
        root=server_root,
        context="logfile_path",
    )
    current_spec, current_mapping = _normalize_logfile_mapping_from_path(
        resolved_logfile,
        allowed_root=server_root,
    )
    current_section_ids = _section_ids_from_spec(current_spec)

    if previous_text is None:
        message = (
            "No previous_text snapshot was provided. Capture the draft text before edits "
            "if you want a structural change summary."
        )
        return LogfileChangeSummaryResult(
            logfile_path=str(resolved_logfile),
            changed=False,
            message=message,
            section_ids=current_section_ids,
            added_tracks_by_section={},
            removed_tracks_by_section={},
            reordered_tracks_by_section={},
            added_curve_bindings=[],
            removed_curve_bindings=[],
            updated_curve_bindings=[],
            heading_changed=False,
            remarks_changed=False,
            render_output_changed=False,
            summary_lines=[message],
        )

    previous_spec, previous_mapping = _normalized_logfile_mapping_from_text(
        previous_text,
        base_dir=resolved_logfile.parent,
        root=server_root,
    )

    previous_track_ids = {
        section_id: [
            str(track.get("id", ""))
            for track in list(section.get("tracks", []))
            if isinstance(track, dict)
        ]
        for section_id, section in _section_map_from_spec(previous_spec).items()
    }
    current_track_ids = {
        section_id: [
            str(track.get("id", ""))
            for track in list(section.get("tracks", []))
            if isinstance(track, dict)
        ]
        for section_id, section in _section_map_from_spec(current_spec).items()
    }
    section_union = sorted(set(previous_track_ids) | set(current_track_ids))

    added_tracks_by_section: dict[str, list[str]] = {}
    removed_tracks_by_section: dict[str, list[str]] = {}
    reordered_tracks_by_section: dict[str, list[str]] = {}
    for section_id in section_union:
        previous_ids = previous_track_ids.get(section_id, [])
        current_ids = current_track_ids.get(section_id, [])
        added = [track_id for track_id in current_ids if track_id not in previous_ids]
        removed = [track_id for track_id in previous_ids if track_id not in current_ids]
        reordered = _reordered_track_ids(previous_ids, current_ids)
        if added:
            added_tracks_by_section[section_id] = added
        if removed:
            removed_tracks_by_section[section_id] = removed
        if reordered:
            reordered_tracks_by_section[section_id] = reordered

    previous_bindings = _curve_bindings_by_key(previous_spec)
    current_bindings = _curve_bindings_by_key(current_spec)
    previous_keys = set(previous_bindings)
    current_keys = set(current_bindings)
    added_curve_bindings = [
        _binding_ref(
            section_id,
            track_id,
            str(current_bindings[(section_id, track_id, channel)]["channel"]),
        )
        for section_id, track_id, channel in sorted(current_keys - previous_keys)
    ]
    removed_curve_bindings = [
        _binding_ref(
            section_id,
            track_id,
            previous_bindings[(section_id, track_id, channel)]["channel"],
        )
        for section_id, track_id, channel in sorted(previous_keys - current_keys)
    ]
    updated_curve_bindings = [
        _binding_ref(
            section_id,
            track_id,
            current_bindings[(section_id, track_id, channel)]["channel"],
        )
        for section_id, track_id, channel in sorted(previous_keys & current_keys)
        if previous_bindings[(section_id, track_id, channel)]
        != current_bindings[(section_id, track_id, channel)]
    ]

    previous_layout = _logfile_mapping_layout(previous_mapping)
    current_layout = _logfile_mapping_layout(current_mapping)
    previous_heading = previous_layout.get("heading")
    current_heading = current_layout.get("heading")
    previous_remarks = previous_layout.get("remarks")
    current_remarks = current_layout.get("remarks")
    heading_changed = (dict(previous_heading) if isinstance(previous_heading, dict) else {}) != (
        dict(current_heading) if isinstance(current_heading, dict) else {}
    )
    remarks_changed = (list(previous_remarks) if isinstance(previous_remarks, list) else []) != (
        list(current_remarks) if isinstance(current_remarks, list) else []
    )
    render_output_changed = previous_spec.render_output_path != current_spec.render_output_path

    summary_lines: list[str] = []
    for section_id in section_union:
        if section_id in added_tracks_by_section:
            summary_lines.append(
                f"Section {section_id}: added tracks {added_tracks_by_section[section_id]}."
            )
        if section_id in removed_tracks_by_section:
            summary_lines.append(
                f"Section {section_id}: removed tracks {removed_tracks_by_section[section_id]}."
            )
        if section_id in reordered_tracks_by_section:
            summary_lines.append(
                f"Section {section_id}: reordered tracks {reordered_tracks_by_section[section_id]}."
            )
    if added_curve_bindings:
        summary_lines.append(
            "Added curve bindings: "
            + ", ".join(
                f"{entry['section_id']}/{entry['track_id']}/{entry['channel']}"
                for entry in added_curve_bindings
            )
            + "."
        )
    if removed_curve_bindings:
        summary_lines.append(
            "Removed curve bindings: "
            + ", ".join(
                f"{entry['section_id']}/{entry['track_id']}/{entry['channel']}"
                for entry in removed_curve_bindings
            )
            + "."
        )
    if updated_curve_bindings:
        summary_lines.append(
            "Updated curve bindings: "
            + ", ".join(
                f"{entry['section_id']}/{entry['track_id']}/{entry['channel']}"
                for entry in updated_curve_bindings
            )
            + "."
        )
    if heading_changed:
        summary_lines.append("Heading content changed.")
    if remarks_changed:
        summary_lines.append("Remarks content changed.")
    if render_output_changed:
        summary_lines.append("Render output_path changed.")

    changed = bool(summary_lines)
    if not changed:
        summary_lines.append("No structural changes detected.")
    message = (
        f"Detected {len(summary_lines)} structural change summaries."
        if changed
        else "No structural changes detected."
    )
    return LogfileChangeSummaryResult(
        logfile_path=str(resolved_logfile),
        changed=changed,
        message=message,
        section_ids=current_section_ids,
        added_tracks_by_section=added_tracks_by_section,
        removed_tracks_by_section=removed_tracks_by_section,
        reordered_tracks_by_section=reordered_tracks_by_section,
        added_curve_bindings=added_curve_bindings,
        removed_curve_bindings=removed_curve_bindings,
        updated_curve_bindings=updated_curve_bindings,
        heading_changed=heading_changed,
        remarks_changed=remarks_changed,
        render_output_changed=render_output_changed,
        summary_lines=summary_lines,
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


def author_plot_from_request_prompt(
    goal: str,
    logfile_path: str | None = None,
    example_id: str | None = None,
) -> str:
    """Return the guided prompt text for deterministic MCP authoring from freeform goals."""
    seed_lines: list[str] = []
    if logfile_path is not None:
        seed_lines.append(f"- existing draft logfile: {logfile_path}")
    if example_id is not None:
        seed_lines.append(f"- packaged example seed: {example_id}")
    if not seed_lines:
        seed_lines.append("- no explicit draft seed was provided")
    seed_block = "\n".join(seed_lines)
    return (
        "Translate this plotting request into deterministic wellplot MCP authoring steps.\n\n"
        f"Goal:\n{goal}\n\n"
        "Available starting point:\n"
        f"{seed_block}\n\n"
        "Workflow:\n"
        "1. If the request starts from a raw LAS/DLIS source, call "
        "inspect_data_source(source_path) and check_channel_availability(...) "
        "before you create bindings.\n"
        "2. If you have a draft logfile, call summarize_logfile_draft(logfile_path).\n"
        "3. If the request includes report-header or remarks content from text, call "
        "parse_key_value_text(source_text, format_hint=None) first.\n"
        "4. If the request includes report-header or remarks content, call "
        "inspect_heading_slots(...), preview_header_mapping(...), and "
        "apply_header_values(...) before generic heading patches.\n"
        "5. If the request is mainly about visual conventions, call "
        "inspect_style_presets(...) before inventing ad hoc colors, fills, or scales.\n"
        "6. Call inspect_authoring_vocab(...) with the same logfile_path when possible.\n"
        "7. Plan the smallest explicit edit sequence using add_track(...), bind_curve(...), "
        "update_curve_binding(...), move_track(...), set_heading_content(...), and "
        "set_remarks_content(...).\n"
        "8. Preview the affected section, track, or window before recommending a final render.\n"
        "9. If you captured the previous YAML text before editing, call "
        "summarize_logfile_changes(logfile_path, previous_text=...) before the final summary.\n"
        "10. Prefer explicit, reviewable mutations over full-file rewrites.\n"
    )


def revise_plot_from_feedback_prompt(logfile_path: str, feedback: str) -> str:
    """Return the guided prompt text for revising one draft logfile from user feedback."""
    return (
        "Revise this wellplot draft through deterministic MCP edit operations.\n\n"
        f"Logfile path: {logfile_path}\n"
        f"Feedback:\n{feedback}\n\n"
        "Workflow:\n"
        "1. Call summarize_logfile_draft(logfile_path).\n"
        "2. Call inspect_authoring_vocab(logfile_path=logfile_path).\n"
        "3. Choose the smallest edit sequence that addresses the feedback.\n"
        "4. Preview the affected section, track, or depth window after the edits.\n"
        "5. If the client retained the previous YAML text, call "
        "summarize_logfile_changes(logfile_path, previous_text=...) before the final explanation.\n"
        "6. Validate or save only after the preview looks correct.\n"
    )


def ingest_header_text_prompt(
    logfile_path: str,
    source_text: str,
    source_description: str | None = None,
) -> str:
    """Return the guided prompt text for deterministic report-header ingestion."""
    description_line = (
        "Source description: copied header packet."
        if source_description is None
        else f"Source description: {source_description}"
    )
    return (
        "Ingest this report-header text into a wellplot draft through deterministic MCP steps.\n\n"
        f"Logfile path: {logfile_path}\n"
        f"{description_line}\n\n"
        "Source text\n"
        "```text\n"
        f"{source_text}\n"
        "```\n\n"
        "Workflow:\n"
        "1. Call inspect_heading_slots(logfile_path=logfile_path) to see the exact provider, "
        "general-field, service-title, detail-row, and remarks targets.\n"
        "2. Call parse_key_value_text(source_text, format_hint=None) before inventing any "
        "mapping.\n"
        "3. If the parsed output leaves important lines unparsed, explain that instead of "
        "guessing values.\n"
        "4. Build the smallest explicit values mapping you can, using disambiguated keys like "
        "general_field.company, detail.date, or service_title_1 when needed.\n"
        '5. Call preview_header_mapping(logfile_path, values, overwrite_policy="fill_empty") '
        "before any mutation.\n"
        "6. If preview_header_mapping(...) reports ambiguities or conflicts, resolve them before "
        "apply_header_values(...).\n"
        "7. Call apply_header_values(logfile_path, values, overwrite_policy=...) only after the "
        "preview looks correct.\n"
        "8. If the source text includes freeform note blocks that do not belong in heading "
        "slots, use set_remarks_content(...) separately.\n"
        "9. Summarize the saved heading state and recommend a first-page preview before any "
        "final render.\n"
    )
