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

"""High-level rendering pipeline from logfile specification to output."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .errors import TemplateValidationError
from .logfile import (
    LogFileSpec,
    build_documents_for_logfile,
    load_datasets_for_logfile,
    load_logfile,
)
from .model import LogDocument, WellDataset
from .renderers import MatplotlibRenderer, PlotlyRenderer
from .renderers.base import RenderResult


def _resolve_output_path(
    logfile_path: Path,
    configured_output: str,
    output_override: str | Path | None,
) -> Path:
    """Resolve the final render output path relative to the logfile."""
    output_path = Path(output_override) if output_override is not None else Path(configured_output)
    if not output_path.is_absolute():
        output_path = (logfile_path.parent / output_path).resolve()
    return output_path


def _document_section_id(document: LogDocument) -> str:
    """Return the active layout section identifier stored in document metadata."""
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


@dataclass(slots=True)
class PreparedLogfileRender:
    """Resolved logfile data, documents, and dataset mapping for one render request."""

    logfile_path: Path
    spec: LogFileSpec
    datasets_by_section: dict[str, WellDataset]
    source_paths_by_section: dict[str, Path]
    documents: tuple[LogDocument, ...]
    document_datasets: tuple[WellDataset, ...]


def prepare_logfile_render(
    logfile_path: str | Path,
    *,
    allowed_root: Path | None = None,
) -> PreparedLogfileRender:
    """Load a logfile, its datasets, and render-ready documents."""
    resolved_logfile = Path(logfile_path).resolve()
    spec = load_logfile(resolved_logfile, allowed_root=allowed_root)
    datasets_by_section, source_paths_by_section = load_datasets_for_logfile(
        spec,
        base_dir=resolved_logfile.parent,
        allowed_root=allowed_root,
    )
    documents = build_documents_for_logfile(
        spec,
        datasets_by_section,
        source_path=source_paths_by_section,
    )
    if not datasets_by_section:
        raise TemplateValidationError("No datasets were resolved for the configured log sections.")
    default_dataset = next(iter(datasets_by_section.values()))
    document_datasets = tuple(
        datasets_by_section.get(_document_section_id(document), default_dataset)
        for document in documents
    )
    return PreparedLogfileRender(
        logfile_path=resolved_logfile,
        spec=spec,
        datasets_by_section=datasets_by_section,
        source_paths_by_section=source_paths_by_section,
        documents=documents,
        document_datasets=document_datasets,
    )


def render_prepared_logfile(
    prepared: PreparedLogfileRender,
    *,
    output_path: str | Path | None = None,
) -> RenderResult:
    """Render a previously prepared logfile payload."""
    resolved_output = _resolve_output_path(
        prepared.logfile_path,
        prepared.spec.render_output_path,
        output_path,
    )

    if prepared.spec.render_backend == "matplotlib":
        renderer_kwargs = {"dpi": prepared.spec.render_dpi}
        if prepared.spec.render_continuous_strip_page_height_mm is not None:
            renderer_kwargs["continuous_strip_page_height_mm"] = (
                prepared.spec.render_continuous_strip_page_height_mm
            )
        matplotlib_style = prepared.spec.render_matplotlib.get("style")
        if matplotlib_style is not None:
            renderer_kwargs["style"] = matplotlib_style
        renderer = MatplotlibRenderer(**renderer_kwargs)
        return renderer.render_documents(
            prepared.documents,
            prepared.document_datasets,
            output_path=resolved_output,
        )
    if prepared.spec.render_backend == "plotly":
        if len(prepared.documents) > 1:
            raise TemplateValidationError(
                "Plotly backend currently supports a single log section. "
                "Use matplotlib for multisection rendering."
            )
        renderer = PlotlyRenderer()
        return renderer.render(
            prepared.documents[0],
            prepared.document_datasets[0],
            output_path=resolved_output,
        )
    raise TemplateValidationError(
        f"Unsupported render backend {prepared.spec.render_backend!r}. "
        "Supported backends: matplotlib, plotly."
    )


def render_from_logfile(
    logfile_path: str | Path,
    *,
    output_path: str | Path | None = None,
) -> RenderResult:
    """Load a logfile spec, resolve datasets, and render its configured output."""
    prepared = prepare_logfile_render(logfile_path)
    return render_prepared_logfile(prepared, output_path=output_path)
