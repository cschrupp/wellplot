from __future__ import annotations

from pathlib import Path

from .errors import TemplateValidationError
from .logfile import build_documents_for_logfile, load_dataset_for_logfile, load_logfile
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


def render_from_logfile(
    logfile_path: str | Path,
    *,
    output_path: str | Path | None = None,
) -> RenderResult:
    resolved_logfile = Path(logfile_path).resolve()
    spec = load_logfile(resolved_logfile)
    dataset, source_path = load_dataset_for_logfile(spec, base_dir=resolved_logfile.parent)
    documents = build_documents_for_logfile(spec, dataset, source_path=source_path)
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
        return renderer.render_documents(documents, dataset, output_path=resolved_output)
    elif spec.render_backend == "plotly":
        if len(documents) > 1:
            raise TemplateValidationError(
                "Plotly backend currently supports a single log section. "
                "Use matplotlib for multisection rendering."
            )
        renderer = PlotlyRenderer()
        return renderer.render(documents[0], dataset, output_path=resolved_output)
    else:
        raise TemplateValidationError(
            f"Unsupported render backend {spec.render_backend!r}. "
            "Supported backends: matplotlib, plotly."
        )
