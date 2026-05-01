###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
###############################################################################

"""Demonstrate the experimental wellplot MCP workflow against a production example."""

from __future__ import annotations

import base64
import json
import shutil
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

DEFAULT_EXAMPLE_ID = "cbl_log_example"
DEFAULT_LOGFILE = Path("examples/production/cbl_log_example/full_reconstruction.log.yaml")
DEFAULT_BASE_DIR = DEFAULT_LOGFILE.parent
DEFAULT_OUTPUT_ROOT = Path("workspace/mcp_demo")
DEFAULT_RENDER_LOGFILE = DEFAULT_LOGFILE
DEFAULT_HEADER_LOGFILE = Path(
    "examples/production/forge16b_porosity_example/full_reconstruction.log.yaml"
)
DEFAULT_HEADER_DRAFT_SUFFIX = "header_ingestion_draft.log.yaml"
SAMPLE_HEADER_PACKET = "\n".join(
    [
        "Provider: Acme Logging",
        "Company: Acme Energy",
        "Well: Demo-01",
        "Service Company: Acme Wireline",
        "Date: 2026-04-30",
        "Run: ONE",
        "Direction: Up",
        "Service Title: Gamma Ray Review",
    ]
)
HEADER_PAIR_TO_SLOT_KEY = {
    "provider": "provider",
    "company": "general_field.company",
    "well": "general_field.well",
    "service company": "general_field.service_company",
    "date": "detail.date",
    "run": "detail.run",
    "direction": "detail.direction",
    "service title": "service_title_1",
}


def repo_root() -> Path:
    """Return the repository root that contains the example checkout."""
    return Path(__file__).resolve().parents[1]


def default_export_dir(
    *,
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
    example_id: str = DEFAULT_EXAMPLE_ID,
) -> Path:
    """Return the export target used by the writable MCP example calls."""
    return Path(output_root) / f"exported_{example_id}"


def default_render_output(
    *,
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
    logfile_path: str | Path = DEFAULT_RENDER_LOGFILE,
) -> Path:
    """Return the explicit render target used by the demo."""
    stem = Path(logfile_path).name.removesuffix(".log.yaml")
    return Path(output_root) / f"{stem}_mcp.pdf"


def default_saved_logfile(
    *,
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
    example_id: str = DEFAULT_EXAMPLE_ID,
) -> Path:
    """Return the normalized logfile path written by the demo."""
    return Path(output_root) / f"{example_id}_saved.log.yaml"


def default_header_draft_logfile(
    *,
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
    logfile_path: str | Path = DEFAULT_LOGFILE,
) -> Path:
    """Return the normalized draft path used by the header-ingestion walkthrough."""
    stem = Path(logfile_path).name.removesuffix(".log.yaml")
    return Path(output_root) / f"{stem}_{DEFAULT_HEADER_DRAFT_SUFFIX}"


def relative_repo_path(path: str | Path) -> str:
    """Return one path relative to the repository root."""
    raw = Path(path)
    if not raw.is_absolute():
        return raw.as_posix()
    return raw.resolve().relative_to(repo_root()).as_posix()


def logfile_text(logfile_path: str | Path = DEFAULT_LOGFILE) -> str:
    """Return the source logfile text used for text-authoring demo calls."""
    return (repo_root() / Path(relative_repo_path(logfile_path))).read_text(encoding="utf-8")


def decode_image_data(image_data: str | bytes) -> bytes:
    """Return raw PNG bytes from one MCP image payload."""
    if isinstance(image_data, bytes):
        return image_data
    return base64.b64decode(image_data)


def header_packet_text(source_text: str | None = None) -> str:
    """Return the copied header packet text used by the ingestion walkthrough."""
    return SAMPLE_HEADER_PACKET if source_text is None else source_text


def map_header_pairs_to_values(
    pairs: list[dict[str, str]],
) -> tuple[dict[str, str], list[dict[str, str]]]:
    """Map parsed header pairs onto explicit wellplot heading-slot keys."""
    values: dict[str, str] = {}
    unmapped_pairs: list[dict[str, str]] = []
    for pair in pairs:
        key = str(pair.get("key", "")).strip().lower()
        value = str(pair.get("value", "")).strip()
        target_key = HEADER_PAIR_TO_SLOT_KEY.get(key)
        if target_key is None:
            unmapped_pairs.append({"key": key, "value": value})
            continue
        values[target_key] = value
    return values, unmapped_pairs


