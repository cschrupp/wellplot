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
from collections.abc import Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from wellplot.errors import DependencyUnavailableError

from .core import FunctionToolDefinition

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterable


STABLE_MCP_SERVER_MODULE = "wellplot.mcp.server"
AGENTIC_MCP_SERVER_MODULE = "wellplot.mcp.agentic_server"
_SUPPORTED_SERVER_MODULES = frozenset(
    {
        STABLE_MCP_SERVER_MODULE,
        AGENTIC_MCP_SERVER_MODULE,
    }
)


def _server_command(server_module: str) -> tuple[str, list[str]]:
    """Launch one supported local MCP server with the host interpreter."""
    if server_module not in _SUPPORTED_SERVER_MODULES:
        raise ValueError(f"Unsupported local MCP server module: {server_module!r}.")
    return sys.executable, ["-m", server_module]


def _server_env(extra_environment: Mapping[str, str]) -> dict[str, str]:
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
    env.update(extra_environment)
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
    """Runtime adapter that launches one supported local MCP server over stdio."""

    server_root: Path | str | None = None
    server_module: str = STABLE_MCP_SERVER_MODULE
    server_environment: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Normalize the configured root, entry point, and child environment."""
        root = (
            Path.cwd().resolve() if self.server_root is None else Path(self.server_root).resolve()
        )
        if self.server_module not in _SUPPORTED_SERVER_MODULES:
            raise ValueError(f"Unsupported local MCP server module: {self.server_module!r}.")
        environment: dict[str, str] = {}
        for key, value in self.server_environment.items():
            if not isinstance(key, str) or not key:
                raise ValueError("MCP child environment keys must be non-empty strings.")
            if not isinstance(value, str):
                raise ValueError("MCP child environment values must be strings.")
            environment[key] = value
        object.__setattr__(self, "server_root", root)
        object.__setattr__(self, "server_environment", environment)

    @asynccontextmanager
    async def open_session(self) -> AsyncIterator[object]:
        """Open one MCP client session rooted at the configured local directory."""
        ClientSession, StdioServerParameters, stdio_client = _load_mcp_runtime()
        command, args = _server_command(self.server_module)
        server = StdioServerParameters(
            command=command,
            args=args,
            env=_server_env(self.server_environment),
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
        is_error = bool(getattr(result, "isError", False))
        payload: dict[str, object] = {"is_error": is_error}
        structured = getattr(result, "structuredContent", None)
        if isinstance(structured, dict):
            payload["structured"] = structured
            if is_error:
                error_value = structured.get("error") or structured.get("message")
                if isinstance(error_value, str) and error_value.strip():
                    payload["error"] = error_value.strip()
            return payload

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
        payload["content"] = content_items
        if is_error:
            error_text = "\n".join(
                str(item["text"]).strip()
                for item in content_items
                if isinstance(item.get("text"), str) and item["text"].strip()
            )
            if error_text:
                payload["error"] = error_text
        return payload
