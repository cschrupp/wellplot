from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from ..errors import TemplateValidationError
from ..logfile import build_documents_for_logfile, logfile_from_mapping
from ..model import LogDocument
from ..renderers import MatplotlibRenderer, PlotlyRenderer
from ..renderers.base import RenderResult
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


def _filtered_report(
    report: ProgrammaticLogSpec,
    section_ids: tuple[str, ...] | None,
) -> ProgrammaticLogSpec:
    if not section_ids:
        return report

    requested = set(section_ids)
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
        if str(binding.get("section", "")) in requested
    ]
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
) -> tuple[LogDocument, ...]:
    filtered = _filtered_report(
        report,
        tuple(section_ids) if section_ids is not None else None,
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
) -> RenderResult:
    filtered = _filtered_report(
        report,
        tuple(section_ids) if section_ids is not None else None,
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


__all__ = [
    "build_documents",
    "render_report",
]
