#!/usr/bin/env python3
"""Capture the client-visible Wellplot MCP surface over production stdio."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from wellplot.agent.mcp import LocalStdioMcpRuntime

REPO_ROOT = Path(__file__).resolve().parents[1]


def _model_mapping(value: object) -> dict[str, Any]:
    """Return one MCP SDK model as a JSON-compatible mapping."""
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        payload = model_dump(by_alias=True, exclude_none=True)
        if isinstance(payload, dict):
            return json.loads(json.dumps(payload, default=str))
    return {}


def _json_size(value: object) -> int:
    """Return UTF-8 bytes for one protocol payload."""
    return len(
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


def _tool_record(tool: object) -> dict[str, Any]:
    """Extract the intended baseline fields from a real ``tools/list`` item."""
    payload = _model_mapping(tool)
    input_schema = payload.get("inputSchema", {})
    output_schema = payload.get("outputSchema")
    annotations = payload.get("annotations")
    return {
        "name": payload.get("name"),
        "description": payload.get("description", ""),
        "input_schema": input_schema,
        "output_schema": output_schema,
        "annotations": annotations,
        "input_schema_bytes": _json_size(input_schema),
        "output_schema_bytes": _json_size(output_schema) if output_schema is not None else 0,
    }


def _named_records(values: object) -> list[dict[str, Any]]:
    """Capture stable resource, prompt, and template identities from the wire."""
    if not isinstance(values, list):
        return []
    records: list[dict[str, Any]] = []
    for value in values:
        payload = _model_mapping(value)
        records.append(
            {
                key: payload[key]
                for key in ("name", "uri", "description", "mimeType", "arguments", "uriTemplate")
                if key in payload
            }
        )
    return records


def _tool_result_record(result: object) -> dict[str, Any]:
    """Measure a live tool response without preserving its data payload."""
    payload = _model_mapping(result)
    structured = payload.get("structuredContent")
    content = payload.get("content", [])
    return {
        "tool_name": "inspect_vocab",
        "arguments": {"detail": "summary"},
        "is_error": bool(payload.get("isError", False)),
        "result_bytes": _json_size(payload),
        "structured_content_bytes": _json_size(structured) if structured is not None else 0,
        "content_bytes": _json_size(content),
    }


async def capture_mcp_surface(repo_root: str | Path = REPO_ROOT) -> dict[str, Any]:
    """Capture the public MCP surface through the same runtime used by the agent."""
    runtime = LocalStdioMcpRuntime(server_root=Path(repo_root))
    async with runtime.open_session() as session:
        tools_result = await session.list_tools()
        resources_result = await session.list_resources()
        prompts_result = await session.list_prompts()
        templates_result = await session.list_resource_templates()
        probe_result = await session.call_tool("inspect_vocab", {"detail": "summary"})
    tools = getattr(tools_result, "tools", [])
    return {
        "version": 1,
        "transport": "production-stdio",
        "tools": [_tool_record(tool) for tool in tools],
        "resources": _named_records(getattr(resources_result, "resources", [])),
        "prompts": _named_records(getattr(prompts_result, "prompts", [])),
        "resource_templates": _named_records(getattr(templates_result, "resourceTemplates", [])),
        "probe": _tool_result_record(probe_result),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "tests" / "fixtures" / "mcp_contract_baseline_v1.json",
        help="Baseline JSON destination.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root used by the production MCP subprocess.",
    )
    return parser.parse_args()


def main() -> int:
    """Capture the baseline and write deterministic JSON evidence."""
    args = _parse_args()
    payload = asyncio.run(capture_mcp_surface(args.repo_root.resolve()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote MCP contract baseline: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
