from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from ..errors import DependencyUnavailableError
from ..layout import LayoutEngine
from ..model import (
    CurveElement,
    LogDocument,
    RasterChannel,
    RasterElement,
    ScalarChannel,
    ScaleKind,
    TrackHeaderObjectKind,
    WellDataset,
)
from ..units import DEFAULT_UNITS, SimpleUnitRegistry
from .base import Renderer, RenderResult


class MatplotlibRenderer(Renderer):
    def __init__(self, registry: SimpleUnitRegistry = DEFAULT_UNITS, *, dpi: int = 200) -> None:
        if dpi <= 0:
            raise ValueError("Renderer dpi must be positive.")
        self.registry = registry
        self.layout_engine = LayoutEngine(registry)
        self.dpi = dpi

    def render(
        self,
        document: LogDocument,
        dataset: WellDataset,
        *,
        output_path: str | Path | None = None,
    ) -> RenderResult:
        output = Path(output_path) if output_path is not None else None

        try:
            import matplotlib

            # Use a non-GUI backend when writing files or when no display is available.
            if output is not None or not os.environ.get("DISPLAY"):
                matplotlib.use("Agg", force=True)
            import matplotlib.pyplot as plt
            from matplotlib.backends.backend_pdf import PdfPages
        except ImportError as exc:
            raise DependencyUnavailableError(
                "Matplotlib is required for static rendering. Install well-log-os[pdf]."
            ) from exc

        layouts = self.layout_engine.layout(document, dataset)
        figures = []
        pdf = None
        if output is not None and output.suffix.lower() == ".pdf":
            pdf = PdfPages(output)

        try:
            for page_layout in layouts:
                fig = plt.figure(
                    figsize=(page_layout.page.width_mm / 25.4, page_layout.page.height_mm / 25.4),
                    dpi=self.dpi,
                )
                self._draw_header(fig, document, dataset, page_layout)
                self._draw_footer(fig, document, page_layout)
                for track_header in page_layout.track_header_frames:
                    ax = fig.add_axes(self._normalize_frame(page_layout.page, track_header.frame))
                    self._draw_track_header(ax, track_header.track, document)
                for track_frame in page_layout.track_frames:
                    ax = fig.add_axes(self._normalize_frame(page_layout.page, track_frame.frame))
                    self._draw_track(ax, track_frame.track, document, dataset, page_layout)
                if pdf is not None:
                    pdf.savefig(fig)
                    plt.close(fig)
                else:
                    figures.append(fig)
        finally:
            if pdf is not None:
                pdf.close()

        artifact = str(output) if output is not None else figures
        return RenderResult(
            backend="matplotlib",
            page_count=len(layouts),
            artifact=artifact,
            output_path=output,
        )

    def _normalize_frame(self, page, frame) -> list[float]:
        left = frame.x_mm / page.width_mm
        bottom = 1.0 - (frame.y_mm + frame.height_mm) / page.height_mm
        width = frame.width_mm / page.width_mm
        height = frame.height_mm / page.height_mm
        return [left, bottom, width, height]

    def _draw_header(self, fig, document, dataset, page_layout) -> None:
        header = document.header
        if header.title:
            fig.text(0.5, 0.98, header.title, ha="center", va="top", fontsize=11, fontweight="bold")
        if header.subtitle:
            fig.text(0.5, 0.955, header.subtitle, ha="center", va="top", fontsize=8)
        if not header.fields:
            return
        start_y = 0.935
        step_y = 0.018
        for index, field in enumerate(header.fields):
            value = dataset.header_value(field.source_key, field.default)
            fig.text(
                0.05,
                start_y - index * step_y,
                f"{field.label}: {value}",
                ha="left",
                va="top",
                fontsize=7,
            )

    def _draw_footer(self, fig, document, page_layout) -> None:
        if not document.footer.lines:
            return
        for index, line in enumerate(document.footer.lines):
            fig.text(0.05, 0.03 + index * 0.012, line, ha="left", va="bottom", fontsize=6)
        fig.text(0.95, 0.02, f"Page {page_layout.page_number}", ha="right", va="bottom", fontsize=6)

    def _draw_track_header(self, ax, track, document) -> None:
        ax.set_facecolor("#e8e8e8")
        ax.set_xticks([])
        ax.set_yticks([])
        self._style_track_frame(ax)
        slots = self._track_header_slots(track)
        for index, (item, slot_top, slot_bottom) in enumerate(slots):
            if index > 0:
                ax.plot(
                    [0.0, 1.0],
                    [slot_top, slot_top],
                    transform=ax.transAxes,
                    color="#9a9a9a",
                    linewidth=0.35,
                )
            if not item.enabled:
                continue
            if item.kind == TrackHeaderObjectKind.TITLE:
                self._draw_track_header_title(ax, track, slot_top, slot_bottom)
            elif item.kind == TrackHeaderObjectKind.SCALE:
                self._draw_track_header_scale(ax, track, document, slot_top, slot_bottom)
            elif item.kind == TrackHeaderObjectKind.LEGEND:
                self._draw_track_header_legend(ax, track, slot_top, slot_bottom)

    def _track_header_slots(self, track) -> tuple[tuple[object, float, float], ...]:
        reserved = track.header.reserved_objects()
        if not reserved:
            return ()
        top = 0.97
        bottom = 0.03
        span = top - bottom
        total_units = sum(item.line_units for item in reserved)
        cursor = top
        slots = []
        for item in reserved:
            item_height = span * (item.line_units / total_units)
            slot_top = cursor
            slot_bottom = cursor - item_height
            slots.append((item, slot_top, slot_bottom))
            cursor = slot_bottom
        return tuple(slots)

    def _slot_font_size(
        self,
        ax,
        slot_top: float,
        slot_bottom: float,
        *,
        min_pt: float,
        max_pt: float,
    ) -> float:
        slot_height_px = max((slot_top - slot_bottom) * ax.bbox.height, 1.0)
        return max(min_pt, min(max_pt, slot_height_px * 0.45))

    def _draw_track_header_title(self, ax, track, slot_top: float, slot_bottom: float) -> None:
        fontsize = self._slot_font_size(ax, slot_top, slot_bottom, min_pt=4.6, max_pt=6.8)
        ax.text(
            0.03,
            0.5 * (slot_top + slot_bottom),
            track.title,
            transform=ax.transAxes,
            ha="left",
            va="center",
            fontsize=fontsize,
            fontweight="bold",
            clip_on=True,
        )

    def _draw_track_header_scale(
        self,
        ax,
        track,
        document,
        slot_top: float,
        slot_bottom: float,
    ) -> None:
        if track.kind.value == "depth":
            scale_text = f"{document.depth_axis.unit} 1:{document.depth_axis.scale_ratio}"
        elif track.x_scale is None:
            scale_text = "Scale: auto"
        else:
            kind = track.x_scale.kind.value.upper()
            scale_text = f"{kind} {track.x_scale.minimum:g} to {track.x_scale.maximum:g}"

        fontsize = self._slot_font_size(ax, slot_top, slot_bottom, min_pt=4.3, max_pt=6.2)
        ax.text(
            0.03,
            0.5 * (slot_top + slot_bottom),
            scale_text,
            transform=ax.transAxes,
            ha="left",
            va="center",
            fontsize=fontsize,
            clip_on=True,
        )

    def _draw_track_header_legend(self, ax, track, slot_top: float, slot_bottom: float) -> None:
        curves = [element for element in track.elements if isinstance(element, CurveElement)]
        if not curves:
            fontsize = self._slot_font_size(ax, slot_top, slot_bottom, min_pt=3.6, max_pt=5.4)
            ax.text(
                0.03,
                0.5 * (slot_top + slot_bottom),
                "-",
                transform=ax.transAxes,
                ha="left",
                va="center",
                fontsize=fontsize,
                clip_on=True,
            )
            return

        slot_height = slot_top - slot_bottom
        row_count = len(curves)
        for index, element in enumerate(curves):
            row_top = slot_top - (index * slot_height / row_count)
            row_bottom = slot_top - ((index + 1) * slot_height / row_count)
            y_center = 0.5 * (row_top + row_bottom)
            fontsize = self._slot_font_size(ax, row_top, row_bottom, min_pt=3.2, max_pt=5.2)
            line_start = 0.04
            line_end = 0.14
            ax.plot(
                [line_start, line_end],
                [y_center, y_center],
                transform=ax.transAxes,
                color=element.style.color,
                linewidth=max(0.75, element.style.line_width),
            )

            label = element.label or element.channel
            available_px = max(ax.bbox.width * 0.78, 1.0)
            approx_char_px = max(fontsize * 0.75, 1.0)
            max_chars = max(4, int(available_px / approx_char_px))
            if len(label) > max_chars:
                label = f"{label[: max_chars - 3]}..."

            ax.text(
                0.16,
                y_center,
                label,
                transform=ax.transAxes,
                ha="left",
                va="center",
                fontsize=fontsize,
                clip_on=True,
            )

    def _draw_track(self, ax, track, document, dataset, page_layout) -> None:
        window = page_layout.depth_window
        ax.set_ylim(window.stop, window.start)
        ax.set_facecolor("white")
        ax.set_axisbelow(True)
        self._style_track_frame(ax)
        self._configure_depth_axis(
            ax,
            document,
            show_labels=track.kind.value == "depth",
        )
        self._draw_depth_grid(ax)

        for zone in document.zones:
            if zone.base < window.start or zone.top > window.stop:
                continue
            zone_top = max(zone.top, window.start)
            zone_base = min(zone.base, window.stop)
            ax.axhspan(zone_top, zone_base, color=zone.fill_color, alpha=zone.alpha, linewidth=0)
        for marker in document.markers:
            if marker.depth < window.start or marker.depth > window.stop:
                continue
            ax.axhline(marker.depth, color=marker.color, linestyle=marker.line_style, linewidth=0.6)

        if track.kind.value == "depth":
            ax.set_facecolor("#f2f2f2")
            ax.set_xlim(0, 1)
            ax.set_xticks([])
            ax.tick_params(axis="y", labelsize=6, colors="#333333")
            self._draw_marker_callouts(ax, document, window)
            return

        for element in track.elements:
            if isinstance(element, CurveElement):
                self._draw_curve(ax, track, element, document, dataset)
            elif isinstance(element, RasterElement):
                self._draw_raster(ax, track, element, document, dataset)

        self._configure_x_axis(ax, track)
        self._apply_scale(ax, track)
        ax.grid(
            track.grid.major,
            axis="x",
            which="major",
            alpha=track.grid.major_alpha,
            linewidth=0.45,
        )
        ax.grid(
            track.grid.minor,
            axis="x",
            which="minor",
            alpha=track.grid.minor_alpha,
            linewidth=0.35,
        )
        ax.tick_params(axis="x", labelsize=6)
        ax.xaxis.tick_top()
        ax.tick_params(axis="y", length=0, labelleft=False)

    def _draw_curve(self, ax, track, element, document, dataset) -> None:
        channel = dataset.get_channel(element.channel)
        if not isinstance(channel, ScalarChannel):
            raise TypeError(f"Curve element {element.channel} requires a scalar channel.")
        depth = channel.depth_in(document.depth_axis.unit, self.registry)
        values = channel.masked_values()
        scale = element.scale or track.x_scale
        if scale is None:
            xmin = float(np.nanmin(values))
            xmax = float(np.nanmax(values))
        else:
            xmin = scale.minimum
            xmax = scale.maximum
        if scale is not None and scale.kind == ScaleKind.LOG:
            ax.set_xscale("log")
            valid = values > 0
            ax.plot(
                values[valid],
                depth[valid],
                color=element.style.color,
                linewidth=element.style.line_width,
            )
        else:
            ax.plot(
                values,
                depth,
                color=element.style.color,
                linewidth=element.style.line_width,
                linestyle=element.style.line_style,
                alpha=element.style.opacity,
            )
        if scale is not None and scale.reverse:
            ax.set_xlim(xmax, xmin)
        else:
            ax.set_xlim(xmin, xmax)

    def _draw_raster(self, ax, track, element, document, dataset) -> None:
        channel = dataset.get_channel(element.channel)
        if not isinstance(channel, RasterChannel):
            raise TypeError(f"Raster element {element.channel} requires a raster channel.")
        depth = channel.depth_in(document.depth_axis.unit, self.registry)
        extent = [
            float(channel.sample_axis[0]),
            float(channel.sample_axis[-1]),
            float(depth[-1]),
            float(depth[0]),
        ]
        image_kwargs = {
            "aspect": "auto",
            "extent": extent,
            "cmap": element.style.colormap,
            "interpolation": element.interpolation,
            "origin": "upper",
        }
        if element.color_limits is not None:
            image_kwargs["vmin"], image_kwargs["vmax"] = element.color_limits
        ax.imshow(channel.values.T, **image_kwargs)
        if track.x_scale is not None:
            if track.x_scale.reverse:
                ax.set_xlim(track.x_scale.maximum, track.x_scale.minimum)
            else:
                ax.set_xlim(track.x_scale.minimum, track.x_scale.maximum)

    def _apply_scale(self, ax, track) -> None:
        if track.x_scale is None:
            return
        scale = track.x_scale
        if scale.kind == ScaleKind.LOG:
            ax.set_xscale("log")
        if scale.reverse:
            ax.set_xlim(scale.maximum, scale.minimum)
        else:
            ax.set_xlim(scale.minimum, scale.maximum)

    def _configure_depth_axis(self, ax, document, *, show_labels: bool) -> None:
        import matplotlib.ticker as mticker

        major_step = max(document.depth_axis.major_step, document.depth_axis.minor_step)
        minor_step = document.depth_axis.minor_step
        ax.yaxis.set_major_locator(mticker.MultipleLocator(major_step))
        ax.yaxis.set_minor_locator(mticker.MultipleLocator(minor_step))
        ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f"))
        ax.tick_params(axis="y", which="major", length=0, labelleft=show_labels)
        ax.tick_params(axis="y", which="minor", length=0, labelleft=False)

    def _configure_x_axis(self, ax, track) -> None:
        import matplotlib.ticker as mticker

        if track.x_scale is not None and track.x_scale.kind == ScaleKind.LOG:
            ax.set_xscale("log")
            ax.xaxis.set_minor_locator(mticker.LogLocator(base=10.0, subs=np.arange(2, 10) * 0.1))
            ax.xaxis.set_minor_formatter(mticker.NullFormatter())
            return

        ax.xaxis.set_minor_locator(mticker.AutoMinorLocator())

    def _draw_depth_grid(self, ax) -> None:
        ax.grid(True, axis="y", which="major", color="#5f5f5f", linewidth=0.65, alpha=0.9)
        ax.grid(True, axis="y", which="minor", color="#b6b6b6", linewidth=0.3, alpha=0.9)

    def _style_track_frame(self, ax) -> None:
        for spine in ax.spines.values():
            spine.set_color("#2f2f2f")
            spine.set_linewidth(0.8)

    def _draw_marker_callouts(self, ax, document, window) -> None:
        if not document.markers:
            return
        from matplotlib.transforms import blended_transform_factory

        transform = blended_transform_factory(ax.transAxes, ax.transData)
        y_offset = max(document.depth_axis.minor_step * 0.4, 1.0)
        for marker in document.markers:
            if marker.depth < window.start or marker.depth > window.stop:
                continue
            if not marker.label:
                continue
            ax.annotate(
                marker.label,
                xy=(0.03, marker.depth),
                xycoords=transform,
                xytext=(0.7, marker.depth - y_offset),
                textcoords=transform,
                fontsize=5.8,
                color="#222222",
                ha="left",
                va="center",
                arrowprops={
                    "arrowstyle": "-|>",
                    "color": marker.color,
                    "lw": 0.7,
                    "shrinkA": 0,
                    "shrinkB": 0,
                },
            )
