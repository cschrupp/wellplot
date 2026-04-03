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

from __future__ import annotations

from pathlib import Path

from .errors import TemplateValidationError
from .logfile import build_documents_for_logfile, load_datasets_for_logfile, load_logfile
from .renderers import MatplotlibRenderer, PlotlyRenderer
from .renderers.base import RenderResult


def _resolve_output_path(
    logfile_path: Path,
    configured_output: str,
    output_override: str | Path | None,
) -> Path:
    output_path = Path(output_override) if output_override is not None else Path(configured_output)
    if not output_path.is_absolute():
        output_path = (logfile_path.parent / output_path).resolve()
    return output_path


def _document_section_id(document) -> str:
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


def render_from_logfile(
    logfile_path: str | Path,
    *,
    output_path: str | Path | None = None,
) -> RenderResult:
    resolved_logfile = Path(logfile_path).resolve()
    spec = load_logfile(resolved_logfile)
    datasets_by_section, source_paths_by_section = load_datasets_for_logfile(
        spec,
        base_dir=resolved_logfile.parent,
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
    resolved_output = _resolve_output_path(resolved_logfile, spec.render_output_path, output_path)

    if spec.render_backend == "matplotlib":
        renderer_kwargs = {"dpi": spec.render_dpi}
        if spec.render_continuous_strip_page_height_mm is not None:
            renderer_kwargs["continuous_strip_page_height_mm"] = (
                spec.render_continuous_strip_page_height_mm
            )
        matplotlib_style = spec.render_matplotlib.get("style")
        if matplotlib_style is not None:
            renderer_kwargs["style"] = matplotlib_style
        renderer = MatplotlibRenderer(**renderer_kwargs)
        return renderer.render_documents(documents, document_datasets, output_path=resolved_output)
    elif spec.render_backend == "plotly":
        if len(documents) > 1:
            raise TemplateValidationError(
                "Plotly backend currently supports a single log section. "
                "Use matplotlib for multisection rendering."
            )
        renderer = PlotlyRenderer()
        return renderer.render(documents[0], document_datasets[0], output_path=resolved_output)
    else:
        raise TemplateValidationError(
            f"Unsupported render backend {spec.render_backend!r}. "
            "Supported backends: matplotlib, plotly."
        )
