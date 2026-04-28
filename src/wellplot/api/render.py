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

"""Programmatic rendering helpers for reports and scoped subsets."""

from __future__ import annotations

from copy import deepcopy
from io import BytesIO
from pathlib import Path
from typing import Any

from ..errors import TemplateValidationError
from ..logfile import build_documents_for_logfile, logfile_from_mapping
from ..model import LogDocument
from ..renderers import MatplotlibRenderer, PlotlyRenderer
from ..renderers.base import RenderResult
from ..units import DEFAULT_UNITS
from .builder import ProgrammaticLogSpec


def _document_section_id(document: LogDocument) -> str:
    metadata = getattr(document, "metadata", None)
    if isinstance(metadata, dict):
        layout_sections = metadata.get("layout_sections")
        if isinstance(layout_sections, dict):
            active_section = layout_sections.get("active_section")
            if isinstance(active_section, dict):
                section_id = active_section.get("id")
                if isinstance(section_id, str):
                    return section_id
    return ""


def _normalized_output_path(
    report: ProgrammaticLogSpec,
    output_path: str | Path | None,
) -> Path | None:
    if output_path is None:
        return None
    return Path(output_path).expanduser().resolve()


def _normalize_section_ids(
    section_ids: list[str] | tuple[str, ...] | None,
) -> tuple[str, ...] | None:
    if section_ids is None:
        return None
    normalized = tuple(str(section_id) for section_id in section_ids)
    return normalized or None


def _normalize_track_selection(
    section_id: str | None = None,
    track_ids: str | list[str] | tuple[str, ...] | None = None,
    *,
    track_ids_by_section: dict[str, list[str] | tuple[str, ...]] | None = None,
) -> dict[str, tuple[str, ...]] | None:
    normalized: dict[str, tuple[str, ...]] = {}
    if track_ids_by_section:
        for selected_section_id, selected_track_ids in track_ids_by_section.items():
            values = tuple(str(track_id) for track_id in selected_track_ids)
            if not values:
                continue
            normalized[str(selected_section_id)] = values
    if track_ids is not None:
        if section_id is None:
            raise TemplateValidationError("Track filtering requires a section_id.")
        if isinstance(track_ids, str):
            values = (track_ids,)
        else:
            values = tuple(str(track_id) for track_id in track_ids)
        if not values:
            raise TemplateValidationError("Track filtering requires at least one track_id.")
        normalized[str(section_id)] = values
    return normalized or None


def _normalized_depth_range(
    report: ProgrammaticLogSpec,
    depth_range: tuple[float, float] | None,
    depth_range_unit: str | None,
) -> tuple[float, float] | None:
    if depth_range is None:
        return None
    top, base = float(depth_range[0]), float(depth_range[1])
    document_depth = report.mapping["document"].get("depth", {})
    target_unit = str(document_depth.get("unit", "")).strip()
    if not target_unit:
        return top, base
    source_unit = target_unit if depth_range_unit is None else str(depth_range_unit).strip()
    if source_unit == target_unit or not source_unit:
        return top, base
    return (
        DEFAULT_UNITS.convert(top, source_unit, target_unit),
        DEFAULT_UNITS.convert(base, source_unit, target_unit),
    )


def _suppress_report_pages(filtered_mapping: dict[str, Any]) -> None:
    layout = filtered_mapping["document"]["layout"]
    layout.pop("heading", None)
    layout.pop("tail", None)
    layout["remarks"] = []


def _filter_track_layout(
    filtered_mapping: dict[str, Any],
    track_ids_by_section: dict[str, tuple[str, ...]],
    *,
    implicit_section_id: str | None = None,
) -> None:
    layout = filtered_mapping["document"]["layout"]
    sections = list(layout.get("log_sections", []))
    selected_by_section = {
        section_id: set(track_ids) for section_id, track_ids in track_ids_by_section.items()
    }
    for section in sections:
        current_section_id = str(section.get("id"))
        selected = selected_by_section.get(current_section_id)
        if selected is None:
            continue
        tracks = list(section.get("tracks", []))
        filtered_tracks = [track for track in tracks if str(track.get("id")) in selected]
        if not filtered_tracks:
            raise TemplateValidationError(
                f"No matching tracks were selected for section {current_section_id!r}."
            )
        section["tracks"] = filtered_tracks

    bindings = filtered_mapping["document"]["bindings"]
    bindings["channels"] = [
        binding
        for binding in bindings.get("channels", [])
        if (
            selected_by_section.get(
                _binding_section_id(binding, implicit_section_id=implicit_section_id)
            )
            is None
            or str(binding.get("track_id", ""))
            in selected_by_section[
                _binding_section_id(binding, implicit_section_id=implicit_section_id)
            ]
        )
    ]