def _empty_heading_patch() -> dict[str, object]:
    """Return one minimal editable heading skeleton for ingestion demos."""
    return {
        "enabled": True,
        "provider_name": "",
        "general_fields": [
            {"label": "Company", "value": ""},
            {"label": "Well", "value": ""},
            {"label": "Service Company", "value": ""},
        ],
        "service_titles": [{"value": "", "alignment": "left"}],
        "detail": [
            {
                "label_cells": ["Date", "Run", "Direction"],
                "columns": [
                    {"cells": ["", "", ""]},
                    {"cells": ["", "", ""]},
                ],
            }
        ],
        "tail_enabled": True,
    }


def _load_mcp_runtime() -> tuple[type[Any], type[Any], Any]:
    try:
        from mcp.client.session import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Install the published 'wellplot[mcp,notebook]' package in the active "
            "environment before running this example."
        ) from exc
    return ClientSession, StdioServerParameters, stdio_client


def _server_command() -> tuple[str, list[str]]:
    entry_point = shutil.which("wellplot-mcp")
    if entry_point is not None:
        return entry_point, []
    return sys.executable, ["-m", "wellplot.mcp.server"]


def _tool_image_bytes(result: object) -> bytes:
    content = getattr(result, "content", None)
    if not content:
        raise RuntimeError("Expected image content from the MCP tool call.")
    image_data = getattr(content[0], "data", None)
    if image_data is None:
        raise RuntimeError("Expected image data in the MCP tool response.")
    return decode_image_data(image_data)


def _first_resource_text(result: object) -> str:
    contents = getattr(result, "contents", None)
    if not contents:
        raise RuntimeError("Expected text content from the MCP resource response.")
    text = getattr(contents[0], "text", None)
    if not isinstance(text, str):
        raise RuntimeError("Expected text content from the MCP resource response.")
    return text


def _first_prompt_text(result: object) -> str:
    messages = getattr(result, "messages", None)
    if not messages:
        raise RuntimeError("Expected prompt messages from the MCP prompt response.")
    content = getattr(messages[0], "content", None)
    text = getattr(content, "text", None)
    if not isinstance(text, str):
        raise RuntimeError("Expected text content from the MCP prompt response.")
    return text


@asynccontextmanager
async def open_mcp_session(root: str | Path | None = None) -> AsyncIterator[Any]:
    """Start one stdio MCP session rooted at the repository checkout."""
    ClientSession, StdioServerParameters, stdio_client = _load_mcp_runtime()
    server_root = repo_root() if root is None else Path(root).resolve()
    command, args = _server_command()
    server = StdioServerParameters(
        command=command,
        args=args,
        cwd=str(server_root),
    )
    async with stdio_client(server) as streams, ClientSession(*streams) as session:
        await session.initialize()
        yield session


async def collect_server_contract(
    logfile_path: str | Path = DEFAULT_LOGFILE,
    *,
    root: str | Path | None = None,
) -> dict[str, Any]:
    """Return the current public MCP surface in a notebook-friendly structure."""
    relative_logfile = relative_repo_path(logfile_path)
    async with open_mcp_session(root) as session:
        tools = await session.list_tools()
        resources = await session.list_resources()
        templates = await session.list_resource_templates()
        prompts = await session.list_prompts()
        manifest = await session.read_resource("wellplot://examples/production/index.json")
        review_prompt = await session.get_prompt(
            "review_logfile",
            {"logfile_path": relative_logfile},
        )

    return {
        "tools": [tool.name for tool in tools.tools],
        "resources": [str(resource.uri) for resource in resources.resources],
        "resource_templates": [template.uriTemplate for template in templates.resourceTemplates],
        "prompts": [prompt.name for prompt in prompts.prompts],
        "example_manifest": json.loads(_first_resource_text(manifest)),
        "review_prompt": _first_prompt_text(review_prompt),
    }


