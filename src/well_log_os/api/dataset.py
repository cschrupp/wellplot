from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..model import ArrayChannel, BaseChannel, RasterChannel, ScalarChannel, WellDataset


def create_dataset(
    name: str,
    *,
    well_metadata: Mapping[str, Any] | None = None,
    provenance: Mapping[str, Any] | None = None,
) -> WellDataset:
    return WellDataset(
        name=name,
        well_metadata=dict(well_metadata or {}),
        provenance=dict(provenance or {}),
    )


class DatasetBuilder:
    def __init__(
        self,
        *,
        name: str,
        well_metadata: Mapping[str, Any] | None = None,
        provenance: Mapping[str, Any] | None = None,
    ) -> None:
        self._dataset = create_dataset(
            name,
            well_metadata=well_metadata,
            provenance=provenance,
        )

    @property
    def dataset(self) -> WellDataset:
        return self._dataset

    def build(self) -> WellDataset:
        self._dataset.validate()
        return self._dataset

    def add_channel(self, channel: BaseChannel, *, replace: bool = True) -> DatasetBuilder:
        self._dataset.add_channel(channel, replace=replace)
        return self

    def add_or_replace_channel(self, channel: BaseChannel) -> DatasetBuilder:
        self._dataset.add_or_replace_channel(channel)
        return self

    def rename_channel(self, mnemonic: str, new_mnemonic: str) -> DatasetBuilder:
        self._dataset.rename_channel(mnemonic, new_mnemonic)
        return self

    def add_curve(
        self,
        *,
        mnemonic: str,
        values: Any,
        index: Any,
        index_unit: str,
        value_unit: str | None = None,
        description: str = "",
        null_value: float | None = None,
        source: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        replace: bool = True,
    ) -> DatasetBuilder:
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
        values: Any,
        index: Any,
        index_unit: str,
        sample_axis: Any,
        sample_unit: str | None = None,
        sample_label: str = "sample",
        value_unit: str | None = None,
        description: str = "",
        null_value: float | None = None,
        source: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        replace: bool = True,
    ) -> DatasetBuilder:
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
        series: Any,
        index_unit: str,
        mnemonic: str | None = None,
        index: Any | None = None,
        value_unit: str | None = None,
        description: str = "",
        null_value: float | None = None,
        source: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        replace: bool = True,
    ) -> DatasetBuilder:
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
        frame: Any,
        *,
        index_unit: str,
        index_column: str | None = None,
        use_index: bool = False,
        curves: Mapping[str, Mapping[str, Any]] | None = None,
        skip_columns: list[str] | None = None,
        replace: bool = True,
        source: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> DatasetBuilder:
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
        values: Any,
        index: Any,
        index_unit: str,
        sample_axis: Any,
        sample_unit: str | None = None,
        sample_label: str = "sample",
        value_unit: str | None = None,
        description: str = "",
        null_value: float | None = None,
        source: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        colormap: str = "viridis",
        replace: bool = True,
    ) -> DatasetBuilder:
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
        self._dataset.sort_index(ascending=ascending, channels=channels)
        return self

    def convert_index_unit(
        self,
        unit: str,
        *,
        channels: list[str] | None = None,
    ) -> DatasetBuilder:
        self._dataset.convert_index_unit(unit, channels=channels)
        return self

    def reindex_to(
        self,
        *,
        channel: str | None = None,
        index: Any | None = None,
        index_unit: str | None = None,
        method: str = "linear",
        channels: list[str] | None = None,
    ) -> DatasetBuilder:
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
