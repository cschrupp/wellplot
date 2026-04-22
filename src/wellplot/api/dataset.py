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

"""Dataset creation and ingestion helpers for programmatic workflows."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from numpy.typing import ArrayLike

from ..model import ArrayChannel, BaseChannel, RasterChannel, ScalarChannel, WellDataset


def create_dataset(
    name: str,
    *,
    well_metadata: Mapping[str, object] | None = None,
    provenance: Mapping[str, object] | None = None,
) -> WellDataset:
    """Create an empty in-memory dataset for programmatic ingestion workflows.

    Use this helper when you want direct access to a mutable :class:`WellDataset`
    without going through the fluent :class:`DatasetBuilder` chain.
    """
    return WellDataset(
        name=name,
        well_metadata=dict(well_metadata or {}),
        provenance=dict(provenance or {}),
    )


class DatasetBuilder:
    """Fluent builder for assembling computed or imported log datasets.

    The builder wraps a mutable :class:`WellDataset` and returns itself from
    every mutating method so notebook and scripting workflows can build a
    dataset step by step before calling :meth:`build`.
    """

    def __init__(
        self,
        *,
        name: str,
        well_metadata: Mapping[str, object] | None = None,
        provenance: Mapping[str, object] | None = None,
    ) -> None:
        """Start a new mutable dataset with optional well metadata and provenance."""
        self._dataset = create_dataset(
            name,
            well_metadata=well_metadata,
            provenance=provenance,
        )

    @property
    def dataset(self) -> WellDataset:
        """Return the mutable dataset currently owned by the builder."""
        return self._dataset

    def build(self) -> WellDataset:
        """Validate the current dataset state and return it.

        This is the point where builder-oriented workflows should stop mutating
        the dataset and start handing it to the layout or render layers.
        """
        self._dataset.validate()
        return self._dataset

    def add_channel(self, channel: BaseChannel, *, replace: bool = True) -> DatasetBuilder:
        """Insert a fully constructed channel object into the dataset."""
        self._dataset.add_channel(channel, replace=replace)
        return self

    def add_or_replace_channel(self, channel: BaseChannel) -> DatasetBuilder:
        """Insert a channel and overwrite any existing mnemonic match."""
        self._dataset.add_or_replace_channel(channel)
        return self

    def rename_channel(self, mnemonic: str, new_mnemonic: str) -> DatasetBuilder:
        """Rename an existing channel in-place before later render binding."""
        self._dataset.rename_channel(mnemonic, new_mnemonic)
        return self

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
        metadata: Mapping[str, object] | None = None,
        replace: bool = True,
    ) -> DatasetBuilder:
        """Add a scalar curve from values plus an index axis.

        This is the normal ingestion path for computed petrophysical curves,
        QC flags, and any other one-dimensional sampled channel.
        """
        self._dataset.add_curve(
            mnemonic=mnemonic,
            values=values,
            index=index,
            index_unit=index_unit,
            value_unit=value_unit,
            description=description,
            null_value=null_value,
            source=source,
            metadata=dict(metadata or {}),
            replace=replace,
        )
        return self

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
        metadata: Mapping[str, object] | None = None,
        replace: bool = True,
    ) -> DatasetBuilder:
        """Add a two-dimensional sampled array channel.

        Use this for waveform-style or image-like channels that have both a
        reference index and a sample axis.
        """
        self._dataset.add_array(
            mnemonic=mnemonic,
            values=values,
            index=index,
            index_unit=index_unit,
            sample_axis=sample_axis,
            sample_unit=sample_unit,
            sample_label=sample_label,
            value_unit=value_unit,
            description=description,
            null_value=null_value,
            source=source,
            metadata=dict(metadata or {}),
            replace=replace,
        )
        return self

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
    ) -> DatasetBuilder:
        """Add a scalar curve from a pandas-style series object.

        The series values become channel values and either the series index or
        an explicit ``index`` argument becomes the reference axis.
        """
        self._dataset.add_series(
            series=series,
            index_unit=index_unit,
            mnemonic=mnemonic,
            index=index,
            value_unit=value_unit,
            description=description,
            null_value=null_value,
            source=source,
            metadata=dict(metadata or {}),
            replace=replace,
        )
        return self

    def add_dataframe(
        self,
        frame: object,
        *,
        index_unit: str,
        index_column: str | None = None,
        use_index: bool = False,
        curves: Mapping[str, Mapping[str, object]] | None = None,
        skip_columns: Sequence[str] | None = None,
        replace: bool = True,
        source: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> DatasetBuilder:
        """Add multiple scalar curves from a pandas-style dataframe.

        Each selected column becomes one curve channel. Use ``curves`` to pass
        per-column metadata and ``index_column`` or ``use_index`` to define the
        reference axis.
        """
        self._dataset.add_dataframe(
            frame,
            index_unit=index_unit,
            index_column=index_column,
            use_index=use_index,
            curves=curves,
            skip_columns=skip_columns,
            replace=replace,
            source=source,
            metadata=dict(metadata or {}),
        )
        return self

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
        metadata: Mapping[str, object] | None = None,
        colormap: str = "viridis",
        replace: bool = True,
    ) -> DatasetBuilder:
        """Add a raster-oriented array channel with display metadata.

        This is a convenience wrapper over :meth:`add_array` that also stores
        colormap metadata used by array-track renderers.
        """
        self._dataset.add_raster(
            mnemonic=mnemonic,
            values=values,
            index=index,
            index_unit=index_unit,
            sample_axis=sample_axis,
            sample_unit=sample_unit,
            sample_label=sample_label,
            value_unit=value_unit,
            description=description,
            null_value=null_value,
            source=source,
            metadata=dict(metadata or {}),
            colormap=colormap,
            replace=replace,
        )
        return self

    def merge(
        self,
        other: WellDataset,
        *,
        replace: bool = False,
        collision: str | None = None,
        rename_template: str = "{mnemonic}_{dataset}",
        merge_well_metadata: bool = False,
        merge_provenance: bool = False,
    ) -> DatasetBuilder:
        """Merge another dataset using the selected collision policy.

        This is the main bridge for workflows that combine raw, derived, and QC
        channels into one working dataset before layout binding.
        """
        self._dataset.merge(
            other,
            replace=replace,
            collision=collision,
            rename_template=rename_template,
            merge_well_metadata=merge_well_metadata,
            merge_provenance=merge_provenance,
        )
        return self

    def sort_index(
        self,
        *,
        ascending: bool = True,
        channels: list[str] | None = None,
    ) -> DatasetBuilder:
        """Sort one or more channels by their reference axis."""
        self._dataset.sort_index(ascending=ascending, channels=channels)
        return self

    def convert_index_unit(
        self,
        unit: str,
        *,
        channels: list[str] | None = None,
    ) -> DatasetBuilder:
        """Convert one or more channel indices to another unit.

        This is useful when notebook calculations were performed in a different
        index unit than the target report layout.
        """
        self._dataset.convert_index_unit(unit, channels=channels)
        return self

    def reindex_to(
        self,
        *,
        channel: str | None = None,
        index: ArrayLike | None = None,
        index_unit: str | None = None,
        method: str = "linear",
        channels: list[str] | None = None,
    ) -> DatasetBuilder:
        """Reindex selected channels to another channel or explicit axis.

        Use ``channel`` to align to an existing dataset channel or ``index`` and
        ``index_unit`` to align to an explicit sampling grid.
        """
        self._dataset.reindex_to(
            channel=channel,
            index=index,
            index_unit=index_unit,
            method=method,
            channels=channels,
        )
        return self


__all__ = [
    "ArrayChannel",
    "DatasetBuilder",
    "RasterChannel",
    "ScalarChannel",
    "WellDataset",
    "create_dataset",
]