async def run_review_flow(
    logfile_path: str | Path = DEFAULT_LOGFILE,
    *,
    dpi: int = 96,
    root: str | Path | None = None,
) -> dict[str, Any]:
    """Validate, inspect, and preview one production logfile through MCP."""
    relative_logfile = relative_repo_path(logfile_path)
    async with open_mcp_session(root) as session:
        validation = await session.call_tool(
            "validate_logfile",
            {"logfile_path": relative_logfile},
        )
        inspection = await session.call_tool(
            "inspect_logfile",
            {"logfile_path": relative_logfile},
        )
        inspection_data = dict(inspection.structuredContent)
        first_section = inspection_data["sections"][0]
        section_id = first_section["id"]
        candidate_track_ids = [
            track_id for track_id in first_section["track_ids"] if track_id != "depth"
        ]
        selected_track_ids = (
            candidate_track_ids[:2] if candidate_track_ids else first_section["track_ids"][:1]
        )
        section_depth_range = first_section.get("depth_range") or [100.0, 200.0]
        window_top = float(section_depth_range[0])
        window_bottom = min(window_top + 100.0, float(section_depth_range[1]))
        if window_bottom <= window_top:
            window_bottom = window_top + 1.0

        section_preview = await session.call_tool(
            "preview_section_png",
            {
                "logfile_path": relative_logfile,
                "section_id": section_id,
                "dpi": dpi,
            },
        )
        track_preview = await session.call_tool(
            "preview_track_png",
            {
                "logfile_path": relative_logfile,
                "section_id": section_id,
                "track_ids": selected_track_ids,
                "dpi": dpi,
            },
        )
        window_preview = await session.call_tool(
            "preview_window_png",
            {
                "logfile_path": relative_logfile,
                "depth_range": [window_top, window_bottom],
                "section_ids": [section_id],
                "dpi": dpi,
            },
        )

    return {
        "validation": dict(validation.structuredContent),
        "inspection": inspection_data,
        "selected_section_id": section_id,
        "selected_track_ids": selected_track_ids,
        "window_depth_range": [window_top, window_bottom],
        "section_preview_png": _tool_image_bytes(section_preview),
        "track_preview_png": _tool_image_bytes(track_preview),
        "window_preview_png": _tool_image_bytes(window_preview),
    }


async def run_authoring_flow(
    logfile_path: str | Path = DEFAULT_LOGFILE,
    *,
    example_id: str = DEFAULT_EXAMPLE_ID,
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
    render_logfile_path: str | Path = DEFAULT_RENDER_LOGFILE,
    root: str | Path | None = None,
) -> dict[str, Any]:
    """Exercise the writable MCP tools against the same production example."""
    relative_base_dir = relative_repo_path(Path(logfile_path).parent)
    relative_output_root = relative_repo_path(output_root)
    relative_export_dir = relative_repo_path(
        default_export_dir(output_root=output_root, example_id=example_id)
    )
    relative_render_output = relative_repo_path(
        default_render_output(output_root=output_root, logfile_path=render_logfile_path)
    )
    relative_saved_logfile = relative_repo_path(
        default_saved_logfile(output_root=output_root, example_id=example_id)
    )
    relative_render_logfile = relative_repo_path(render_logfile_path)
    yaml_text = logfile_text(logfile_path)

    async with open_mcp_session(root) as session:
        exported = await session.call_tool(
            "export_example_bundle",
            {
                "example_id": example_id,
                "output_dir": relative_export_dir,
                "overwrite": True,
            },
        )
        text_validation = await session.call_tool(
            "validate_logfile_text",
            {
                "yaml_text": yaml_text,
                "base_dir": relative_base_dir,
            },
        )
        formatting = await session.call_tool(
            "format_logfile_text",
            {
                "yaml_text": yaml_text,
                "base_dir": relative_base_dir,
            },
        )
        saved = await session.call_tool(
            "save_logfile_text",
            {
                "yaml_text": yaml_text,
                "output_path": relative_saved_logfile,
                "overwrite": True,
                "base_dir": relative_base_dir,
            },
        )
        rendered = await session.call_tool(
            "render_logfile_to_file",
            {
                "logfile_path": relative_render_logfile,
                "output_path": relative_render_output,
                "overwrite": True,
            },
        )

    return {
        "output_root": relative_output_root,
        "rendered_logfile": relative_render_logfile,
        "export": dict(exported.structuredContent),
        "text_validation": dict(text_validation.structuredContent),
        "format": dict(formatting.structuredContent),
        "save": dict(saved.structuredContent),
        "render": dict(rendered.structuredContent),
        "formatted_yaml": formatting.structuredContent["yaml_text"],
    }


