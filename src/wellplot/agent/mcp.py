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

"""Local stdio MCP runtime helpers for the public authoring API."""

from __future__ import annotations

import base64
import os
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from wellplot.errors import DependencyUnavailableError

from .core import FunctionToolDefinition

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterable


def _server_command() -> tuple[str, list[str]]:
    """Return the preferred command for launching the local stdio MCP server."""
    sibling_entry_point = Path(sys.executable).with_name("wellplot-mcp")
    if sibling_entry_point.exists():
        return str(sibling_entry_point), []
    return sys.executable, ["-m", "wellplot.mcp.server"]


def _server_env() -> dict[str, str]:
    """Build one child environment that preserves the current import resolution."""
    env = dict(os.environ)
    pythonpath_entries: list[str] = []
    for entry in sys.path:
        if not entry:
            continue
        try:
            resolved = str(Path(entry).resolve())
        except OSError:
            continue
        if resolved not in pythonpath_entries:
            pythonpath_entries.append(resolved)
    existing_pythonpath = env.get("PYTHONPATH")
    if existing_pythonpath:
        for entry in existing_pythonpath.split(os.pathsep):
            if entry and entry not in pythonpath_entries:
                pythonpath_entries.append(entry)
    if pythonpath_entries:
        env["PYTHONPATH"] = os.pathsep.join(pythonpath_entries)
    return env


def _load_mcp_runtime() -> tuple[type[object], type[object], object]:
    """Import the optional MCP client SDK on demand."""
    try:
        from mcp.client.session import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client
    except ModuleNotFoundError as exc:
        raise DependencyUnavailableError(
            "Install `wellplot[agent]` or `wellplot[mcp]` to use the public authoring session."
        ) from exc
    return ClientSession, StdioServerParameters, stdio_client


@dataclass(frozen=True)
class LocalStdioMcpRuntime:
    """Runtime adapter that launches `wellplot-mcp` over local stdio."""

    server_root: Path | str | None = None

    def __post_init__(self) -> None:
        """Normalize the configured server root into one absolute path."""
        root = (
            Path.cwd().resolve() if self.server_root is None else Path(self.server_root).resolve()
        )
        object.__setattr__(self, "server_root", root)

    @asynccontextmanager
    async def open_session(self) -> AsyncIterator[object]:
        """Open one MCP client session rooted at the configured local directory."""
        ClientSession, StdioServerParameters, stdio_client = _load_mcp_runtime()
        command, args = _server_command()
        server = StdioServerParameters(
            command=command,
            args=args,
            env=_server_env(),
            cwd=str(self.server_root),
        )
        async with stdio_client(server) as streams, ClientSession(*streams) as session:
            await session.initialize()
            yield session

    def build_tool_definitions(
        self,
        mcp_tools: Iterable[object],
        *,
        allowed_names: set[str],
        excluded_names: set[str] | None = None,
    ) -> list[FunctionToolDefinition]:
        """Convert raw MCP tool descriptors into generic function-tool models."""
        excluded = set() if excluded_names is None else set(excluded_names)
        definitions: list[FunctionToolDefinition] = []
        for tool in mcp_tools:
            name = getattr(tool, "name", "")
            if not isinstance(name, str) or name not in allowed_names or name in excluded:
                continue
            description = getattr(tool, "description", None)
            schema = getattr(tool, "inputSchema", None)
            parameters = (
                schema if isinstance(schema, dict) else {"type": "object", "properties": {}}
            )
            definitions.append(
                FunctionToolDefinition(
                    name=name,
                    description=description if isinstance(description, str) else f"Call {name}.",
                    parameters=parameters,
                )
            )
        return definitions

    def prompt_text(self, result: object) -> str:
        """Extract the first text prompt from one MCP prompt response."""
        messages = getattr(result, "messages", None)
        if not messages:
            raise RuntimeError("Expected prompt messages from the MCP prompt response.")
        content = getattr(messages[0], "content", None)
        text = getattr(content, "text", None)
        if not isinstance(text, str):
            raise RuntimeError("Expected text content from the MCP prompt response.")
        return text

    def image_bytes(self, result: object) -> bytes:
        """Extract raw bytes from one MCP image response."""
        content = getattr(result, "content", None)
        if not content:
            raise RuntimeError("Expected image content from the MCP tool response.")
        image_data = getattr(content[0], "data", None)
        if isinstance(image_data, bytes):
            return image_data
        if isinstance(image_data, str):
            return base64.b64decode(image_data)
        raise RuntimeError("Expected base64 image data from the MCP tool response.")

    def tool_result_payload(self, result: object) -> dict[str, object]:
        """Normalize one MCP tool result for provider tool-loop replay."""
        structured = getattr(result, "structuredContent", None)
        if isinstance(structured, dict):
            return {"structured": structured}

        content_items: list[dict[str, object]] = []
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
                        "note": "Binary content omitted from provider tool replay.",
                    }
                )
        return {"content": content_items}
