from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from ..errors import DatasetValidationError
from ..units import DEFAULT_UNITS, SimpleUnitRegistry
from .channels import ArrayChannel, BaseChannel, RasterChannel, ScalarChannel


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
