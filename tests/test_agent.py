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
import sys
import tempfile
import unittest
from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock

import anyio
import yaml

from wellplot.agent import (
    AuthoringRequest,
    AuthoringResult,
    AuthoringSession,
    AuthoringToolCall,
    ProjectPaths,
    ProjectSession,
    ProjectStarter,
    RevisionRequest,
    create_project_session,
    display_authoring_result,
    relative_path,
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

    def test_authoring_result_exposes_summary_lines_and_preview_selection(self) -> None:
        """Expose compact display helpers directly on the public result object."""
        result = AuthoringResult(
            provider="openai",
            model="gpt-5.4",
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
            change_summary={"summary_lines": ["Updated heading.", "", 123]},
            draft_text="name: Demo Draft\n",
            report_preview_png=b"report-preview",
            section_preview_png=b"section-preview",
        )

        self.assertEqual(result.summary_lines, ("Updated heading.",))
        self.assertEqual(result.preview_bytes("report"), b"report-preview")
        self.assertEqual(result.preview_bytes("section"), b"section-preview")
        with self.assertRaisesRegex(ValueError, "preview kind"):
            result.preview_bytes("thumbnail")

    def test_relative_path_formats_paths_under_root(self) -> None:
        """Expose one reusable notebook path helper in the public agent layer."""
        root = Path("/tmp/project")
        self.assertEqual(
            relative_path(root / "workspace" / "demo.log.yaml", root=root),
            "workspace/demo.log.yaml",
        )
        self.assertEqual(
            relative_path("workspace/demo.log.yaml", root=root),
            "workspace/demo.log.yaml",
        )

    def test_display_authoring_result_uses_ipython_image(self) -> None:
        """Wrap notebook display behavior in one public helper instead of local glue code."""
        result = AuthoringResult(
            provider="openai",
            model="gpt-5.4",
            credential_source="environment variable OPENAI_API_KEY",
            request_kind="author",
            example_id="forge16b_porosity_example",
            source_logfile_path=None,
            goal="Simplify the heading.",
            draft_logfile="workspace/demo.log.yaml",
            server_root=Path("/tmp"),
            tool_trace=(AuthoringToolCall(round=1, name="set_heading_content", arguments={}),),
            final_text="done",
            validation={"valid": True},
            draft_summary={},
            inspect_summary={"section_ids": ["main"]},
            change_summary={"summary_lines": ["Updated heading."]},
            draft_text="name: Demo Draft\n",
            report_preview_png=b"report-preview",
            section_preview_png=b"section-preview",
        )
        display_calls: list[object] = []

        class FakeImage:
            def __init__(self, *, data: bytes) -> None:
                self.data = data

        fake_display_module = ModuleType("IPython.display")
        fake_display_module.Image = FakeImage
        fake_display_module.display = display_calls.append

        with mock.patch.dict(sys.modules, {"IPython.display": fake_display_module}):
            output = display_authoring_result("Demo", result, preview="report")

        self.assertIsNone(output)
        self.assertEqual(len(display_calls), 1)
        image = display_calls[0]
        self.assertIsInstance(image, FakeImage)
        self.assertEqual(image.data, b"report-preview")
        self.assertEqual(display_calls, [image])

    def test_display_authoring_result_can_return_image_explicitly(self) -> None:
        """Allow callers to opt into the display object when they actually need it."""
        result = AuthoringResult(
            provider="openai",
            model="gpt-5.4",
            credential_source="environment variable OPENAI_API_KEY",
            request_kind="author",
            example_id="forge16b_porosity_example",
            source_logfile_path=None,
            goal="Simplify the heading.",
            draft_logfile="workspace/demo.log.yaml",
            server_root=Path("/tmp"),
            tool_trace=(AuthoringToolCall(round=1, name="set_heading_content", arguments={}),),
            final_text="done",
            validation={"valid": True},
            draft_summary={},
            inspect_summary={"section_ids": ["main"]},
            change_summary={"summary_lines": ["Updated heading."]},
            draft_text="name: Demo Draft\n",
            report_preview_png=b"report-preview",
            section_preview_png=b"section-preview",
        )
        display_calls: list[object] = []

        class FakeImage:
            def __init__(self, *, data: bytes) -> None:
                self.data = data

        fake_display_module = ModuleType("IPython.display")
        fake_display_module.Image = FakeImage
        fake_display_module.display = display_calls.append

        with mock.patch.dict(sys.modules, {"IPython.display": fake_display_module}):
            image = display_authoring_result(
                "Demo",
                result,
                preview="report",
                return_image=True,
            )

        self.assertIsInstance(image, FakeImage)
        self.assertEqual(display_calls, [image])

    def test_create_project_session_builds_project_scoped_wrapper(self) -> None:
        """Create one generic project session rooted under the configured server root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            fake_session = mock.Mock(spec=AuthoringSession)
            with mock.patch.object(
                AuthoringSession,
                "from_local_mcp",
                return_value=fake_session,
            ) as factory:
                session, paths = create_project_session(
                    server_root=repo_root,
                    project_dir="workspace/demo-job",
                    model="demo-model",
                )
            self.assertIsInstance(session, ProjectSession)
            self.assertIs(session.authoring_session, fake_session)
            self.assertIsInstance(paths, ProjectPaths)
            self.assertEqual(paths.server_root, repo_root.resolve())
            self.assertEqual(paths.project_dir, (repo_root / "workspace/demo-job").resolve())
            self.assertTrue(paths.project_dir.exists())
            self.assertEqual(paths.path("draft.log.yaml"), paths.project_dir / "draft.log.yaml")
            factory.assert_called_once_with(
                provider="openai",
                model="demo-model",
                server_root=paths.server_root,
                api_key=None,
                base_url=None,
            )
            self.assertEqual(session.run_max_rounds, 12)
            self.assertEqual(session.revise_max_rounds, 12)

    def test_project_session_add_data_file_stages_one_input(self) -> None:
        """Expose one session method for staging user data into the project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            replacement_path = repo_root / "incoming" / "replacement.las"
            replacement_path.parent.mkdir(parents=True, exist_ok=True)
            replacement_path.write_text("replacement", encoding="utf-8")

            with mock.patch.object(
                AuthoringSession,
                "from_local_mcp",
                return_value=mock.Mock(spec=AuthoringSession),
            ):
                session, paths = create_project_session(
                    server_root=repo_root,
                    project_dir="workspace/demo-job",
                    model="demo-model",
                )
                copied_path = session.add_data_file(
                    replacement_path,
                    destination_name="data/user_input.las",
                    overwrite=True,
                )
            self.assertEqual(copied_path, paths.path("data", "user_input.las"))
            self.assertEqual(copied_path.read_text(encoding="utf-8"), "replacement")

    def test_project_session_add_data_file_can_keep_existing_target(self) -> None:
        """Allow rerunnable notebook setup cells to preserve an existing staged file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            replacement_path = repo_root / "incoming" / "replacement.las"
            replacement_path.parent.mkdir(parents=True, exist_ok=True)
            replacement_path.write_text("replacement", encoding="utf-8")

            with mock.patch.object(
                AuthoringSession,
                "from_local_mcp",
                return_value=mock.Mock(spec=AuthoringSession),
            ):
                session, paths = create_project_session(
                    server_root=repo_root,
                    project_dir="workspace/demo-job",
                    model="demo-model",
                )
                existing_path = paths.path("user_input.las")
                existing_path.write_text("keep-me", encoding="utf-8")
                copied_path = session.add_data_file(
                    replacement_path,
                    destination_name="user_input.las",
                    keep_existing=True,
                )
            self.assertEqual(copied_path, existing_path)
            self.assertEqual(copied_path.read_text(encoding="utf-8"), "keep-me")

    def test_project_paths_reject_escape_segments(self) -> None:
        """Keep helper-generated project paths inside the configured project directory."""
        paths = ProjectPaths.under_root("/tmp/server-root", "workspace/demo-job")
        with self.assertRaisesRegex(ValueError, "project directory"):
            paths.path("..", "outside.log.yaml")

    def test_project_session_run_normalizes_text_and_uses_configured_rounds(self) -> None:
        """Hide dedent/strip boilerplate and round defaults inside the project helper."""
        authoring_session = mock.Mock(spec=AuthoringSession)
        authoring_session.run = mock.AsyncMock(return_value=mock.Mock(spec=AuthoringResult))
        session = ProjectSession(
            authoring_session=authoring_session,
            paths=ProjectPaths.under_root("/tmp/server-root", "workspace/demo-job"),
            run_max_rounds=18,
            revise_max_rounds=24,
        )

        anyio.run(
            partial(
                session.run,
                goal="""
                    Build one open-hole draft.
                """,
                source_logfile_path="workspace/demo-job/starter.log.yaml",
                output_logfile="workspace/demo-job/draft.log.yaml",
            )
        )

        authoring_session.run.assert_awaited_once_with(
            goal="Build one open-hole draft.",
            output_logfile="workspace/demo-job/draft.log.yaml",
            example_id=None,
            source_logfile_path="workspace/demo-job/starter.log.yaml",
            max_rounds=18,
        )

    def test_project_session_revise_normalizes_text_and_can_update_defaults(self) -> None:
        """Allow round budgets to be configured once in notebook setup code."""
        authoring_session = mock.Mock(spec=AuthoringSession)
        authoring_session.revise = mock.AsyncMock(return_value=mock.Mock(spec=AuthoringResult))
        session = ProjectSession(
            authoring_session=authoring_session,
            paths=ProjectPaths.under_root("/tmp/server-root", "workspace/demo-job"),
        )

        configured = session.configure_rounds(run_max_rounds=14, revise_max_rounds=22)
        self.assertIs(configured, session)

        anyio.run(
            partial(
                session.revise,
                feedback="""
                    Add one QC track.
                """,
                logfile_path="workspace/demo-job/draft.log.yaml",
            )
        )

        authoring_session.revise.assert_awaited_once_with(
            feedback="Add one QC track.",
            logfile_path="workspace/demo-job/draft.log.yaml",
            max_rounds=22,
        )

    def test_project_session_configure_paths_sets_defaults_for_run_revise_and_render(self) -> None:
        """Allow notebook setup code to define one default draft and render target."""
        authoring_session = mock.Mock(spec=AuthoringSession)
        authoring_session.run = mock.AsyncMock(return_value=mock.Mock(spec=AuthoringResult))
        authoring_session.revise = mock.AsyncMock(return_value=mock.Mock(spec=AuthoringResult))
        authoring_session.render_logfile_to_file = mock.AsyncMock(
            return_value={"output_path": "workspace/demo-job/final.pdf", "page_count": 1}
        )
        session = ProjectSession(
            authoring_session=authoring_session,
            paths=ProjectPaths.under_root("/tmp/server-root", "workspace/demo-job"),
        )
        session.configure_paths(
            draft_logfile="workspace/demo-job/draft.log.yaml",
            render_output_path="workspace/demo-job/final.pdf",
        )

        anyio.run(
            partial(
                session.run,
                goal="Build one open-hole draft.",
                source_logfile_path="workspace/demo-job/starter.log.yaml",
            )
        )
        anyio.run(partial(session.revise, feedback="Add one QC track."))
        render_result = anyio.run(partial(session.render_logfile_to_file, overwrite=True))

        authoring_session.run.assert_awaited_once_with(
            goal="Build one open-hole draft.",
            output_logfile="workspace/demo-job/draft.log.yaml",
            example_id=None,
            source_logfile_path="workspace/demo-job/starter.log.yaml",
            max_rounds=12,
        )
        authoring_session.revise.assert_awaited_once_with(
            feedback="Add one QC track.",
            logfile_path="workspace/demo-job/draft.log.yaml",
            max_rounds=12,
        )
        authoring_session.render_logfile_to_file.assert_awaited_once_with(
            logfile_path="workspace/demo-job/draft.log.yaml",
            output_path="workspace/demo-job/final.pdf",
            overwrite=True,
        )
        self.assertEqual(render_result["page_count"], 1)

    def test_project_session_requires_configured_paths_when_omitted(self) -> None:
        """Raise a clear error if notebook code omits paths before configuring them."""
        session = ProjectSession(
            authoring_session=mock.Mock(spec=AuthoringSession),
            paths=ProjectPaths.under_root("/tmp/server-root", "workspace/demo-job"),
        )

        with self.assertRaisesRegex(ValueError, "draft_logfile"):
            anyio.run(partial(session.revise, feedback="Add one QC track."))
        session.configure_paths(draft_logfile="workspace/demo-job/draft.log.yaml")
        with self.assertRaisesRegex(ValueError, "render_output_path"):
            anyio.run(partial(session.render_logfile_to_file))

    def test_project_session_create_starter_writes_template_and_logfile(self) -> None:
        """Replace raw notebook YAML scaffolding with one starter preset helper."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            data_file = repo_root / "workspace" / "demo-job" / "user_input.las"
            data_file.parent.mkdir(parents=True, exist_ok=True)
            data_file.write_text("~Version Information\nVERS. 2.0\n", encoding="utf-8")
            session = ProjectSession(
                authoring_session=mock.Mock(spec=AuthoringSession),
                paths=ProjectPaths.under_root(repo_root, "workspace/demo-job"),
                render_output_path="workspace/demo-job/final.pdf",
            )

            starter = session.create_starter(
                kind="open_hole_quicklook",
                data_file=data_file,
                title="Main Review",
                subtitle="Starter subtitle",
                depth_range=(8400, 9300),
                starter_logfile="starter.log.yaml",
                template_path="base.template.yaml",
                starter_name="Agent LAS Starter",
            )

            self.assertIsInstance(starter, ProjectStarter)
            self.assertEqual(starter.template_path, session.paths.path("base.template.yaml"))
            self.assertEqual(starter.logfile_path, session.paths.path("starter.log.yaml"))
            self.assertEqual(starter.render_output_path, session.paths.path("final.pdf"))
            self.assertTrue(starter.template_path.exists())
            self.assertTrue(starter.logfile_path.exists())
            template_payload = yaml.safe_load(starter.template_yaml)
            logfile_payload = yaml.safe_load(starter.logfile_yaml)
            self.assertEqual(template_payload["document"]["layout"]["heading"]["enabled"], True)
            self.assertEqual(logfile_payload["name"], "Agent LAS Starter")
            section = logfile_payload["document"]["layout"]["log_sections"][0]
            self.assertEqual(section["title"], "Main Review")
            self.assertEqual(section["subtitle"], "Starter subtitle")
            self.assertEqual(section["depth_range"], [8400, 9300])
            self.assertEqual(section["data"]["source_format"], "las")
            self.assertEqual(logfile_payload["render"]["output_path"], "final.pdf")

    def test_project_session_create_starter_accepts_absolute_project_paths(self) -> None:
        """Allow notebook code to pass absolute project-scoped paths directly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            project_dir = repo_root / "workspace" / "demo-job"
            data_file = project_dir / "user_input.las"
            data_file.parent.mkdir(parents=True, exist_ok=True)
            data_file.write_text("~Version Information\nVERS. 2.0\n", encoding="utf-8")
            template_path = project_dir / "base.template.yaml"
            starter_logfile = project_dir / "agent_starter.log.yaml"
            final_pdf = project_dir / "agent_open_hole_draft.pdf"
            session = ProjectSession(
                authoring_session=mock.Mock(spec=AuthoringSession),
                paths=ProjectPaths.under_root(repo_root, project_dir),
                render_output_path=final_pdf,
            )

            starter = session.create_starter(
                kind="open_hole_quicklook",
                data_file=data_file,
                title="Main Review",
                subtitle="Starter subtitle",
                depth_range=(8400, 9300),
                template_path=template_path,
                starter_logfile=starter_logfile,
            )

            logfile_payload = yaml.safe_load(starter.logfile_yaml)
            self.assertEqual(starter.template_path, template_path.resolve())
            self.assertEqual(starter.logfile_path, starter_logfile.resolve())
            self.assertEqual(starter.render_output_path, final_pdf.resolve())
            self.assertEqual(
                logfile_payload["template"]["path"],
                "base.template.yaml",
            )
            self.assertEqual(
                logfile_payload["render"]["output_path"],
                "agent_open_hole_draft.pdf",
            )

    def test_project_session_create_starter_requires_supported_kind(self) -> None:
        """Reject unknown starter presets instead of leaking low-level schema details."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            data_file = repo_root / "workspace" / "demo-job" / "user_input.las"
            data_file.parent.mkdir(parents=True, exist_ok=True)
            data_file.write_text("~Version Information\nVERS. 2.0\n", encoding="utf-8")
            session = ProjectSession(
                authoring_session=mock.Mock(spec=AuthoringSession),
                paths=ProjectPaths.under_root(repo_root, "workspace/demo-job"),
            )

            with self.assertRaisesRegex(ValueError, "Supported starter kinds"):
                session.create_starter(
                    kind="unknown",
                    data_file=data_file,
                    title="Main Review",
                    subtitle="Starter subtitle",
                )

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
