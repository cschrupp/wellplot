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

"""Unit tests for the public host-side wellplot agent layer."""

from __future__ import annotations

import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import anyio

from wellplot.agent import AuthoringRequest, AuthoringResult, AuthoringSession, AuthoringToolCall
from wellplot.agent.core import FunctionToolDefinition, run_authoring_request


class FakeBackend:
    """Minimal provider backend for exercising the authoring core."""

    provider = "fake"
    model = "fake-model"
    credential_source = "fake credential"

    def __init__(self) -> None:
        """Initialize one fake backend capture container."""
        self.instructions = ""
        self.initial_user_message = ""
        self.tool_names: list[str] = []
        self.tool_payload: dict[str, object] | None = None

    async def run_authoring(
        self,
        *,
        instructions: str,
        initial_user_message: str,
        tool_definitions: list[FunctionToolDefinition],
        tool_caller: object,
        max_rounds: int,
    ) -> SimpleNamespace:
        """Replay one deterministic fake tool call through the authoring core."""
        self.instructions = instructions
        self.initial_user_message = initial_user_message
        self.tool_names = [tool.name for tool in tool_definitions]
        assert callable(tool_caller)
        self.tool_payload = await tool_caller(
            "set_heading_content",
            {
                "logfile_path": "workspace/demo.log.yaml",
                "patch": {"provider_name": "Demo Provider"},
            },
        )
        return SimpleNamespace(
            final_text="Applied one heading patch.",
            tool_trace=(
                AuthoringToolCall(
                    round=1,
                    name="set_heading_content",
                    arguments={
                        "logfile_path": "workspace/demo.log.yaml",
                        "patch": {"provider_name": "Demo Provider"},
                    },
                ),
            ),
        )


class FakeMcpSession:
    """Minimal MCP session double for the authoring workflow."""

    def __init__(self, root: Path) -> None:
        """Initialize one fake session rooted at a temporary directory."""
        self.root = root

    async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
        """Return deterministic payloads for the MCP tools used by the core."""
        if name == "create_logfile_draft":
            output_path = self.root / str(arguments["output_path"])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text("name: Demo Draft\n", encoding="utf-8")
            return SimpleNamespace(structuredContent={"created": True, "example_id": "demo"})
        if name == "summarize_logfile_draft":
            return SimpleNamespace(
                structuredContent={
                    "sections": [
                        {
                            "id": "main",
                            "track_ids": ["gamma"],
                            "track_kinds": ["curve"],
                            "available_channels": ["GR"],
                        }
                    ]
                }
            )
        if name == "inspect_authoring_vocab":
            return SimpleNamespace(
                structuredContent={
                    "heading_patch_keys": ["provider_name"],
                    "curve_binding_patch_keys": ["label"],
                }
            )
        if name == "set_heading_content":
            return SimpleNamespace(structuredContent={"applied": 1})
        if name == "validate_logfile":
            return SimpleNamespace(structuredContent={"valid": True})
        if name == "inspect_logfile":
            return SimpleNamespace(structuredContent={"section_ids": ["main"]})
        if name == "summarize_logfile_changes":
            return SimpleNamespace(
                structuredContent={"summary_lines": ["Updated heading content."]}
            )
        if name == "preview_logfile_png":
            return SimpleNamespace(content=[SimpleNamespace(data=b"report-preview")])
        if name == "preview_section_png":
            return SimpleNamespace(content=[SimpleNamespace(data=b"section-preview")])
        raise AssertionError(f"Unexpected MCP tool call: {name}")

    async def get_prompt(self, name: str, arguments: dict[str, object]) -> object:
        """Return one fake authoring prompt payload."""
        self._assert_prompt_args(name, arguments)
        return SimpleNamespace(
            messages=[SimpleNamespace(content=SimpleNamespace(text="authoring prompt"))]
        )

    async def list_tools(self) -> object:
        """Expose the minimal tool catalog needed by the orchestration test."""
        return SimpleNamespace(
            tools=[
                SimpleNamespace(
                    name="create_logfile_draft",
                    description="create draft",
                    inputSchema={"type": "object"},
                ),
                SimpleNamespace(
                    name="set_heading_content",
                    description="set heading",
                    inputSchema={"type": "object"},
                ),
            ]
        )

    def _assert_prompt_args(self, name: str, arguments: dict[str, object]) -> None:
        self_name = "author_plot_from_request"
        if name != self_name:
            raise AssertionError(f"Unexpected prompt request: {name}")
        if arguments.get("example_id") != "forge16b_porosity_example":
            raise AssertionError("Unexpected example id in prompt arguments.")


