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

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..errors import DatasetValidationError
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
        self.validate()

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

    def validate(self) -> None:
        if not str(self.mnemonic).strip():
            raise DatasetValidationError("Channel mnemonic cannot be empty.")
        if not str(self.depth_unit).strip():
            raise DatasetValidationError(f"Channel {self.mnemonic} must declare a depth unit.")
        depth = np.asarray(self.depth, dtype=float)
        if depth.ndim != 1:
            raise DatasetValidationError(
                f"Channel {self.mnemonic} depth axis must be 1D, got shape {depth.shape}."
            )
        if depth.size == 0:
            raise DatasetValidationError(f"Channel {self.mnemonic} depth axis cannot be empty.")
        diffs = np.diff(depth)
        monotonic_up = np.all(diffs >= 0)
        monotonic_down = np.all(diffs <= 0)
        if not (monotonic_up or monotonic_down):
            raise DatasetValidationError(f"Depth for {self.mnemonic} must be monotonic.")


@dataclass(slots=True)
class ScalarChannel(BaseChannel):
    values: np.ndarray = field(default_factory=lambda: np.asarray([], dtype=float))

    def __post_init__(self) -> None:
        self.values = _as_float_array(self.values, name="values", ndim=1)
        BaseChannel.__post_init__(self)

    def masked_values(self) -> np.ndarray:
        masked = self.values.astype(float, copy=True)
        if self.null_value is not None:
            masked[np.isclose(masked, self.null_value, equal_nan=False)] = np.nan
        return masked

    def validate(self) -> None:
        BaseChannel.validate(self)
        values = np.asarray(self.values, dtype=float)
        if values.ndim != 1:
            raise DatasetValidationError(
                f"Scalar channel {self.mnemonic} values must be 1D, got shape {values.shape}."
            )
        if values.shape[0] != np.asarray(self.depth, dtype=float).shape[0]:
            raise DatasetValidationError(
                f"Scalar channel {self.mnemonic} depth/value length mismatch: "
                f"{np.asarray(self.depth, dtype=float).shape[0]} vs {values.shape[0]}."
            )


@dataclass(slots=True)
class ArrayChannel(BaseChannel):
    values: np.ndarray = field(default_factory=lambda: np.empty((0, 0), dtype=float))
    sample_axis: np.ndarray = field(default_factory=lambda: np.asarray([], dtype=float))
    sample_unit: str | None = None
    sample_label: str = "sample"

    def __post_init__(self) -> None:
        self.values = _as_float_array(self.values, name="values", ndim=2)
        self.sample_axis = _as_float_array(self.sample_axis, name="sample_axis", ndim=1)
        BaseChannel.__post_init__(self)

    def validate(self) -> None:
        BaseChannel.validate(self)
        values = np.asarray(self.values, dtype=float)
        sample_axis = np.asarray(self.sample_axis, dtype=float)
        depth = np.asarray(self.depth, dtype=float)
        if values.ndim != 2:
            raise DatasetValidationError(
                f"Array channel {self.mnemonic} values must be 2D, got shape {values.shape}."
            )
        if sample_axis.ndim != 1:
            raise DatasetValidationError(
                f"Array channel {self.mnemonic} sample axis must be 1D, "
                f"got shape {sample_axis.shape}."
            )
        if values.shape[0] != depth.shape[0]:
            raise DatasetValidationError(
                f"Array channel {self.mnemonic} must have one row per depth sample."
            )
        if values.shape[1] != sample_axis.shape[0]:
            raise DatasetValidationError(
                f"Array channel {self.mnemonic} sample axis length must match column count."
            )


@dataclass(slots=True)
class RasterChannel(ArrayChannel):
    colormap: str = "viridis"
