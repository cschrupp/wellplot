from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from ..errors import DatasetValidationError
from ..units import DEFAULT_UNITS, SimpleUnitRegistry
from .channels import ArrayChannel, BaseChannel, RasterChannel, ScalarChannel


def _require_pandas() -> Any:
    try:
        import pandas as pd
    except ModuleNotFoundError as exc:
        raise ImportError(
            "pandas adapters require pandas to be installed. "
            "Install the optional pandas dependency to use add_series/add_dataframe."
        ) from exc
    return pd


@dataclass(slots=True)
class WellDataset:
    name: str
    channels: dict[str, BaseChannel] = field(default_factory=dict)
    well_metadata: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.validate()

    def add_channel(self, channel: BaseChannel, *, replace: bool = True) -> BaseChannel:
        channel.validate()
        if not replace and channel.mnemonic in self.channels:
            raise DatasetValidationError(
                f"Dataset {self.name!r} already has a channel named {channel.mnemonic!r}."
            )
        self.channels[channel.mnemonic] = channel
        return channel

    def add_or_replace_channel(self, channel: BaseChannel) -> BaseChannel:
        return self.add_channel(channel, replace=True)

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
        metadata: dict[str, Any] | None = None,
        replace: bool = True,
    ) -> ScalarChannel:
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
        metadata: dict[str, Any] | None = None,
        replace: bool = True,
    ) -> ArrayChannel:
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
        metadata: dict[str, Any] | None = None,
        colormap: str = "viridis",
        replace: bool = True,
    ) -> RasterChannel:
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
    ) -> ScalarChannel:
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
        frame: Any,
        *,
        index_unit: str,
        index_column: str | None = None,
        use_index: bool = False,
        curves: Mapping[str, Mapping[str, Any]] | None = None,
        skip_columns: Iterable[str] | None = None,
        replace: bool = True,
        source: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> list[ScalarChannel]:
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
                selected_columns = [
                    column for column in selected_columns if column != index_column
                ]
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
        merge_well_metadata: bool = False,
        merge_provenance: bool = False,
    ) -> WellDataset:
        other.validate()
        for channel in other.channels.values():
            self.add_channel(deepcopy(channel), replace=replace)
        if merge_well_metadata:
            self.well_metadata.update(other.well_metadata)
        if merge_provenance:
            self.provenance.update(other.provenance)
        return self

    def get_channel(self, mnemonic: str) -> BaseChannel:
        return self.channels[mnemonic]

    def depth_range(
        self,
        unit: str,
        registry: SimpleUnitRegistry = DEFAULT_UNITS,
    ) -> tuple[float, float]:
        if not self.channels:
            raise ValueError("Dataset has no channels.")
        mins = []
        maxs = []
        for channel in self.channels.values():
            mins.append(registry.convert(channel.depth_min, channel.depth_unit, unit))
            maxs.append(registry.convert(channel.depth_max, channel.depth_unit, unit))
        return min(mins), max(maxs)

    def header_value(self, key: str, default: Any = "") -> Any:
        return self.well_metadata.get(key, default)

    def validate(self) -> None:
        if not str(self.name).strip():
            raise DatasetValidationError("Dataset name cannot be empty.")
        for mnemonic, channel in self.channels.items():
            if mnemonic != channel.mnemonic:
                raise DatasetValidationError(
                    f"Dataset channel key {mnemonic!r} does not match channel mnemonic "
                    f"{channel.mnemonic!r}."
                )
            channel.validate()
