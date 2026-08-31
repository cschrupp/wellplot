"""Tests for the opt-in high-level graph MCP adapter."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

pytest.importorskip("lasio")

try:
    from tests._mcp_fixtures import REPO_ROOT, create_mcp_fixture_paths
except ModuleNotFoundError:  # pragma: no cover - unittest discovery mode
    from _mcp_fixtures import REPO_ROOT, create_mcp_fixture_paths
from wellplot.authoring_service import AuthoringService
from wellplot.mcp import service
from wellplot.mcp.agentic import GraphAuthoringMcpOperations, register_agentic_tools


class _ToolCollector:
    """Minimal FastMCP-compatible collector for registration tests."""

    def __init__(self) -> None:
        self.tools: list[dict[str, object]] = []

    def add_tool(self, function: object, **metadata: object) -> None:
        self.tools.append({"function": function, **metadata})


class _Graph:
    """Deterministic compiled-graph substitute for adapter tests."""

    def __init__(self, *, intent: dict[str, object], mode: str) -> None:
        self.intent = intent
        self.mode = mode
        self.states: list[dict[str, object]] = []

    async def ainvoke(self, input: dict[str, object]) -> dict[str, object]:
        """Return one valid reconstruction or revision graph output."""
        self.states.append(deepcopy(input))
        section = {
            "section_id": "main",
            "capability_id": "section.log_plot",
            "goal": "Update the main section.",
        }
        return {
            "plan": {
                "summary": f"{self.mode} main section.",
                "sections": [section],
            },
            "merged_intent": self.intent,
        }


def _canonical_document(path: Path) -> dict[str, object]:
    """Read one persisted logfile through the canonical authoring projection."""
    spec = service.load_logfile(path, allowed_root=REPO_ROOT)
    return AuthoringService.from_mapping(service.report_to_dict(spec)).document.model_dump(
        mode="json"
    )


def test_agentic_tools_persist_successful_build_and_revision() -> None:
    """High-level tools use one graph transaction and persist verified output."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        fixture_paths = create_mcp_fixture_paths(Path(temporary_directory))
        build_graph = _Graph(intent={"title": "Graph reconstruction"}, mode="reconstruct")
        build_operations = GraphAuthoringMcpOperations.create(
            graph=build_graph,
            root=REPO_ROOT,
        )
        collector = _ToolCollector()
        assert register_agentic_tools(collector, operations=build_operations) == (
            "build_plot_from_request",
            "revise_plot_from_request",
        )

        build_tool = next(
            item["function"]
            for item in collector.tools
            if item["name"] == "build_plot_from_request"
        )
        build_result = asyncio.run(
            build_tool(
                logfile_path=str(fixture_paths.single_logfile),
                request="Set the report title.",
            )
        )

        revision_graph = _Graph(
            intent={
                "sections": [
                    {"section_id": "main", "subtitle": "Graph revision"},
                ]
            },
            mode="revise",
        )
        revision_operations = GraphAuthoringMcpOperations.create(
            graph=revision_graph,
            root=REPO_ROOT,
        )
        revision_result = asyncio.run(
            revision_operations.revise(
                logfile_path=str(fixture_paths.single_logfile),
                request="Set the main subtitle.",
            )
        )

        persisted = _canonical_document(fixture_paths.single_logfile)

    assert build_result.success is True, build_result.errors
    assert build_result.changed is True
    assert build_result.mode == "reconstruct"
    assert revision_result.success is True, revision_result.errors
    assert revision_result.changed is True
    assert revision_result.mode == "revise"
    assert build_graph.states[0]["mode"] == "reconstruct"
    assert revision_graph.states[0]["mode"] == "revise"
    assert persisted["title"] == "Graph reconstruction"
    assert persisted["sections"][0]["subtitle"] == "Graph revision"


def test_agentic_tools_do_not_persist_blocked_execution() -> None:
    """A blocked graph transaction leaves the logfile text untouched."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        fixture_paths = create_mcp_fixture_paths(Path(temporary_directory))
        before = fixture_paths.single_logfile.read_text(encoding="utf-8")
        graph = _Graph(
            intent={
                "sections": [
                    {
                        "section_id": "main",
                        "tracks": [
                            {
                                "track_id": "missing_curve",
                                "title": "Missing curve",
                                "kind": "normal",
                                "width_mm": 20,
                                "bindings": [
                                    {
                                        "kind": "curve",
                                        "binding_id": "main.missing_curve.UNKNOWN.1",
                                        "channel": "UNKNOWN",
                                    }
                                ],
                            }
                        ],
                    }
                ]
            },
            mode="reconstruct",
        )
        operations = GraphAuthoringMcpOperations.create(graph=graph, root=REPO_ROOT)

        result = asyncio.run(
            operations.build(
                logfile_path=str(fixture_paths.single_logfile),
                request="Add an unavailable curve.",
            )
        )

        after = fixture_paths.single_logfile.read_text(encoding="utf-8")

    assert result.success is False
    assert result.changed is False
    assert result.errors
    assert before == after
