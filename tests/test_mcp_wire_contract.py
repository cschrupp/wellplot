"""Real-client MCP wire-contract and S0 baseline tests."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import subprocess
from collections.abc import Mapping
from math import ceil
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from wellplot.agent.mcp import LocalStdioMcpRuntime
from wellplot.agent.tool_contract import stable_tool_profile

REPO_ROOT = Path(__file__).resolve().parents[1]
S0_BASELINE_PATH = REPO_ROOT / "tests" / "fixtures" / "mcp_contract_baseline_v1.json"
S1_BASELINE_PATH = REPO_ROOT / "tests" / "fixtures" / "mcp_contract_baseline_v2.json"
S2_BASELINE_PATH = REPO_ROOT / "tests" / "fixtures" / "mcp_contract_baseline_v3.json"
CAPTURE_SCRIPT = REPO_ROOT / "scripts" / "capture_mcp_contract_baseline.py"
MCP_AVAILABLE = importlib.util.find_spec("mcp") is not None


def _result_mapping(value: object) -> dict[str, object]:
    """Return one MCP result as a mapping for direct structured-output assertions."""
    model_dump = getattr(value, "model_dump", None)
    assert callable(model_dump)
    payload = model_dump(by_alias=True)
    assert isinstance(payload, dict)
    return payload


def _result_size(value: Mapping[str, object]) -> int:
    """Measure the complete MCP result returned to the client."""
    return len(json.dumps(value, ensure_ascii=True, sort_keys=True).encode("utf-8"))


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


async def _exercise_typed_results() -> list[dict[str, object]]:
    """Execute representative result families through the production stdio client."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        draft_path = Path(temporary_directory) / "wire-contract.log.yaml"
        runtime = LocalStdioMcpRuntime(server_root=REPO_ROOT)
        async with runtime.open_session() as session:
            created = await session.call_tool(
                "create_draft",
                {
                    "operation": "clone",
                    "logfile_path": str(draft_path),
                    "source_logfile_path": "examples/cbl_main.log.yaml",
                },
            )
            header = await session.call_tool(
                "edit_header",
                {
                    "operation": "apply_values",
                    "logfile_path": str(draft_path),
                    "values": {"Company": "Wire Contract"},
                },
            )
            inspected = await session.call_tool(
                "inspect_source",
                {"logfile_path": str(draft_path)},
            )
            validated = await session.call_tool(
                "validate_logfile",
                {"logfile_path": str(draft_path)},
            )
            rendered = await session.call_tool(
                "render_logfile",
                {
                    "logfile_path": str(draft_path),
                    "output_path": str(Path(temporary_directory) / "wire-contract.pdf"),
                    "overwrite": True,
                },
            )
    return [_result_mapping(result) for result in (created, header, inspected, validated, rendered)]