def _apply_depth_window(
    filtered_mapping: dict[str, Any],
    depth_range: tuple[float, float],
) -> None:
    filtered_mapping["document"]["depth_range"] = [float(depth_range[0]), float(depth_range[1])]


def _binding_section_id(
    binding: dict[str, Any],
    *,
    implicit_section_id: str | None = None,
) -> str:
    section_id = str(binding.get("section", "")).strip()
    if section_id:
        return section_id
    return "" if implicit_section_id is None else implicit_section_id


def _filtered_report(
    report: ProgrammaticLogSpec,
    section_ids: tuple[str, ...] | None,
    *,
    track_ids_by_section: dict[str, tuple[str, ...]] | None = None,
    depth_range: tuple[float, float] | None = None,
    include_report_pages: bool = True,
) -> ProgrammaticLogSpec:
    if (
        not section_ids
        and not track_ids_by_section
        and depth_range is None
        and include_report_pages
    ):
        return report

    source_sections = list(report.mapping["document"]["layout"].get("log_sections", []))
    available_section_ids = [str(section.get("id")) for section in source_sections]
    if section_ids is not None:
        requested = set(section_ids)
    elif track_ids_by_section is not None:
        requested = set(track_ids_by_section)
    else:
        requested = set(available_section_ids)
    implicit_section_id = available_section_ids[0] if len(available_section_ids) == 1 else None

    filtered_mapping = report.to_mapping()
    layout = filtered_mapping["document"]["layout"]
    sections = list(layout.get("log_sections", []))
    filtered_sections = [section for section in sections if str(section.get("id")) in requested]
    if not filtered_sections:
        raise TemplateValidationError("No matching sections were selected for rendering.")
    layout["log_sections"] = filtered_sections
    bindings = filtered_mapping["document"]["bindings"]
    bindings["channels"] = [
        binding
        for binding in bindings.get("channels", [])
        if _binding_section_id(binding, implicit_section_id=implicit_section_id) in requested
    ]
    if track_ids_by_section:
        _filter_track_layout(
            filtered_mapping,
            track_ids_by_section,
            implicit_section_id=implicit_section_id,
        )
    if depth_range is not None:
        _apply_depth_window(filtered_mapping, depth_range)
    if not include_report_pages:
        _suppress_report_pages(filtered_mapping)
    filtered_spec = logfile_from_mapping(filtered_mapping)
    filtered_datasets = {
        section_id: dataset
        for section_id, dataset in report.datasets_by_section.items()
        if section_id in requested
    }
    filtered_sources = {
        section_id: source_path
        for section_id, source_path in report.source_paths_by_section.items()
        if section_id in requested
    }
    return ProgrammaticLogSpec(
        spec=filtered_spec,
        mapping=filtered_mapping,
        datasets_by_section=filtered_datasets,
        source_paths_by_section=filtered_sources,
    )


def build_documents(
    report: ProgrammaticLogSpec,
    *,
    section_ids: list[str] | tuple[str, ...] | None = None,
    track_ids_by_section: dict[str, list[str] | tuple[str, ...]] | None = None,
    depth_range: tuple[float, float] | None = None,
    depth_range_unit: str | None = None,
    include_report_pages: bool = True,
) -> tuple[LogDocument, ...]:
    """Build render-ready documents for the selected report scope.

    This is the normalization step to use when you want to inspect or reuse the
    concrete :class:`LogDocument` objects before rendering them.
    """
    normalized_sections = _normalize_section_ids(section_ids)
    normalized_tracks = _normalize_track_selection(
        track_ids_by_section=track_ids_by_section,
    )
    filtered = _filtered_report(
        report,
        normalized_sections,
        track_ids_by_section=normalized_tracks,
        depth_range=_normalized_depth_range(report, depth_range, depth_range_unit),
        include_report_pages=include_report_pages,
    )
    return build_documents_for_logfile(
        filtered.spec,
        filtered.datasets_by_section,
        source_path=filtered.source_paths_by_section,
    )


