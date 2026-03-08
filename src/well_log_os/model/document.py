from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from ..errors import TemplateValidationError
from ..units import DEFAULT_UNITS, SimpleUnitRegistry
from .dataset import WellDataset


class TrackKind(StrEnum):
    DEPTH = "depth"
    CURVE = "curve"
    IMAGE = "image"


class ScaleKind(StrEnum):
    LINEAR = "linear"
    LOG = "log"


class TrackHeaderObjectKind(StrEnum):
    TITLE = "title"
    SCALE = "scale"
    LEGEND = "legend"


@dataclass(slots=True)
class StyleSpec:
    color: str = "black"
    line_width: float = 0.8
    line_style: str = "-"
    opacity: float = 1.0
    fill_color: str | None = None
    fill_alpha: float = 0.2
    colormap: str = "viridis"


@dataclass(slots=True)
class ScaleSpec:
    kind: ScaleKind = ScaleKind.LINEAR
    minimum: float = 0.0
    maximum: float = 1.0
    reverse: bool = False

    def __post_init__(self) -> None:
        if self.minimum == self.maximum:
            raise ValueError("Scale minimum and maximum must differ.")
        if self.kind == ScaleKind.LOG and (self.minimum <= 0 or self.maximum <= 0):
            raise ValueError("Log scales require positive bounds.")


@dataclass(slots=True)
class GridSpec:
    major: bool = True
    minor: bool = True
    major_alpha: float = 0.35
    minor_alpha: float = 0.15


@dataclass(slots=True, frozen=True)
class TrackHeaderObjectSpec:
    kind: TrackHeaderObjectKind
    enabled: bool = True
    reserve_space: bool = True
    line_units: int = 1

    def __post_init__(self) -> None:
        if self.line_units <= 0:
            raise ValueError("Track header object line_units must be positive.")


def _default_track_header_objects() -> tuple[TrackHeaderObjectSpec, ...]:
    return (
        TrackHeaderObjectSpec(kind=TrackHeaderObjectKind.TITLE, line_units=1),
        TrackHeaderObjectSpec(kind=TrackHeaderObjectKind.SCALE, line_units=1),
        TrackHeaderObjectSpec(kind=TrackHeaderObjectKind.LEGEND, line_units=2),
    )


@dataclass(slots=True)
class TrackHeaderSpec:
    objects: tuple[TrackHeaderObjectSpec, ...] = field(
        default_factory=_default_track_header_objects
    )

    def __post_init__(self) -> None:
        if not self.objects:
            raise ValueError("Track header must contain at least one object.")
        kinds = [item.kind for item in self.objects]
        if len(set(kinds)) != len(kinds):
            raise ValueError("Track header object kinds must be unique per track.")

    def reserved_objects(self) -> tuple[TrackHeaderObjectSpec, ...]:
        return tuple(item for item in self.objects if item.reserve_space)


@dataclass(slots=True)
class CurveElement:
    channel: str
    label: str | None = None
    style: StyleSpec = field(default_factory=StyleSpec)
    scale: ScaleSpec | None = None


@dataclass(slots=True)
class RasterElement:
    channel: str
    style: StyleSpec = field(default_factory=StyleSpec)
    interpolation: str = "nearest"
    color_limits: tuple[float, float] | None = None


TrackElement = CurveElement | RasterElement


@dataclass(slots=True)
class HeaderField:
    label: str
    source_key: str
    default: str = ""


@dataclass(slots=True)
class HeaderSpec:
    title: str | None = None
    subtitle: str | None = None
    fields: tuple[HeaderField, ...] = ()


@dataclass(slots=True)
class FooterSpec:
    lines: tuple[str, ...] = ()


@dataclass(slots=True)
class MarkerSpec:
    depth: float
    label: str
    color: str = "#666666"
    line_style: str = "--"


@dataclass(slots=True)
class ZoneSpec:
    top: float
    base: float
    label: str
    fill_color: str = "#d9d9d9"
    alpha: float = 0.25

    def __post_init__(self) -> None:
        if self.base <= self.top:
            raise ValueError("Zone base must be greater than top.")


