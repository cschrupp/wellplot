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

"""Public host-side agent API for LLM-driven wellplot authoring."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Iterable
    from contextlib import AbstractAsyncContextManager

DEFAULT_ALLOWED_MCP_TOOLS = (
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


@dataclass(frozen=True)
class AuthoringRequest:
    """High-level natural-language authoring request."""

    goal: str
    example_id: str
    output_logfile: str
    max_rounds: int = 12


@dataclass(frozen=True)
class AuthoringToolCall:
    """One provider-issued tool call replayed through wellplot MCP."""

    round: int
    name: str
    arguments: dict[str, object]


@dataclass(frozen=True)
class FunctionToolDefinition:
    """Generic function-tool definition passed to one provider adapter."""

    name: str
    description: str
    parameters: dict[str, object]


@dataclass(frozen=True)
class ProviderRunResult:
    """Normalized provider loop result returned to the orchestration core."""

    final_text: str
    tool_trace: tuple[AuthoringToolCall, ...]


@dataclass(frozen=True)
class AuthoringResult:
    """Final result for one authoring request."""

    provider: str
    model: str
    credential_source: str | None
    example_id: str
    goal: str
    draft_logfile: str
    server_root: Path
    tool_trace: tuple[AuthoringToolCall, ...]
    final_text: str
    validation: dict[str, object]
    draft_summary: dict[str, object]
    inspect_summary: dict[str, object]
    change_summary: dict[str, object]
    draft_text: str
    report_preview_png: bytes = field(repr=False)
    section_preview_png: bytes = field(repr=False)

    @property
    def draft_path(self) -> Path:
        """Return the absolute path to the generated draft logfile."""
        return self.server_root / self.draft_logfile

    def write_preview_artifacts(
        self,
        *,
        output_dir: str | Path | None = None,
    ) -> dict[str, Path]:
        """Persist the in-memory preview PNGs and return their paths."""
        if output_dir is None:
            target_dir = self.draft_path.parent
        else:
            raw_target_dir = Path(output_dir)
            target_dir = (
                raw_target_dir
                if raw_target_dir.is_absolute()
                else self.server_root / raw_target_dir
            )
        target_dir.mkdir(parents=True, exist_ok=True)
        stem = self.draft_path.stem.removesuffix(".log")
        report_preview = target_dir / f"{stem}_report_preview.png"
        section_preview = target_dir / f"{stem}_section_preview.png"
        report_preview.write_bytes(self.report_preview_png)
        section_preview.write_bytes(self.section_preview_png)
        return {
            "report_preview": report_preview,
            "section_preview": section_preview,
        }


class McpSessionProtocol(Protocol):
    """Minimal MCP client session surface needed by the agent layer."""

    async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
        """Call one MCP tool."""

    async def get_prompt(self, name: str, arguments: dict[str, object]) -> object:
        """Request one MCP prompt."""

    async def list_tools(self) -> object:
        """List registered MCP tools."""


class McpRuntimeProtocol(Protocol):
    """Transport/runtime adapter for local MCP access."""

    server_root: Path

    def open_session(self) -> AbstractAsyncContextManager[McpSessionProtocol]:
        """Open one MCP client session."""

    def build_tool_definitions(
        self,
        mcp_tools: Iterable[object],
        *,
        allowed_names: set[str],
        excluded_names: set[str] | None = None,
    ) -> list[FunctionToolDefinition]:
        """Convert raw MCP tool descriptors into generic function tools."""

    def prompt_text(self, result: object) -> str:
        """Extract the first text prompt from one MCP prompt response."""

    def image_bytes(self, result: object) -> bytes:
        """Extract raw bytes from one MCP image response."""

    def tool_result_payload(self, result: object) -> dict[str, object]:
        """Normalize one MCP tool result for provider tool-loop replay."""


ToolCaller = Callable[[str, dict[str, object]], Awaitable[dict[str, object]]]


class ProviderBackendProtocol(Protocol):
    """Provider adapter used by the public authoring session."""

    provider: str
    model: str
    credential_source: str | None

    async def run_authoring(
        self,
        *,
        instructions: str,
        initial_user_message: str,
        tool_definitions: list[FunctionToolDefinition],
        tool_caller: ToolCaller,
        max_rounds: int,
    ) -> ProviderRunResult:
        """Run one authoring loop and replay provider tool calls."""


def _relative_logfile_path(root: Path, output_logfile: str | Path) -> str:
    """Return one logfile path relative to the configured server root."""
    raw = Path(output_logfile)
    if raw.is_absolute():
        return raw.resolve().relative_to(root).as_posix()
    return raw.as_posix()


def _structured_content(result: object) -> dict[str, object]:
    """Return one MCP structured content payload as a plain dict."""
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return dict(structured)
    if structured is None:
        return {}
    raise RuntimeError("Expected MCP structured content to be a mapping.")


def _authoring_bootstrap_message(
    *,
    goal: str,
    example_id: str,
    logfile_path: str,
    seed_result: dict[str, object],
    sections: list[dict[str, object]],
    heading_patch_keys: list[object],
    curve_binding_patch_keys: list[object],
) -> str:
    """Return the initial user message passed into the provider loop."""
    bootstrap_context = {
        "draft_logfile": logfile_path,
        "seed_result": seed_result,
        "sections": sections,
        "heading_patch_keys": heading_patch_keys,
        "curve_binding_patch_keys": curve_binding_patch_keys,
    }
    return (
        f"A starter draft already exists at `{logfile_path}` from packaged example "
        f"`{example_id}`. Do not call create_logfile_draft again. Use MCP mutation "
        "tools only, and make real changes before you finish. At minimum, apply one "
        "heading patch and one concise remarks replacement that satisfy the goal.\n\n"
        "Draft context:\n"
        f"{json.dumps(bootstrap_context, indent=2)}\n\n"
        "Mutation call examples:\n"
        f'- set_heading_content({{"logfile_path": "{logfile_path}", "patch": '
        '{"provider_name": "OpenAI Demo", "service_titles": [{"value": '
        '"Simplified Porosity Review", "alignment": "center", "bold": true}]}})\n'
        f'- set_remarks_content({{"logfile_path": "{logfile_path}", "remarks": '
        '[{"title": "Simplified reconstruction", "lines": ["Short QC note."], '
        '"alignment": "left"}]}})\n\n'
        "Use MCP tools only; do not rewrite YAML in prose.\n\n"
        f"Goal:\n{goal}"
    )


@dataclass
class AuthoringSession:
    """High-level authoring session bound to one provider and local MCP runtime."""

    backend: ProviderBackendProtocol
    runtime: McpRuntimeProtocol
    allowed_tool_names: tuple[str, ...] = DEFAULT_ALLOWED_MCP_TOOLS

    @classmethod
    def from_local_mcp(
        cls,
        *,
        provider: str,
        model: str,
        server_root: str | Path | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> AuthoringSession:
        """Create one public authoring session backed by local stdio MCP."""
        from .mcp import LocalStdioMcpRuntime
        from .providers.openai import OpenAIAuthoringBackend
        from .providers.openai_compat import OpenAICompatibleAuthoringBackend

        runtime = LocalStdioMcpRuntime(server_root=server_root)
        if provider == "openai":
            backend = OpenAIAuthoringBackend.from_local_configuration(
                model=model,
                server_root=runtime.server_root,
                api_key=api_key,
            )
        elif provider == "openai_compat":
            if base_url is None or not base_url.strip():
                raise ValueError("provider='openai_compat' requires a non-empty base_url.")
            backend = OpenAICompatibleAuthoringBackend.from_local_configuration(
                model=model,
                server_root=runtime.server_root,
                api_key=api_key,
                base_url=base_url,
            )
        else:
            raise ValueError(
                "Unsupported authoring provider. Supported values: 'openai', 'openai_compat'."
            )
        return cls(backend=backend, runtime=runtime)

    async def run_request(self, request: AuthoringRequest) -> AuthoringResult:
        """Run one authoring request from the provider-neutral request model."""
        relative_output_logfile = _relative_logfile_path(
            self.runtime.server_root, request.output_logfile
        )

        async with self.runtime.open_session() as session:
            baseline_result = await session.call_tool(
                "create_logfile_draft",
                {
                    "output_path": relative_output_logfile,
                    "example_id": request.example_id,
                    "overwrite": True,
                },
            )
            output_path = self.runtime.server_root / relative_output_logfile
            baseline_draft_text = output_path.read_text(encoding="utf-8")

            bootstrap_summary_result = await session.call_tool(
                "summarize_logfile_draft",
                {"logfile_path": relative_output_logfile},
            )
            bootstrap_vocab_result = await session.call_tool(
                "inspect_authoring_vocab",
                {"logfile_path": relative_output_logfile},
            )
            prompt_result = await session.get_prompt(
                "author_plot_from_request",
                {
                    "goal": request.goal,
                    "logfile_path": relative_output_logfile,
                    "example_id": request.example_id,
                },
            )
            authoring_prompt = self.runtime.prompt_text(prompt_result)
            tools_result = await session.list_tools()
            tool_definitions = self.runtime.build_tool_definitions(
                getattr(tools_result, "tools", []),
                allowed_names=set(self.allowed_tool_names),
                excluded_names={"create_logfile_draft"},
            )
            if not tool_definitions:
                raise RuntimeError("No MCP tools were exposed to the authoring loop.")

            bootstrap_summary = _structured_content(bootstrap_summary_result)
            bootstrap_vocab = _structured_content(bootstrap_vocab_result)
            sections = []
            for section in bootstrap_summary.get("sections", []):
                if not isinstance(section, dict):
                    continue
                sections.append(
                    {
                        "id": section.get("id"),
                        "track_ids": section.get("track_ids", []),
                        "track_kinds": section.get("track_kinds", []),
                        "available_channels": section.get("available_channels", []),
                    }
                )

            async def call_mcp_tool(name: str, arguments: dict[str, object]) -> dict[str, object]:
                tool_result = await session.call_tool(name, arguments)
                return self.runtime.tool_result_payload(tool_result)

            provider_result = await self.backend.run_authoring(
                instructions=authoring_prompt,
                initial_user_message=_authoring_bootstrap_message(
                    goal=request.goal,
                    example_id=request.example_id,
                    logfile_path=relative_output_logfile,
                    seed_result=_structured_content(baseline_result),
                    sections=sections,
                    heading_patch_keys=list(bootstrap_vocab.get("heading_patch_keys", [])),
                    curve_binding_patch_keys=list(
                        bootstrap_vocab.get("curve_binding_patch_keys", [])
                    ),
                ),
                tool_definitions=tool_definitions,
                tool_caller=call_mcp_tool,
                max_rounds=request.max_rounds,
            )

            if not output_path.exists():
                raise RuntimeError(
                    "The model finished without creating the expected draft logfile."
                )

            validation_result = await session.call_tool(
                "validate_logfile",
                {"logfile_path": relative_output_logfile},
            )
            draft_summary_result = await session.call_tool(
                "summarize_logfile_draft",
                {"logfile_path": relative_output_logfile},
            )
            inspect_summary_result = await session.call_tool(
                "inspect_logfile",
                {"logfile_path": relative_output_logfile},
            )
            change_summary_result = await session.call_tool(
                "summarize_logfile_changes",
                {
                    "logfile_path": relative_output_logfile,
                    "previous_text": baseline_draft_text,
                },
            )
            inspect_summary = _structured_content(inspect_summary_result)
            section_ids = inspect_summary.get("section_ids", [])
            if not isinstance(section_ids, list) or not section_ids:
                raise RuntimeError("Expected at least one section id after authoring.")
            first_section_id = section_ids[0]
            report_preview_result = await session.call_tool(
                "preview_logfile_png",
                {
                    "logfile_path": relative_output_logfile,
                    "page_index": 0,
                    "dpi": 72,
                    "include_report_pages": True,
                },
            )
            section_preview_result = await session.call_tool(
                "preview_section_png",
                {
                    "logfile_path": relative_output_logfile,
                    "section_id": first_section_id,
                    "dpi": 72,
                },
            )

        return AuthoringResult(
            provider=self.backend.provider,
            model=self.backend.model,
            credential_source=self.backend.credential_source,
            example_id=request.example_id,
            goal=request.goal,
            draft_logfile=relative_output_logfile,
            server_root=self.runtime.server_root,
            tool_trace=provider_result.tool_trace,
            final_text=provider_result.final_text,
            validation=_structured_content(validation_result),
            draft_summary=_structured_content(draft_summary_result),
            inspect_summary=inspect_summary,
            change_summary=_structured_content(change_summary_result),
            draft_text=output_path.read_text(encoding="utf-8"),
            report_preview_png=self.runtime.image_bytes(report_preview_result),
            section_preview_png=self.runtime.image_bytes(section_preview_result),
        )

    async def run(
        self,
        *,
        goal: str,
        example_id: str,
        output_logfile: str | Path,
        max_rounds: int = 12,
    ) -> AuthoringResult:
        """Run one authoring request with keyword arguments."""
        return await self.run_request(
            AuthoringRequest(
                goal=goal,
                example_id=example_id,
                output_logfile=_relative_logfile_path(self.runtime.server_root, output_logfile),
                max_rounds=max_rounds,
            )
        )


async def run_authoring_request(
    *,
    goal: str,
    example_id: str,
    output_logfile: str | Path,
    provider: str,
    model: str,
    server_root: str | Path | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    max_rounds: int = 12,
) -> AuthoringResult:
    """Run one high-level authoring request against local stdio MCP."""
    session = AuthoringSession.from_local_mcp(
        provider=provider,
        model=model,
        server_root=server_root,
        api_key=api_key,
        base_url=base_url,
    )
    return await session.run(
        goal=goal,
        example_id=example_id,
        output_logfile=output_logfile,
        max_rounds=max_rounds,
    )
