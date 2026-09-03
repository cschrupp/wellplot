"""Tests for the notebook client of the explicit agentic MCP host."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from wellplot.agent.mcp import AGENTIC_MCP_SERVER_MODULE
from wellplot.agent.notebook import AgenticMcpClient, create_agentic_mcp_client


class _Result:
    """Minimal MCP result carrying structured tool content."""

    isError = False

    def __init__(self, structured: dict[str, object]) -> None:
        self.structuredContent = structured


class _Session:
    """Record calls made through the notebook client."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def call_tool(self, name: str, arguments: dict[str, object]) -> _Result:
        """Return one successful structured response for the requested tool."""
        self.calls.append((name, arguments))
        if name == "render_logfile":
            return _Result({"artifact": "workspace/output.pdf"})
        if arguments.get("request") == "Provider unavailable.":
            return _Result(
                {
                    "logfile_path": str(arguments["logfile_path"]),
                    "mode": "reconstruct" if name.startswith("build_") else "revise",
                    "success": False,
                    "changed": False,
                    "rolled_back": False,
                    "section_ids": ["main"],
                    "errors": [
                        "Provider request failed before graph compilation completed "
                        "(transport_failure)."
                    ],
                }
            )
        return _Result(
            {
                "logfile_path": str(arguments["logfile_path"]),
                "mode": "reconstruct" if name.startswith("build_") else "revise",
                "success": True,
                "changed": True,
                "rolled_back": False,
                "section_ids": ["main"],
                "errors": [],
            }
        )


class _Runtime:
    """Minimal runtime implementation for notebook-client unit tests."""

    def __init__(self, root: Path) -> None:
        self.server_root = root
        self.session = _Session()

    @asynccontextmanager
    async def open_session(self) -> AsyncIterator[_Session]:
        """Yield the recorded fake MCP session."""
        yield self.session

    @staticmethod
    def tool_result_payload(result: _Result) -> dict[str, object]:
        """Expose the fixture result through the runtime normalization contract."""
        return {"is_error": result.isError, "structured": result.structuredContent}


def test_create_agentic_mcp_client_uses_explicit_server_configuration(tmp_path: Path) -> None:
    """Notebook setup starts the graph host rather than the stable MCP server."""
    client = create_agentic_mcp_client(
        server_root=tmp_path,
        provider="openai_compat",
        model="provider/test-model",
        api_key="test-key",
        base_url="https://example.invalid/v1",
        timeout=120,
    )

    assert client.runtime.server_module == AGENTIC_MCP_SERVER_MODULE
    assert dict(client.runtime.server_environment) == {
        "WELLPLOT_AGENTIC_PROVIDER": "openai_compat",
        "WELLPLOT_AGENTIC_MODEL": "provider/test-model",
        "WELLPLOT_AGENTIC_API_KEY": "test-key",
        "WELLPLOT_AGENTIC_BASE_URL": "https://example.invalid/v1",
        "WELLPLOT_AGENTIC_TIMEOUT": "120",
    }


def test_agentic_notebook_client_uses_graph_host_tools(tmp_path: Path) -> None:
    """Graph and render calls preserve the intended MCP boundary."""
    runtime = _Runtime(tmp_path)
    client = AgenticMcpClient(runtime=runtime)  # type: ignore[arg-type]
    logfile = tmp_path / "workspace" / "draft.log.yaml"
    output = tmp_path / "workspace" / "report.pdf"

    build = asyncio.run(client.build(request="Build the plot.", logfile_path=logfile))
    revision = asyncio.run(client.revise(feedback="Revise the plot.", logfile_path=logfile))
    render = asyncio.run(
        client.render_logfile_to_file(
            logfile_path=logfile,
            output_path=output,
            overwrite=True,
        )
    )

    assert build.success is True
    assert revision.mode == "revise"
    assert render["output_path"] == "workspace/output.pdf"
    assert runtime.session.calls == [
        (
            "build_plot_from_request",
            {"logfile_path": "workspace/draft.log.yaml", "request": "Build the plot."},
        ),
        (
            "revise_plot_from_request",
            {"logfile_path": "workspace/draft.log.yaml", "request": "Revise the plot."},
        ),
        (
            "render_logfile",
            {
                "logfile_path": "workspace/draft.log.yaml",
                "output_path": "workspace/report.pdf",
                "overwrite": True,
            },
        ),
    ]


def test_agentic_notebook_client_returns_structured_provider_failure(tmp_path: Path) -> None:
    """Notebook callers can display a provider failure without an MCP exception."""
    runtime = _Runtime(tmp_path)
    client = AgenticMcpClient(runtime=runtime)  # type: ignore[arg-type]

    result = asyncio.run(
        client.build(
            request="Provider unavailable.",
            logfile_path=tmp_path / "workspace" / "draft.log.yaml",
        )
    )

    assert result.success is False
    assert result.changed is False
    assert result.errors == [
        "Provider request failed before graph compilation completed (transport_failure)."
    ]
