"""Real-client MCP wire-contract and S0 baseline tests."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import re
import subprocess
from collections.abc import Mapping
from math import ceil
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest

try:
    from tests._mcp_fixtures import create_mcp_fixture_paths
except ModuleNotFoundError:  # pragma: no cover - exercised by unittest discovery mode
    from _mcp_fixtures import create_mcp_fixture_paths

from wellplot.agent.mcp import LocalStdioMcpRuntime
from wellplot.agent.tool_contract import stable_tool_profile
from wellplot.mcp import service

REPO_ROOT = Path(__file__).resolve().parents[1]
S0_BASELINE_PATH = REPO_ROOT / "tests" / "fixtures" / "mcp_contract_baseline_v1.json"
S1_BASELINE_PATH = REPO_ROOT / "tests" / "fixtures" / "mcp_contract_baseline_v2.json"
S2_BASELINE_PATH = REPO_ROOT / "tests" / "fixtures" / "mcp_contract_baseline_v3.json"
S4_BASELINE_PATH = REPO_ROOT / "tests" / "fixtures" / "mcp_contract_baseline_v4.json"
S8_BASELINE_PATH = REPO_ROOT / "tests" / "fixtures" / "mcp_contract_baseline_v8.json"
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
                {"logfile_path": str(draft_path), "level": "structural"},
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


def _content_text(value: object) -> str:
    """Extract text content from one real MCP resource or prompt result."""
    payload = dict(value) if isinstance(value, Mapping) else _result_mapping(value)
    content = payload.get("contents", payload.get("messages", payload.get("content", [])))
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, Mapping):
            continue
        text = item.get("text")
        if isinstance(text, str):
            parts.append(text)
            continue
        message = item.get("content")
        if isinstance(message, Mapping) and isinstance(message.get("text"), str):
            parts.append(str(message["text"]))
    return "\n".join(parts)


async def _exercise_every_stable_tool() -> dict[str, dict[str, object]]:
    """Call every stable responsibility through the production stdio client."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        fixture = create_mcp_fixture_paths(Path(temporary_directory), repo_root=REPO_ROOT)
        draft_path = fixture.single_logfile
        full_draft = Path(temporary_directory) / "full-reconstruction.log.yaml"
        service.create_logfile_draft(
            str(full_draft),
            source_logfile_path="examples/production/cbl_log_example/full_reconstruction.log.yaml",
            root=REPO_ROOT,
        )
        service.add_track(
            str(draft_path),
            section_id="main",
            id="overlay",
            title="Overlay",
            kind="normal",
            width_mm=18,
            root=REPO_ROOT,
        )
        for channel, binding_id in (("GR", "overlay.gr"), ("CALI", "overlay.cali")):
            service.bind_curve(
                str(draft_path),
                section_id="main",
                track_id="overlay",
                channel=channel,
                binding_id=binding_id,
                root=REPO_ROOT,
            )
        created_path = Path(temporary_directory) / "created.log.yaml"
        render_path = Path(temporary_directory) / "wire-contract.pdf"
        runtime = LocalStdioMcpRuntime(server_root=REPO_ROOT)
        async with runtime.open_session() as session:
            calls: tuple[tuple[str, dict[str, Any]], ...] = (
                (
                    "create_draft",
                    {
                        "operation": "clone",
                        "logfile_path": str(created_path),
                        "source_logfile_path": fixture.single_logfile_relative,
                    },
                ),
                (
                    "inspect_authoring",
                    {
                        "logfile_path": str(draft_path),
                        "object_kind": "track",
                        "section_id": "main",
                    },
                ),
                (
                    "inspect_source",
                    {"source_path": str(fixture.las_path), "source_format": "las"},
                ),
                ("inspect_vocab", {"detail": "summary"}),
                (
                    "edit_header",
                    {
                        "operation": "apply_values",
                        "logfile_path": str(draft_path),
                        "values": {"Company": "Wire Contract"},
                    },
                ),
                (
                    "edit_report_settings",
                    {
                        "operation": "set_matplotlib_style",
                        "logfile_path": str(draft_path),
                        "style_patch": {"grid": {"x_minor_linewidth": 0.3}},
                    },
                ),
                (
                    "edit_remarks",
                    {
                        "operation": "add",
                        "logfile_path": str(draft_path),
                        "remark": {
                            "title": "Wire",
                            "lines": ["Wire conformance."],
                            "alignment": "left",
                        },
                    },
                ),
                (
                    "edit_section",
                    {
                        "operation": "update",
                        "logfile_path": str(draft_path),
                        "section_id": "main",
                        "subtitle": "Wire conformance",
                    },
                ),
                (
                    "replicate_section_structure",
                    {
                        "operation": "replicate",
                        "logfile_path": str(draft_path),
                        "source_section_id": "main",
                        "target_section_id": "repeat",
                        "source_path": str(fixture.las_path),
                        "source_format": "las",
                        "include_bindings": False,
                    },
                ),
                (
                    "edit_track",
                    {
                        "operation": "add",
                        "logfile_path": str(draft_path),
                        "section_id": "main",
                        "track_id": "notes",
                        "title": "Notes",
                        "kind": "annotation",
                        "width_mm": 14,
                    },
                ),
                (
                    "edit_curve_binding",
                    {
                        "operation": "update",
                        "logfile_path": str(draft_path),
                        "section_id": "main",
                        "track_id": "cbl",
                        "channel": "CBL",
                        "label": "CBL wire check",
                    },
                ),
                (
                    "edit_raster_binding",
                    {
                        "operation": "update",
                        "logfile_path": str(full_draft),
                        "section_id": "main_pass",
                        "track_id": "vdl",
                        "channel": "VDL",
                        "profile": "vdl",
                    },
                ),
                (
                    "edit_fill",
                    {
                        "operation": "add",
                        "logfile_path": str(draft_path),
                        "section_id": "main",
                        "track_id": "overlay",
                        "channel": "CALI",
                        "binding_id": "overlay.cali",
                        "other_binding_id": "overlay.gr",
                        "kind": "between_instances",
                        "color": "#d1d5db",
                        "alpha": 0.2,
                    },
                ),
                (
                    "edit_annotation",
                    {
                        "operation": "add",
                        "logfile_path": str(draft_path),
                        "section_id": "main",
                        "track_id": "notes",
                        "annotation": {
                            "kind": "text",
                            "depth": 1008,
                            "text": "Wire conformance",
                            "lane_start": 0,
                            "lane_end": 1,
                        },
                    },
                ),
                ("validate_logfile", {"logfile_path": str(draft_path), "level": "structural"}),
                ("preview_logfile", {"logfile_path": str(draft_path), "section_id": "main"}),
                (
                    "render_logfile",
                    {
                        "logfile_path": str(draft_path),
                        "output_path": str(render_path),
                        "overwrite": True,
                    },
                ),
            )
            results: dict[str, dict[str, object]] = {}
            for name, arguments in calls:
                result = await session.call_tool(name, arguments)
                results[name] = _result_mapping(result)
    return results


