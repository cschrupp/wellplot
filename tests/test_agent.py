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
from contextlib import asynccontextmanager, redirect_stdout
from functools import partial
from io import StringIO
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
    AuthoringUserReport,
    ExecutedAuthoringPhase,
    ProjectPaths,
    ProjectSession,
    ProjectStarter,
    RevisionRequest,
    create_project_session,
    display_authoring_result,
    display_phase_previews,
    relative_path,
)
from wellplot.agent.core import (
    AuthoringPlanPhase,
    AuthoringPlanResult,
    AuthoringRunState,
    FunctionToolDefinition,
    _extract_packet_header_fill_intent,
    _merge_omitted_defaults,
    _phase_allowed_tool_names,
    revise_authoring_request,
    run_authoring_request,
)
from wellplot.agent.mcp import _server_command, _server_env
from wellplot.agent.providers import load_openai_compatible_api_key
from wellplot.agent.providers._openai_responses import load_openai_client


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

    def __init__(self, root: Path, *, header_conflict: bool = False) -> None:
        """Initialize one fake session rooted at a temporary directory."""
        self.root = root
        self.header_conflict = header_conflict
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
                    "has_heading": True,
                    "has_remarks": False,
                    "section_ids": ["main"],
                    "sections": [
                        {
                            "id": "main",
                            "track_ids": ["gamma"],
                            "track_kinds": ["curve"],
                            "available_channels": ["GR"],
                            "source_path": "workspace/data/demo.las",
                            "source_format": "las",
                            "bindings_by_track": {},
                        }
                    ]
                }
            )
        if name == "check_channel_availability":
            requested_channels = [
                str(channel)
                for channel in arguments.get("requested_channels", [])
                if str(channel).strip()
            ]
            return SimpleNamespace(
                structuredContent={
                    "found_channels": requested_channels,
                    "missing_channels": [],
                    "resolutions": [
                        {
                            "requested_channel": channel,
                            "status": "exact",
                            "matched_channels": [channel],
                        }
                        for channel in requested_channels
                    ],
                    "warnings": [],
                }
            )
        if name == "inspect_authoring_objects":
            return SimpleNamespace(structuredContent={"objects": []})
        if name == "apply_header_archetype":
            return SimpleNamespace(structuredContent={"applied": True})
        if name == "inspect_packet_blueprints":
            return SimpleNamespace(
                structuredContent={
                    "selected_blueprint_id": None,
                    "blueprints": [],
                    "resource_uris": ["wellplot://authoring/catalog/packet-blueprints.json"],
                }
            )
        if name == "replicate_section_structure":
            return SimpleNamespace(
                structuredContent={
                    "source_section_id": arguments["source_section_id"],
                    "target_section_id": arguments["target_section_id"],
                    "copied_track_ids": ["gamma"],
                    "curve_binding_count": 0,
                    "raster_binding_count": 0,
                }
            )
        if name == "inspect_heading_slots":
            return SimpleNamespace(
                structuredContent={
                    "has_heading": True,
                    "slots": [
                        {
                            "target_key": "RMF @ Measured Temp",
                            "display_label": "RMF @ Measured Temp",
                        }
                    ],
                }
            )
        if name == "parse_key_value_text":
            pairs: list[dict[str, object]] = []
            for line_number, raw_line in enumerate(
                str(arguments.get("source_text", "")).splitlines(),
                start=1,
            ):
                line = raw_line.strip()
                if not line or ":" not in line:
                    continue
                key, value = line.split(":", 1)
                pairs.append(
                    {
                        "key": key.strip(),
                        "value": value.strip(),
                        "line_number": line_number,
                        "normalized_key": key.strip().upper(),
                    }
                )
            return SimpleNamespace(
                structuredContent={
                    "format_detected": "colon",
                    "pairs": pairs,
                    "unparsed_lines": [],
                    "warnings": [],
                }
            )
        if name == "preview_header_mapping":
            values = dict(arguments.get("values", {}))
            if self.header_conflict and any(
                str(key).startswith("detail.") for key in values
            ):
                value = values.get("detail.rm_measured_temp")
                return SimpleNamespace(
                    structuredContent={
                        "resolved_assignments": [
                            {
                                "request_key": "detail.rm_measured_temp",
                                "target_key": "rm_measured_temp",
                                "display_label": "RM @ Measured Temp",
                                "value": value,
                                "action": "set",
                            }
                        ],
                        "conflicting_values": [],
                        "unmatched_values": [],
                        "warnings": [],
                    }
                )
            if self.header_conflict and "RM" in values:
                return SimpleNamespace(
                    structuredContent={
                        "resolved_assignments": [
                            {
                                "request_key": "Company",
                                "target_key": "company",
                                "display_label": "Company",
                                "value": values.get("Company"),
                                "action": "set",
                            }
                        ],
                        "conflicting_values": [
                            {
                                "input_key": "RM",
                                "input_value": values.get("RM"),
                                "clarification_question": (
                                    "Which header field should receive value "
                                    "'0.005 @ 35' for `RM`? Choose one: "
                                    "`RM @ Measured Temp` or `RM @ Bottom Temp`."
                                ),
                                "candidate_labels": [
                                    "RM @ Measured Temp",
                                    "RM @ Bottom Temp",
                                ],
                                "candidate_targets": [
                                    {
                                        "target_kind": "detail_field",
                                        "target_key": "rm_measured_temp",
                                        "display_label": "RM @ Measured Temp",
                                    },
                                    {
                                        "target_kind": "detail_field",
                                        "target_key": "rm_bottom_temp",
                                        "display_label": "RM @ Bottom Temp",
                                    },
                                ],
                            }
                        ],
                        "unmatched_values": [],
                        "warnings": [],
                    }
                )
            return SimpleNamespace(
                structuredContent={
                    "resolved_assignments": [
                        {"request_key": key, "value": value} for key, value in values.items()
                    ],
                    "skipped_assignments": [],
                    "warnings": [],
                }
            )
        if name == "apply_header_values":
            values = dict(arguments.get("values", {}))
            if self.header_conflict and any(
                str(key).startswith("detail.") for key in values
            ):
                value = values.get("detail.rm_measured_temp")
                return SimpleNamespace(
                    structuredContent={
                        "applied_assignments": [
                            {
                                "request_key": "detail.rm_measured_temp",
                                "target_key": "rm_measured_temp",
                                "display_label": "RM @ Measured Temp",
                                "value": value,
                                "action": "set",
                            }
                        ],
                        "skipped_assignments": [],
                        "warnings": [],
                    }
                )
            if self.header_conflict and "RM" in values:
                return SimpleNamespace(
                    structuredContent={
                        "applied_assignments": [
                            {
                                "request_key": "Company",
                                "target_key": "company",
                                "display_label": "Company",
                                "value": values.get("Company"),
                                "action": "set",
                            }
                        ],
                        "skipped_assignments": [
                            {
                                "input_key": "RM",
                                "input_value": values.get("RM"),
                                "status": "conflict",
                                "reason": (
                                    "Which header field should receive value "
                                    "'0.005 @ 35' for `RM`? Choose one: "
                                    "`RM @ Measured Temp` or `RM @ Bottom Temp`."
                                ),
                                "clarification_question": (
                                    "Which header field should receive value "
                                    "'0.005 @ 35' for `RM`? Choose one: "
                                    "`RM @ Measured Temp` or `RM @ Bottom Temp`."
                                ),
                                "candidate_labels": [
                                    "RM @ Measured Temp",
                                    "RM @ Bottom Temp",
                                ],
                                "candidate_targets": [
                                    {
                                        "target_kind": "detail_field",
                                        "target_key": "rm_measured_temp",
                                        "display_label": "RM @ Measured Temp",
                                    },
                                    {
                                        "target_kind": "detail_field",
                                        "target_key": "rm_bottom_temp",
                                        "display_label": "RM @ Bottom Temp",
                                    },
                                ],
                            }
                        ],
                        "warnings": [],
                    }
                )
            return SimpleNamespace(
                structuredContent={
                    "applied_assignments": [
                        {"request_key": key, "value": value} for key, value in values.items()
                    ],
                    "skipped_assignments": [],
                    "warnings": [],
                }
            )
        if name == "edit_header":
            values = dict(arguments.get("values", {}))
            return SimpleNamespace(
                structuredContent={
                    "ok": True,
                    "changed": True,
                    "target": {"object_kind": "header", "object_id": "header"},
                    "before": {},
                    "after": {},
                    "applied_assignments": [
                        {
                            "input_key": key,
                            "input_value": value,
                            "target_key": "rm_bottom_temp",
                            "display_label": "RM @ Bottom Temp",
                        }
                        for key, value in values.items()
                    ],
                    "skipped_assignments": [],
                    "warnings": [],
                    "next_steps": [],
                }
            )
        if name == "inspect_authoring":
            return SimpleNamespace(
                structuredContent={
                    "ok": True,
                    "items": [
                        {
                            "ref": {"object_kind": "section", "object_id": "main"},
                            "object": {"tracks": [{"id": "gamma"}]},
                        }
                    ],
                    "warnings": [],
                    "next_steps": [],
                }
            )
        if name == "preview_logfile":
            return SimpleNamespace(content=[SimpleNamespace(data=b"stable-preview")])
        if name == "inspect_authoring_vocab":
            return SimpleNamespace(
                structuredContent={
                    "heading_patch_keys": ["provider_name"],
                    "curve_binding_patch_keys": ["label"],
                }
            )
        if name == "set_matplotlib_style":
            return SimpleNamespace(
                structuredContent={
                    "style": dict(arguments.get("style_patch", {})),
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
        if name == "render_logfile":
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

    def __init__(self, root: Path, *, header_conflict: bool = False) -> None:
        """Initialize one fake runtime rooted at a temporary directory."""
        self.server_root = root
        self.header_conflict = header_conflict
        self.last_session: FakeMcpSession | None = None

    @asynccontextmanager
    async def open_session(self) -> object:
        """Yield one fake MCP session."""
        session = FakeMcpSession(self.server_root, header_conflict=self.header_conflict)
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
            self.assertEqual(backend.tool_names, [])
            self.assertIsNone(backend.tool_payload)
            self.assertEqual(result.tool_trace, ())
            self.assertEqual(result.report_facts["extraction"]["status"], "unsupported_provider")
            self.assertTrue(result.user_report.why_not)
            self.assertIsNotNone(runtime.last_session)
            assert runtime.last_session is not None

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
            self.assertEqual(backend.initial_user_message, "")
            self.assertEqual(result.report_facts["extraction"]["status"], "unsupported_provider")
            assert runtime.last_session is not None
            create_call = runtime.last_session.tool_calls[0]
            self.assertEqual(create_call[0], "create_logfile_draft")
            self.assertEqual(create_call[1]["source_logfile_path"], "examples/starter.log.yaml")

    def test_authoring_session_routes_header_fill_requests_to_deterministic_tools(self) -> None:
        """Bypass the freeform provider loop for narrow header-value requests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            backend = mock.Mock()
            backend.provider = "fake"
            backend.model = "fake-model"
            backend.credential_source = "fake credential"
            backend.run_authoring = mock.AsyncMock()
            runtime = FakeRuntime(root)
            session = AuthoringSession(backend=backend, runtime=runtime)

            result = anyio.run(
                session.run_request,
                AuthoringRequest(
                    goal="""
                        Fill the following header fields with the following values:
                        - Rmf: 0.01 @ 25
                        - Rmc: 0.2 @ 25
                        - Rm: 0.005 @ 35
                    """,
                    output_logfile="workspace/demo.log.yaml",
                    example_id="forge16b_porosity_example",
                ),
            )

            backend.run_authoring.assert_not_awaited()
            self.assertIn("deterministic header value assignment", result.final_text)
            self.assertEqual(
                [item.name for item in result.tool_trace],
                [
                    "inspect_heading_slots",
                    "parse_key_value_text",
                    "preview_header_mapping",
                    "apply_header_values",
                ],
            )
            assert runtime.last_session is not None
            self.assertEqual(runtime.last_session.prompt_calls, [])
            tool_names = [name for name, _arguments in runtime.last_session.tool_calls]
            self.assertEqual(
                tool_names[:5],
                [
                    "create_logfile_draft",
                    "inspect_heading_slots",
                    "parse_key_value_text",
                    "preview_header_mapping",
                    "apply_header_values",
                ],
            )
            preview_call = runtime.last_session.tool_calls[3]
            self.assertEqual(preview_call[1]["overwrite_policy"], "replace")
            self.assertEqual(
                preview_call[1]["values"],
                {
                    "Rmf": "0.01 @ 25",
                    "Rmc": "0.2 @ 25",
                    "Rm": "0.005 @ 35",
                },
            )
            self.assertIn("Filled `Rmf`.", result.user_report.done)
            self.assertEqual(result.user_report.could_not_do, ())

    def test_header_fill_report_exposes_visible_labels_and_clarification_data(self) -> None:
        """Expose human labels and structured ambiguity data from deterministic header runs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            backend = mock.Mock()
            backend.provider = "fake"
            backend.model = "fake-model"
            backend.credential_source = "fake credential"
            backend.run_authoring = mock.AsyncMock()
            runtime = FakeRuntime(root, header_conflict=True)
            session = AuthoringSession(backend=backend, runtime=runtime)

            result = anyio.run(
                session.run_request,
                AuthoringRequest(
                    goal="""
                        Fill the following header fields with the following values:
                        - Company: Acme Energy
                        - RM: 0.005 @ 35
                    """,
                    output_logfile="workspace/demo.log.yaml",
                    example_id="forge16b_porosity_example",
                ),
            )

            self.assertIn("Filled `Company`.", result.user_report.done)
            self.assertEqual(len(result.needs_clarification), 1)
            clarification = result.needs_clarification[0]
            self.assertEqual(clarification["input_key"], "RM")
            self.assertEqual(
                clarification["candidate_labels"],
                ["RM @ Measured Temp", "RM @ Bottom Temp"],
            )
            self.assertIn(
                "Which header field should receive value",
                result.user_report_text,
            )
            self.assertIn("RM @ Measured Temp", result.user_report_text)

    def test_revision_routes_qualified_header_fill_before_stable_provider_loop(self) -> None:
        """Keep a qualified header revision out of the model's target-selection loop."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            draft_path = root / "workspace" / "demo.log.yaml"
            draft_path.parent.mkdir(parents=True, exist_ok=True)
            draft_path.write_text("name: Demo Draft\n", encoding="utf-8")

            backend = mock.Mock()
            backend.provider = "fake"
            backend.model = "fake-model"
            backend.credential_source = "fake credential"
            backend.run_authoring = mock.AsyncMock()
            runtime = FakeRuntime(root)
            session = AuthoringSession(backend=backend, runtime=runtime)

            with mock.patch.object(
                AuthoringSession,
                "_stable_tool_catalog",
                new=mock.AsyncMock(
                    return_value=[SimpleNamespace(name="inspect_authoring")],
                ),
            ) as stable_catalog:
                result = anyio.run(
                    session.revise_request,
                    RevisionRequest(
                        feedback="Set header RM at bottom temperature to 0.010 @ 100.",
                        logfile_path="workspace/demo.log.yaml",
                    ),
                )

            backend.run_authoring.assert_not_awaited()
            stable_catalog.assert_awaited_once()
            self.assertIn("deterministic stable header assignment", result.final_text)
            assert runtime.last_session is not None
            tool_names = [name for name, _arguments in runtime.last_session.tool_calls]
            self.assertEqual(
                tool_names[:4],
                [
                    "edit_header",
                    "validate_logfile",
                    "inspect_authoring",
                    "preview_logfile",
                ],
            )
            header_call = next(
                arguments
                for name, arguments in runtime.last_session.tool_calls
                if name == "edit_header"
            )
            self.assertEqual(
                header_call["values"],
                {"RM at bottom temperature": "0.010 @ 100"},
            )

    def test_header_clarification_follow_up_revalidates_and_applies_choice(self) -> None:
        """Resolve an ambiguous header value from a natural follow-up request."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            backend = mock.Mock()
            backend.provider = "fake"
            backend.model = "fake-model"
            backend.credential_source = "fake credential"
            backend.run_authoring = mock.AsyncMock()
            runtime = FakeRuntime(root, header_conflict=True)
            session = AuthoringSession(backend=backend, runtime=runtime)

            initial = anyio.run(
                session.run_request,
                AuthoringRequest(
                    goal="""
                        Fill the following header fields with the following values:
                        - Company: Acme Energy
                        - RM: 0.005 @ 35
                    """,
                    output_logfile="workspace/demo.log.yaml",
                    example_id="forge16b_porosity_example",
                ),
            )

            self.assertEqual(len(initial.needs_clarification), 1)

            follow_up = anyio.run(
                session.revise_request,
                RevisionRequest(
                    feedback="Use the measured one.",
                    logfile_path="workspace/demo.log.yaml",
                ),
            )

            backend.run_authoring.assert_not_awaited()
            self.assertEqual(follow_up.needs_clarification, ())
            self.assertIn("Filled `RM @ Measured Temp`.", follow_up.user_report.done)
            assert runtime.last_session is not None
            tool_names = [name for name, _arguments in runtime.last_session.tool_calls]
            self.assertEqual(
                tool_names[:2],
                ["inspect_heading_slots", "preview_header_mapping"],
            )
            self.assertIn("apply_header_values", tool_names)
            preview_calls = [
                arguments
                for name, arguments in runtime.last_session.tool_calls
                if name == "preview_header_mapping"
            ]
            self.assertEqual(
                preview_calls[-1]["values"],
                {"detail.rm_measured_temp": "0.005 @ 35"},
            )

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
            self.assertEqual(backend.initial_user_message, "")
            assert runtime.last_session is not None
            tool_names = [name for name, _arguments in runtime.last_session.tool_calls]
            self.assertNotIn("create_logfile_draft", tool_names)
            self.assertEqual(runtime.last_session.prompt_calls, [])
            self.assertEqual(
                result.report_facts["extraction"]["status"],
                "unsupported_provider",
            )

    def test_revision_request_routes_header_fill_requests_to_deterministic_tools(self) -> None:
        """Reuse one existing draft and bypass the provider loop for header-only edits."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            draft_path = root / "workspace" / "demo.log.yaml"
            draft_path.parent.mkdir(parents=True, exist_ok=True)
            draft_path.write_text("name: Demo Draft\n", encoding="utf-8")
            backend = mock.Mock()
            backend.provider = "fake"
            backend.model = "fake-model"
            backend.credential_source = "fake credential"
            backend.run_authoring = mock.AsyncMock()
            runtime = FakeRuntime(root)
            session = AuthoringSession(backend=backend, runtime=runtime)

            result = anyio.run(
                session.revise_request,
                RevisionRequest(
                    feedback="Fill header RMF value as 0.5",
                    logfile_path="workspace/demo.log.yaml",
                ),
            )

            backend.run_authoring.assert_not_awaited()
            self.assertEqual(result.request_kind, "revise")
            self.assertIn("deterministic header value assignment", result.final_text)
            assert runtime.last_session is not None
            self.assertEqual(runtime.last_session.prompt_calls, [])
            tool_names = [name for name, _arguments in runtime.last_session.tool_calls]
            self.assertEqual(
                tool_names[:4],
                [
                    "inspect_heading_slots",
                    "parse_key_value_text",
                    "preview_header_mapping",
                    "apply_header_values",
                ],
            )
            apply_call = runtime.last_session.tool_calls[3]
            self.assertEqual(
                apply_call[1]["values"],
                {"RMF": "0.5"},
            )

    def test_revision_request_reports_missing_curve_inconsistency(self) -> None:
        """Report explicit missing curve references against the current draft context."""
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
                    feedback="Change the PEF curve scale to 0 to 1.2.",
                    logfile_path="workspace/demo.log.yaml",
                ),
            )

            self.assertTrue(result.user_report.request_inconsistencies)
            self.assertIn("PEF", result.user_report.request_inconsistencies[0])
            self.assertTrue(result.user_report.next_help)

    def test_revision_request_routes_copied_header_packet_to_deterministic_tools(self) -> None:
        """Treat copied header packets as deterministic header ingestion, not freeform authoring."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            draft_path = root / "workspace" / "demo.log.yaml"
            draft_path.parent.mkdir(parents=True, exist_ok=True)
            draft_path.write_text("name: Demo Draft\n", encoding="utf-8")
            backend = mock.Mock()
            backend.provider = "fake"
            backend.model = "fake-model"
            backend.credential_source = "fake credential"
            backend.run_authoring = mock.AsyncMock()
            runtime = FakeRuntime(root)
            session = AuthoringSession(backend=backend, runtime=runtime)

            result = anyio.run(
                session.revise_request,
                RevisionRequest(
                    feedback="""
                        Use the following values to complete the relevant header fields:

                        LOG / SERVICE
                        - Cement Bond Log
                        - Variable Density Log
                        - Gamma Ray - CCL

                        COMPANY / WELL IDENTIFICATION
                        - Company: University of Utah
                        - Well: FORGE 16B (78)-32
                        - Field: Utah Forge
                        - County: Beaver

                        LOCATION
                        - Section: NWSW 32
                        - Township: 26
                        - Range: 9
                    """,
                    logfile_path="workspace/demo.log.yaml",
                ),
            )

            backend.run_authoring.assert_not_awaited()
            self.assertIn("deterministic header value assignment", result.final_text)
            assert runtime.last_session is not None
            tool_names = [name for name, _arguments in runtime.last_session.tool_calls]
            self.assertEqual(
                tool_names[:4],
                [
                    "inspect_heading_slots",
                    "parse_key_value_text",
                    "preview_header_mapping",
                    "apply_header_values",
                ],
            )
            apply_call = runtime.last_session.tool_calls[3]
            self.assertEqual(
                apply_call[1]["values"],
                {
                    "service_title_1": "Cement Bond Log",
                    "service_title_2": "Variable Density Log",
                    "service_title_3": "Gamma Ray - CCL",
                    "Company": "University of Utah",
                    "Well": "FORGE 16B (78)-32",
                    "Field": "Utah Forge",
                    "County": "Beaver",
                    "Section": "NWSW 32",
                    "Township": "26",
                    "Range": "9",
                },
            )

    def test_extract_packet_header_fill_intent_parses_isolated_header_block(self) -> None:
        """Keep packet header parsing working after the block is isolated from the outer prompt."""
        intent = _extract_packet_header_fill_intent(
            """
            Reconstruct one cased-hole packet.

            Header Values:
            LOG / SERVICE
            - Cement Bond Log
            - Variable Density Log
            - Gamma Ray - CCL

            COMPANY / WELL IDENTIFICATION
            - Company: University of Utah
            - Well: FORGE 16B (78)-32
            - Field: Utah Forge
            - County: Beaver
            """
        )

        assert intent is not None
        self.assertEqual(
            dict(intent.values),
            {
                "service_title_1": "Cement Bond Log",
                "service_title_2": "Variable Density Log",
                "service_title_3": "Gamma Ray - CCL",
                "Company": "University of Utah",
                "Well": "FORGE 16B (78)-32",
                "Field": "Utah Forge",
                "County": "Beaver",
            },
        )

    def test_revision_request_does_not_route_mixed_scope_requests_to_header_ingestion(self) -> None:
        """Reject deterministic header routing when the request also asks for track edits."""
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
                    feedback="""
                        Fill header company as University of Utah.
                        Add one QC track.
                    """,
                    logfile_path="workspace/demo.log.yaml",
                ),
            )

            assert runtime.last_session is not None
            tool_names = [name for name, _arguments in runtime.last_session.tool_calls]
            self.assertNotIn("apply_header_values", tool_names)
            self.assertEqual(runtime.last_session.prompt_calls, [])
            self.assertEqual(
                result.report_facts["extraction"]["status"],
                "unsupported_provider",
            )

    def test_revision_request_applies_grid_style_preflight_before_provider_loop(self) -> None:
        """Apply deterministic report-style edits before the broader revision loop."""
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
                    feedback="""
                        Revise the existing draft.
                        - Make darker grid lines
                        - Add one short remarks block.
                    """,
                    logfile_path="workspace/demo.log.yaml",
                ),
            )

            self.assertEqual(result.request_kind, "revise")
            self.assertEqual(
                [item.name for item in result.tool_trace],
                ["set_matplotlib_style"],
            )
            self.assertEqual(backend.initial_user_message, "")
            assert runtime.last_session is not None
            tool_names = [name for name, _arguments in runtime.last_session.tool_calls]
            self.assertEqual(tool_names[0], "set_matplotlib_style")
            self.assertNotIn("get_prompt", tool_names)
            self.assertEqual(runtime.last_session.prompt_calls, [])

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
            self.assertEqual(runtime.last_session.tool_calls[0][0], "render_logfile")

    def test_authoring_session_plan_does_not_infer_packet_blueprint(self) -> None:
        """Freeform planning does not turn packet terminology into authority."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            session = AuthoringSession(backend=FakeBackend(), runtime=FakeRuntime(root))

            plan = session.plan(
                text="""
                    Reconstruct one Cement Bond Log / Variable Density Log packet
                    from two DLIS files with main-pass and repeat-pass sections.
                """
            )

            self.assertEqual(plan.mode, "freeform")
            self.assertIsNone(plan.packet_blueprint_id)
            self.assertEqual(
                [phase.kind for phase in plan.phases],
                ["structure", "verification"],
            )
            self.assertIn("complete and verify the source section", plan.phases[0].instructions)
            self.assertIn("is_error=true", plan.phases[0].instructions)

    def test_authoring_session_plan_can_explicitly_select_scaffold(self) -> None:
        """Blueprint assets remain available as explicit dry-run scaffolds."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            session = AuthoringSession(backend=FakeBackend(), runtime=FakeRuntime(root))

            plan = session.plan(
                text="Build the supported packet scaffold.",
                blueprint_id="cased_hole_cbl_vdl",
            )

            self.assertEqual(plan.mode, "scaffold")
            self.assertEqual(plan.packet_blueprint_id, "cased_hole_cbl_vdl")
            self.assertTrue(plan.phases)
            self.assertEqual(plan.phases[0].kind, "header_scaffold")

    def test_packet_language_uses_generic_authoring_without_explicit_scaffold(self) -> None:
        """Normal packet requests do not enter the blueprint executor implicitly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            backend = FakeBackend()
            runtime = FakeRuntime(root)
            session = AuthoringSession(backend=backend, runtime=runtime)

            result = anyio.run(
                session.run_request,
                AuthoringRequest(
                    goal="Reconstruct a CBL and VDL packet from the available source channels.",
                    output_logfile="workspace/demo.log.yaml",
                    example_id="forge16b_porosity_example",
                ),
            )

            self.assertIsNone(result.plan)
            self.assertEqual(result.phase_summaries, ())
            self.assertEqual(backend.tool_names, [])
            self.assertTrue(
                any(
                    "legacy provider-to-MCP mutation loop is disabled" in item
                    for item in result.user_report.why_not
                )
            )
            assert runtime.last_session is not None
            self.assertNotIn(
                "inspect_packet_blueprints",
                [name for name, _arguments in runtime.last_session.tool_calls],
            )

    def test_structure_phase_excludes_binding_and_content_mutations(self) -> None:
        """Phase routing keeps structure work separate from later authoring phases."""
        phase = AuthoringPlanPhase(
            id="structure",
            kind="structure",
            summary="Apply structure.",
            instructions="Apply structure.",
            tool_families=("sections", "tracks", "layout"),
        )

        allowed = _phase_allowed_tool_names(phase)

        self.assertIn("add_track", allowed)
        self.assertIn("replicate_section_structure", allowed)
        self.assertIn("set_section_view", allowed)
        self.assertNotIn("bind_curve", allowed)
        self.assertNotIn("bind_raster", allowed)
        self.assertNotIn("set_heading_content", allowed)

    def test_omitted_defaults_preserve_explicit_nested_binding_values(self) -> None:
        """Defaults fill missing nested fields without overriding explicit presentation."""
        existing = {
            "style": {"color": "magenta", "line_width": 1.4},
            "sample_axis": {"enabled": True, "unit": "us"},
        }
        defaults = {
            "style": {"color": "gray", "colormap": "gray_r"},
            "sample_axis": {"enabled": False, "ticks": 7},
            "show_raster": True,
        }

        missing = _merge_omitted_defaults(existing, defaults)

        self.assertEqual(
            missing,
            {
                "style": {"colormap": "gray_r"},
                "sample_axis": {"ticks": 7},
                "show_raster": True,
            },
        )

    def test_phase_success_state_requires_persisted_header_values(self) -> None:
        """Do not count header fill as complete when the scaffold still shows pending edits."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session = AuthoringSession(backend=FakeBackend(), runtime=FakeRuntime(Path(tmpdir)))
            phase = AuthoringPlanPhase(
                id="header_fill",
                kind="header_fill",
                summary="Fill header values.",
                instructions="Fill matching header values.",
                success_check_specs=(
                    {"kind": "heading_exists"},
                    {"kind": "header_values_applied"},
                ),
            )

            before_state = session._phase_success_state(  # type: ignore[attr-defined]
                phase=phase,
                draft_summary={"has_heading": True, "sections": []},
                verification_context={
                    "header_fill_intent_present": True,
                    "header_mapping_preview": {
                        "resolved_assignments": [
                            {"input_key": "Company", "action": "set"},
                        ],
                        "unmatched_values": [],
                        "conflicting_values": [],
                    },
                },
            )
            after_state = session._phase_success_state(  # type: ignore[attr-defined]
                phase=phase,
                draft_summary={"has_heading": True, "sections": []},
                verification_context={
                    "header_fill_intent_present": True,
                    "header_mapping_preview": {
                        "resolved_assignments": [
                            {"input_key": "Company", "action": "unchanged"},
                        ],
                        "unmatched_values": [],
                        "conflicting_values": [],
                    },
                },
            )

            self.assertFalse(before_state["ok"])
            self.assertTrue(after_state["ok"])

    def test_phase_success_state_requires_persisted_changes(self) -> None:
        """A generic phase is incomplete when its persisted diff is empty."""
        session = AuthoringSession(backend=FakeBackend(), runtime=FakeRuntime(Path("/tmp")))
        phase = AuthoringPlanPhase(
            id="bindings",
            kind="bindings",
            summary="Apply bindings.",
            instructions="Bind requested source channels.",
            success_check_specs=({"kind": "changes_detected"},),
        )

        unchanged_state = session._phase_success_state(  # type: ignore[attr-defined]
            phase=phase,
            draft_summary={"sections": []},
            verification_context={"change_summary": {"summary_lines": []}},
        )
        changed_state = session._phase_success_state(  # type: ignore[attr-defined]
            phase=phase,
            draft_summary={"sections": []},
            verification_context={"change_summary": {"summary_lines": ["Added binding."]}},
        )

        self.assertFalse(unchanged_state["ok"])
        self.assertTrue(changed_state["ok"])

    def test_tool_outcome_verification_checks_persisted_binding_style_and_scale(self) -> None:
        """Verify binding calls against canonical track inspection state."""

        class OutcomeInspectionSession(FakeMcpSession):
            async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
                if name == "inspect_track_bindings":
                    return SimpleNamespace(
                        structuredContent={
                            "track": {
                                "id": "gamma",
                                "x_scale": {"kind": "linear", "min": 0, "max": 150},
                            },
                            "bindings": [
                                {
                                    "id": "gr_1",
                                    "kind": "curve",
                                    "channel": "GR",
                                    "label": "Gamma Ray",
                                    "scale": {"kind": "linear", "min": 0, "max": 150},
                                    "style": {
                                        "color": "#2563eb",
                                        "line_style": "dashed",
                                    },
                                }
                            ],
                        }
                    )
                return await super().call_tool(name, arguments)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            session = AuthoringSession(backend=FakeBackend(), runtime=FakeRuntime(root))
            fake_mcp = OutcomeInspectionSession(root)
            tool_trace = (
                AuthoringToolCall(
                    round=1,
                    name="bind_curve",
                    arguments={
                        "logfile_path": "workspace/demo.log.yaml",
                        "section_id": "main",
                        "track_id": "gamma",
                        "channel": "GR",
                        "binding_id": "gr_1",
                        "label": "Gamma Ray",
                        "scale": {"kind": "linear", "min": 0, "max": 150},
                        "style": {"color": "#2563eb", "line_style": "dashed"},
                    },
                ),
                AuthoringToolCall(
                    round=1,
                    name="set_track_scales",
                    arguments={
                        "logfile_path": "workspace/demo.log.yaml",
                        "section_id": "main",
                        "track_id": "gamma",
                        "x_scale": {"kind": "linear", "min": 0, "max": 150},
                        "channel_scales": {
                            "GR": {"kind": "linear", "min": 0, "max": 150}
                        },
                    },
                ),
            )

            outcome = anyio.run(
                partial(
                    session._verify_tool_outcomes,  # type: ignore[attr-defined]
                    session=fake_mcp,
                    draft_logfile="workspace/demo.log.yaml",
                    draft_summary={"sections": []},
                    tool_trace=tool_trace,
                    change_summary={"changed": True},
                )
            )

            self.assertTrue(outcome["ok"])
            self.assertEqual(len(outcome["outcomes"]), 2)

            fake_mcp = OutcomeInspectionSession(root)
            mismatched_trace = (
                AuthoringToolCall(
                    round=1,
                    name="update_curve_binding",
                    arguments={
                        "logfile_path": "workspace/demo.log.yaml",
                        "section_id": "main",
                        "track_id": "gamma",
                        "channel": "GR",
                        "binding_id": "gr_1",
                        "patch": {"style": {"color": "#dc2626"}},
                    },
                ),
            )
            mismatched = anyio.run(
                partial(
                    session._verify_tool_outcomes,  # type: ignore[attr-defined]
                    session=fake_mcp,
                    draft_logfile="workspace/demo.log.yaml",
                    draft_summary={"sections": []},
                    tool_trace=mismatched_trace,
                    change_summary={"changed": True},
                )
            )

            self.assertFalse(mismatched["ok"])

            class MissingChannelSession(OutcomeInspectionSession):
                async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
                    if name == "check_channel_availability":
                        return SimpleNamespace(
                            structuredContent={
                                "found_channels": [],
                                "missing_channels": ["GR"],
                                "warnings": ["Requested channel 'GR' was not found."],
                            }
                        )
                    return await super().call_tool(name, arguments)

            missing = anyio.run(
                partial(
                    session._verify_tool_outcomes,  # type: ignore[attr-defined]
                    session=MissingChannelSession(root),
                    draft_logfile="workspace/demo.log.yaml",
                    draft_summary={"sections": []},
                    tool_trace=tool_trace[:1],
                    change_summary={"changed": True},
                )
            )

            self.assertFalse(missing["ok"])
            self.assertIn("source channel is missing", missing["outcomes"][0]["detail"])

    def test_tool_outcome_verification_reports_missing_section_without_raising(self) -> None:
        """Treat a provider target for an absent section as a failed outcome."""

        class MissingSectionSession(FakeMcpSession):
            async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
                if name == "inspect_track_bindings":
                    return SimpleNamespace(
                        isError=True,
                        content=[
                            SimpleNamespace(
                                text=(
                                    "Error executing tool inspect_track_bindings: "
                                    "Unknown section_id 'repeat_pass'."
                                )
                            )
                        ],
                    )
                return await super().call_tool(name, arguments)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            session = AuthoringSession(backend=FakeBackend(), runtime=FakeRuntime(root))
            outcome = anyio.run(
                partial(
                    session._verify_tool_outcomes,  # type: ignore[attr-defined]
                    session=MissingSectionSession(root),
                    draft_logfile="workspace/demo.log.yaml",
                    draft_summary={"sections": [{"id": "main_pass"}]},
                    tool_trace=(
                        AuthoringToolCall(
                            round=1,
                            name="bind_curve",
                            arguments={
                                "logfile_path": "workspace/demo.log.yaml",
                                "section_id": "repeat_pass",
                                "track_id": "cbl",
                                "channel": "CBL",
                            },
                        ),
                    ),
                    change_summary={"changed": True},
                )
            )

            self.assertFalse(outcome["ok"])
            self.assertIn("Unknown section_id", outcome["outcomes"][0]["detail"])

    def test_tool_outcome_verification_checks_canonical_layout_and_annotations(self) -> None:
        """Verify non-binding mutations against typed authoring objects."""

        class CanonicalInspectionSession(FakeMcpSession):
            async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
                if name == "inspect_authoring_objects":
                    object_kind = str(arguments["object_kind"])
                    objects = {
                        "section": [
                            {
                                "ref": {"object_id": "main", "index": 0},
                                "object": {
                                    "id": "main",
                                    "title": "Updated Main",
                                    "subtitle": "Review",
                                    "depth_range": [100.0, 200.0],
                                },
                            }
                        ],
                        "depth": [
                            {
                                "ref": {"object_id": "depth", "index": 0},
                                "object": {
                                    "unit": "ft",
                                    "scale": 240.0,
                                    "major_step": 10.0,
                                },
                            }
                        ],
                        "page": [
                            {
                                "ref": {"object_id": "page", "index": 0},
                                "object": {
                                    "size": "letter",
                                    "orientation": "landscape",
                                    "continuous": True,
                                },
                            }
                        ],
                        "annotation": [
                            {
                                "ref": {
                                    "object_id": "marker-1",
                                    "index": 0,
                                    "section_id": "main",
                                    "track_id": "notes",
                                },
                                "object": {
                                    "kind": "marker",
                                    "annotation_id": "marker-1",
                                    "depth": 150.0,
                                    "marker": "circle",
                                    "color": "#2563eb",
                                },
                            }
                        ],
                        "remark": [
                            {
                                "ref": {"object_id": "remark-1", "index": 0},
                                "object": {
                                    "remark_id": "remark-1",
                                    "title": "Notes",
                                    "lines": ["Updated note"],
                                    "alignment": "left",
                                },
                            }
                        ],
                    }
                    return SimpleNamespace(
                        structuredContent={"objects": objects.get(object_kind, [])}
                    )
                return await super().call_tool(name, arguments)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            session = AuthoringSession(backend=FakeBackend(), runtime=FakeRuntime(root))
            tool_trace = (
                AuthoringToolCall(
                    round=1,
                    name="update_section",
                    arguments={
                        "logfile_path": "workspace/demo.log.yaml",
                        "section_id": "main",
                        "title": "Updated Main",
                        "subtitle": "Review",
                        "depth_range": [100.0, 200.0],
                    },
                ),
                AuthoringToolCall(
                    round=1,
                    name="set_depth_axis",
                    arguments={
                        "logfile_path": "workspace/demo.log.yaml",
                        "unit": "ft",
                        "scale": 240.0,
                        "major_step": 10.0,
                    },
                ),
                AuthoringToolCall(
                    round=1,
                    name="set_page_layout",
                    arguments={
                        "logfile_path": "workspace/demo.log.yaml",
                        "page_patch": {
                            "size": "letter",
                            "orientation": "landscape",
                            "continuous": True,
                        },
                    },
                ),
                AuthoringToolCall(
                    round=1,
                    name="add_annotation_object",
                    arguments={
                        "logfile_path": "workspace/demo.log.yaml",
                        "section_id": "main",
                        "track_id": "notes",
                        "annotation": {
                            "kind": "marker",
                            "annotation_id": "marker-1",
                            "depth": 150.0,
                            "marker": "circle",
                            "color": "#2563eb",
                        },
                    },
                ),
                AuthoringToolCall(
                    round=1,
                    name="set_remarks_content",
                    arguments={
                        "logfile_path": "workspace/demo.log.yaml",
                        "remarks": [
                            {
                                "title": "Notes",
                                "lines": ["Updated note"],
                                "alignment": "left",
                            }
                        ],
                    },
                ),
            )

            outcome = anyio.run(
                partial(
                    session._verify_tool_outcomes,  # type: ignore[attr-defined]
                    session=CanonicalInspectionSession(root),
                    draft_logfile="workspace/demo.log.yaml",
                    draft_summary={"sections": []},
                    tool_trace=tool_trace,
                    change_summary={"changed": True},
                )
            )

            self.assertTrue(outcome["ok"])
            self.assertEqual(len(outcome["outcomes"]), len(tool_trace))

    def test_tool_outcome_success_requires_at_least_one_verified_mutation(self) -> None:
        """Do not pass a generic phase when no mutating outcome was inspected."""
        session = AuthoringSession(backend=FakeBackend(), runtime=FakeRuntime(Path("/tmp")))
        phase = AuthoringPlanPhase(
            id="structure",
            kind="structure",
            summary="Apply structure.",
            instructions="Apply structure.",
            success_check_specs=({"kind": "tool_outcomes_match"},),
        )

        state = session._phase_success_state(  # type: ignore[attr-defined]
            phase=phase,
            draft_summary={"sections": []},
            verification_context={"tool_outcomes": {"ok": True, "outcomes": []}},
        )

        self.assertFalse(state["ok"])

    def test_tool_outcome_failure_detail_is_exposed_in_phase_state(self) -> None:
        """Expose the failed mutation and verifier detail to the operator report."""
        session = AuthoringSession(backend=FakeBackend(), runtime=FakeRuntime(Path("/tmp")))
        phase = AuthoringPlanPhase(
            id="structure",
            kind="structure",
            summary="Apply structure.",
            instructions="Apply structure.",
            success_check_specs=({"kind": "tool_outcomes_match"},),
        )

        state = session._phase_success_state(  # type: ignore[attr-defined]
            phase=phase,
            draft_summary={"sections": []},
            verification_context={
                "tool_outcomes": {
                    "ok": False,
                    "outcomes": [
                        {
                            "tool": "add_track",
                            "target": "section_id=main_pass, track_id=cbl",
                            "ok": False,
                            "detail": "track is missing after mutation",
                        }
                    ],
                }
            },
        )

        self.assertFalse(state["ok"])
        detail = str(state["checks"][0]["detail"])
        self.assertIn("failed=1", detail)
        self.assertIn("add_track", detail)
        self.assertIn("track is missing after mutation", detail)

    def test_phase_success_state_requires_matching_remarks_payload(self) -> None:
        """Do not count remarks as complete when the persisted block does not match the request."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session = AuthoringSession(backend=FakeBackend(), runtime=FakeRuntime(Path(tmpdir)))
            phase = AuthoringPlanPhase(
                id="remarks",
                kind="remarks",
                summary="Apply remarks.",
                instructions="Apply the requested remarks block.",
                success_check_specs=(
                    {"kind": "remarks_exists"},
                    {"kind": "remarks_match"},
                ),
            )

            mismatched_state = session._phase_success_state(  # type: ignore[attr-defined]
                phase=phase,
                draft_summary={"has_remarks": True, "sections": []},
                verification_context={
                    "expected_remarks": [
                        {"title": "Requested Notes", "alignment": "left", "lines": ["One", "Two"]}
                    ],
                    "heading_slots": {
                        "current_values": {
                            "remarks": [
                                {"title": "Notes", "alignment": "left", "lines": ["Placeholder"]}
                            ]
                        }
                    },
                },
            )
            matched_state = session._phase_success_state(  # type: ignore[attr-defined]
                phase=phase,
                draft_summary={"has_remarks": True, "sections": []},
                verification_context={
                    "expected_remarks": [
                        {"title": "Requested Notes", "alignment": "left", "lines": ["One", "Two"]}
                    ],
                    "heading_slots": {
                        "current_values": {
                            "remarks": [
                                {
                                    "title": "Requested Notes",
                                    "alignment": "left",
                                    "lines": ["One", "Two"],
                                }
                            ]
                        }
                    },
                },
            )

            self.assertFalse(mismatched_state["ok"])
            self.assertTrue(matched_state["ok"])

    def test_phase_success_state_can_require_track_kind(self) -> None:
        """Allow packet phases to verify a specific track kind, not just track existence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session = AuthoringSession(backend=FakeBackend(), runtime=FakeRuntime(Path(tmpdir)))
            phase = AuthoringPlanPhase(
                id="section_scaffold",
                kind="section_scaffold",
                summary="Build the main packet section.",
                instructions="Create the main-pass section first.",
                success_check_specs=(
                    {
                        "kind": "track_kind_is",
                        "section_id": "main_pass",
                        "track_id": "vdl",
                        "track_kind": "array",
                    },
                ),
            )

            wrong_kind = session._phase_success_state(  # type: ignore[attr-defined]
                phase=phase,
                draft_summary={
                    "sections": [
                        {"id": "main_pass", "track_ids": ["vdl"], "track_kinds": ["normal"]}
                    ]
                },
            )
            right_kind = session._phase_success_state(  # type: ignore[attr-defined]
                phase=phase,
                draft_summary={
                    "sections": [
                        {"id": "main_pass", "track_ids": ["vdl"], "track_kinds": ["array"]}
                    ]
                },
            )

            self.assertFalse(wrong_kind["ok"])
            self.assertTrue(right_kind["ok"])

    def test_packet_phase_completes_if_verification_passes_after_round_budget_exhaustion(
        self,
    ) -> None:
        """Treat one phase as complete after budget exhaustion if checks already pass."""

        class ExhaustedBackend(FakeBackend):
            async def run_authoring(self, **_: object) -> SimpleNamespace:  # type: ignore[override]
                raise RuntimeError("The fake authoring loop exceeded 8 rounds.")

        class PacketSummarySession(FakeMcpSession):
            def __init__(self, root: Path) -> None:
                super().__init__(root)
                self.summary_calls = 0

            async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
                if name == "summarize_logfile_draft":
                    self.summary_calls += 1
                    if self.summary_calls == 1:
                        return SimpleNamespace(
                            structuredContent={
                                "has_heading": True,
                                "has_remarks": False,
                                "section_ids": [],
                                "sections": [],
                            }
                        )
                    return SimpleNamespace(
                        structuredContent={
                            "has_heading": True,
                            "has_remarks": False,
                            "section_ids": ["main_pass"],
                            "sections": [
                                {
                                    "id": "main_pass",
                                    "track_ids": ["combo", "depth", "cbl", "vdl"],
                                    "track_kinds": ["normal", "reference", "normal", "array"],
                                    "available_channels": [],
                                    "source_path": "workspace/data/main.dlis",
                                    "source_format": "dlis",
                                    "bindings_by_track": {},
                                }
                            ],
                        }
                    )
                if name == "preview_section_png":
                    return SimpleNamespace(content=[SimpleNamespace(data=b"section-preview")])
                return await super().call_tool(name, arguments)

        class PacketSummaryRuntime(FakeRuntime):
            @asynccontextmanager
            async def open_session(self) -> object:  # type: ignore[override]
                session = PacketSummarySession(self.server_root)
                self.last_session = session
                yield session

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            session = AuthoringSession(
                backend=ExhaustedBackend(),
                runtime=PacketSummaryRuntime(root),
            )
            phase = AuthoringPlanPhase(
                id="section_scaffold",
                kind="section_scaffold",
                summary="Build the main packet section.",
                instructions="Create the main-pass section first.",
                success_check_specs=(
                    {"kind": "section_exists", "section_id": "main_pass"},
                    {"kind": "track_exists", "section_id": "main_pass", "track_id": "combo"},
                    {"kind": "track_exists", "section_id": "main_pass", "track_id": "depth"},
                    {"kind": "track_exists", "section_id": "main_pass", "track_id": "cbl"},
                    {"kind": "track_exists", "section_id": "main_pass", "track_id": "vdl"},
                ),
                max_rounds=2,
            )
            plan = session.plan(text="Reconstruct one cased-hole packet.")
            plan = type(plan)(
                mode="packet",
                packet_blueprint_id=None,
                phases=(phase,),
                blocked=False,
                run_state=plan.run_state,
            )

            async def run_plan() -> tuple[object, tuple[ExecutedAuthoringPhase, ...], object]:
                async with session.runtime.open_session() as mcp_session:
                    return await session._execute_authoring_plan(  # type: ignore[attr-defined]
                        session=mcp_session,
                        draft_logfile="workspace/demo.log.yaml",
                        request_text="Reconstruct one cased-hole packet.",
                        plan=plan,
                        prompt_text="authoring prompt",
                        tool_definitions=[],
                        request_max_rounds=8,
                    )

            _, phase_summaries, _ = anyio.run(run_plan)
            self.assertEqual(len(phase_summaries), 1)
            self.assertEqual(phase_summaries[0].status, "completed")
            self.assertEqual(phase_summaries[0].blocked_reasons, ())

    def test_section_scaffold_reconciles_track_kind_after_round_budget_exhaustion(self) -> None:
        """Reconcile packet track kinds even if the provider loop stops on budget."""

        class ExhaustedBackend(FakeBackend):
            async def run_authoring(self, **_: object) -> SimpleNamespace:  # type: ignore[override]
                raise RuntimeError("The fake authoring loop exceeded 8 rounds.")

        class ReconcileSession(FakeMcpSession):
            def __init__(self, root: Path) -> None:
                super().__init__(root)
                self.vdl_kind = "normal"
                self.summary_calls = 0

            async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
                if name == "summarize_logfile_draft":
                    self.summary_calls += 1
                    if self.summary_calls == 1:
                        return SimpleNamespace(
                            structuredContent={
                                "has_heading": True,
                                "has_remarks": False,
                                "section_ids": [],
                                "sections": [],
                            }
                        )
                    return SimpleNamespace(
                        structuredContent={
                            "has_heading": True,
                            "has_remarks": False,
                            "section_ids": ["main_pass"],
                            "sections": [
                                {
                                    "id": "main_pass",
                                    "track_ids": ["combo", "depth", "cbl", "vdl"],
                                    "track_kinds": [
                                        "normal",
                                        "reference",
                                        "normal",
                                        self.vdl_kind,
                                    ],
                                    "available_channels": [],
                                    "source_path": "workspace/data/main.dlis",
                                    "source_format": "dlis",
                                    "bindings_by_track": {},
                                }
                            ],
                        }
                    )
                if (
                    name == "update_track"
                    and arguments.get("section_id") == "main_pass"
                    and arguments.get("track_id") == "vdl"
                    and dict(arguments.get("patch", {})).get("kind") == "array"
                ):
                    self.vdl_kind = "array"
                    return SimpleNamespace(structuredContent={"track_id": "vdl"})
                if name == "preview_section_png":
                    return SimpleNamespace(content=[SimpleNamespace(data=b"section-preview")])
                return await super().call_tool(name, arguments)

        class ReconcileRuntime(FakeRuntime):
            @asynccontextmanager
            async def open_session(self) -> object:  # type: ignore[override]
                session = ReconcileSession(self.server_root)
                self.last_session = session
                yield session

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            session = AuthoringSession(
                backend=ExhaustedBackend(),
                runtime=ReconcileRuntime(root),
            )
            phase = AuthoringPlanPhase(
                id="section_scaffold",
                kind="section_scaffold",
                summary="Build the main packet section.",
                instructions="Create the main-pass section first.",
                success_check_specs=(
                    {"kind": "section_exists", "section_id": "main_pass"},
                    {"kind": "track_exists", "section_id": "main_pass", "track_id": "combo"},
                    {"kind": "track_exists", "section_id": "main_pass", "track_id": "depth"},
                    {"kind": "track_exists", "section_id": "main_pass", "track_id": "cbl"},
                    {"kind": "track_exists", "section_id": "main_pass", "track_id": "vdl"},
                    {
                        "kind": "track_kind_is",
                        "section_id": "main_pass",
                        "track_id": "vdl",
                        "track_kind": "array",
                    },
                ),
                max_rounds=2,
                metadata={
                    "section_template": {
                        "id": "main_pass",
                        "track_templates": [
                            {"id": "combo", "kind": "normal"},
                            {"id": "depth", "kind": "reference"},
                            {"id": "cbl", "kind": "normal"},
                            {"id": "vdl", "kind": "array"},
                        ],
                    }
                },
            )
            plan = session.plan(text="Reconstruct one cased-hole packet.")
            plan = type(plan)(
                mode="packet",
                packet_blueprint_id=None,
                phases=(phase,),
                blocked=False,
                run_state=plan.run_state,
            )

            async def run_plan() -> tuple[object, tuple[ExecutedAuthoringPhase, ...], object]:
                async with session.runtime.open_session() as mcp_session:
                    return await session._execute_authoring_plan(  # type: ignore[attr-defined]
                        session=mcp_session,
                        draft_logfile="workspace/demo.log.yaml",
                        request_text="Reconstruct one cased-hole packet.",
                        plan=plan,
                        prompt_text="authoring prompt",
                        tool_definitions=[],
                        request_max_rounds=8,
                    )

            _, phase_summaries, _ = anyio.run(run_plan)
            self.assertEqual(len(phase_summaries), 1)
            self.assertEqual(phase_summaries[0].status, "completed")
            self.assertIn("update_track", [call.name for call in phase_summaries[0].tool_trace])

    def test_complete_packet_expected_bindings_fills_missing_repeat_combo_curves(self) -> None:
        """Deterministically fill missing expected bindings that the provider loop skipped."""

        class BindingCompletionSession(FakeMcpSession):
            def __init__(self, root: Path) -> None:
                super().__init__(root)
                self.bindings_by_track: dict[tuple[str, str], list[dict[str, object]]] = {
                    ("main_pass", "combo"): [
                        {"kind": "curve", "channel": "ECGR_STGC", "label": "GR"},
                        {"kind": "curve", "channel": "TT", "label": "TT"},
                        {"kind": "curve", "channel": "TENS", "label": "TENS"},
                        {"kind": "curve", "channel": "MTEM", "label": "MTEM"},
                    ],
                    ("repeat_pass", "combo"): [],
                }

            async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
                if name == "summarize_logfile_draft":
                    return SimpleNamespace(
                        structuredContent={
                            "has_heading": True,
                            "has_remarks": True,
                            "section_ids": ["main_pass", "repeat_pass"],
                            "sections": [
                                {
                                    "id": "main_pass",
                                    "track_ids": ["combo"],
                                    "track_kinds": ["normal"],
                                    "available_channels": [],
                                    "source_path": "workspace/data/main.dlis",
                                    "source_format": "dlis",
                                    "bindings_by_track": {
                                        "combo": list(
                                            self.bindings_by_track[("main_pass", "combo")]
                                        )
                                    },
                                },
                                {
                                    "id": "repeat_pass",
                                    "track_ids": ["combo"],
                                    "track_kinds": ["normal"],
                                    "available_channels": [],
                                    "source_path": "workspace/data/repeat.dlis",
                                    "source_format": "dlis",
                                    "bindings_by_track": {
                                        "combo": list(
                                            self.bindings_by_track[("repeat_pass", "combo")]
                                        )
                                    },
                                },
                            ],
                        }
                    )
                if name == "check_channel_availability":
                    return SimpleNamespace(
                        structuredContent={
                            "found_channels": ["ECGR_STGC", "TT", "TENS", "MTEM"],
                            "missing_channels": [],
                        }
                    )
                if name == "inspect_track_bindings":
                    section_id = str(arguments["section_id"])
                    track_id = str(arguments["track_id"])
                    return SimpleNamespace(
                        structuredContent={
                            "bindings": list(self.bindings_by_track.get((section_id, track_id), []))
                        }
                    )
                if name == "bind_curve":
                    section_id = str(arguments["section_id"])
                    track_id = str(arguments["track_id"])
                    channel = str(arguments["channel"])
                    binding: dict[str, object] = {
                        "kind": "curve",
                        "channel": channel,
                        "label": arguments.get("label", channel),
                    }
                    binding_id = arguments.get("binding_id")
                    if binding_id is not None:
                        binding["id"] = binding_id
                    self.bindings_by_track.setdefault((section_id, track_id), []).append(binding)
                    return SimpleNamespace(structuredContent={"channel": channel})
                return await super().call_tool(name, arguments)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            session = AuthoringSession(backend=FakeBackend(), runtime=FakeRuntime(root))
            fake_mcp = BindingCompletionSession(root)
            blueprint = {
                "section_templates": [
                    {
                        "id": "main_pass",
                        "expected_bindings_by_track": {
                            "combo": ["ECGR_STGC", "TT", "TENS", "MTEM"]
                        },
                    },
                    {
                        "id": "repeat_pass",
                        "expected_bindings_by_track": {
                            "combo": ["ECGR_STGC", "TT", "TENS", "MTEM"]
                        },
                    },
                ]
            }

            async def run_helper() -> tuple[AuthoringToolCall, ...]:
                return await session._complete_packet_expected_bindings(  # type: ignore[attr-defined]
                    session=fake_mcp,
                    draft_logfile="workspace/demo.log.yaml",
                    blueprint=blueprint,
                )

            tool_trace = anyio.run(run_helper)
            self.assertTrue(all(call.name == "bind_curve" for call in tool_trace))
            self.assertGreaterEqual(len(tool_trace), 4)
            self.assertEqual(
                [
                    binding["channel"]
                    for binding in fake_mcp.bindings_by_track[("repeat_pass", "combo")]
                ],
                ["ECGR_STGC", "TT", "TENS", "MTEM"],
            )

    def test_phase_success_state_requires_binding_subset_match(self) -> None:
        """Packet binding success checks should fail when the binding content is incomplete."""
        session = AuthoringSession(backend=FakeBackend(), runtime=FakeRuntime(Path("/tmp")))
        phase = AuthoringPlanPhase(
            id="bindings_raster",
            kind="bindings_raster",
            summary="Bind the packet channels.",
            instructions="Apply one packet binding.",
            success_check_specs=(
                {
                    "kind": "binding_subset_matches",
                    "section_id": "main_pass",
                    "track_id": "combo",
                    "channel": "TT",
                    "expected": {
                        "label": "Transit Time for CBL (TT) QSLT-B",
                        "scale": {"kind": "linear", "min": 200, "max": 400, "reverse": True},
                        "style": {"color": "#2142ff", "line_width": 0.75},
                    },
                },
            ),
        )
        draft_summary = {
            "sections": [
                {
                    "id": "main_pass",
                    "bindings_by_track": {
                        "combo": [
                            {
                                "kind": "curve",
                                "channel": "TT",
                                "label": "Transit Time for CBL (TT) QSLT-B",
                            }
                        ]
                    },
                }
            ]
        }
        incomplete_state = session._phase_success_state(
            phase=phase,
            draft_summary=draft_summary,
        )
        self.assertFalse(incomplete_state["ok"])
        self.assertEqual(
            incomplete_state["checks"][0]["kind"],
            "binding_subset_matches",
        )

        draft_summary["sections"][0]["bindings_by_track"]["combo"][0]["scale"] = {
            "kind": "linear",
            "min": 200,
            "max": 400,
            "reverse": True,
        }
        draft_summary["sections"][0]["bindings_by_track"]["combo"][0]["style"] = {
            "color": "#2142ff",
            "line_width": 0.75,
        }
        complete_state = session._phase_success_state(
            phase=phase,
            draft_summary=draft_summary,
        )
        self.assertTrue(complete_state["ok"])

    def test_complete_packet_expected_bindings_patches_existing_and_rebuilds_duplicates(
        self,
    ) -> None:
        """Patch unique bindings in place and rebuild duplicate-channel tracks deterministically."""

        class BindingPatchSession(FakeMcpSession):
            def __init__(self, root: Path) -> None:
                super().__init__(root)
                self.bindings_by_track: dict[tuple[str, str], list[dict[str, object]]] = {
                    ("main_pass", "combo"): [
                        {
                            "kind": "curve",
                            "channel": "TT",
                            "label": "Transit Time for CBL (TT) QSLT-B",
                            "style": {"color": "#2142ff", "line_width": 0.75},
                        }
                    ],
                    ("main_pass", "cbl"): [
                        {
                            "kind": "curve",
                            "channel": "CBL",
                            "label": "CBL Amplitude (CBL) QSLT-B",
                            "style": {"color": "#111111", "line_width": 0.75},
                        },
                        {
                            "kind": "curve",
                            "channel": "CBL",
                            "label": "CBL Amplitude (CBL) QSLT-B",
                            "style": {
                                "color": "#2563eb",
                                "line_width": 0.65,
                                "line_style": "dashed",
                            },
                        },
                    ],
                }

            async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
                if name == "summarize_logfile_draft":
                    return SimpleNamespace(
                        structuredContent={
                            "has_heading": True,
                            "has_remarks": True,
                            "section_ids": ["main_pass"],
                            "sections": [
                                {
                                    "id": "main_pass",
                                    "track_ids": ["combo", "cbl"],
                                    "track_kinds": ["normal", "normal"],
                                    "available_channels": [],
                                    "source_path": "workspace/data/main.dlis",
                                    "source_format": "dlis",
                                    "bindings_by_track": {
                                        "combo": list(
                                            self.bindings_by_track[("main_pass", "combo")]
                                        ),
                                        "cbl": list(
                                            self.bindings_by_track[("main_pass", "cbl")]
                                        ),
                                    },
                                }
                            ],
                        }
                    )
                if name == "check_channel_availability":
                    return SimpleNamespace(
                        structuredContent={
                            "found_channels": ["TT", "CBL"],
                            "missing_channels": [],
                        }
                    )
                if name == "inspect_track_bindings":
                    section_id = str(arguments["section_id"])
                    track_id = str(arguments["track_id"])
                    return SimpleNamespace(
                        structuredContent={
                            "bindings": list(self.bindings_by_track.get((section_id, track_id), []))
                        }
                    )
                if name == "update_curve_binding":
                    section_id = str(arguments["section_id"])
                    track_id = str(arguments["track_id"])
                    channel = str(arguments["channel"])
                    patch = dict(arguments["patch"])
                    for binding in self.bindings_by_track[(section_id, track_id)]:
                        if str(binding.get("channel")) == channel:
                            binding.update(patch)
                            return SimpleNamespace(structuredContent={"channel": channel})
                if name == "clear_track_bindings":
                    section_id = str(arguments["section_id"])
                    track_id = str(arguments["track_id"])
                    removed = len(self.bindings_by_track.get((section_id, track_id), []))
                    self.bindings_by_track[(section_id, track_id)] = []
                    return SimpleNamespace(
                        structuredContent={
                            "removed_curve_binding_count": removed,
                            "removed_raster_binding_count": 0,
                        }
                    )
                if name == "bind_curve":
                    section_id = str(arguments["section_id"])
                    track_id = str(arguments["track_id"])
                    binding: dict[str, object] = {
                        "kind": "curve",
                        "channel": str(arguments["channel"]),
                    }
                    for key in ("binding_id", "label", "style", "scale"):
                        value = arguments.get(key)
                        if value is not None:
                            binding["id" if key == "binding_id" else key] = value
                    self.bindings_by_track.setdefault((section_id, track_id), []).append(binding)
                    return SimpleNamespace(structuredContent={"channel": arguments["channel"]})
                return await super().call_tool(name, arguments)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            session = AuthoringSession(backend=FakeBackend(), runtime=FakeRuntime(root))
            fake_mcp = BindingPatchSession(root)
            blueprint = {
                "section_templates": [
                    {
                        "id": "main_pass",
                        "expected_bindings_by_track": {
                            "combo": ["TT"],
                            "cbl": ["CBL", "CBL"],
                        },
                        "expected_binding_specs_by_track": {
                            "combo": [
                                {
                                    "channel": "TT",
                                    "kind": "curve",
                                    "label": "Transit Time for CBL (TT) QSLT-B",
                                    "scale": {
                                        "kind": "linear",
                                        "min": 200,
                                        "max": 400,
                                        "reverse": True,
                                    },
                                    "style": {"color": "#2142ff", "line_width": 0.75},
                                }
                            ],
                            "cbl": [
                                {
                                    "channel": "CBL",
                                    "kind": "curve",
                                    "binding_id": "cbl_main_pass_1",
                                    "label": "CBL Amplitude (CBL) QSLT-B",
                                    "scale": {"kind": "linear", "min": 0, "max": 100},
                                    "style": {"color": "#111111", "line_width": 0.75},
                                },
                                {
                                    "channel": "CBL",
                                    "kind": "curve",
                                    "binding_id": "cbl_main_pass_2",
                                    "label": "CBL Amplitude (CBL) QSLT-B",
                                    "scale": {"kind": "linear", "min": 0, "max": 10},
                                    "style": {
                                        "color": "#2563eb",
                                        "line_width": 0.65,
                                        "line_style": "dashed",
                                    },
                                },
                            ],
                        },
                    }
                ]
            }

            async def run_helper() -> tuple[AuthoringToolCall, ...]:
                return await session._complete_packet_expected_bindings(  # type: ignore[attr-defined]
                    session=fake_mcp,
                    draft_logfile="workspace/demo.log.yaml",
                    blueprint=blueprint,
                )

            tool_trace = anyio.run(run_helper)
            tool_names = [call.name for call in tool_trace]
            self.assertIn("update_curve_binding", tool_names)
            self.assertIn("clear_track_bindings", tool_names)
            self.assertEqual(
                fake_mcp.bindings_by_track[("main_pass", "combo")][0]["scale"],
                {"kind": "linear", "min": 200, "max": 400, "reverse": True},
            )
            self.assertEqual(
                [binding.get("id") for binding in fake_mcp.bindings_by_track[("main_pass", "cbl")]],
                ["cbl_main_pass_1", "cbl_main_pass_2"],
            )
            self.assertEqual(
                fake_mcp.bindings_by_track[("main_pass", "cbl")][1]["scale"],
                {"kind": "linear", "min": 0, "max": 10},
            )

    def test_display_phase_previews_renders_captured_images(self) -> None:
        """Display packet phase previews through one public notebook helper."""
        result = AuthoringResult(
            provider="openai",
            model="gpt-5.4",
            credential_source="environment variable OPENAI_API_KEY",
            request_kind="author",
            example_id=None,
            source_logfile_path=None,
            goal="Build one packet.",
            draft_logfile="workspace/demo.log.yaml",
            server_root=Path("/tmp"),
            tool_trace=(),
            final_text="done",
            validation={"valid": True},
            draft_summary={},
            inspect_summary={"section_ids": ["main_pass"]},
            change_summary={"summary_lines": []},
            draft_text="name: Demo Draft\n",
            report_preview_png=b"report-preview",
            section_preview_png=b"section-preview",
            phase_summaries=(
                ExecutedAuthoringPhase(
                    id="header_fill",
                    kind="header_fill",
                    summary="Fill packet header values.",
                    status="completed",
                    tool_trace=(),
                    verification={"ok": True, "checks": []},
                    preview_kind="report",
                    preview_png=b"phase-report",
                ),
                ExecutedAuthoringPhase(
                    id="section_scaffold",
                    kind="section_scaffold",
                    summary="Build the main packet section.",
                    status="completed",
                    tool_trace=(),
                    verification={"ok": True, "checks": []},
                    preview_kind="section",
                    preview_target="main_pass",
                    preview_png=b"phase-section",
                ),
            ),
        )
        display_calls: list[object] = []

        class FakeImage:
            def __init__(self, *, data: bytes) -> None:
                self.data = data

        fake_display_module = ModuleType("IPython.display")
        fake_display_module.Image = FakeImage
        fake_display_module.display = display_calls.append

        with mock.patch.dict(sys.modules, {"IPython.display": fake_display_module}):
            images = display_phase_previews(result, return_images=True)

        assert images is not None
        self.assertEqual([image.data for image in images], [b"phase-report", b"phase-section"])

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

    def test_authoring_result_exposes_user_report_text(self) -> None:
        """Expose the deterministic operator report directly on the public result."""
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
            change_summary={"summary_lines": []},
            draft_text="name: Demo Draft\n",
            report_preview_png=b"report-preview",
            section_preview_png=b"section-preview",
            user_report=AuthoringUserReport(
                done=("Updated heading.",),
                could_not_do=("Did not apply `RMF`.",),
                why_not=("The current scaffold did not expose a matching slot.",),
                warnings_or_errors=("1 packet field was ignored.",),
                request_inconsistencies=("Requested curve `PEF` is not available.",),
                next_help=("I can inspect the draft context next.",),
            ),
        )

        self.assertIn("Done:", result.user_report_text)
        self.assertIn("Updated heading.", result.user_report_text)
        self.assertIn("Request inconsistencies:", result.user_report_text)

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

    def test_display_authoring_result_shows_phase_previews_before_final_preview(self) -> None:
        """Render checkpoint previews before the final preview to preserve execution flow."""
        result = AuthoringResult(
            provider="openai",
            model="gpt-5.4",
            credential_source="environment variable OPENAI_API_KEY",
            request_kind="author",
            example_id=None,
            source_logfile_path=None,
            goal="Build one packet.",
            draft_logfile="workspace/demo.log.yaml",
            server_root=Path("/tmp"),
            tool_trace=(),
            final_text="done",
            validation={"valid": True},
            draft_summary={},
            inspect_summary={"section_ids": ["main_pass"]},
            change_summary={"summary_lines": []},
            draft_text="name: Demo Draft\n",
            report_preview_png=b"final-report",
            section_preview_png=b"section-preview",
            plan=AuthoringPlanResult(
                mode="desired_state",
                packet_blueprint_id=None,
                phases=(
                    AuthoringPlanPhase(
                        id="desired-tracks",
                        kind="desired_state_tracks",
                        summary="Apply track operations.",
                        instructions="Apply and verify.",
                        metadata={"operation_ids": ["track-1"]},
                    ),
                ),
                blocked=False,
            ),
            run_state=AuthoringRunState(
                discovered_sections=("main",),
                available_channels_by_section={"main": ("GR", "RHOB")},
            ),
            request_coverage=(
                {"request_item_id": "request-1", "status": "mapped"},
            ),
            defaults_provenance={"main.tracks[0]": "generic_normal_track"},
            phase_summaries=(
                ExecutedAuthoringPhase(
                    id="header_fill",
                    kind="header_fill",
                    summary="Fill packet header values.",
                    status="completed",
                    tool_trace=(),
                    verification={"ok": True, "checks": []},
                    preview_kind="report",
                    preview_png=b"phase-report",
                ),
                ExecutedAuthoringPhase(
                    id="section_scaffold",
                    kind="section_scaffold",
                    summary="Build the main packet section.",
                    status="completed",
                    tool_trace=(),
                    verification={"ok": True, "checks": []},
                    preview_kind="section",
                    preview_target="main_pass",
                    preview_png=b"phase-section",
                ),
            ),
        )
        display_calls: list[object] = []

        class FakeImage:
            def __init__(self, *, data: bytes) -> None:
                self.data = data

        fake_display_module = ModuleType("IPython.display")
        fake_display_module.Image = FakeImage
        fake_display_module.display = display_calls.append

        stdout = StringIO()
        with (
            mock.patch.dict(sys.modules, {"IPython.display": fake_display_module}),
            redirect_stdout(stdout),
        ):
            output = display_authoring_result(
                "Demo",
                result,
                preview="report",
                include_phase_previews=True,
            )

        self.assertIsNone(output)
        self.assertIn("Plan: desired_state", stdout.getvalue())
        self.assertIn("Defaults provenance:", stdout.getvalue())
        self.assertIn("Request coverage:", stdout.getvalue())
        self.assertIn("Context:", stdout.getvalue())
        self.assertIn("verification=passed", stdout.getvalue())
        self.assertEqual(
            [image.data for image in display_calls],
            [b"phase-report", b"phase-section", b"final-report"],
        )

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
                timeout=None,
            )
            self.assertEqual(session.run_max_rounds, 12)
            self.assertEqual(session.revise_max_rounds, 12)

    def test_create_project_session_uses_openai_compat_env_defaults(self) -> None:
        """Resolve OpenAI-compatible model and base URL defaults from env vars."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            fake_session = mock.Mock(spec=AuthoringSession)
            with (
                mock.patch.dict(
                    os.environ,
                    {
                        "OPENAI_COMPAT_MODEL": "compat-model",
                        "OPENAI_COMPAT_BASE_URL": "https://compat.example.test/v1",
                    },
                    clear=False,
                ),
                mock.patch.object(
                    AuthoringSession,
                    "from_local_mcp",
                    return_value=fake_session,
                ) as factory,
            ):
                session, _ = create_project_session(
                    server_root=repo_root,
                    project_dir="workspace/demo-job",
                    provider="openai_compat",
                )
            self.assertIs(session.authoring_session, fake_session)
            factory.assert_called_once_with(
                provider="openai_compat",
                model="compat-model",
                server_root=repo_root.resolve(),
                api_key=None,
                base_url="https://compat.example.test/v1",
                timeout=None,
            )

    def test_create_project_session_passes_custom_timeout(self) -> None:
        """Forward a larger request timeout to local OpenAI-compatible sessions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            fake_session = mock.Mock(spec=AuthoringSession)
            with mock.patch.object(
                AuthoringSession,
                "from_local_mcp",
                return_value=fake_session,
            ) as factory:
                session, _ = create_project_session(
                    server_root=repo_root,
                    project_dir="workspace/demo-job",
                    provider="openai_compat",
                    model="compat-model",
                    api_key="compat-token",
                    base_url="https://compat.example.test/v1",
                    timeout=1800,
                )

            self.assertIs(session.authoring_session, fake_session)
            factory.assert_called_once_with(
                provider="openai_compat",
                model="compat-model",
                server_root=repo_root.resolve(),
                api_key="compat-token",
                base_url="https://compat.example.test/v1",
                timeout=1800,
            )

    def test_create_project_session_supports_ollama_alias_defaults(self) -> None:
        """Provide a notebook-facing Ollama alias over the OpenAI-compatible backend."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            fake_session = mock.Mock(spec=AuthoringSession)
            with mock.patch.object(
                AuthoringSession,
                "from_local_mcp",
                return_value=fake_session,
            ) as factory:
                session, _ = create_project_session(
                    server_root=repo_root,
                    project_dir="workspace/demo-job",
                    provider="ollama",
                )
            self.assertIs(session.authoring_session, fake_session)
            factory.assert_called_once_with(
                provider="openai_compat",
                model="llama3.2",
                server_root=repo_root.resolve(),
                api_key=None,
                base_url="http://localhost:11434/v1",
                timeout=None,
            )

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

    def test_project_session_exposes_direct_header_value_helpers(self) -> None:
        """Allow notebooks to fill known header values without routing through the LLM loop."""
        authoring_session = mock.Mock(spec=AuthoringSession)
        authoring_session.inspect_heading_slots = mock.AsyncMock(return_value={"has_heading": True})
        authoring_session.preview_header_mapping = mock.AsyncMock(
            return_value={"resolved_assignments": []}
        )
        authoring_session.apply_header_values = mock.AsyncMock(
            return_value={"applied_assignments": []}
        )
        session = ProjectSession(
            authoring_session=authoring_session,
            paths=ProjectPaths.under_root("/tmp/server-root", "workspace/demo-job"),
            draft_logfile="workspace/demo-job/draft.log.yaml",
        )

        inspect_result = anyio.run(session.inspect_heading_slots)
        preview_result = anyio.run(
            partial(
                session.preview_header_mapping,
                values={"rmf": "0.01 @ 25"},
            )
        )
        apply_result = anyio.run(
            partial(
                session.apply_header_values,
                values={"rmf": "0.01 @ 25"},
            )
        )

        self.assertEqual(inspect_result["has_heading"], True)
        self.assertEqual(preview_result["resolved_assignments"], [])
        self.assertEqual(apply_result["applied_assignments"], [])
        authoring_session.inspect_heading_slots.assert_awaited_once_with(
            logfile_path="workspace/demo-job/draft.log.yaml",
        )
        authoring_session.preview_header_mapping.assert_awaited_once_with(
            logfile_path="workspace/demo-job/draft.log.yaml",
            values={"rmf": "0.01 @ 25"},
            overwrite_policy="fill_empty",
        )
        authoring_session.apply_header_values.assert_awaited_once_with(
            logfile_path="workspace/demo-job/draft.log.yaml",
            values={"rmf": "0.01 @ 25"},
            overwrite_policy="fill_empty",
        )

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
            self.assertEqual(
                template_payload["document"]["layout"]["heading"]["detail"]["kind"],
                "open_hole",
            )
            self.assertIn(
                "RMF @ Measured Temp",
                [
                    row["label"]
                    for row in template_payload["document"]["layout"]["heading"]["detail"]["rows"]
                    if isinstance(row, dict) and "label" in row
                ],
            )
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

    def test_project_session_create_starter_supports_cased_hole_quicklook(self) -> None:
        """Allow users to start from the deterministic cased-hole header scaffold too."""
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
                kind="cased_hole_quicklook",
                data_file=data_file,
                title="Main Review",
                subtitle="Starter subtitle",
                depth_range=(8400, 9300),
            )

            template_payload = yaml.safe_load(starter.template_yaml)
            self.assertEqual(
                template_payload["document"]["layout"]["heading"]["detail"]["kind"],
                "cased_hole",
            )
            self.assertEqual(
                template_payload["document"]["layout"]["heading"]["service_titles"][0]["value"],
                "Cased Hole Quicklook",
            )
            general_fields = {
                field["key"]: field
                for field in template_payload["document"]["layout"]["heading"]["general_fields"]
            }
            country = general_fields["country"]
            self.assertEqual(country["aliases"], ["State", "State / Country"])

    def test_project_session_create_starter_supports_combo_seed_track(self) -> None:
        """Allow minimal cased-hole starters to seed one valid combo/depth layout."""
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
                kind="cased_hole_quicklook",
                data_file=data_file,
                title="Main Review",
                subtitle="Starter subtitle",
                depth_range=(8400, 9300),
                seed_tracks=("combo", "depth"),
            )

            logfile_payload = yaml.safe_load(starter.logfile_yaml)
            section = logfile_payload["document"]["layout"]["log_sections"][0]
            self.assertEqual([track["id"] for track in section["tracks"]], ["combo", "depth"])
            self.assertEqual(
                logfile_payload["document"]["bindings"]["channels"],
                [
                    {
                        "channel": "ECGR_STGC",
                        "track_id": "combo",
                        "kind": "curve",
                        "label": "GR",
                        "style": {"color": "#2e7d32"},
                    }
                ],
            )

    def test_project_session_create_starter_rejects_binding_free_seed_track_selection(self) -> None:
        """Reject one starter seed selection that would fail schema validation later."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            data_file = repo_root / "workspace" / "demo-job" / "user_input.las"
            data_file.parent.mkdir(parents=True, exist_ok=True)
            data_file.write_text("~Version Information\nVERS. 2.0\n", encoding="utf-8")
            session = ProjectSession(
                authoring_session=mock.Mock(spec=AuthoringSession),
                paths=ProjectPaths.under_root(repo_root, "workspace/demo-job"),
            )

            with self.assertRaisesRegex(ValueError, "must include at least one bindable track"):
                session.create_starter(
                    kind="cased_hole_quicklook",
                    data_file=data_file,
                    title="Main Review",
                    subtitle="Starter subtitle",
                    seed_tracks=("depth",),
                )

    def test_project_session_bootstrap_starter_stages_data_and_configures_paths(self) -> None:
        """Collapse repeated notebook setup into one generic project bootstrap helper."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            incoming_las = repo_root / "incoming" / "replacement.las"
            incoming_las.parent.mkdir(parents=True, exist_ok=True)
            incoming_las.write_text("~Version Information\nVERS. 2.0\n", encoding="utf-8")
            session = ProjectSession(
                authoring_session=mock.Mock(spec=AuthoringSession),
                paths=ProjectPaths.under_root(repo_root, "workspace/demo-job"),
            )

            starter = session.bootstrap_starter(
                kind="open_hole_quicklook",
                source_data_file=incoming_las,
                staged_data_name="data/user_input.las",
                draft_logfile="drafts/agent_open_hole_draft.log.yaml",
                render_output_path="renders/agent_open_hole_draft.pdf",
                starter_logfile="drafts/agent_starter.log.yaml",
                template_path="drafts/base.template.yaml",
                title="Main Review",
                subtitle="Starter subtitle",
                depth_range=(8400, 9300),
                starter_name="Agent LAS Starter",
            )

            self.assertEqual(starter.data_file, session.paths.path("data", "user_input.las"))
            self.assertTrue(starter.data_file.exists())
            self.assertEqual(
                session.draft_logfile,
                session.paths.path("drafts", "agent_open_hole_draft.log.yaml"),
            )
            self.assertEqual(
                session.render_output_path,
                session.paths.path("renders", "agent_open_hole_draft.pdf"),
            )
            self.assertEqual(
                starter.logfile_path,
                session.paths.path("drafts", "agent_starter.log.yaml"),
            )
            self.assertEqual(
                starter.template_path,
                session.paths.path("drafts", "base.template.yaml"),
            )
            draft = session.create_draft_from_starter(
                source_logfile_path=starter.logfile_path,
                output_logfile_path="drafts/agent_open_hole_draft.log.yaml",
                overwrite=True,
            )
            self.assertEqual(
                draft,
                session.paths.path("drafts", "agent_open_hole_draft.log.yaml"),
            )
            self.assertTrue(draft.exists())
            logfile_payload = yaml.safe_load(starter.logfile_yaml)
            self.assertEqual(
                logfile_payload["render"]["output_path"],
                "../renders/agent_open_hole_draft.pdf",
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
                timeout=1800,
            )

        runtime_factory.assert_called_once_with(server_root="/tmp/openai-root")
        backend_factory.assert_called_once_with(
            model="demo-model",
            server_root=runtime.server_root,
            api_key="demo-token",
            timeout=1800,
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
                timeout=1800,
            )

        runtime_factory.assert_called_once_with(server_root="/tmp/compat-root")
        backend_factory.assert_called_once_with(
            model="demo-model",
            server_root=runtime.server_root,
            api_key="compat-token",
            base_url="http://localhost:11434/v1",
            timeout=1800,
        )
        self.assertIs(session.backend, backend)
        self.assertIs(session.runtime, runtime)

    def test_from_local_mcp_requires_base_url_for_openai_compat(self) -> None:
        """Reject the compatibility provider when no base URL is supplied."""
        with self.assertRaisesRegex(ValueError, "base_url"):
            AuthoringSession.from_local_mcp(provider="openai_compat", model="demo")

    def test_load_openai_client_passes_timeout_to_sdk(self) -> None:
        """Configure the SDK request timeout used by local model gateways."""
        with mock.patch("openai.OpenAI") as openai_client:
            load_openai_client(
                api_key="demo-token",
                base_url="https://compat.example.test/v1",
                timeout=1800,
            )

        openai_client.assert_called_once_with(
            api_key="demo-token",
            base_url="https://compat.example.test/v1",
            timeout=1800,
        )

    def test_load_openai_client_rejects_non_positive_timeout(self) -> None:
        """Reject invalid request timeout values before constructing the client."""
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            load_openai_client(api_key="demo-token", timeout=0)

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
            timeout=None,
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
