from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..errors import DatasetValidationError
from ..units import DEFAULT_UNITS, SimpleUnitRegistry
from .channels import BaseChannel


@dataclass(slots=True)
class WellDataset:
    name: str
    channels: dict[str, BaseChannel] = field(default_factory=dict)
    well_metadata: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.validate()

    def add_channel(self, channel: BaseChannel) -> None:
        channel.validate()
        self.channels[channel.mnemonic] = channel

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