async def _exercise_discovery_content() -> tuple[dict[str, int], dict[str, str]]:
    """Resolve registered resources and prompts through a real MCP client."""
    prompt_arguments = {
        "review_logfile": {"logfile_path": "examples/cbl_main.log.yaml"},
        "preview_logfile": {"logfile_path": "examples/cbl_main.log.yaml", "focus": "report"},
        "start_from_example": {"example_id": "cbl_log_example", "goal": "Inspect the example."},
        "author_plot_from_request": {"goal": "Add a curve."},
        "revise_plot_from_feedback": {
            "logfile_path": "examples/cbl_main.log.yaml",
            "feedback": "Update the title.",
        },
        "ingest_header_text": {
            "logfile_path": "examples/cbl_main.log.yaml",
            "source_text": "Company: Wire Contract",
        },
    }
    template_uris = (
        "wellplot://examples/production/cbl_log_example/README.md",
        "wellplot://examples/production/cbl_log_example/base.template.yaml",
        "wellplot://examples/production/cbl_log_example/full_reconstruction.log.yaml",
        "wellplot://examples/production/cbl_log_example/data-notes.md",
    )
    runtime = LocalStdioMcpRuntime(server_root=REPO_ROOT)
    async with runtime.open_session() as session:
        listed = await session.list_resources()
        resource_uris = [str(resource.uri) for resource in getattr(listed, "resources", [])]
        contents: dict[str, int] = {}
        for uri in (*resource_uris, *template_uris):
            response = await session.read_resource(uri)
            text = _content_text(response)
            contents[uri] = len(text.encode("utf-8"))
        prompts = await session.list_prompts()
        prompt_text = {
            str(prompt.name): _content_text(
                await session.get_prompt(str(prompt.name), prompt_arguments[str(prompt.name)])
            )
            for prompt in getattr(prompts, "prompts", [])
        }
    return contents, prompt_text


@pytest.mark.skipif(not MCP_AVAILABLE, reason="optional mcp dependency is not installed")
def test_real_stdio_surface_matches_s8_baseline() -> None:
    """Compare real MCP protocol output with the committed S8 wire contract."""
    expected = json.loads(S8_BASELINE_PATH.read_text(encoding="utf-8"))
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
    assert structured[3]["validation_level"] == "structural"
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


