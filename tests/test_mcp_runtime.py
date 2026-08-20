"""Tests for MCP result normalization used by the authoring feedback loop."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from wellplot.agent.mcp import LocalStdioMcpRuntime


def test_tool_result_payload_preserves_mcp_error_text(tmp_path: Path) -> None:
    """Expose MCP text errors to the provider instead of only an error flag."""
    runtime = LocalStdioMcpRuntime(server_root=tmp_path)
    result = SimpleNamespace(
        isError=True,
        structuredContent=None,
        content=[SimpleNamespace(type="text", text="Unknown object kind 'document'.")],
    )

    payload = runtime.tool_result_payload(result)

    assert payload["is_error"] is True
    assert payload["error"] == "Unknown object kind 'document'."
