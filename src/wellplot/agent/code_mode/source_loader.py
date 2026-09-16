"""Host-owned source loading for the agentic Code Mode MCP edge."""

from __future__ import annotations

from pathlib import Path

from ...logfile import load_dataset_from_source
from ...model.channels import ArrayChannel
from .enrichment import (
    ChannelContext,
    LoadedSource,
    SourceFormat,
    SourceLoaderProtocol,
    SourceMetadata,
)


class LogfileSourceLoader(SourceLoaderProtocol):
    """Load bounded channel metadata from one explicit LAS or DLIS source."""

    def load(self, path: Path, source_format: SourceFormat) -> LoadedSource:
        """Read one source through the neutral dataset loader."""
        dataset, _loaded_path, _resolved_format = load_dataset_from_source(
            str(path),
            source_format,
            base_dir=path.parent,
        )
        metadata = tuple(
            SourceMetadata(key=str(key), value=str(value))
            for key, value in sorted(dataset.well_metadata.items(), key=lambda item: str(item[0]))
            if str(key).strip() and str(value).strip()
        )
        channels = tuple(
            _channel_context(channel)
            for _mnemonic, channel in sorted(dataset.channels.items(), key=lambda item: item[0])
        )
        return LoadedSource(
            dataset_name=dataset.name,
            well_metadata=metadata,
            channels=channels,
        )


def _channel_context(channel: object) -> ChannelContext:
    """Project one dataset channel without retaining samples or parser objects."""
    values = getattr(channel, "values", None)
    shape = tuple(int(value) for value in getattr(values, "shape", ()))
    return ChannelContext(
        mnemonic=str(channel.mnemonic),
        kind="array" if isinstance(channel, ArrayChannel) else "scalar",
        unit=str(channel.value_unit) if channel.value_unit else None,
        shape=shape,
        description=str(channel.description or ""),
    )


__all__ = ["LogfileSourceLoader"]
