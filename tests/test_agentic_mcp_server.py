"""Integration tests for the explicit provider-backed graph MCP host."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

pytest.importorskip("lasio")

try:
    from tests._mcp_fixtures import REPO_ROOT, create_mcp_fixture_paths
except ModuleNotFoundError:  # pragma: no cover - unittest discovery mode
    from _mcp_fixtures import REPO_ROOT, create_mcp_fixture_paths
from wellplot.agent.tool_contract import stable_tool_profile
from wellplot.authoring_service import AuthoringService
from wellplot.mcp import service
from wellplot.mcp.agentic_server import _server_from_environment, create_agentic_mcp_server

MCP_AVAILABLE = importlib.util.find_spec("mcp") is not None
GRAPH_AVAILABLE = importlib.util.find_spec("langgraph") is not None
OPENAI_AVAILABLE = importlib.util.find_spec("openai") is not None
FIXTURE_SERVER = REPO_ROOT / "tests" / "fixtures" / "agentic_stdio_server.py"


def _canonical_document(path: Path) -> dict[str, object]:
    """Read one persisted logfile through the canonical authoring projection."""
    spec = service.load_logfile(path, allowed_root=REPO_ROOT)
    return AuthoringService.from_mapping(service.report_to_dict(spec)).document.model_dump(
        mode="json"
    )


def test_agentic_server_requires_explicit_provider_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Avoid silently starting the graph host with an unintended provider."""
    monkeypatch.delenv("WELLPLOT_AGENTIC_PROVIDER", raising=False)

    with pytest.raises(ValueError, match="WELLPLOT_AGENTIC_PROVIDER"):
        _server_from_environment()


@pytest.mark.skipif(not MCP_AVAILABLE, reason="optional mcp dependency is not installed")
@pytest.mark.skipif(not GRAPH_AVAILABLE, reason="optional graph dependency is not installed")
@pytest.mark.skipif(not OPENAI_AVAILABLE, reason="optional openai dependency is not installed")
def test_agentic_server_composes_provider_and_graph_without_network() -> None:
    """Composition creates a server without executing a provider request."""
    server = create_agentic_mcp_server(
        provider="openai_compat",
        model="test-model",
        root=REPO_ROOT,
        api_key="test-key",
        base_url="https://example.invalid/v1",
    )

    assert server is not None


@pytest.mark.skipif(not MCP_AVAILABLE, reason="optional mcp dependency is not installed")
def test_real_stdio_agentic_surface_persists_and_rolls_back() -> None:
    """The opt-in stdio surface exposes high-level tools without changing stable tools."""
    import anyio
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    async def exercise() -> None:
        with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
            fixture_paths = create_mcp_fixture_paths(Path(temporary_directory))
            server = StdioServerParameters(
                command=sys.executable,
                args=[str(FIXTURE_SERVER)],
                cwd=str(REPO_ROOT),
                env={
                    **os.environ,
                    "WELLPLOT_AGENTIC_TEST_ROOT": str(REPO_ROOT),
                },
            )
            async with stdio_client(server) as streams, ClientSession(*streams) as session:
                with anyio.fail_after(15):
                    await session.initialize()
                tools = await session.list_tools()
                build = await session.call_tool(
                    "build_plot_from_request",
                    {
                        "logfile_path": str(fixture_paths.single_logfile),
                        "request": "Set the report title.",
                    },
                )
                revision = await session.call_tool(
                    "revise_plot_from_request",
                    {
                        "logfile_path": str(fixture_paths.single_logfile),
                        "request": "Set the section subtitle.",
                    },
                )
                before_invalid = fixture_paths.single_logfile.read_text(encoding="utf-8")
                invalid = await session.call_tool(
                    "build_plot_from_request",
                    {
                        "logfile_path": str(fixture_paths.single_logfile),
                        "request": "Create an invalid curve.",
                    },
                )

            persisted = _canonical_document(fixture_paths.single_logfile)
            after_invalid = fixture_paths.single_logfile.read_text(encoding="utf-8")

        assert [tool.name for tool in tools.tools] == [
            *(tool.name for tool in stable_tool_profile()),
            "build_plot_from_request",
            "revise_plot_from_request",
        ]
        assert build.isError is False
        assert build.structuredContent["success"] is True
        assert revision.isError is False
        assert revision.structuredContent["success"] is True
        assert invalid.isError is False
        assert invalid.structuredContent["success"] is False
        assert persisted["title"] == "Graph stdio reconstruction"
        assert persisted["sections"][0]["subtitle"] == "Revised"
        assert before_invalid == after_invalid

    anyio.run(exercise)
