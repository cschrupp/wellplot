from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import TemplateValidationError
from ..logfile import LogFileSpec, build_documents_for_logfile, logfile_from_mapping
from ..model import LogDocument, WellDataset


def _copy_if_present(target: dict[str, Any], key: str, value: Any) -> None:
    if value is not None:
        target[key] = deepcopy(value)


@dataclass(slots=True)
class ProgrammaticLogSpec:
    spec: LogFileSpec
    mapping: dict[str, Any]
    datasets_by_section: dict[str, WellDataset]
    source_paths_by_section: dict[str, Path]

    def to_mapping(self) -> dict[str, Any]:
        return deepcopy(self.mapping)

    def to_yaml(self, destination: str | Path | None = None) -> str | None:
        from .serialize import report_to_yaml

        return report_to_yaml(self, destination)

    def build_documents(self) -> tuple[LogDocument, ...]:
        return build_documents_for_logfile(
            self.spec,
            self.datasets_by_section,
            source_path=self.source_paths_by_section,
        )


class SectionBuilder:
    def __init__(self, builder: LogBuilder, section_id: str) -> None:
        self._builder = builder
        self._section_id = section_id

    @property
    def section_id(self) -> str:
        return self._section_id

    @property
    def _section(self) -> dict[str, Any]:
        return self._builder._section_map[self._section_id]

    def add_track(
        self,
        *,
        id: str,
        title: str,
        kind: str,
        width_mm: float,
        position: int | None = None,
        x_scale: dict[str, Any] | None = None,
        grid: dict[str, Any] | None = None,
        track_header: dict[str, Any] | None = None,
        reference: dict[str, Any] | None = None,
        annotations: list[dict[str, Any]] | None = None,
    ) -> SectionBuilder:
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
        options: dict[str, Any],
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
        style: dict[str, Any] | None = None,
        scale: dict[str, Any] | None = None,
        header_display: dict[str, Any] | None = None,
        callouts: list[dict[str, Any]] | None = None,
        fill: dict[str, Any] | None = None,
        reference_overlay: dict[str, Any] | None = None,
        value_labels: dict[str, Any] | None = None,
        wrap: bool | dict[str, Any] | None = None,
        render_mode: str | None = None,
    ) -> SectionBuilder:
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
        style: dict[str, Any] | None = None,
        profile: str | None = None,
        normalization: str | None = None,
        waveform_normalization: str | None = None,
        clip_percentiles: list[float] | tuple[float, float] | None = None,
        interpolation: str | None = None,
        show_raster: bool | None = None,
        raster_alpha: float | None = None,
        color_limits: list[float] | tuple[float, float] | None = None,
        colorbar: dict[str, Any] | bool | None = None,
        sample_axis: dict[str, Any] | bool | None = None,
        waveform: dict[str, Any] | None = None,
    ) -> SectionBuilder:
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
    def __init__(self, *, name: str) -> None:
        self._mapping: dict[str, Any] = {
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
        self._section_map: dict[str, dict[str, Any]] = {}
        self._datasets_by_section: dict[str, WellDataset] = {}
        self._source_paths_by_section: dict[str, Path] = {}

    def set_render(
        self,
        *,
        backend: str = "matplotlib",
        output_path: str = "programmatic_render.pdf",
        dpi: int = 300,
        continuous_strip_page_height_mm: float | None = None,
        matplotlib_style: dict[str, Any] | None = None,
    ) -> LogBuilder:
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

    def set_page(self, **page: Any) -> LogBuilder:
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
        self._mapping["document"]["depth"] = {
            "unit": unit,
            "scale": scale,
            "major_step": float(major_step),
            "minor_step": float(minor_step),
        }
        return self

    def set_depth_range(self, top: float, base: float) -> LogBuilder:
        self._mapping["document"]["depth_range"] = [float(top), float(base)]
        return self

    def set_header(
        self,
        *,
        title: str | None = None,
        subtitle: str | None = None,
        fields: list[dict[str, Any]] | None = None,
    ) -> LogBuilder:
        header = self._mapping["document"].setdefault("header", {})
        if title is not None:
            header["title"] = title
        if subtitle is not None:
            header["subtitle"] = subtitle
        if fields is not None:
            header["fields"] = deepcopy(fields)
        return self

    def set_footer(self, *, lines: list[str]) -> LogBuilder:
        self._mapping["document"]["footer"] = {"lines": list(lines)}
        return self

    def set_heading(
        self,
        *,
        enabled: bool = True,
        provider_name: str | None = None,
        general_fields: list[dict[str, Any]] | None = None,
        service_titles: list[dict[str, Any] | str] | None = None,
        detail: dict[str, Any] | None = None,
        tail_enabled: bool | None = None,
    ) -> LogBuilder:
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

    def set_remarks(self, remarks: list[dict[str, Any]]) -> LogBuilder:
        self._mapping["document"]["layout"]["remarks"] = deepcopy(remarks)
        return self

    def set_on_missing(self, mode: str) -> LogBuilder:
        self._mapping["document"]["bindings"]["on_missing"] = str(mode)
        return self

    def save_yaml(self, destination: str | Path | None = None) -> str | None:
        from .serialize import report_to_yaml

        return report_to_yaml(self, destination)

    def add_section(
        self,
        section_id: str,
        *,
        dataset: WellDataset,
        title: str = "",
        subtitle: str = "",
        source_name: str | Path | None = None,
        source_path: str | Path | None = None,
        source_format: str = "auto",
    ) -> SectionBuilder:
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
                str(source_name).strip()
                if source_name is not None
                else f"{normalized_id}.memory"
            )
        )
        self._source_paths_by_section[normalized_id] = Path(path_text)
        return SectionBuilder(self, normalized_id)

    def to_mapping(self) -> dict[str, Any]:
        mapping = deepcopy(self._mapping)
        mapping["document"]["bindings"]["channels"] = deepcopy(self._bindings)
        return mapping

    @property
    def _bindings(self) -> list[dict[str, Any]]:
        return self._mapping["document"]["bindings"]["channels"]

    def build(self) -> ProgrammaticLogSpec:
        mapping = self.to_mapping()
        spec = logfile_from_mapping(mapping)
        section_ids = {
            str(section["id"])
            for section in mapping["document"]["layout"].get("log_sections", [])
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
