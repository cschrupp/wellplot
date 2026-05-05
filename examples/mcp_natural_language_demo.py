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

"""Drive local wellplot MCP authoring from the OpenAI Responses API."""

from __future__ import annotations

import base64
import json
import os
import shutil
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterable

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
DEFAULT_EXAMPLE_ID = "forge16b_porosity_example"
DEFAULT_OUTPUT_LOGFILE = Path("workspace/mcp_demo/openai_forge16b_recreated.log.yaml")
DEFAULT_GOAL = (
    "Recreate the forge16b porosity example as a simplified interpretation packet. "
    "Keep one GR/SP track, one depth track, one resistivity track, and one porosity "
    "overlay track with RHOB and NPHI. Shorten the remarks to one concise block and "
    "simplify the heading."
)
ALLOWED_MCP_TOOLS = (
    "create_logfile_draft",
    "summarize_logfile_draft",
    "validate_logfile",
    "inspect_logfile",
    "inspect_data_source",
    "check_channel_availability",
    "inspect_heading_slots",
    "parse_key_value_text",
    "preview_header_mapping",
    "apply_header_values",
    "inspect_style_presets",
    "inspect_authoring_vocab",
    "add_track",
    "bind_curve",
    "update_curve_binding",
    "move_track",
    "set_heading_content",
    "set_remarks_content",
    "summarize_logfile_changes",
)


def repo_root() -> Path:
    """Return the repository root that contains the example checkout."""
    return Path(__file__).resolve().parents[1]


def repo_relative(path: str | Path) -> str:
    """Return one path relative to the repository root."""
    raw = Path(path)
    if raw.is_absolute():
        return raw.resolve().relative_to(repo_root()).as_posix()
    return raw.as_posix()


def load_openai_api_key() -> tuple[str, str]:
    """Load one API key from ignored local files or the process environment."""
    env_key = os.getenv("OPENAI_API_KEY", "").strip()
    if env_key:
        return env_key, "environment variable OPENAI_API_KEY"

    env_paths = (repo_root() / ".env.local", repo_root() / ".env")
    for env_path in env_paths:
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            if key.strip() != "OPENAI_API_KEY" or not value.strip():
                continue
            token = value.strip().strip('"').strip("'")
            if token:
                return token, str(env_path.relative_to(repo_root()))

    text_paths = (
        repo_root() / "OPENAI_API_KEY.txt",
        repo_root() / "openai_api_key.txt",
    )
    for text_path in text_paths:
        if not text_path.exists():
            continue
        token = text_path.read_text(encoding="utf-8").strip()
        if token:
            return token, str(text_path.relative_to(repo_root()))

    raise RuntimeError(
        "Set OPENAI_API_KEY or create one of .env.local, .env, OPENAI_API_KEY.txt, "
        "or openai_api_key.txt in the repository root."
    )


def load_openai_client() -> tuple[object, str]:
    """Return one configured OpenAI client and the token source description."""
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("Install the `openai` package before running this example.") from exc
    api_key, token_source = load_openai_api_key()
    return OpenAI(api_key=api_key), token_source


def _load_mcp_runtime() -> tuple[type[Any], type[Any], Any]:
    try:
        from mcp.client.session import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Install the published 'wellplot[mcp,las]' package in the active "
            "environment before running this example."
        ) from exc
    return ClientSession, StdioServerParameters, stdio_client


def _server_command() -> tuple[str, list[str]]:
    entry_point = shutil.which("wellplot-mcp")
    if entry_point is not None:
        return entry_point, []
    return sys.executable, ["-m", "wellplot.mcp.server"]


@asynccontextmanager
async def open_mcp_session() -> AsyncIterator[object]:
    """Start one stdio MCP session rooted at the repository checkout."""
    ClientSession, StdioServerParameters, stdio_client = _load_mcp_runtime()
    command, args = _server_command()
    server = StdioServerParameters(
        command=command,
        args=args,
        cwd=str(repo_root()),
    )
    async with stdio_client(server) as streams, ClientSession(*streams) as session:
        await session.initialize()
        yield session


def first_prompt_text(result: object) -> str:
    """Return the first prompt text payload from one MCP prompt response."""
    messages = getattr(result, "messages", None)
    if not messages:
        raise RuntimeError("Expected prompt messages from the MCP prompt response.")
    content = getattr(messages[0], "content", None)
    text = getattr(content, "text", None)
    if not isinstance(text, str):
        raise RuntimeError("Expected text content from the MCP prompt response.")
    return text


def decode_image_bytes(result: object) -> bytes:
    """Return raw image bytes from one MCP image result."""
    content = getattr(result, "content", None)
    if not content:
        raise RuntimeError("Expected image content from the MCP tool response.")
    image_data = getattr(content[0], "data", None)
    if isinstance(image_data, bytes):
        return image_data
    if isinstance(image_data, str):
        return base64.b64decode(image_data)
    raise RuntimeError("Expected base64 image data from the MCP tool response.")