_PAGE_SIZES_MM = {
    "A4": (210.0, 297.0),
    "LETTER": (215.9, 279.4),
}


@dataclass(slots=True)
class PageSpec:
    width_mm: float
    height_mm: float
    continuous: bool = False
    margin_left_mm: float = 10.0
    margin_right_mm: float = 10.0
    margin_top_mm: float = 10.0
    margin_bottom_mm: float = 10.0
    header_height_mm: float = 18.0
    track_header_height_mm: float = 8.0
    footer_height_mm: float = 10.0
    track_gap_mm: float = 1.5

    @classmethod
    def from_name(cls, name: str, orientation: str = "portrait", **kwargs: Any) -> PageSpec:
        size_name = name.strip().upper()
        if size_name not in _PAGE_SIZES_MM:
            raise TemplateValidationError(f"Unsupported page size {name!r}.")
        width_mm, height_mm = _PAGE_SIZES_MM[size_name]
        if orientation.strip().lower() == "landscape":
            width_mm, height_mm = height_mm, width_mm
        return cls(width_mm=width_mm, height_mm=height_mm, **kwargs)

    @property
    def usable_width_mm(self) -> float:
        return self.width_mm - self.margin_left_mm - self.margin_right_mm

    @property
    def plot_top_mm(self) -> float:
        return self.margin_top_mm + self.header_height_mm + self.track_header_height_mm

    @property
    def plot_height_mm(self) -> float:
        return (
            self.height_mm
            - self.margin_top_mm
            - self.margin_bottom_mm
            - self.header_height_mm
            - self.track_header_height_mm
            - self.footer_height_mm
        )


@dataclass(slots=True)
class DepthAxisSpec:
    unit: str = "m"
    scale_ratio: int = 200
    major_step: float = 10.0
    minor_step: float = 2.0

    def __post_init__(self) -> None:
        if self.scale_ratio <= 0:
            raise ValueError("Depth scale ratio must be positive.")
        if self.major_step <= 0 or self.minor_step <= 0:
            raise ValueError("Depth tick steps must be positive.")


@dataclass(slots=True)
class TrackSpec:
    id: str
    title: str
    kind: TrackKind
    width_mm: float
    elements: tuple[TrackElement, ...] = ()
    x_scale: ScaleSpec | None = None
    header: TrackHeaderSpec = field(default_factory=TrackHeaderSpec)
    grid: GridSpec = field(default_factory=GridSpec)

    def __post_init__(self) -> None:
        if self.width_mm <= 0:
            raise ValueError(f"Track {self.id} width must be positive.")
        if self.kind == TrackKind.CURVE:
            invalid = [element for element in self.elements if isinstance(element, RasterElement)]
            if invalid:
                raise ValueError(
                    f"Curve track {self.id} cannot contain raster elements. "
                    "Use an image track instead."
                )
        if self.kind == TrackKind.DEPTH and self.elements:
            raise ValueError(f"Depth track {self.id} does not accept elements.")


@dataclass(slots=True)
class LogDocument:
    name: str
    page: PageSpec
    depth_axis: DepthAxisSpec
    tracks: tuple[TrackSpec, ...]
    depth_range: tuple[float, float] | None = None
    header: HeaderSpec = field(default_factory=HeaderSpec)
    footer: FooterSpec = field(default_factory=FooterSpec)
    markers: tuple[MarkerSpec, ...] = ()
    zones: tuple[ZoneSpec, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.tracks:
            raise ValueError("A log document must contain at least one track.")

    def resolve_depth_range(
        self,
        dataset: WellDataset,
        registry: SimpleUnitRegistry = DEFAULT_UNITS,
    ) -> tuple[float, float]:
        if self.depth_range is not None:
            top, base = self.depth_range
        else:
            top, base = dataset.depth_range(self.depth_axis.unit, registry)
        return min(top, base), max(top, base)