@pytest.mark.skipif(not MCP_AVAILABLE, reason="optional mcp dependency is not installed")
def test_real_stdio_exercises_every_stable_responsibility() -> None:
    """Require every public tool to accept one minimal valid wire request."""
    results = asyncio.run(_exercise_every_stable_tool())

    assert set(results) == {profile.name for profile in stable_tool_profile()}
    errors = {
        name: _content_text(result)
        for name, result in results.items()
        if bool(result.get("isError", False))
    }
    assert not errors, errors

    # Image previews are intentionally unstructured artifacts; all other tools
    # must preserve the typed result envelope advertised by tools/list.
    for name, result in results.items():
        if name == "preview_logfile":
            assert result.get("content")
            continue
        assert isinstance(result.get("structuredContent"), dict), name
        assert _result_size(result) <= 20_000, name


@pytest.mark.skipif(not MCP_AVAILABLE, reason="optional mcp dependency is not installed")
def test_real_stdio_rejects_missing_required_and_invalid_operation_values() -> None:
    """Exercise client-visible validation rather than only Pydantic models."""

    async def exercise() -> dict[str, bool]:
        runtime = LocalStdioMcpRuntime(server_root=REPO_ROOT)
        async with runtime.open_session() as session:
            missing = {
                profile.name: bool(
                    _result_mapping(await session.call_tool(profile.name, {})).get("isError", False)
                )
                for profile in stable_tool_profile()
                if profile.name != "inspect_vocab"
            }
            invalid_operations = {
                profile.name: bool(
                    _result_mapping(
                        await session.call_tool(
                            profile.name,
                            {
                                "logfile_path": "examples/cbl_main.log.yaml",
                                "operation": "not-a-real-operation",
                            },
                        )
                    ).get("isError", False)
                )
                for profile in stable_tool_profile()
                if "operation" in profile.input_model.model_fields
            }
            invalid_vocab = _result_mapping(
                await session.call_tool("inspect_vocab", {"detail": "not-a-real-detail"})
            )
        return {
            **{f"missing:{name}": failed for name, failed in missing.items()},
            **{f"operation:{name}": failed for name, failed in invalid_operations.items()},
            "invalid:inspect_vocab": bool(invalid_vocab.get("isError", False)),
        }

    outcomes = asyncio.run(exercise())
    assert outcomes
    assert all(outcomes.values()), outcomes


@pytest.mark.skipif(not MCP_AVAILABLE, reason="optional mcp dependency is not installed")
def test_real_stdio_resolves_resources_and_prompts_within_discovery_budgets() -> None:
    """Check discovery content, not merely resources/list and prompts/list identities."""
    resource_sizes, prompts = asyncio.run(_exercise_discovery_content())
    stable_names = {profile.name for profile in stable_tool_profile()}

    assert len(resource_sizes) == 19
    assert all(size > 0 for size in resource_sizes.values())
    assert max(resource_sizes.values()) <= 1_000_000
    assert set(prompts) == {
        "review_logfile",
        "preview_logfile",
        "start_from_example",
        "author_plot_from_request",
        "revise_plot_from_feedback",
        "ingest_header_text",
    }
    assert all(text.strip() for text in prompts.values())
    for text in prompts.values():
        called_names = set(re.findall(r"\b([a-z][a-z0-9_]*)\(\.\.\.\)", text))
        assert called_names <= stable_names


@pytest.mark.skipif(not MCP_AVAILABLE, reason="optional mcp dependency is not installed")
def test_real_stdio_currently_ignores_unknown_top_level_arguments() -> None:
    """Preserve the known FastMCP limitation as explicit S6 evidence."""

    async def exercise() -> dict[str, object]:
        runtime = LocalStdioMcpRuntime(server_root=REPO_ROOT)
        async with runtime.open_session() as session:
            result = await session.call_tool(
                "inspect_vocab",
                {"detail": "summary", "s6_unknown_argument": "ignored"},
            )
        return _result_mapping(result)

    result = asyncio.run(exercise())
    assert result.get("isError", False) is False
    assert isinstance(result.get("structuredContent"), dict)


def test_prior_baselines_are_retained_as_historical_evidence() -> None:
    """Preserve prior wire evidence instead of overwriting earlier contracts."""
    for path in (S0_BASELINE_PATH, S1_BASELINE_PATH, S2_BASELINE_PATH, S4_BASELINE_PATH):
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