async def run_header_ingestion_flow(
    logfile_path: str | Path = DEFAULT_HEADER_LOGFILE,
    *,
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
    source_text: str | None = None,
    source_description: str = "Copied contractor header packet",
    overwrite_policy: str = "fill_empty",
    dpi: int = 96,
    root: str | Path | None = None,
) -> dict[str, Any]:
    """Exercise the `0.5.0` header-ingestion MCP workflow end to end."""
    relative_logfile = relative_repo_path(logfile_path)
    relative_draft_logfile = relative_repo_path(
        default_header_draft_logfile(output_root=output_root, logfile_path=logfile_path)
    )
    packet_text = header_packet_text(source_text)

    async with open_mcp_session(root) as session:
        draft = await session.call_tool(
            "create_logfile_draft",
            {
                "output_path": relative_draft_logfile,
                "source_logfile_path": relative_logfile,
                "overwrite": True,
            },
        )
        await session.call_tool(
            "set_heading_content",
            {
                "logfile_path": relative_draft_logfile,
                "patch": _empty_heading_patch(),
            },
        )
        await session.call_tool(
            "set_remarks_content",
            {
                "logfile_path": relative_draft_logfile,
                "remarks": [],
            },
        )
        prompt = await session.get_prompt(
            "ingest_header_text",
            {
                "logfile_path": relative_draft_logfile,
                "source_text": packet_text,
                "source_description": source_description,
            },
        )
        slots = await session.call_tool(
            "inspect_heading_slots",
            {"logfile_path": relative_draft_logfile},
        )
        parsed = await session.call_tool(
            "parse_key_value_text",
            {"source_text": packet_text},
        )
        mapped_values, unmapped_pairs = map_header_pairs_to_values(
            list(parsed.structuredContent["pairs"])
        )
        style_presets = await session.call_tool(
            "inspect_style_presets",
            {"preset_family": "report_page_styles"},
        )
        preview = await session.call_tool(
            "preview_header_mapping",
            {
                "logfile_path": relative_draft_logfile,
                "values": mapped_values,
                "overwrite_policy": overwrite_policy,
            },
        )
        applied = await session.call_tool(
            "apply_header_values",
            {
                "logfile_path": relative_draft_logfile,
                "values": mapped_values,
                "overwrite_policy": overwrite_policy,
            },
        )
        first_page_preview = await session.call_tool(
            "preview_logfile_png",
            {
                "logfile_path": relative_draft_logfile,
                "page_index": 0,
                "dpi": dpi,
                "include_report_pages": True,
            },
        )

    return {
        "draft": dict(draft.structuredContent),
        "draft_logfile": relative_draft_logfile,
        "source_text": packet_text,
        "source_description": source_description,
        "ingest_prompt": _first_prompt_text(prompt),
        "slots": dict(slots.structuredContent),
        "parsed": dict(parsed.structuredContent),
        "mapped_values": mapped_values,
        "unmapped_pairs": unmapped_pairs,
        "style_presets": dict(style_presets.structuredContent),
        "preview": dict(preview.structuredContent),
        "apply": dict(applied.structuredContent),
        "page_preview_png": _tool_image_bytes(first_page_preview),
    }


async def _run_demo() -> None:
    contract = await collect_server_contract()
    review = await run_review_flow()
    authoring = await run_authoring_flow()
    header_ingestion = await run_header_ingestion_flow()
    summary = {
        "tools": contract["tools"],
        "resources": contract["resources"],
        "prompts": contract["prompts"],
        "validated": review["validation"]["name"],
        "selected_section_id": review["selected_section_id"],
        "selected_track_ids": review["selected_track_ids"],
        "rendered_logfile": authoring["rendered_logfile"],
        "rendered_output": authoring["render"]["output_path"],
        "saved_logfile": authoring["save"]["output_path"],
        "exported_file_count": len(authoring["export"]["written_files"]),
        "header_draft_logfile": header_ingestion["draft_logfile"],
        "header_assignment_count": len(header_ingestion["apply"]["applied_assignments"]),
    }
    print(json.dumps(summary, indent=2))


def main() -> None:
    """Run the MCP workflow demo as a normal Python script."""
    import anyio

    anyio.run(_run_demo)


if __name__ == "__main__":
    main()