class FakeRuntime:
    """Minimal runtime adapter that avoids the optional MCP dependency."""

    def __init__(self, root: Path) -> None:
        """Initialize one fake runtime rooted at a temporary directory."""
        self.server_root = root

    @asynccontextmanager
    async def open_session(self) -> object:
        """Yield one fake MCP session."""
        yield FakeMcpSession(self.server_root)

    def build_tool_definitions(
        self,
        mcp_tools: list[object],
        *,
        allowed_names: set[str],
        excluded_names: set[str] | None = None,
    ) -> list[FunctionToolDefinition]:
        """Convert fake tool descriptors into generic function-tool models."""
        excluded = set() if excluded_names is None else set(excluded_names)
        return [
            FunctionToolDefinition(
                name=str(getattr(tool, "name", "")),
                description=str(getattr(tool, "description", "")),
                parameters=dict(getattr(tool, "inputSchema", {})),
            )
            for tool in mcp_tools
            if getattr(tool, "name", "") in allowed_names
            and getattr(tool, "name", "") not in excluded
        ]

    def prompt_text(self, result: object) -> str:
        """Extract the first prompt text from one fake prompt response."""
        return str(result.messages[0].content.text)

    def image_bytes(self, result: object) -> bytes:
        """Return the in-memory preview bytes from one fake image result."""
        return bytes(result.content[0].data)

    def tool_result_payload(self, result: object) -> dict[str, object]:
        """Normalize one fake tool result into provider replay payload."""
        return {"structured": dict(result.structuredContent)}


class AgentTests(unittest.TestCase):
    """Verify the public host-side authoring session."""

    def test_authoring_session_runs_with_fake_runtime(self) -> None:
        """Run one authoring request through the provider-neutral core."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            backend = FakeBackend()
            session = AuthoringSession(backend=backend, runtime=FakeRuntime(root))

            result = anyio.run(
                session.run_request,
                AuthoringRequest(
                    goal="Simplify the heading.",
                    example_id="forge16b_porosity_example",
                    output_logfile="workspace/demo.log.yaml",
                ),
            )

            self.assertEqual(result.provider, "fake")
            self.assertEqual(result.model, "fake-model")
            self.assertEqual(result.credential_source, "fake credential")
            self.assertEqual(result.validation["valid"], True)
            self.assertEqual(result.inspect_summary["section_ids"], ["main"])
            self.assertEqual(
                result.change_summary["summary_lines"],
                ["Updated heading content."],
            )
            self.assertEqual(result.draft_path, root / "workspace/demo.log.yaml")
            self.assertEqual(result.draft_text, "name: Demo Draft\n")
            self.assertEqual(result.report_preview_png, b"report-preview")
            self.assertEqual(result.section_preview_png, b"section-preview")
            self.assertEqual(backend.tool_names, ["set_heading_content"])
            self.assertEqual(backend.tool_payload, {"structured": {"applied": 1}})
            self.assertIn("Simplify the heading.", backend.initial_user_message)
            self.assertIn("authoring prompt", backend.instructions)

            preview_paths = result.write_preview_artifacts()
            self.assertEqual(preview_paths["report_preview"].read_bytes(), b"report-preview")
            self.assertEqual(preview_paths["section_preview"].read_bytes(), b"section-preview")

    def test_from_local_mcp_rejects_unknown_provider(self) -> None:
        """Reject unsupported providers before optional imports happen."""
        with self.assertRaisesRegex(ValueError, "Unsupported authoring provider"):
            AuthoringSession.from_local_mcp(provider="anthropic", model="demo")

    def test_run_authoring_request_uses_public_factory(self) -> None:
        """Delegate the convenience helper through the public session factory."""
        result = AuthoringResult(
            provider="openai",
            model="gpt-5.4-mini",
            credential_source="environment variable OPENAI_API_KEY",
            example_id="forge16b_porosity_example",
            goal="Simplify the heading.",
            draft_logfile="workspace/demo.log.yaml",
            server_root=Path("/tmp"),
            tool_trace=(),
            final_text="done",
            validation={"valid": True},
            draft_summary={},
            inspect_summary={"section_ids": ["main"]},
            change_summary={"summary_lines": []},
            draft_text="name: Demo Draft\n",
            report_preview_png=b"report-preview",
            section_preview_png=b"section-preview",
        )
        stub_session = mock.AsyncMock()
        stub_session.run.return_value = result

        with mock.patch.object(
            AuthoringSession,
            "from_local_mcp",
            return_value=stub_session,
        ) as factory:
            returned = anyio.run(self._run_authoring_request_helper)

        self.assertIs(returned, result)
        factory.assert_called_once_with(
            provider="openai",
            model="gpt-5.4-mini",
            server_root=None,
            api_key=None,
        )
        stub_session.run.assert_awaited_once_with(
            goal="Simplify the heading.",
            example_id="forge16b_porosity_example",
            output_logfile="workspace/demo.log.yaml",
            max_rounds=12,
        )

    @staticmethod
    async def _run_authoring_request_helper() -> AuthoringResult:
        """Call the public convenience helper with keyword arguments."""
        return await run_authoring_request(
            goal="Simplify the heading.",
            example_id="forge16b_porosity_example",
            output_logfile="workspace/demo.log.yaml",
            provider="openai",
            model="gpt-5.4-mini",
        )
