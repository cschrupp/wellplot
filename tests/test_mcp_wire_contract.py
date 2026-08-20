"""Real-client MCP wire-contract and S0 baseline tests."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = REPO_ROOT / "tests" / "fixtures" / "mcp_contract_baseline_v1.json"
CAPTURE_SCRIPT = REPO_ROOT / "scripts" / "capture_mcp_contract_baseline.py"
MCP_AVAILABLE = importlib.util.find_spec("mcp") is not None


async def _capture_mcp_surface() -> dict[str, object]:
    """Load the standalone capture utility as the real-client test harness."""
    spec = importlib.util.spec_from_file_location("mcp_contract_capture", CAPTURE_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    capture = module.capture_mcp_surface
    payload = await capture(REPO_ROOT)
    assert isinstance(payload, dict)
    return payload


@pytest.mark.skipif(not MCP_AVAILABLE, reason="optional mcp dependency is not installed")
def test_real_stdio_surface_matches_versioned_baseline() -> None:
    """Compare real MCP protocol output with the committed S0 baseline."""
    expected = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    actual = asyncio.run(_capture_mcp_surface())

    assert actual == expected
    assert len(actual["tools"]) == 17
    assert actual["probe"]["is_error"] is False
    assert actual["probe"]["result_bytes"] > 0


def test_cbl_fixture_is_present_and_tracked_for_mcp_integration() -> None:
    """Keep the integration fixture available in clean repository checkouts."""
    fixture = REPO_ROOT / "examples" / "cbl_main.log.yaml"

    assert fixture.is_file()
    assert fixture.stat().st_size > 0
    if (REPO_ROOT / ".git").exists():
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "examples/cbl_main.log.yaml"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert tracked.returncode == 0, tracked.stderr
