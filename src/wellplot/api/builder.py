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

"""Programmatic builders for reports, sections, and bindings."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from ..errors import TemplateValidationError
from ..logfile import LogFileSpec, build_documents_for_logfile, logfile_from_mapping
from ..model import LogDocument, WellDataset


def _copy_if_present(target: dict[str, object], key: str, value: object) -> None:
    if value is not None:
        target[key] = deepcopy(value)


@dataclass(slots=True)
class ProgrammaticLogSpec:
    """Normalized report specification plus in-memory datasets by section.

    This object is the handoff point between builder-based composition and the
    render or serialization APIs.
    """

    spec: LogFileSpec
    mapping: dict[str, object]
    datasets_by_section: dict[str, WellDataset]
    source_paths_by_section: dict[str, Path]

    def to_mapping(self) -> dict[str, object]:
        """Return a deep-copied YAML-style mapping representation."""
        return deepcopy(self.mapping)

    def to_yaml(self, destination: str | Path | None = None) -> str | None:
        """Serialize the report mapping to YAML text or a destination path."""
        from .serialize import report_to_yaml

        return report_to_yaml(self, destination)

    def build_documents(self) -> tuple[LogDocument, ...]:
        """Build render-ready documents using the attached in-memory datasets."""
        return build_documents_for_logfile(
            self.spec,
            self.datasets_by_section,
            source_path=self.source_paths_by_section,
        )


class SectionBuilder:
    """Fluent builder for one dataset-backed log section.

    A section builder owns the track layout and channel bindings for one section
    inside a larger programmatic report.
    """

    def __init__(self, builder: LogBuilder, section_id: str) -> None:
        """Bind the section builder to one parent-builder section mapping."""
        self._builder = builder
        self._section_id = section_id

    @property
    def section_id(self) -> str:
        """Return the owning section identifier."""
        return self._section_id

    @property
    def _section(self) -> dict[str, object]:
        return self._builder._section_map[self._section_id]

    def add_track(
        self,
        *,
        id: str,
        title: str,
        kind: str,
        width_mm: float,
        position: int | None = None,
        x_scale: Mapping[str, object] | None = None,
        grid: Mapping[str, object] | None = None,
        track_header: Mapping[str, object] | None = None,
        reference: Mapping[str, object] | None = None,
        annotations: Sequence[Mapping[str, object]] | None = None,
    ) -> SectionBuilder:
        """Add one track definition to the current section.

        Use ``kind`` to choose between reference, normal, array, and annotation
        tracks, then add curve or raster bindings separately.
        """
        track = {
            "id": id,
            "title": title,
            "kind": kind,
            "width_mm": float(width_mm),
        }
        _copy_if_present(track, "position", position)
        _copy_if_present(track, "x_scale", x_scale)
        _copy_if_present(track, "grid", grid)
        _copy_if_present(track, "track_header", track_header)
        _copy_if_present(track, "reference", reference)
        _copy_if_present(track, "annotations", annotations)
        self._section.setdefault("tracks", []).append(track)
        return self

    def _add_binding(
        self,
        *,
        kind: str,
        channel: str,
        track_id: str,
        options: Mapping[str, object],
    ) -> SectionBuilder:
        binding = {
            "section": self._section_id,
            "channel": channel,
            "track_id": track_id,
            "kind": kind,
        }
        for key, value in options.items():
            if value is not None:
                binding[key] = deepcopy(value)
        self._builder._bindings.append(binding)
        return self

    def add_curve(
        self,
        *,
        channel: str,
        track_id: str,
        label: str | None = None,
        style: Mapping[str, object] | None = None,
        scale: Mapping[str, object] | None = None,
        header_display: Mapping[str, object] | None = None,
        callouts: Sequence[Mapping[str, object]] | None = None,
        fill: Mapping[str, object] | None = None,
        reference_overlay: Mapping[str, object] | None = None,
        value_labels: Mapping[str, object] | None = None,
        wrap: bool | Mapping[str, object] | None = None,
        render_mode: str | None = None,
    ) -> SectionBuilder:
        """Bind one scalar channel to a track as a curve element.

        The binding options mirror the YAML channel-binding model, including
        scale, style, fills, header display, callouts, and reference overlays.
        """
        return self._add_binding(
            kind="curve",
            channel=channel,
            track_id=track_id,
            options={
                "label": label,
                "style": style,
                "scale": scale,
                "header_display": header_display,
                "callouts": callouts,
                "fill": fill,
                "reference_overlay": reference_overlay,
                "value_labels": value_labels,
                "wrap": wrap,
                "render_mode": render_mode,
            },
        )

    def add_raster(
        self,
        *,
        channel: str,
        track_id: str,
        label: str | None = None,
        style: Mapping[str, object] | None = None,
        profile: str | None = None,
        normalization: str | None = None,
        waveform_normalization: str | None = None,
        clip_percentiles: Sequence[float] | None = None,
        interpolation: str | None = None,
        show_raster: bool | None = None,
        raster_alpha: float | None = None,
        color_limits: Sequence[float] | None = None,
        colorbar: Mapping[str, object] | bool | None = None,
        sample_axis: Mapping[str, object] | bool | None = None,
        waveform: Mapping[str, object] | None = None,
    ) -> SectionBuilder:
        """Bind one raster or array channel to a track.

        The binding options mirror the YAML raster-binding model, including VDL
        profile settings, waveform overlay controls, colorbars, and sample-axis
        metadata.
        """
        return self._add_binding(
            kind="raster",
            channel=channel,
            track_id=track_id,
            options={
                "label": label,
                "style": style,
                "profile": profile,
                "normalization": normalization,
                "waveform_normalization": waveform_normalization,
                "clip_percentiles": clip_percentiles,
                "interpolation": interpolation,
                "show_raster": show_raster,
                "raster_alpha": raster_alpha,
                "color_limits": color_limits,
                "colorbar": colorbar,
                "sample_axis": sample_axis,
                "waveform": waveform,
            },
        )


class LogBuilder:
    """Fluent builder for full report composition in Python.

    ``LogBuilder`` owns render settings, document settings, report packet pages,
    section definitions, and dataset attachments. Call :meth:`build` to produce
    a :class:`ProgrammaticLogSpec`.
    """

    def __init__(self, *, name: str) -> None:
        """Initialize a new builder with default render and document settings."""
        self._mapping: dict[str, object] = {
            "version": 1,
            "name": name,
            "render": {
                "backend": "matplotlib",
                "output_path": "programmatic_render.pdf",
                "dpi": 300,
            },
            "document": {
                "page": {
                    "size": "A4",
                    "orientation": "portrait",
                },
                "depth": {
                    "unit": "m",
                    "scale": 200,
                    "major_step": 10.0,
                    "minor_step": 2.0,
                },
                "layout": {
                    "log_sections": [],
                },
                "bindings": {
                    "on_missing": "skip",
                    "channels": [],
                },
            },
        }
        self._section_map: dict[str, dict[str, object]] = {}
        self._datasets_by_section: dict[str, WellDataset] = {}
        self._source_paths_by_section: dict[str, Path] = {}

    def set_render(
        self,
        *,
        backend: str = "matplotlib",
        output_path: str = "programmatic_render.pdf",
        dpi: int = 300,
        continuous_strip_page_height_mm: float | None = None,
        matplotlib_style: Mapping[str, object] | None = None,
    ) -> LogBuilder:
        """Configure backend-specific render settings.

        This sets the renderer backend, default output path, DPI, and optional
        backend-specific settings such as matplotlib style overrides.
        """
        render = self._mapping["render"]
        render["backend"] = backend
        render["output_path"] = output_path
        render["dpi"] = int(dpi)
        if continuous_strip_page_height_mm is None:
            render.pop("continuous_strip_page_height_mm", None)
        else:
            render["continuous_strip_page_height_mm"] = float(continuous_strip_page_height_mm)
        if matplotlib_style is None:
            render.pop("matplotlib", None)
        else:
            render["matplotlib"] = {"style": deepcopy(matplotlib_style)}
        return self

    def set_page(self, **page: object) -> LogBuilder:
        """Replace the document page configuration block."""
        self._mapping["document"]["page"] = deepcopy(page)
        return self

    def set_depth_axis(
        self,
        *,
        unit: str,
        scale: int | float | str,
        major_step: float,
        minor_step: float,
    ) -> LogBuilder:
        """Configure the shared depth or time axis for the report."""
        self._mapping["document"]["depth"] = {
            "unit": unit,
            "scale": scale,
            "major_step": float(major_step),
            "minor_step": float(minor_step),
        }
        return self

    def set_depth_range(self, top: float, base: float) -> LogBuilder:
        """Set the top/base interval rendered by default."""
        self._mapping["document"]["depth_range"] = [float(top), float(base)]
        return self

    def set_header(
        self,
        *,
        title: str | None = None,
        subtitle: str | None = None,
        fields: Sequence[Mapping[str, object]] | None = None,
    ) -> LogBuilder:
        """Configure the standard document header block.

        This is separate from the report-style heading/tail pages and applies to
        normal rendered log pages.
        """
        header = self._mapping["document"].setdefault("header", {})
        if title is not None:
            header["title"] = title
        if subtitle is not None:
            header["subtitle"] = subtitle
        if fields is not None:
            header["fields"] = deepcopy(fields)
        return self

    def set_footer(self, *, lines: list[str]) -> LogBuilder:
        """Configure the simple footer lines block for rendered log pages."""
        self._mapping["document"]["footer"] = {"lines": list(lines)}
        return self

    def set_heading(
        self,
        *,
        enabled: bool = True,
        provider_name: str | None = None,
        general_fields: Sequence[Mapping[str, object]] | None = None,
        service_titles: Sequence[Mapping[str, object] | str] | None = None,
        detail: Mapping[str, object] | None = None,
        tail_enabled: bool | None = None,
    ) -> LogBuilder:
        """Configure report heading and tail content.

        This controls the first-page heading packet and the optional tail packet
        rendered after the log sections.
        """
        layout = self._mapping["document"]["layout"]
        heading = dict(layout.get("heading", {}))
        heading["enabled"] = bool(enabled)
        _copy_if_present(heading, "provider_name", provider_name)
        _copy_if_present(heading, "general_fields", general_fields)
        _copy_if_present(heading, "service_titles", service_titles)
        _copy_if_present(heading, "detail", detail)
        if tail_enabled is not None:
            heading["tail_enabled"] = bool(tail_enabled)
        layout["heading"] = heading
        return self

    def set_remarks(self, remarks: Sequence[Mapping[str, object]]) -> LogBuilder:
        """Replace the remarks block rendered on the first report page."""
        self._mapping["document"]["layout"]["remarks"] = deepcopy(remarks)
        return self

    def set_on_missing(self, mode: str) -> LogBuilder:
        """Set the binding behavior for missing channels or rasters."""
        self._mapping["document"]["bindings"]["on_missing"] = str(mode)
        return self

    def save_yaml(self, destination: str | Path | None = None) -> str | None:
        """Serialize the current report mapping to YAML text or a file path."""
        from .serialize import report_to_yaml

        return report_to_yaml(self, destination)

    def add_section(
        self,
        section_id: str,
        *,
        dataset: WellDataset,
        title: str = "",
        subtitle: str = "",
        depth_range: tuple[float, float] | None = None,
        source_name: str | Path | None = None,
        source_path: str | Path | None = None,
        source_format: str = "auto",
    ) -> SectionBuilder:
        """Add a dataset-backed log section and return its section builder.

        Each section has its own in-memory dataset attachment, track list, and
        optional source-path metadata for later serialization.
        """
        normalized_id = str(section_id).strip()
        if not normalized_id:
            raise TemplateValidationError("Section id must be non-empty.")
        if normalized_id in self._section_map:
            raise TemplateValidationError(f"Duplicate section id {normalized_id!r}.")

        section = {
            "id": normalized_id,
            "title": title,
            "subtitle": subtitle,
            "tracks": [],
        }
        if depth_range is not None:
            section["depth_range"] = [float(depth_range[0]), float(depth_range[1])]
        if source_path is not None:
            source_path_text = str(source_path).strip()
            if not source_path_text:
                raise TemplateValidationError("Section source_path must be non-empty when set.")
            section["data"] = {
                "source_path": source_path_text,
                "source_format": str(source_format).strip().lower() or "auto",
            }
        self._mapping["document"]["layout"]["log_sections"].append(section)
        self._section_map[normalized_id] = section
        self._datasets_by_section[normalized_id] = dataset
        path_text = (
            str(source_path).strip()
            if source_path is not None
            else (
                str(source_name).strip() if source_name is not None else f"{normalized_id}.memory"
            )
        )
        self._source_paths_by_section[normalized_id] = Path(path_text)
        return SectionBuilder(self, normalized_id)

    def to_mapping(self) -> dict[str, object]:
        """Return the normalized YAML-style mapping for the report."""
        mapping = deepcopy(self._mapping)
        mapping["document"]["bindings"]["channels"] = deepcopy(self._bindings)
        return mapping

    @property
    def _bindings(self) -> list[dict[str, object]]:
        return self._mapping["document"]["bindings"]["channels"]

    def build(self) -> ProgrammaticLogSpec:
        """Validate the builder state and return a render-ready report object.

        The build step verifies the normalized mapping and ensures that every
        declared section has an attached in-memory dataset.
        """
        mapping = self.to_mapping()
        spec = logfile_from_mapping(mapping)
        section_ids = {
            str(section["id"]) for section in mapping["document"]["layout"].get("log_sections", [])
        }
        missing = sorted(section_ids - self._datasets_by_section.keys())
        if missing:
            raise TemplateValidationError(
                f"Missing in-memory datasets for sections: {', '.join(missing)}."
            )
        return ProgrammaticLogSpec(
            spec=spec,
            mapping=mapping,
            datasets_by_section=dict(self._datasets_by_section),
            source_paths_by_section=dict(self._source_paths_by_section),
        )


__all__ = [
    "LogBuilder",
    "ProgrammaticLogSpec",
    "SectionBuilder",
]
