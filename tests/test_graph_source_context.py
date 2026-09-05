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
import wellplot.agent.graph.source_context as source_context
from wellplot.agent.graph import (
    PlannedSourceContextResolver,
    ReconstructionPlan,
    build_graph_authoring_context,
)
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


def test_planned_source_context_loads_new_sections_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A new section receives only its explicitly planned inspected source."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        fixture_paths = create_mcp_fixture_paths(Path(temporary_directory))
        context = build_graph_authoring_context(
            fixture_paths.single_logfile,
            root=REPO_ROOT,
        )
        plan = ReconstructionPlan.model_validate(
            {
                "summary": "Reuse the main source and add one repeat pass.",
                "sections": [
                    {
                        "section_id": "main",
                        "capability_id": "section.log_plot",
                        "goal": "Keep the existing main pass source.",
                        "data_source": {
                            "source_path": "fixture.las",
                            "source_format": "las",
                        },
                    },
                    {
                        "section_id": "repeat_pass",
                        "capability_id": "section.log_plot",
                        "goal": "Use the declared repeat source.",
                        "data_source": {
                            "source_path": "fixture.las",
                            "source_format": "las",
                        },
                    },
                ],
            }
        )
        calls: list[tuple[str, str]] = []
        original_loader = source_context.load_dataset_from_source

        def record_loader(source_path: str, source_format: str, **kwargs: object) -> object:
            calls.append((source_path, source_format))
            return original_loader(source_path, source_format, **kwargs)

        monkeypatch.setattr(source_context, "load_dataset_from_source", record_loader)
        enriched = PlannedSourceContextResolver(root=REPO_ROOT).enrich(
            plan=plan,
            source_manifest=context.source_manifest,
            logfile_path=context.logfile_path,
        )

    assert calls == [(str(fixture_paths.las_path), "las")]
    assert set(enriched) == {"main", "repeat_pass"}
    assert enriched["repeat_pass"]["source_path"] == str(fixture_paths.las_path)
    assert {channel["mnemonic"] for channel in enriched["repeat_pass"]["channels"]} >= {
        "CBL",
        "VDL",
        "GR",
    }


def test_planned_source_context_rejects_source_outside_application_root() -> None:
    """Explicit graph routing retains the canonical source-root boundary."""
    with tempfile.TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        fixture_paths = create_mcp_fixture_paths(Path(temporary_directory))
        context = build_graph_authoring_context(
            fixture_paths.single_logfile,
            root=REPO_ROOT,
        )
        plan = ReconstructionPlan.model_validate(
            {
                "summary": "Add a repeat section from an external source.",
                "sections": [
                    {
                        "section_id": "repeat_pass",
                        "capability_id": "section.log_plot",
                        "goal": "Build the repeat section.",
                        "data_source": {
                            "source_path": "../../outside.las",
                            "source_format": "las",
                        },
                    }
                ],
            }
        )

        with pytest.raises(PathAccessError, match="data.source_path must resolve inside"):
            PlannedSourceContextResolver(root=REPO_ROOT).enrich(
                plan=plan,
                source_manifest=context.source_manifest,
                logfile_path=context.logfile_path,
            )
