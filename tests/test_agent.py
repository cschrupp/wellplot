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

import os
import tempfile
import unittest
from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import anyio

from wellplot.agent import (
    AuthoringRequest,
    AuthoringResult,
    AuthoringSession,
    AuthoringToolCall,
    RevisionRequest,
)
from wellplot.agent.core import (
    FunctionToolDefinition,
    revise_authoring_request,
    run_authoring_request,
)
from wellplot.agent.mcp import _server_command, _server_env
from wellplot.agent.providers import load_openai_compatible_api_key


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
        self.tool_calls: list[tuple[str, dict[str, object]]] = []
        self.prompt_calls: list[tuple[str, dict[str, object]]] = []

    async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
        """Return deterministic payloads for the MCP tools used by the core."""
        self.tool_calls.append((name, dict(arguments)))
        if name == "create_logfile_draft":
            output_path = self.root / str(arguments["output_path"])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text("name: Demo Draft\n", encoding="utf-8")
            seed_kind = "example" if arguments.get("example_id") is not None else "logfile"
            seed_value = str(arguments.get("example_id") or arguments.get("source_logfile_path"))
            return SimpleNamespace(
                structuredContent={
                    "created": True,
                    "seed_kind": seed_kind,
                    "seed_value": seed_value,
                }
            )
        if name == "summarize_logfile_draft":
            return SimpleNamespace(
                structuredContent={
                    "sections": [
                        {
                            "id": "main",
                            "track_ids": ["gamma"],
                            "track_kinds": ["curve"],
                            "available_channels": ["GR"],
                            "source_path": "workspace/data/demo.las",
                            "source_format": "las",
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
        if name == "render_logfile_to_file":
            output_path = self.root / str(arguments["output_path"])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text("fake pdf output", encoding="utf-8")
            return SimpleNamespace(
                structuredContent={
                    "backend": "matplotlib",
                    "page_count": 1,
                    "output_path": str(output_path),
                }
            )
        raise AssertionError(f"Unexpected MCP tool call: {name}")

    async def get_prompt(self, name: str, arguments: dict[str, object]) -> object:
        """Return one fake authoring prompt payload."""
        self.prompt_calls.append((name, dict(arguments)))
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
        if name == "author_plot_from_request":
            if arguments.get("logfile_path") != "workspace/demo.log.yaml":
                raise AssertionError("Unexpected logfile path in authoring prompt arguments.")
            return
        if name == "revise_plot_from_feedback":
            if arguments.get("logfile_path") != "workspace/demo.log.yaml":
                raise AssertionError("Unexpected logfile path in revision prompt arguments.")
            return
        raise AssertionError(f"Unexpected prompt request: {name}")


class FakeRuntime:
    """Minimal runtime adapter that avoids the optional MCP dependency."""

    def __init__(self, root: Path) -> None:
        """Initialize one fake runtime rooted at a temporary directory."""
        self.server_root = root
        self.last_session: FakeMcpSession | None = None

    @asynccontextmanager
    async def open_session(self) -> object:
        """Yield one fake MCP session."""
        session = FakeMcpSession(self.server_root)
        self.last_session = session
        yield session

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


class MissingDraftMcpSession(FakeMcpSession):
    """Fake MCP session that reports draft creation without writing the file."""

    async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
        """Skip the draft write so the core can surface a clearer error."""
        self.tool_calls.append((name, dict(arguments)))
        if name == "create_logfile_draft":
            return SimpleNamespace(
                structuredContent={
                    "created": True,
                    "seed_kind": "example",
                    "seed_value": str(arguments.get("example_id")),
                    "output_path": str(self.root / str(arguments["output_path"])),
                }
            )
        return await super().call_tool(name, arguments)


class MissingDraftRuntime(FakeRuntime):
    """Runtime that exposes one missing-draft MCP session."""

    @asynccontextmanager
    async def open_session(self) -> object:
        """Yield one fake session that never persists the created draft."""
        session = MissingDraftMcpSession(self.server_root)
        self.last_session = session
        yield session


class ToolErrorMcpSession(FakeMcpSession):
    """Fake MCP session that reports one tool error payload."""

    async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
        """Return one MCP-style error result for draft creation."""
        self.tool_calls.append((name, dict(arguments)))
        if name == "create_logfile_draft":
            return SimpleNamespace(
                isError=True,
                content=[
                    SimpleNamespace(
                        text=(
                            "Logfile schema validation failed:\n"
                            "- $.document: 'bindings' is a required property"
                        )
                    )
                ],
                structuredContent=None,
            )
        return await super().call_tool(name, arguments)


class ToolErrorRuntime(FakeRuntime):
    """Runtime that exposes one MCP tool error during draft creation."""

    @asynccontextmanager
    async def open_session(self) -> object:
        """Yield one fake session that returns an MCP error result."""
        session = ToolErrorMcpSession(self.server_root)
        self.last_session = session
        yield session


class AgentTests(unittest.TestCase):
    """Verify the public host-side authoring session."""

    def test_authoring_session_runs_with_fake_runtime(self) -> None:
        """Run one authoring request through the provider-neutral core."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            backend = FakeBackend()
            runtime = FakeRuntime(root)
            session = AuthoringSession(backend=backend, runtime=runtime)

            result = anyio.run(
                session.run_request,
                AuthoringRequest(
                    goal="Simplify the heading.",
                    output_logfile="workspace/demo.log.yaml",
                    example_id="forge16b_porosity_example",
                ),
            )

            self.assertEqual(result.provider, "fake")
            self.assertEqual(result.model, "fake-model")
            self.assertEqual(result.credential_source, "fake credential")
            self.assertEqual(result.request_kind, "author")
            self.assertEqual(result.example_id, "forge16b_porosity_example")
            self.assertIsNone(result.source_logfile_path)
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
            self.assertIn(
                "packaged example `forge16b_porosity_example`",
                backend.initial_user_message,
            )
            self.assertIn("authoring prompt", backend.instructions)
            self.assertIsNotNone(runtime.last_session)
            assert runtime.last_session is not None
            self.assertEqual(runtime.last_session.prompt_calls[0][0], "author_plot_from_request")

            preview_paths = result.write_preview_artifacts()
            self.assertEqual(preview_paths["report_preview"].read_bytes(), b"report-preview")
            self.assertEqual(preview_paths["section_preview"].read_bytes(), b"section-preview")

    def test_authoring_session_can_seed_from_starter_logfile(self) -> None:
        """Support source_logfile_path as the seed for the initial authoring pass."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            backend = FakeBackend()
            runtime = FakeRuntime(root)
            session = AuthoringSession(backend=backend, runtime=runtime)

            result = anyio.run(
                partial(
                    session.run,
                    goal="Point the starter at a new LAS source.",
                    output_logfile="workspace/demo.log.yaml",
                    source_logfile_path="examples/starter.log.yaml",
                )
            )

            self.assertEqual(result.request_kind, "author")
            self.assertIsNone(result.example_id)
            self.assertEqual(result.source_logfile_path, "examples/starter.log.yaml")
            self.assertIn(
                "starter logfile `examples/starter.log.yaml`",
                backend.initial_user_message,
            )
            assert runtime.last_session is not None
            create_call = runtime.last_session.tool_calls[0]
            self.assertEqual(create_call[0], "create_logfile_draft")
            self.assertEqual(create_call[1]["source_logfile_path"], "examples/starter.log.yaml")

    def test_revision_request_reuses_existing_draft_without_recreation(self) -> None:
        """Run one provider-backed revision against an existing draft logfile."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            draft_path = root / "workspace" / "demo.log.yaml"
            draft_path.parent.mkdir(parents=True, exist_ok=True)
            draft_path.write_text("name: Demo Draft\n", encoding="utf-8")
            backend = FakeBackend()
            runtime = FakeRuntime(root)
            session = AuthoringSession(backend=backend, runtime=runtime)

            result = anyio.run(
                session.revise_request,
                RevisionRequest(
                    feedback="Add one short remarks block.",
                    logfile_path="workspace/demo.log.yaml",
                ),
            )

            self.assertEqual(result.request_kind, "revise")
            self.assertIsNone(result.example_id)
            self.assertIsNone(result.source_logfile_path)
            self.assertIn("Add one short remarks block.", backend.initial_user_message)
            assert runtime.last_session is not None
            tool_names = [name for name, _arguments in runtime.last_session.tool_calls]
            self.assertNotIn("create_logfile_draft", tool_names)
            self.assertEqual(runtime.last_session.prompt_calls[0][0], "revise_plot_from_feedback")

    def test_authoring_session_surfaces_missing_seed_draft_clearly(self) -> None:
        """Raise one actionable error when the MCP server reports success without a file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            backend = FakeBackend()
            runtime = MissingDraftRuntime(root)
            session = AuthoringSession(backend=backend, runtime=runtime)

            with self.assertRaisesRegex(
                RuntimeError,
                "create_logfile_draft reported success but no draft file was written",
            ):
                anyio.run(
                    session.run_request,
                    AuthoringRequest(
                        goal="Simplify the heading.",
                        output_logfile="workspace/demo.log.yaml",
                        example_id="forge16b_porosity_example",
                    ),
                )

    def test_authoring_session_surfaces_mcp_tool_errors_clearly(self) -> None:
        """Propagate one explicit MCP tool error instead of a follow-on filesystem failure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            backend = FakeBackend()
            runtime = ToolErrorRuntime(root)
            session = AuthoringSession(backend=backend, runtime=runtime)

            with self.assertRaisesRegex(
                RuntimeError,
                "create_logfile_draft failed:\nLogfile schema validation failed",
            ):
                anyio.run(
                    session.run_request,
                    AuthoringRequest(
                        goal="Simplify the heading.",
                        output_logfile="workspace/demo.log.yaml",
                        example_id="forge16b_porosity_example",
                    ),
                )

    def test_render_logfile_to_file_uses_public_agent_helper(self) -> None:
        """Render one draft through the public session helper instead of raw MCP plumbing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            backend = FakeBackend()
            runtime = FakeRuntime(root)
            session = AuthoringSession(backend=backend, runtime=runtime)
            draft_path = root / "workspace" / "demo.log.yaml"
            draft_path.parent.mkdir(parents=True, exist_ok=True)
            draft_path.write_text("name: Demo Draft\n", encoding="utf-8")

            result = anyio.run(
                partial(
                    session.render_logfile_to_file,
                    logfile_path="workspace/demo.log.yaml",
                    output_path="workspace/demo.pdf",
                    overwrite=True,
                )
            )

            self.assertEqual(result["page_count"], 1)
            self.assertTrue((root / "workspace" / "demo.pdf").exists())
            assert runtime.last_session is not None
            self.assertEqual(runtime.last_session.tool_calls[0][0], "render_logfile_to_file")

    def test_from_local_mcp_rejects_unknown_provider(self) -> None:
        """Reject unsupported providers before optional imports happen."""
        with self.assertRaisesRegex(ValueError, "Unsupported authoring provider"):
            AuthoringSession.from_local_mcp(provider="anthropic", model="demo")

    def test_run_authoring_request_helper_delegates_to_session(self) -> None:
        """Expose the high-level helper for starter requests."""
        fake_result = mock.Mock(spec=AuthoringResult)
        with mock.patch.object(AuthoringSession, "from_local_mcp") as factory:
            factory.return_value.run = mock.AsyncMock(return_value=fake_result)
            result = anyio.run(
                partial(
                    run_authoring_request,
                    goal="Build a starter packet.",
                    output_logfile="workspace/demo.log.yaml",
                    source_logfile_path="examples/starter.log.yaml",
                    provider="openai",
                    model="demo-model",
                )
            )

        self.assertIs(result, fake_result)
        factory.return_value.run.assert_awaited_once_with(
            goal="Build a starter packet.",
            example_id=None,
            source_logfile_path="examples/starter.log.yaml",
            output_logfile="workspace/demo.log.yaml",
            max_rounds=12,
        )

    def test_revise_authoring_request_helper_delegates_to_session(self) -> None:
        """Expose the high-level helper for iterative revisions."""
        fake_result = mock.Mock(spec=AuthoringResult)
        with mock.patch.object(AuthoringSession, "from_local_mcp") as factory:
            factory.return_value.revise = mock.AsyncMock(return_value=fake_result)
            result = anyio.run(
                partial(
                    revise_authoring_request,
                    feedback="Move GR left of resistivity.",
                    logfile_path="workspace/demo.log.yaml",
                    provider="openai",
                    model="demo-model",
                )
            )

        self.assertIs(result, fake_result)
        factory.return_value.revise.assert_awaited_once_with(
            feedback="Move GR left of resistivity.",
            logfile_path="workspace/demo.log.yaml",
            max_rounds=12,
        )

    def test_from_local_mcp_builds_openai_backend(self) -> None:
        """Construct the OpenAI backend through the public session factory."""
        runtime = SimpleNamespace(server_root=Path("/tmp/openai-root"))
        backend = SimpleNamespace(provider="openai", model="demo", credential_source=None)

        with (
            mock.patch(
                "wellplot.agent.mcp.LocalStdioMcpRuntime",
                return_value=runtime,
            ) as runtime_factory,
            mock.patch(
                "wellplot.agent.providers.openai.OpenAIAuthoringBackend.from_local_configuration",
                return_value=backend,
            ) as backend_factory,
        ):
            session = AuthoringSession.from_local_mcp(
                provider="openai",
                model="demo-model",
                server_root="/tmp/openai-root",
                api_key="demo-token",
            )

        runtime_factory.assert_called_once_with(server_root="/tmp/openai-root")
        backend_factory.assert_called_once_with(
            model="demo-model",
            server_root=runtime.server_root,
            api_key="demo-token",
        )
        self.assertIs(session.backend, backend)
        self.assertIs(session.runtime, runtime)

    def test_from_local_mcp_builds_openai_compat_backend(self) -> None:
        """Construct the OpenAI-compatible backend with the required base URL."""
        runtime = SimpleNamespace(server_root=Path("/tmp/compat-root"))
        backend = SimpleNamespace(
            provider="openai_compat",
            model="demo",
            credential_source=None,
        )

        with (
            mock.patch(
                "wellplot.agent.mcp.LocalStdioMcpRuntime",
                return_value=runtime,
            ) as runtime_factory,
            mock.patch(
                "wellplot.agent.providers.openai_compat.OpenAICompatibleAuthoringBackend.from_local_configuration",
                return_value=backend,
            ) as backend_factory,
        ):
            session = AuthoringSession.from_local_mcp(
                provider="openai_compat",
                model="demo-model",
                server_root="/tmp/compat-root",
                api_key="compat-token",
                base_url="http://localhost:11434/v1",
            )

        runtime_factory.assert_called_once_with(server_root="/tmp/compat-root")
        backend_factory.assert_called_once_with(
            model="demo-model",
            server_root=runtime.server_root,
            api_key="compat-token",
            base_url="http://localhost:11434/v1",
        )
        self.assertIs(session.backend, backend)
        self.assertIs(session.runtime, runtime)

    def test_from_local_mcp_requires_base_url_for_openai_compat(self) -> None:
        """Reject the compatibility provider when no base URL is supplied."""
        with self.assertRaisesRegex(ValueError, "base_url"):
            AuthoringSession.from_local_mcp(provider="openai_compat", model="demo")

    def test_openai_compat_uses_placeholder_token_for_loopback_base_url(self) -> None:
        """Allow local OpenAI-compatible endpoints to run without a configured key."""
        with tempfile.TemporaryDirectory() as tmpdir, mock.patch.dict("os.environ", {}, clear=True):
            token, source = load_openai_compatible_api_key(
                server_root=tmpdir,
                base_url="http://localhost:11434/v1",
            )

        self.assertEqual(token, "wellplot-local-openai-compat")
        self.assertEqual(
            source,
            "implicit placeholder api_key for loopback openai_compat base_url",
        )

    def test_openai_compat_still_requires_key_for_non_loopback_base_url(self) -> None:
        """Reject missing credentials for non-local OpenAI-compatible endpoints."""
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            mock.patch.dict("os.environ", {}, clear=True),
            self.assertRaisesRegex(RuntimeError, "OPENAI_COMPAT_API_KEY"),
        ):
            load_openai_compatible_api_key(
                server_root=tmpdir,
                base_url="https://example-hosted-compat.test/v1",
            )

    def test_server_command_prefers_sibling_entry_point(self) -> None:
        """Prefer the MCP entry point beside the active interpreter over PATH lookup."""
        with (
            mock.patch("wellplot.agent.mcp.sys.executable", "/tmp/demo/bin/python3"),
            mock.patch("wellplot.agent.mcp.Path.exists", return_value=True),
        ):
            command, args = _server_command()

        self.assertEqual(command, "/tmp/demo/bin/wellplot-mcp")
        self.assertEqual(args, [])

    def test_server_env_propagates_current_pythonpath(self) -> None:
        """Preserve the current import resolution for the child MCP server process."""
        fake_path_entries = ["/tmp/project/src", "/tmp/project/.venv/lib/python3.12/site-packages"]
        with (
            mock.patch.dict(os.environ, {"PYTHONPATH": "/tmp/existing"}, clear=False),
            mock.patch("wellplot.agent.mcp.sys.path", ["", *fake_path_entries]),
        ):
            env = _server_env()

        pythonpath_entries = env["PYTHONPATH"].split(os.pathsep)
        self.assertEqual(pythonpath_entries[0:2], fake_path_entries)
        self.assertIn("/tmp/existing", pythonpath_entries)

    def test_run_authoring_request_uses_public_factory(self) -> None:
        """Delegate the convenience helper through the public session factory."""
        result = AuthoringResult(
            provider="openai",
            model="gpt-5.4-mini",
            credential_source="environment variable OPENAI_API_KEY",
            request_kind="author",
            example_id="forge16b_porosity_example",
            source_logfile_path=None,
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
            base_url=None,
        )
        stub_session.run.assert_awaited_once_with(
            goal="Simplify the heading.",
            example_id="forge16b_porosity_example",
            output_logfile="workspace/demo.log.yaml",
            source_logfile_path=None,
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