def render_report(
    report: ProgrammaticLogSpec,
    *,
    output_path: str | Path | None = None,
    section_ids: list[str] | tuple[str, ...] | None = None,
    track_ids_by_section: dict[str, list[str] | tuple[str, ...]] | None = None,
    depth_range: tuple[float, float] | None = None,
    depth_range_unit: str | None = None,
    include_report_pages: bool = True,
) -> RenderResult:
    """Render the selected report scope with the configured backend.

    The scope can be narrowed by section, track selection, and depth window. If
    ``output_path`` is omitted for the matplotlib backend, in-memory figures are
    returned inside the :class:`RenderResult`.
    """
    normalized_sections = _normalize_section_ids(section_ids)
    normalized_tracks = _normalize_track_selection(
        track_ids_by_section=track_ids_by_section,
    )
    filtered = _filtered_report(
        report,
        normalized_sections,
        track_ids_by_section=normalized_tracks,
        depth_range=_normalized_depth_range(report, depth_range, depth_range_unit),
        include_report_pages=include_report_pages,
    )
    documents = build_documents_for_logfile(
        filtered.spec,
        filtered.datasets_by_section,
        source_path=filtered.source_paths_by_section,
    )
    default_dataset = next(iter(filtered.datasets_by_section.values()))
    document_datasets = tuple(
        filtered.datasets_by_section.get(_document_section_id(document), default_dataset)
        for document in documents
    )
    resolved_output = _normalized_output_path(filtered, output_path)

    if filtered.spec.render_backend == "matplotlib":
        renderer_kwargs = {"dpi": filtered.spec.render_dpi}
        if filtered.spec.render_continuous_strip_page_height_mm is not None:
            renderer_kwargs["continuous_strip_page_height_mm"] = (
                filtered.spec.render_continuous_strip_page_height_mm
            )
        matplotlib_style = filtered.spec.render_matplotlib.get("style")
        if matplotlib_style is not None:
            renderer_kwargs["style"] = deepcopy(matplotlib_style)
        renderer = MatplotlibRenderer(**renderer_kwargs)
        return renderer.render_documents(documents, document_datasets, output_path=resolved_output)

    if filtered.spec.render_backend == "plotly":
        if len(documents) > 1:
            raise TemplateValidationError(
                "Plotly backend currently supports a single log section. "
                "Use matplotlib for multisection rendering."
            )
        renderer = PlotlyRenderer()
        return renderer.render(documents[0], document_datasets[0], output_path=resolved_output)

    raise TemplateValidationError(
        f"Unsupported render backend {filtered.spec.render_backend!r}. "
        "Supported backends: matplotlib, plotly."
    )


def render_section(
    report: ProgrammaticLogSpec,
    *,
    section_id: str,
    output_path: str | Path | None = None,
) -> RenderResult:
    """Render one section without the report heading, remarks, or tail pages."""
    return render_report(
        report,
        output_path=output_path,
        section_ids=[section_id],
        include_report_pages=False,
    )


def render_track(
    report: ProgrammaticLogSpec,
    *,
    section_id: str,
    track_ids: str | list[str] | tuple[str, ...],
    output_path: str | Path | None = None,
    depth_range: tuple[float, float] | None = None,
    depth_range_unit: str | None = None,
) -> RenderResult:
    """Render selected tracks from one section without report pages."""
    track_selection = _normalize_track_selection(section_id, track_ids)
    return render_report(
        report,
        output_path=output_path,
        section_ids=[section_id],
        track_ids_by_section=track_selection,
        depth_range=depth_range,
        depth_range_unit=depth_range_unit,
        include_report_pages=False,
    )


def render_window(
    report: ProgrammaticLogSpec,
    *,
    depth_range: tuple[float, float],
    depth_range_unit: str | None = None,
    output_path: str | Path | None = None,
    section_ids: list[str] | tuple[str, ...] | None = None,
) -> RenderResult:
    """Render a depth- or time-windowed subset of the report.

    The requested window is converted into the report axis unit when
    ``depth_range_unit`` differs from the report's configured index unit.
    """
    return render_report(
        report,
        output_path=output_path,
        section_ids=section_ids,
        depth_range=depth_range,
        depth_range_unit=depth_range_unit,
        include_report_pages=False,
    )


