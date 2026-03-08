from __future__ import annotations

from dataclasses import dataclass, replace

from .errors import LayoutError
from .model import LogDocument, PageSpec, TrackSpec, WellDataset
from .units import DEFAULT_UNITS, SimpleUnitRegistry


@dataclass(slots=True, frozen=True)
class DepthWindow:
    page_number: int
    start: float
    stop: float
    unit: str


@dataclass(slots=True, frozen=True)
class Frame:
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float


@dataclass(slots=True, frozen=True)
class TrackFrame:
    track: TrackSpec
    frame: Frame


@dataclass(slots=True, frozen=True)
class PageLayout:
    page_number: int
    page: PageSpec
    depth_window: DepthWindow
    header_frame: Frame
    track_header_frames: tuple[TrackFrame, ...]
    footer_frame: Frame
    track_frames: tuple[TrackFrame, ...]


class LayoutEngine:
    def __init__(self, registry: SimpleUnitRegistry = DEFAULT_UNITS) -> None:
        self.registry = registry

    def depth_units_per_mm(self, document: LogDocument) -> float:
        return self.registry.convert(
            float(document.depth_axis.scale_ratio),
            "mm",
            document.depth_axis.unit,
        )

    def depth_span_per_page(self, document: LogDocument) -> float:
        return self.depth_units_per_mm(document) * document.page.plot_height_mm

    def paginate(self, document: LogDocument, dataset: WellDataset) -> tuple[DepthWindow, ...]:
        start, stop = document.resolve_depth_range(dataset, self.registry)
        span = self.depth_span_per_page(document)
        if span <= 0:
            raise LayoutError("Depth span per page must be positive.")

        windows = []
        cursor = start
        page_number = 1
        while cursor < stop:
            page_stop = min(cursor + span, stop)
            windows.append(
                DepthWindow(
                    page_number=page_number,
                    start=cursor,
                    stop=page_stop,
                    unit=document.depth_axis.unit,
                )
            )
            cursor = page_stop
            page_number += 1
        return tuple(windows)

    def track_frames(self, document: LogDocument) -> tuple[TrackFrame, ...]:
        return self._track_frames_for_page(document, document.page)

    def _track_frames_for_page(
        self, document: LogDocument, page: PageSpec
    ) -> tuple[TrackFrame, ...]:
        plot_height = page.plot_height_mm
        total_width = sum(track.width_mm for track in document.tracks)
        total_gaps = max(len(document.tracks) - 1, 0) * page.track_gap_mm
        required_width = total_width + total_gaps
        if required_width > page.usable_width_mm + 1e-9:
            raise LayoutError(
                "Tracks require "
                f"{required_width:.1f} mm but only {page.usable_width_mm:.1f} mm "
                "are available."
            )

        x_cursor = page.margin_left_mm
        y_origin = page.plot_top_mm
        frames = []
        for track in document.tracks:
            frame = Frame(
                x_mm=x_cursor,
                y_mm=y_origin,
                width_mm=track.width_mm,
                height_mm=plot_height,
            )
            frames.append(TrackFrame(track=track, frame=frame))
            x_cursor += track.width_mm + page.track_gap_mm
        return tuple(frames)

    def _page_with_plot_height(self, page: PageSpec, plot_height_mm: float) -> PageSpec:
        if plot_height_mm <= 0:
            raise LayoutError("Continuous mode requires a positive depth span.")
        height_mm = (
            page.margin_top_mm
            + page.header_height_mm
            + page.track_header_height_mm
            + plot_height_mm
            + page.footer_height_mm
            + page.margin_bottom_mm
        )
        return replace(page, height_mm=height_mm)

    def layout(self, document: LogDocument, dataset: WellDataset) -> tuple[PageLayout, ...]:
        start, stop = document.resolve_depth_range(dataset, self.registry)
        page = document.page

        if page.continuous:
            units_per_mm = self.depth_units_per_mm(document)
            depth_span = stop - start
            if units_per_mm <= 0:
                raise LayoutError("Depth units per mm must be positive.")
            page = self._page_with_plot_height(page, depth_span / units_per_mm)
            windows = (
                DepthWindow(
                    page_number=1,
                    start=start,
                    stop=stop,
                    unit=document.depth_axis.unit,
                ),
            )
        else:
            windows = self.paginate(document, dataset)

        track_frames = self._track_frames_for_page(document, page)
        track_header_frames = tuple(
            TrackFrame(
                track=track_frame.track,
                frame=Frame(
                    x_mm=track_frame.frame.x_mm,
                    y_mm=page.margin_top_mm + page.header_height_mm,
                    width_mm=track_frame.frame.width_mm,
                    height_mm=page.track_header_height_mm,
                ),
            )
            for track_frame in track_frames
        )
        header_frame = Frame(
            x_mm=page.margin_left_mm,
            y_mm=page.margin_top_mm,
            width_mm=page.usable_width_mm,
            height_mm=page.header_height_mm,
        )
        footer_frame = Frame(
            x_mm=page.margin_left_mm,
            y_mm=page.height_mm - page.margin_bottom_mm - page.footer_height_mm,
            width_mm=page.usable_width_mm,
            height_mm=page.footer_height_mm,
        )
        return tuple(
            PageLayout(
                page_number=window.page_number,
                page=page,
                depth_window=window,
                header_frame=header_frame,
                track_header_frames=track_header_frames,
                footer_frame=footer_frame,
                track_frames=track_frames,
            )
            for window in windows
        )
