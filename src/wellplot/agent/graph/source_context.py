###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Deterministic source context assembly for graph authoring operations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...api.serialize import report_to_dict
from ...authoring_context import AuthoringChannelCandidate
from ...authoring_service import AuthoringService
from ...errors import PathAccessError
from ...logfile import (
    load_datasets_for_logfile,
    load_logfile,
    resolve_section_data_sources_for_logfile,
)
from ...model.authoring import AuthoringDocumentSpec
from ...model.channels import ArrayChannel, BaseChannel
from ...model.dataset import WellDataset


@dataclass(frozen=True)
class GraphAuthoringContext:
    """Canonical document and inspected source facts for one graph request.

    The context is assembled before any provider call. ``source_manifest`` is
    JSON-safe graph input, while ``available_channels`` preserves typed channel
    candidates for deterministic execution and verification.
    """

    logfile_path: Path
    document: AuthoringDocumentSpec
    source_manifest: dict[str, dict[str, Any]]
    available_channels: dict[str, tuple[AuthoringChannelCandidate, ...]]


def _resolve_logfile_path(logfile_path: str | Path, *, root: Path) -> Path:
    """Resolve a caller path and keep the logfile inside the application root."""
    requested_path = Path(logfile_path).expanduser()
    resolved_path = (
        requested_path.resolve()
        if requested_path.is_absolute()
        else (root / requested_path).resolve()
    )
    try:
        resolved_path.relative_to(root)
    except ValueError as exc:
        raise PathAccessError(
            f"logfile_path must resolve inside the application root {root}."
        ) from exc
    return resolved_path


def _json_safe(value: object) -> object:
    """Convert source metadata to graph-state-safe Python values."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _json_safe(item())
        except (TypeError, ValueError):
            pass
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        try:
            return _json_safe(tolist())
        except (TypeError, ValueError):
            pass
    return str(value)


def _channel_candidate(channel: BaseChannel, *, source_path: Path) -> AuthoringChannelCandidate:
    """Project one loaded domain channel into deterministic authoring context."""
    unit = str(channel.value_unit or "").strip() or None
    return AuthoringChannelCandidate(
        mnemonic=channel.mnemonic,
        kind="array" if isinstance(channel, ArrayChannel) else "scalar",
        unit=unit,
        description=channel.description,
        value_shape=[int(size) for size in channel.values.shape],
        source_path=str(source_path),
    )


def _source_manifest_entry(
    dataset: WellDataset,
    *,
    source_path: Path,
    source_format: str,
    channels: tuple[AuthoringChannelCandidate, ...],
) -> dict[str, Any]:
    """Build the JSON-safe source facts available to graph workers."""
    return {
        "source_path": str(source_path),
        "source_format": source_format,
        "dataset_name": dataset.name,
        "channels": [channel.model_dump(mode="json") for channel in channels],
        "metadata_keys": sorted(str(key) for key in dataset.well_metadata),
        "well_metadata": _json_safe(dataset.well_metadata),
        "provenance": _json_safe(dataset.provenance),
    }


def build_graph_authoring_context(
    logfile_path: str | Path,
    *,
    root: str | Path | None = None,
) -> GraphAuthoringContext:
    """Load one canonical logfile and its declared section sources.

    The returned data is the complete deterministic source input for a graph
    reconstruction or revision. It deliberately does not call MCP, providers,
    renderers, or persistence APIs.
    """
    application_root = Path.cwd().resolve() if root is None else Path(root).expanduser().resolve()
    resolved_logfile = _resolve_logfile_path(logfile_path, root=application_root)
    spec = load_logfile(resolved_logfile, allowed_root=application_root)
    document = AuthoringService.from_mapping(report_to_dict(spec)).document
    resolved_sources = resolve_section_data_sources_for_logfile(
        spec,
        base_dir=resolved_logfile.parent,
        allowed_root=application_root,
    )
    datasets_by_section, source_paths_by_section = load_datasets_for_logfile(
        spec,
        base_dir=resolved_logfile.parent,
        allowed_root=application_root,
    )

    source_manifest: dict[str, dict[str, Any]] = {}
    available_channels: dict[str, tuple[AuthoringChannelCandidate, ...]] = {}
    for section in document.sections:
        section_id = section.id
        dataset = datasets_by_section.get(section_id)
        source_path = source_paths_by_section.get(section_id)
        source_details = resolved_sources.get(section_id)
        if dataset is None or source_path is None or source_details is None:
            raise ValueError(f"No loaded source context is available for section {section_id!r}.")
        _resolved_source_path, source_format = source_details
        channels = tuple(
            _channel_candidate(channel, source_path=source_path)
            for channel in dataset.channels.values()
        )
        available_channels[section_id] = channels
        source_manifest[section_id] = _source_manifest_entry(
            dataset,
            source_path=source_path,
            source_format=source_format,
            channels=channels,
        )

    return GraphAuthoringContext(
        logfile_path=resolved_logfile,
        document=document,
        source_manifest=source_manifest,
        available_channels=available_channels,
    )


__all__ = ["GraphAuthoringContext", "build_graph_authoring_context"]