def tool_result_payload(result: object) -> dict[str, Any]:
    """Normalize one MCP tool result for replay into the OpenAI loop."""
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        return {"structured": structured}

    content_items: list[dict[str, Any]] = []
    for item in getattr(result, "content", []) or []:
        item_type = getattr(item, "type", None)
        text = getattr(item, "text", None)
        if isinstance(text, str):
            content_items.append({"type": item_type, "text": text})
            continue
        if getattr(item, "data", None) is not None:
            content_items.append(
                {
                    "type": item_type,
                    "mime_type": getattr(item, "mimeType", None),
                    "note": "Binary content omitted from OpenAI tool replay.",
                }
            )
    return {"content": content_items}


def build_openai_function_tools(
    mcp_tools: Iterable[object],
    *,
    excluded_names: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Convert the MCP tool list into OpenAI Responses API function tools."""
    excluded = set() if excluded_names is None else set(excluded_names)
    function_tools: list[dict[str, Any]] = []
    for tool in mcp_tools:
        name = getattr(tool, "name", "")
        if name not in ALLOWED_MCP_TOOLS or name in excluded:
            continue
        schema = getattr(tool, "inputSchema", None) or {
            "type": "object",
            "properties": {},
        }
        function_tools.append(
            {
                "type": "function",
                "name": name,
                "description": getattr(tool, "description", None) or f"Call {name}.",
                "parameters": schema,
            }
        )
    return function_tools


async def run_openai_authoring(
    *,
    goal: str = DEFAULT_GOAL,
    example_id: str = DEFAULT_EXAMPLE_ID,
    output_logfile: str | Path = DEFAULT_OUTPUT_LOGFILE,
    model: str = DEFAULT_MODEL,
    max_rounds: int = 12,
) -> dict[str, Any]:
    """Run one natural-language authoring pass through OpenAI + local MCP."""
    client, token_source = load_openai_client()
    relative_output_logfile = repo_relative(output_logfile)
    output_path = repo_root() / relative_output_logfile
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    async with open_mcp_session() as session:
        baseline_result = await session.call_tool(
            "create_logfile_draft",
            {
                "output_path": relative_output_logfile,
                "example_id": example_id,
                "overwrite": True,
            },
        )
        baseline_draft_text = output_path.read_text(encoding="utf-8")
        bootstrap_summary = await session.call_tool(
            "summarize_logfile_draft",
            {"logfile_path": relative_output_logfile},
        )
        bootstrap_vocab = await session.call_tool(
            "inspect_authoring_vocab",
            {"logfile_path": relative_output_logfile},
        )
        prompt_result = await session.get_prompt(
            "author_plot_from_request",
            {
                "goal": goal,
                "logfile_path": relative_output_logfile,
                "example_id": example_id,
            },
        )
        authoring_prompt = first_prompt_text(prompt_result)
        tools_result = await session.list_tools()
        function_tools = build_openai_function_tools(
            tools_result.tools,
            excluded_names={"create_logfile_draft"},
        )
        if not function_tools:
            raise RuntimeError("No MCP tools were exposed to the OpenAI loop.")

        bootstrap_sections = []
        for section in bootstrap_summary.structuredContent.get("sections", []):
            bootstrap_sections.append(
                {
                    "id": section.get("id"),
                    "track_ids": section.get("track_ids", []),
                    "track_kinds": section.get("track_kinds", []),
                    "available_channels": section.get("available_channels", []),
                }
            )
        bootstrap_context = {
            "draft_logfile": relative_output_logfile,
            "seed_result": baseline_result.structuredContent,
            "sections": bootstrap_sections,
            "heading_patch_keys": bootstrap_vocab.structuredContent.get("heading_patch_keys", []),
            "curve_binding_patch_keys": bootstrap_vocab.structuredContent.get(
                "curve_binding_patch_keys", []
            ),
        }
        initial_input: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            f"A starter draft already exists at `{relative_output_logfile}` "
                            f"from packaged example `{example_id}`. Do not call "
                            "create_logfile_draft again. Use MCP mutation tools only, and "
                            "make real changes before you finish. At minimum, apply one "
                            "heading patch and one concise remarks replacement that satisfy "
                            f"the goal.\n\nDraft context:\n"
                            f"{json.dumps(bootstrap_context, indent=2)}\n\n"
                            "Mutation call examples:\n"
                            f'- set_heading_content({{"logfile_path": "{relative_output_logfile}", '
                            '"patch": {"provider_name": "OpenAI Demo", "service_titles": '
                            '[{"value": "Simplified Porosity Review", "alignment": "center", '
                            '"bold": true}]}}})\n'
                            f'- set_remarks_content({{"logfile_path": "{relative_output_logfile}", '
                            '"remarks": [{"title": "Simplified reconstruction", "lines": '
                            '["Short QC note."], "alignment": "left"}]}})\n\n'
                            "Use MCP tools only; do not rewrite YAML in prose.\n\n"
                            f"Goal:\n{goal}"
                        ),
                    }
                ],
            }
        ]
        tool_trace: list[dict[str, Any]] = []
        final_text = ""
        response = None
        pending_input: list[dict[str, Any]] = initial_input

        for round_index in range(1, max_rounds + 1):
            request_kwargs: dict[str, Any] = {
                "model": model,
                "tools": function_tools,
            }
            if response is None:
                request_kwargs["instructions"] = authoring_prompt
                request_kwargs["input"] = pending_input
            else:
                request_kwargs["previous_response_id"] = response.id
                request_kwargs["input"] = pending_input
            response = client.responses.create(**request_kwargs)
            function_calls = [
                item for item in response.output if getattr(item, "type", None) == "function_call"
            ]
            if not function_calls:
                final_text = response.output_text
                break

            pending_input = []
            for call in function_calls:
                arguments = json.loads(call.arguments or "{}")
                tool_trace.append(
                    {
                        "round": round_index,
                        "name": call.name,
                        "arguments": arguments,
                    }
                )
                tool_result = await session.call_tool(call.name, arguments)
                pending_input.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps(tool_result_payload(tool_result)),
                    }
                )
        else:
            raise RuntimeError(f"The OpenAI authoring loop exceeded {max_rounds} rounds.")

        if response is not None and not final_text.strip():
            summary_response = client.responses.create(
                model=model,
                previous_response_id=response.id,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": (
                                    "Summarize the applied draft changes in three concise "
                                    "bullet points without calling more tools."
                                ),
                            }
                        ],
                    }
                ],
            )
            final_text = summary_response.output_text

        if not output_path.exists():
            raise RuntimeError("The model finished without creating the expected draft logfile.")

        validation = await session.call_tool(
            "validate_logfile",
            {"logfile_path": relative_output_logfile},
        )
        draft_summary = await session.call_tool(
            "summarize_logfile_draft",
            {"logfile_path": relative_output_logfile},
        )
        inspect_summary = await session.call_tool(
            "inspect_logfile",
            {"logfile_path": relative_output_logfile},
        )
        change_summary = await session.call_tool(
            "summarize_logfile_changes",
            {
                "logfile_path": relative_output_logfile,
                "previous_text": baseline_draft_text,
            },
        )
        first_section_id = inspect_summary.structuredContent["section_ids"][0]
        report_preview = await session.call_tool(
            "preview_logfile_png",
            {
                "logfile_path": relative_output_logfile,
                "page_index": 0,
                "dpi": 72,
                "include_report_pages": True,
            },
        )
        section_preview = await session.call_tool(
            "preview_section_png",
            {
                "logfile_path": relative_output_logfile,
                "section_id": first_section_id,
                "dpi": 72,
            },
        )

    return {
        "token_source": token_source,
        "model": model,
        "example_id": example_id,
        "goal": goal,
        "draft_logfile": relative_output_logfile,
        "tool_trace": tool_trace,
        "final_text": final_text,
        "validation": dict(validation.structuredContent),
        "draft_summary": dict(draft_summary.structuredContent),
        "inspect_summary": dict(inspect_summary.structuredContent),
        "change_summary": dict(change_summary.structuredContent),
        "report_preview_png": decode_image_bytes(report_preview),
        "section_preview_png": decode_image_bytes(section_preview),
        "draft_text": output_path.read_text(encoding="utf-8"),
    }


def write_preview_artifacts(result: dict[str, Any]) -> dict[str, str]:
    """Write the returned preview PNGs next to the generated draft logfile."""
    draft_relative = Path(str(result["draft_logfile"]))
    output_dir = repo_root() / draft_relative.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = draft_relative.stem.removesuffix(".log")

    report_preview = output_dir / f"{stem}_report_preview.png"
    section_preview = output_dir / f"{stem}_section_preview.png"
    report_preview.write_bytes(result["report_preview_png"])
    section_preview.write_bytes(result["section_preview_png"])
    return {
        "report_preview": repo_relative(report_preview),
        "section_preview": repo_relative(section_preview),
    }


async def _run_demo() -> None:
    result = await run_openai_authoring()
    preview_paths = write_preview_artifacts(result)
    summary = {
        "model": result["model"],
        "token_source": result["token_source"],
        "draft_logfile": result["draft_logfile"],
        "preview_paths": preview_paths,
        "tool_trace": result["tool_trace"],
        "validation": result["validation"],
        "summary_lines": result["change_summary"].get("summary_lines", []),
        "final_text": result["final_text"],
    }
    print(json.dumps(summary, indent=2))


def main() -> None:
    """Run the natural-language MCP authoring demo as a normal Python script."""
    import anyio

    anyio.run(_run_demo)


if __name__ == "__main__":
    main()
