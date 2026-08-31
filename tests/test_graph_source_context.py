"""Tests for deterministic graph source-context assembly."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("lasio")

try:
    from tests._mcp_fixtures import REPO_ROOT, create_mcp_fixture_paths
except ModuleNotFoundError:  # pragma: no cover - unittest discovery mode
    from _mcp_fixtures import REPO_ROOT, create_mcp_fixture_paths
from wellplot.agent.graph import build_graph_authoring_context
from wellplot.errors import PathAccessError


def test_graph_context_loads_declared_multisection_sources() -> None:
    """One source-backed document yields context for each canonical section."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        fixture_paths = create_mcp_fixture_paths(Path(temporary_directory))
        context = build_graph_authoring_context(
            fixture_paths.multi_logfile,
            root=REPO_ROOT,
        )

    assert [section.id for section in context.document.sections] == ["main_pass", "repeat_pass"]
    assert list(context.source_manifest) == ["main_pass", "repeat_pass"]
    assert json.loads(json.dumps(context.source_manifest)) == context.source_manifest

    for section_id in ("main_pass", "repeat_pass"):
        manifest = context.source_manifest[section_id]
        channels = context.available_channels[section_id]
        assert manifest["source_format"] == "las"
        assert manifest["well_metadata"]["WELL"] == "MCP FIXTURE-01"
        assert {channel.mnemonic for channel in channels} >= {"GR", "CBL", "VDL"}
        assert all(channel.kind == "scalar" for channel in channels)
        assert manifest["channels"] == [channel.model_dump(mode="json") for channel in channels]


def test_graph_context_rejects_logfile_outside_application_root(tmp_path: Path) -> None:
    """Source assembly preserves the application root safety boundary."""
    outside_logfile = tmp_path / "outside.log.yaml"
    outside_logfile.write_text("name: outside\n", encoding="utf-8")

    with pytest.raises(PathAccessError, match="inside the application root"):
        build_graph_authoring_context(outside_logfile, root=REPO_ROOT)