async def _capture_default_result_sizes() -> dict[str, int]:
    """Measure representative default and explicitly expanded stdio responses."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        draft_path = Path(temporary_directory) / "result-budget.log.yaml"
        runtime = LocalStdioMcpRuntime(server_root=REPO_ROOT)
        async with runtime.open_session() as session:
            results = {
                "create_draft": await session.call_tool(
                    "create_draft",
                    {
                        "operation": "clone",
                        "logfile_path": str(draft_path),
                        "source_logfile_path": "examples/cbl_main.log.yaml",
                    },
                ),
                "inspect_authoring_summary": await session.call_tool(
                    "inspect_authoring",
                    {
                        "logfile_path": str(draft_path),
                        "object_kind": "track",
                        "section_id": "main",
                        "detail": "summary",
                    },
                ),
                "inspect_authoring_full": await session.call_tool(
                    "inspect_authoring",
                    {
                        "logfile_path": str(draft_path),
                        "object_kind": "track",
                        "section_id": "main",
                        "detail": "full",
                    },
                ),
                "inspect_source": await session.call_tool(
                    "inspect_source",
                    {
                        "source_path": "workspace/data/CBL_Main_REV1.las",
                        "source_format": "las",
                    },
                ),
                "inspect_vocab_summary": await session.call_tool(
                    "inspect_vocab",
                    {"detail": "summary"},
                ),
                "inspect_vocab_track": await session.call_tool(
                    "inspect_vocab",
                    {"family": "track", "detail": "summary"},
                ),
                "edit_section": await session.call_tool(
                    "edit_section",
                    {
                        "operation": "update",
                        "logfile_path": str(draft_path),
                        "section_id": "main",
                        "subtitle": "Result budget verification",
                    },
                ),
                "validate_logfile": await session.call_tool(
                    "validate_logfile",
                    {"logfile_path": str(draft_path)},
                ),
            }
    payloads = {name: _result_mapping(result) for name, result in results.items()}
    errors = {
        name: payload.get("content", [])
        for name, payload in payloads.items()
        if bool(payload.get("isError", False))
    }
    assert not errors, errors
    assert _result_size(payloads["inspect_authoring_summary"]) < _result_size(
        payloads["inspect_authoring_full"]
    )
    assert _result_size(payloads["inspect_vocab_summary"]) < _result_size(
        payloads["inspect_vocab_track"]
    )
    return {name: _result_size(payload) for name, payload in payloads.items()}


@pytest.mark.skipif(not MCP_AVAILABLE, reason="optional mcp dependency is not installed")
def test_real_stdio_surface_matches_s2_baseline() -> None:
    """Compare real MCP protocol output with the committed S2 wire contract."""
    expected = json.loads(S2_BASELINE_PATH.read_text(encoding="utf-8"))
    actual = asyncio.run(_capture_mcp_surface())

    assert actual == expected
    assert len(actual["tools"]) == 17
    assert actual["probe"]["is_error"] is False
    assert actual["probe"]["result_bytes"] > 0


@pytest.mark.skipif(not MCP_AVAILABLE, reason="optional mcp dependency is not installed")
def test_real_stdio_tool_schemas_equal_typed_profile() -> None:
    """Keep the profile, callable signature, and public stdio schema identical."""
    actual = asyncio.run(_capture_mcp_surface())
    actual_by_name = {str(tool["name"]): tool for tool in actual["tools"]}

    assert set(actual_by_name) == {tool.name for tool in stable_tool_profile()}
    for profile in stable_tool_profile():
        observed = actual_by_name[profile.name]
        assert observed["description"] == profile.description
        assert observed["input_schema"] == profile.input_schema
        assert observed["output_schema"] == profile.output_schema
        assert observed["annotations"] == profile.annotations


@pytest.mark.skipif(not MCP_AVAILABLE, reason="optional mcp dependency is not installed")
def test_real_stdio_results_validate_against_declared_output_models() -> None:
    """The SDK validates mutation, specialized, inspection, and validation outputs."""
    results = asyncio.run(_exercise_typed_results())

    assert all(not bool(result.get("isError", False)) for result in results)
    structured = [result.get("structuredContent") for result in results]
    assert all(isinstance(item, dict) for item in structured)
    assert structured[0]["changed"] is True
    assert "applied_assignments" in structured[1]
    assert "available_channels" in structured[2]
    assert structured[3]["valid"] is True
    assert structured[4]["artifact"] == structured[4]["output_path"]
    assert structured[4]["page_count"] >= 1


@pytest.mark.skipif(not MCP_AVAILABLE, reason="optional mcp dependency is not installed")
def test_default_stable_result_payloads_stay_within_s2_budgets() -> None:
    """Enforce result budgets on real responses rather than internal Python values."""
    sizes = asyncio.run(_capture_default_result_sizes())
    default_sizes = [size for name, size in sizes.items() if name not in {"inspect_authoring_full"}]
    p95 = sorted(default_sizes)[ceil(len(default_sizes) * 0.95) - 1]

    assert sizes["create_draft"] < 12_000
    assert sum(sizes[name] for name in ("create_draft", "inspect_authoring_summary")) < 20_000
    assert p95 < 12_000
    assert max(default_sizes) <= 20_000


def test_prior_baselines_are_retained_as_historical_evidence() -> None:
    """Preserve S0 and S1 evidence instead of overwriting prior wire contracts."""
    for path in (S0_BASELINE_PATH, S1_BASELINE_PATH):
        baseline = json.loads(path.read_text(encoding="utf-8"))

        assert baseline["version"] == 1
        assert baseline["transport"] == "production-stdio"
        assert len(baseline["tools"]) == 17


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
