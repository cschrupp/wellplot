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

"""Dataset container and alignment helpers for log channels."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import ArrayLike

from ..errors import DatasetValidationError
from ..units import DEFAULT_UNITS, SimpleUnitRegistry
from .channels import ArrayChannel, BaseChannel, RasterChannel, ScalarChannel


def _require_pandas() -> object:
    try:
        import pandas as pd
    except ModuleNotFoundError as exc:
        raise ImportError(
            "pandas adapters require pandas to be installed. "
            "Install the optional pandas dependency to use add_series/add_dataframe."
        ) from exc
    return pd


def _normalized_mnemonics(
    dataset: WellDataset,
    channels: Iterable[str] | None,
) -> list[str]:
    if channels is None:
        return list(dataset.channels)
    selected = [str(mnemonic).strip() for mnemonic in channels]
    missing = [mnemonic for mnemonic in selected if mnemonic not in dataset.channels]
    if missing:
        joined = ", ".join(repr(mnemonic) for mnemonic in missing)
        raise DatasetValidationError(f"Dataset is missing requested channels: {joined}.")
    return selected


def _normalized_collision_policy(
    *,
    replace: bool,
    collision: str | None,
) -> str:
    if collision is None:
        return "replace" if replace else "error"
    normalized = str(collision).strip().lower()
    if normalized not in {"error", "replace", "rename", "skip"}:
        raise DatasetValidationError(
            "merge collision must be one of: error, replace, rename, skip."
        )
    if replace and normalized != "replace":
        raise DatasetValidationError(
            "merge replace=True cannot be combined with collision policies other than replace."
        )
    return normalized


def _resolved_renamed_mnemonic(
    dataset: WellDataset,
    *,
    mnemonic: str,
    source_dataset: str,
    rename_template: str,
) -> str:
    template = str(rename_template).strip()
    if not template:
        raise DatasetValidationError("merge rename_template must be non-empty.")
    base = template.format(mnemonic=mnemonic, dataset=source_dataset).strip()
    if not base:
        raise DatasetValidationError("merge rename_template produced an empty mnemonic.")
    if base not in dataset.channels:
        return base
    counter = 2
    while True:
        candidate = f"{base}_{counter}"
        if candidate not in dataset.channels:
            return candidate
        counter += 1


def _sorted_channel(channel: BaseChannel, *, ascending: bool) -> BaseChannel:
    updated = deepcopy(channel)
    order = np.argsort(updated.depth)
    if not ascending:
        order = order[::-1]
    updated.depth = np.asarray(updated.depth, dtype=float)[order]
    if isinstance(updated, ScalarChannel):
        updated.values = np.asarray(updated.values, dtype=float)[order]
    else:
        updated.values = np.asarray(updated.values, dtype=float)[order, :]
    updated.validate()
    return updated


def _convert_channel_index_unit(
    channel: BaseChannel,
    *,
    unit: str,
    registry: SimpleUnitRegistry,
) -> BaseChannel:
    updated = deepcopy(channel)
    updated.depth = channel.depth_in(unit, registry)
    updated.depth_unit = unit
    updated.validate()
    return updated


def _deduplicate_sorted_axis(
    axis: np.ndarray,
    values: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    unique_axis, indices = np.unique(axis, return_index=True)
    if values.ndim == 1:
        return unique_axis, values[indices]
    return unique_axis, values[indices, :]


def _reindex_scalar_values(
    source_index: np.ndarray,
    values: np.ndarray,
    target_index: np.ndarray,
    *,
    method: str,
) -> np.ndarray:
    valid = np.isfinite(source_index) & np.isfinite(values)
    index = source_index[valid]
    data = values[valid]
    if index.size == 0:
        return np.full(target_index.shape, np.nan, dtype=float)
    index, data = _deduplicate_sorted_axis(index, data)
    if index.size == 1:
        result = np.full(target_index.shape, np.nan, dtype=float)
        result[np.isclose(target_index, index[0])] = data[0]
        return result
    if method == "linear":
        return np.interp(target_index, index, data, left=np.nan, right=np.nan)
    if method == "nearest":
        result = np.full(target_index.shape, np.nan, dtype=float)
        insertion = np.searchsorted(index, target_index)
        left = np.clip(insertion - 1, 0, index.size - 1)
        right = np.clip(insertion, 0, index.size - 1)
        choose_right = np.abs(index[right] - target_index) < np.abs(target_index - index[left])
        nearest = np.where(choose_right, right, left)
        in_bounds = (target_index >= index[0]) & (target_index <= index[-1])
        result[in_bounds] = data[nearest[in_bounds]]
        return result
    raise DatasetValidationError("reindex_to method must be linear or nearest.")


def _reindex_channel(
    channel: BaseChannel,
    *,
    target_index: np.ndarray,
    target_unit: str,
    method: str,
    registry: SimpleUnitRegistry,
) -> BaseChannel:
    source_index = channel.depth_in(target_unit, registry)
    order = np.argsort(source_index)
    source_index = source_index[order]
    updated = deepcopy(channel)
    updated.depth = np.asarray(target_index, dtype=float)
    updated.depth_unit = target_unit
    if isinstance(updated, ScalarChannel):
        values = updated.masked_values()[order]
        updated.values = _reindex_scalar_values(
            source_index,
            values,
            target_index,
            method=method,
        )
    else:
        values = np.asarray(updated.values, dtype=float)[order, :]
        columns = [
            _reindex_scalar_values(
                source_index,
                values[:, column_index],
                target_index,
                method=method,
            )
            for column_index in range(values.shape[1])
        ]
        updated.values = np.column_stack(columns)
    updated.validate()
    return updated


def _merged_channel_copy(
    channel: BaseChannel,
    *,
    source_dataset: str,
    final_mnemonic: str,
    collision_policy: str,
) -> BaseChannel:
    updated = deepcopy(channel)
    updated.metadata = dict(updated.metadata)
    updated.metadata["merged_from_dataset"] = source_dataset
    updated.metadata["merged_from_channel"] = channel.mnemonic
    updated.metadata["merge_collision_policy"] = collision_policy
    if final_mnemonic != channel.mnemonic:
        updated.metadata["original_mnemonic"] = channel.mnemonic
    updated.mnemonic = final_mnemonic
    updated.validate()
    return updated


@dataclass(slots=True)
class WellDataset:
    """Collection of channels plus well metadata and provenance."""

    name: str
    channels: dict[str, BaseChannel] = field(default_factory=dict)
    well_metadata: dict[str, object] = field(default_factory=dict)
    provenance: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate the dataset immediately after dataclass construction."""
        self.validate()

    def add_channel(self, channel: BaseChannel, *, replace: bool = True) -> BaseChannel:
        """Insert a channel object into the dataset."""
        channel.validate()
        if not replace and channel.mnemonic in self.channels:
            raise DatasetValidationError(
                f"Dataset {self.name!r} already has a channel named {channel.mnemonic!r}."
            )
        self.channels[channel.mnemonic] = channel
        return channel

    def add_or_replace_channel(self, channel: BaseChannel) -> BaseChannel:
        """Insert a channel, replacing any existing channel with the same mnemonic."""
        return self.add_channel(channel, replace=True)

    def rename_channel(self, mnemonic: str, new_mnemonic: str) -> BaseChannel:
        """Rename an existing channel and update the internal lookup key."""
        current = str(mnemonic).strip()
        updated_name = str(new_mnemonic).strip()
        if not current or not updated_name:
            raise DatasetValidationError("rename_channel requires non-empty mnemonics.")
        if current not in self.channels:
            raise DatasetValidationError(f"Dataset {self.name!r} is missing channel {current!r}.")
        if updated_name in self.channels and updated_name != current:
            raise DatasetValidationError(
                f"Dataset {self.name!r} already has a channel named {updated_name!r}."
            )
        channel = self.channels.pop(current)
        channel.mnemonic = updated_name
        channel.validate()
        self.channels[updated_name] = channel
        return channel

    def add_curve(
        self,
        *,
        mnemonic: str,
        values: ArrayLike,
        index: ArrayLike,
        index_unit: str,
        value_unit: str | None = None,
        description: str = "",
        null_value: float | None = None,
        source: str | None = None,
        metadata: dict[str, object] | None = None,
        replace: bool = True,
    ) -> ScalarChannel:
        """Construct and insert a scalar channel from values plus an index."""
        channel = ScalarChannel(
            mnemonic=mnemonic,
            depth=index,
            depth_unit=index_unit,
            values=values,
            value_unit=value_unit,
            description=description,
            null_value=null_value,
            source=source,
            metadata=dict(metadata or {}),
        )
        return self.add_channel(channel, replace=replace)

    def add_array(
        self,
        *,
        mnemonic: str,
        values: ArrayLike,
        index: ArrayLike,
        index_unit: str,
        sample_axis: ArrayLike,
        sample_unit: str | None = None,
        sample_label: str = "sample",
        value_unit: str | None = None,
        description: str = "",
        null_value: float | None = None,
        source: str | None = None,
        metadata: dict[str, object] | None = None,
        replace: bool = True,
    ) -> ArrayChannel:
        """Construct and insert a 2D array channel."""
        channel = ArrayChannel(
            mnemonic=mnemonic,
            depth=index,
            depth_unit=index_unit,
            values=values,
            sample_axis=sample_axis,
            sample_unit=sample_unit,
            sample_label=sample_label,
            value_unit=value_unit,
            description=description,
            null_value=null_value,
            source=source,
            metadata=dict(metadata or {}),
        )
        return self.add_channel(channel, replace=replace)

    def add_raster(
        self,
        *,
        mnemonic: str,
        values: ArrayLike,
        index: ArrayLike,
        index_unit: str,
        sample_axis: ArrayLike,
        sample_unit: str | None = None,
        sample_label: str = "sample",
        value_unit: str | None = None,
        description: str = "",
        null_value: float | None = None,
        source: str | None = None,
        metadata: dict[str, object] | None = None,
        colormap: str = "viridis",
        replace: bool = True,
    ) -> RasterChannel:
        """Construct and insert a raster channel."""
        channel = RasterChannel(
            mnemonic=mnemonic,
            depth=index,
            depth_unit=index_unit,
            values=values,
            sample_axis=sample_axis,
            sample_unit=sample_unit,
            sample_label=sample_label,
            value_unit=value_unit,
            description=description,
            null_value=null_value,
            source=source,
            metadata=dict(metadata or {}),
            colormap=colormap,
        )
        return self.add_channel(channel, replace=replace)

    def add_series(
        self,
        *,
        series: object,
        index_unit: str,
        mnemonic: str | None = None,
        index: ArrayLike | None = None,
        value_unit: str | None = None,
        description: str = "",
        null_value: float | None = None,
        source: str | None = None,
        metadata: Mapping[str, object] | None = None,
        replace: bool = True,
    ) -> ScalarChannel:
        """Ingest a pandas Series as a scalar channel."""
        pd = _require_pandas()
        if not isinstance(series, pd.Series):
            raise DatasetValidationError("add_series expects a pandas Series.")
        resolved_mnemonic = str(mnemonic or series.name or "").strip()
        if not resolved_mnemonic:
            raise DatasetValidationError(
                "Series ingestion requires a mnemonic or a non-empty series.name."
            )
        source_index = index if index is not None else series.index.to_numpy()
        return self.add_curve(
            mnemonic=resolved_mnemonic,
            values=series.to_numpy(),
            index=source_index,
            index_unit=index_unit,
            value_unit=value_unit,
            description=description,
            null_value=null_value,
            source=source,
            metadata=dict(metadata or {}),
            replace=replace,
        )

    def add_dataframe(
        self,
        frame: object,
        *,
        index_unit: str,
        index_column: str | None = None,
        use_index: bool = False,
        curves: Mapping[str, Mapping[str, object]] | None = None,
        skip_columns: Iterable[str] | None = None,
        replace: bool = True,
        source: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> list[ScalarChannel]:
        """Ingest selected pandas DataFrame columns as scalar channels."""
        pd = _require_pandas()
        if not isinstance(frame, pd.DataFrame):
            raise DatasetValidationError("add_dataframe expects a pandas DataFrame.")
        if bool(index_column) == bool(use_index):
            raise DatasetValidationError(
                "add_dataframe requires exactly one of index_column or use_index=True."
            )
        if index_column is not None and index_column not in frame.columns:
            raise DatasetValidationError(
                f"Index column {index_column!r} was not found in the DataFrame."
            )
        skip = set(skip_columns or ())
        base_metadata = dict(metadata or {})
        source_index = frame.index.to_numpy() if use_index else frame[index_column].to_numpy()
        selected_columns: list[str]
        if curves is None:
            selected_columns = [column for column in frame.columns if column not in skip]
            if index_column is not None:
                selected_columns = [column for column in selected_columns if column != index_column]
        else:
            selected_columns = list(curves)
            missing = [column for column in selected_columns if column not in frame.columns]
            if missing:
                joined = ", ".join(repr(column) for column in missing)
                raise DatasetValidationError(
                    f"DataFrame is missing requested curve columns: {joined}."
                )
        if not selected_columns:
            raise DatasetValidationError("add_dataframe did not select any columns to ingest.")

        channels: list[ScalarChannel] = []
        for column in selected_columns:
            spec = dict((curves or {}).get(column, {}))
            channel_metadata = dict(base_metadata)
            channel_metadata.update(dict(spec.pop("metadata", {}) or {}))
            channel = self.add_curve(
                mnemonic=str(spec.pop("mnemonic", column)),
                values=frame[column].to_numpy(),
                index=source_index,
                index_unit=index_unit,
                value_unit=spec.pop("value_unit", None),
                description=spec.pop("description", ""),
                null_value=spec.pop("null_value", None),
                source=spec.pop("source", source),
                metadata=channel_metadata,
                replace=spec.pop("replace", replace),
            )
            if spec:
                unknown = ", ".join(sorted(spec))
                raise DatasetValidationError(
                    f"Unsupported DataFrame curve options for column {column!r}: {unknown}."
                )
            channels.append(channel)
        return channels

    def merge(
        self,
        other: WellDataset,
        *,
        replace: bool = False,
        collision: str | None = None,
        rename_template: str = "{mnemonic}_{dataset}",
        merge_well_metadata: bool = False,
        merge_provenance: bool = False,
    ) -> WellDataset:
        """Merge another dataset into this dataset using the selected collision policy."""
        other.validate()
        collision_policy = _normalized_collision_policy(replace=replace, collision=collision)
        history_entry: dict[str, object] = {
            "dataset": other.name,
            "collision": collision_policy,
            "added": [],
            "replaced": [],
            "renamed": {},
            "skipped": [],
        }
        for channel in other.channels.values():
            final_mnemonic = channel.mnemonic
            if final_mnemonic in self.channels:
                if collision_policy == "error":
                    raise DatasetValidationError(
                        f"Dataset {self.name!r} already has a channel named {final_mnemonic!r}."
                    )
                if collision_policy == "skip":
                    history_entry["skipped"].append(final_mnemonic)
                    continue
                if collision_policy == "rename":
                    final_mnemonic = _resolved_renamed_mnemonic(
                        self,
                        mnemonic=channel.mnemonic,
                        source_dataset=other.name,
                        rename_template=rename_template,
                    )
                    history_entry["renamed"][channel.mnemonic] = final_mnemonic
                elif collision_policy == "replace":
                    history_entry["replaced"].append(final_mnemonic)
            merged = _merged_channel_copy(
                channel,
                source_dataset=other.name,
                final_mnemonic=final_mnemonic,
                collision_policy=collision_policy,
            )
            self.add_channel(merged, replace=collision_policy == "replace")
            history_entry["added"].append(final_mnemonic)
        if merge_well_metadata:
            self.well_metadata.update(other.well_metadata)
        if merge_provenance:
            self.provenance.update(other.provenance)
        self.provenance.setdefault("merge_history", []).append(history_entry)
        return self

    def sort_index(
        self,
        *,
        ascending: bool = True,
        channels: Iterable[str] | None = None,
    ) -> WellDataset:
        """Sort selected channels by their reference axis."""
        for mnemonic in _normalized_mnemonics(self, channels):
            self.channels[mnemonic] = _sorted_channel(self.channels[mnemonic], ascending=ascending)
        return self

    def convert_index_unit(
        self,
        unit: str,
        *,
        channels: Iterable[str] | None = None,
        registry: SimpleUnitRegistry = DEFAULT_UNITS,
    ) -> WellDataset:
        """Convert selected channel indices to another unit."""
        normalized_unit = str(unit).strip()
        if not normalized_unit:
            raise DatasetValidationError("convert_index_unit requires a non-empty target unit.")
        for mnemonic in _normalized_mnemonics(self, channels):
            self.channels[mnemonic] = _convert_channel_index_unit(
                self.channels[mnemonic],
                unit=normalized_unit,
                registry=registry,
            )
        return self

    def reindex_to(
        self,
        *,
        channel: str | None = None,
        index: ArrayLike | None = None,
        index_unit: str | None = None,
        method: str = "linear",
        channels: Iterable[str] | None = None,
        registry: SimpleUnitRegistry = DEFAULT_UNITS,
    ) -> WellDataset:
        """Reindex selected channels to another channel or explicit axis."""
        normalized_method = str(method).strip().lower()
        if normalized_method not in {"linear", "nearest"}:
            raise DatasetValidationError("reindex_to method must be linear or nearest.")

        if (channel is None) == (index is None):
            raise DatasetValidationError("reindex_to requires exactly one of channel or index.")
        if channel is not None and index_unit is not None:
            raise DatasetValidationError(
                "reindex_to does not accept index_unit when channel is used as the target axis."
            )

        if channel is not None:
            target_channel_name = str(channel).strip()
            if target_channel_name not in self.channels:
                raise DatasetValidationError(
                    f"Dataset is missing target channel {target_channel_name!r}."
                )
            target_channel = self.channels[target_channel_name]
            target_index = np.asarray(target_channel.depth, dtype=float).copy()
            target_unit = target_channel.depth_unit
        else:
            target_unit = str(index_unit or "").strip()
            if not target_unit:
                raise DatasetValidationError(
                    "reindex_to with an explicit index requires index_unit."
                )
            target_index = np.asarray(index, dtype=float)
            if target_index.ndim != 1 or target_index.size == 0:
                raise DatasetValidationError("reindex_to index must be a non-empty 1D array.")

        for mnemonic in _normalized_mnemonics(self, channels):
            self.channels[mnemonic] = _reindex_channel(
                self.channels[mnemonic],
                target_index=target_index,
                target_unit=target_unit,
                method=normalized_method,
                registry=registry,
            )
        return self

    def get_channel(self, mnemonic: str) -> BaseChannel:
        """Return a channel by mnemonic."""
        return self.channels[mnemonic]

    def depth_range(
        self,
        unit: str,
        registry: SimpleUnitRegistry = DEFAULT_UNITS,
    ) -> tuple[float, float]:
        """Return the dataset top/base range in the requested unit."""
        if not self.channels:
            raise ValueError("Dataset has no channels.")
        mins = []
        maxs = []
        for channel in self.channels.values():
            mins.append(registry.convert(channel.depth_min, channel.depth_unit, unit))
            maxs.append(registry.convert(channel.depth_max, channel.depth_unit, unit))
        return min(mins), max(maxs)

    def header_value(self, key: str, default: object = "") -> object:
        """Return one well-metadata value for header/report population."""
        return self.well_metadata.get(key, default)

    def validate(self) -> None:
        """Validate dataset identity and contained channels."""
        if not str(self.name).strip():
            raise DatasetValidationError("Dataset name cannot be empty.")
        for mnemonic, channel in self.channels.items():
            if mnemonic != channel.mnemonic:
                raise DatasetValidationError(
                    f"Dataset channel key {mnemonic!r} does not match channel mnemonic "
                    f"{channel.mnemonic!r}."
                )
            channel.validate()