def _result_figure_bytes(
    result: RenderResult,
    *,
    image_format: str,
    page_index: int = 0,
    dpi: int | None = None,
) -> bytes:
    if result.backend != "matplotlib":
        raise TemplateValidationError(
            f"{image_format.upper()} byte output currently requires the matplotlib backend."
        )
    figures = result.artifact
    if not isinstance(figures, list) or not figures:
        raise TemplateValidationError(
            f"{image_format.upper()} byte output requires in-memory matplotlib figures."
        )
    if page_index < 0 or page_index >= len(figures):
        raise TemplateValidationError(
            f"Requested page_index {page_index} is out of range for {len(figures)} rendered pages."
        )

    buffer = BytesIO()
    try:
        save_kwargs: dict[str, Any] = {"format": image_format}
        if dpi is not None and image_format.lower() == "png":
            save_kwargs["dpi"] = dpi
        figures[page_index].savefig(buffer, **save_kwargs)
        return buffer.getvalue()
    finally:
        buffer.close()
        try:
            import matplotlib.pyplot as plt

            for figure in figures:
                plt.close(figure)
        except Exception:
            for figure in figures:
                clf = getattr(figure, "clf", None)
                if callable(clf):
                    clf()


def render_png_bytes(
    report: ProgrammaticLogSpec,
    *,
    page_index: int = 0,
    dpi: int | None = None,
    section_ids: list[str] | tuple[str, ...] | None = None,
    track_ids_by_section: dict[str, list[str] | tuple[str, ...]] | None = None,
    depth_range: tuple[float, float] | None = None,
    depth_range_unit: str | None = None,
    include_report_pages: bool = True,
) -> bytes:
    """Render the selected scope and return one page as PNG bytes.

    This helper is designed for notebooks, dashboards, and API responses that
    need an in-memory raster preview instead of a saved file.
    """
    result = render_report(
        report,
        output_path=None,
        section_ids=section_ids,
        track_ids_by_section=track_ids_by_section,
        depth_range=depth_range,
        depth_range_unit=depth_range_unit,
        include_report_pages=include_report_pages,
    )
    return _result_figure_bytes(result, image_format="png", page_index=page_index, dpi=dpi)


def render_svg_bytes(
    report: ProgrammaticLogSpec,
    *,
    page_index: int = 0,
    section_ids: list[str] | tuple[str, ...] | None = None,
    track_ids_by_section: dict[str, list[str] | tuple[str, ...]] | None = None,
    depth_range: tuple[float, float] | None = None,
    depth_range_unit: str | None = None,
    include_report_pages: bool = True,
) -> bytes:
    """Render the selected scope and return one page as SVG bytes.

    This is the vector equivalent of :func:`render_png_bytes` and is useful for
    notebook or browser workflows that prefer scalable output.
    """
    result = render_report(
        report,
        output_path=None,
        section_ids=section_ids,
        track_ids_by_section=track_ids_by_section,
        depth_range=depth_range,
        depth_range_unit=depth_range_unit,
        include_report_pages=include_report_pages,
    )
    return _result_figure_bytes(result, image_format="svg", page_index=page_index)


def render_section_png(
    report: ProgrammaticLogSpec,
    *,
    section_id: str,
    page_index: int = 0,
    dpi: int | None = None,
) -> bytes:
    """Render one section and return the selected page as PNG bytes."""
    return render_png_bytes(
        report,
        page_index=page_index,
        dpi=dpi,
        section_ids=[section_id],
        include_report_pages=False,
    )


def render_track_png(
    report: ProgrammaticLogSpec,
    *,
    section_id: str,
    track_ids: str | list[str] | tuple[str, ...],
    page_index: int = 0,
    dpi: int | None = None,
    depth_range: tuple[float, float] | None = None,
    depth_range_unit: str | None = None,
) -> bytes:
    """Render selected tracks from one section and return PNG bytes."""
    track_selection = _normalize_track_selection(section_id, track_ids)
    return render_png_bytes(
        report,
        page_index=page_index,
        dpi=dpi,
        section_ids=[section_id],
        track_ids_by_section=track_selection,
        depth_range=depth_range,
        depth_range_unit=depth_range_unit,
        include_report_pages=False,
    )


def render_window_png(
    report: ProgrammaticLogSpec,
    *,
    depth_range: tuple[float, float],
    depth_range_unit: str | None = None,
    page_index: int = 0,
    dpi: int | None = None,
    section_ids: list[str] | tuple[str, ...] | None = None,
) -> bytes:
    """Render a depth or time window and return PNG bytes."""
    return render_png_bytes(
        report,
        page_index=page_index,
        dpi=dpi,
        section_ids=section_ids,
        depth_range=depth_range,
        depth_range_unit=depth_range_unit,
        include_report_pages=False,
    )


__all__ = [
    "build_documents",
    "render_png_bytes",
    "render_section",
    "render_section_png",
    "render_svg_bytes",
    "render_track",
    "render_track_png",
    "render_window",
    "render_window_png",
    "render_report",
]
