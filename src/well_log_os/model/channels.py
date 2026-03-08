from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..units import DEFAULT_UNITS, SimpleUnitRegistry

ChannelMetadata = dict[str, Any]


def _as_float_array(values: Any, *, name: str, ndim: int) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim != ndim:
        raise ValueError(f"{name} must be a {ndim}D array, got shape {array.shape}.")
    if array.size == 0:
        raise ValueError(f"{name} cannot be empty.")
    return array


@dataclass(slots=True)
class BaseChannel:
    mnemonic: str
    depth: np.ndarray
    depth_unit: str
    value_unit: str | None = None
    description: str = ""
    null_value: float | None = None
    source: str | None = None
    metadata: ChannelMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.depth = _as_float_array(self.depth, name="depth", ndim=1)
        diffs = np.diff(self.depth)
        monotonic_up = np.all(diffs >= 0)
        monotonic_down = np.all(diffs <= 0)
        if not (monotonic_up or monotonic_down):
            raise ValueError(f"Depth for {self.mnemonic} must be monotonic.")

    @property
    def depth_min(self) -> float:
        return float(np.nanmin(self.depth))

    @property
    def depth_max(self) -> float:
        return float(np.nanmax(self.depth))

    def depth_in(self, unit: str, registry: SimpleUnitRegistry = DEFAULT_UNITS) -> np.ndarray:
        if registry.normalize(self.depth_unit) == registry.normalize(unit):
            return self.depth.copy()
        return np.asarray([registry.convert(value, self.depth_unit, unit) for value in self.depth])


@dataclass(slots=True)
class ScalarChannel(BaseChannel):
    values: np.ndarray = field(default_factory=lambda: np.asarray([], dtype=float))

    def __post_init__(self) -> None:
        BaseChannel.__post_init__(self)
        self.values = _as_float_array(self.values, name="values", ndim=1)
        if self.values.shape[0] != self.depth.shape[0]:
            raise ValueError(
                f"Scalar channel {self.mnemonic} depth/value length mismatch: "
                f"{self.depth.shape[0]} vs {self.values.shape[0]}."
            )

    def masked_values(self) -> np.ndarray:
        masked = self.values.astype(float, copy=True)
        if self.null_value is not None:
            masked[np.isclose(masked, self.null_value, equal_nan=False)] = np.nan
        return masked


@dataclass(slots=True)
class ArrayChannel(BaseChannel):
    values: np.ndarray = field(default_factory=lambda: np.empty((0, 0), dtype=float))
    sample_axis: np.ndarray = field(default_factory=lambda: np.asarray([], dtype=float))
    sample_unit: str | None = None
    sample_label: str = "sample"

    def __post_init__(self) -> None:
        BaseChannel.__post_init__(self)
        self.values = _as_float_array(self.values, name="values", ndim=2)
        self.sample_axis = _as_float_array(self.sample_axis, name="sample_axis", ndim=1)
        if self.values.shape[0] != self.depth.shape[0]:
            raise ValueError(f"Array channel {self.mnemonic} must have one row per depth sample.")
        if self.values.shape[1] != self.sample_axis.shape[0]:
            raise ValueError(
                f"Array channel {self.mnemonic} sample axis length must match column count."
            )


@dataclass(slots=True)
class RasterChannel(ArrayChannel):
    colormap: str = "viridis"
