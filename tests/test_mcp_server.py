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

"""Server-entry tests for the optional wellplot MCP support."""

from __future__ import annotations

import importlib.util
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

try:
    from tests._mcp_fixtures import REPO_ROOT, McpFixturePaths, create_mcp_fixture_paths
except ModuleNotFoundError:  # pragma: no cover - unittest discovery mode
    from _mcp_fixtures import REPO_ROOT, McpFixturePaths, create_mcp_fixture_paths
from wellplot.agent.tool_contract import stable_tool_profile
from wellplot.errors import DependencyUnavailableError
from wellplot.mcp.server import create_mcp_server, main

MCP_AVAILABLE = importlib.util.find_spec("mcp") is not None
HAS_LAS = importlib.util.find_spec("lasio") is not None


@unittest.skipIf(MCP_AVAILABLE, "optional mcp dependency is installed")
class McpServerDependencyTests(unittest.TestCase):
    """Verify graceful behavior when the optional SDK is unavailable."""

    def test_create_mcp_server_requires_optional_dependency(self) -> None:
        """Raise a dedicated error when the MCP SDK is not installed."""
        with self.assertRaises(DependencyUnavailableError):
            create_mcp_server()

    def test_main_returns_error_when_dependency_is_missing(self) -> None:
        """Return a non-zero exit code with a helpful install hint."""
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            code = main()

        self.assertEqual(code, 1)
        self.assertIn("wellplot[mcp]", stderr.getvalue())


@unittest.skipUnless(MCP_AVAILABLE, "optional mcp dependency is not installed")
@unittest.skipUnless(HAS_LAS, "lasio is not installed")
class McpServerIntegrationTests(unittest.TestCase):
    """Verify the stdio MCP surface against the real SDK."""

    def test_stdio_server_exposes_stable_surface(self) -> None:
        """Start the stdio server and exercise the stable projection."""
        import anyio

        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmpdir:
            anyio.run(
                self._exercise_stdio_server,
                create_mcp_fixture_paths(Path(tmpdir)),
            )

    async def _exercise_stdio_server(self, fixture_paths: McpFixturePaths) -> None:
        import anyio
        from mcp.client.session import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        draft_logfile = fixture_paths.fixture_dir / "drafts" / "stable-draft.log.yaml"
        rendered = fixture_paths.fixture_dir / "stable-render.pdf"
        server = StdioServerParameters(
            command=sys.executable,
            args=["-m", "wellplot.mcp.server"],
            cwd=str(REPO_ROOT),
        )
        async with stdio_client(server) as streams, ClientSession(*streams) as session:
            with anyio.fail_after(15):
                await session.initialize()

            tools = await session.list_tools()
            resources = await session.list_resources()
            prompts = await session.list_prompts()
            templates = await session.list_resource_templates()
            source = await session.call_tool(
                "inspect_source",
                {
                    "source_path": str(fixture_paths.las_path),
                    "source_format": "auto",
                    "channels": ["GR", "RT"],
                },
            )
            created = await session.call_tool(
                "create_draft",
                {
                    "operation": "clone",
                    "logfile_path": str(draft_logfile),
                    "source_logfile_path": fixture_paths.single_logfile_relative,
                    "overwrite": False,
                },
            )
            inspected = await session.call_tool(
                "inspect_authoring",
                {
                    "logfile_path": str(draft_logfile),
                    "object_kind": "section",
                    "detail": "summary",
                },
            )
            section_edit = await session.call_tool(
                "edit_section",
                {
                    "operation": "update",
                    "logfile_path": str(draft_logfile),
                    "section_id": "main",
                    "subtitle": "Stable MCP integration",
                },
            )
            track_edit = await session.call_tool(
                "edit_track",
                {
                    "operation": "add",
                    "logfile_path": str(draft_logfile),
                    "section_id": "main",
                    "track_id": "qc",
                    "title": "QC",
                    "kind": "normal",
                    "width_mm": 24.0,
                },
            )
            binding_edit = await session.call_tool(
                "edit_curve_binding",
                {
                    "operation": "add",
                    "logfile_path": str(draft_logfile),
                    "section_id": "main",
                    "track_id": "qc",
                    "channel": "GR",
                    "binding_id": "qc.gr.1",
                    "label": "Gamma Ray",
                    "style": {"color": "#008000"},
                },
            )
            remarks_edit = await session.call_tool(
                "edit_remarks",
                {
                    "operation": "add",
                    "logfile_path": str(draft_logfile),
                    "remark": {
                        "title": "Stable projection",
                        "lines": ["Created through the deterministic MCP surface."],
                        "alignment": "left",
                    },
                },
            )
            validation = await session.call_tool(
                "validate_logfile",
                {
                    "operation": "validate",
                    "logfile_path": str(draft_logfile),
                },
            )
            preview = await session.call_tool(
                "preview_logfile",
                {
                    "operation": "preview",
                    "logfile_path": str(draft_logfile),
                    "section_id": "main",
                    "page": 0,
                },
            )
            render = await session.call_tool(
                "render_logfile",
                {
                    "operation": "render",
                    "logfile_path": str(draft_logfile),
                    "output_path": str(rendered),
                    "overwrite": False,
                },
            )

            self.assertEqual(
                [tool.name for tool in tools.tools],
                [tool.name for tool in stable_tool_profile()],
            )
            self.assertEqual(
                [str(resource.uri) for resource in resources.resources],
                [
                    "wellplot://schema/logfile.json",
                    "wellplot://examples/production/index.json",
                    "wellplot://authoring/schema/patch.json",
                    "wellplot://authoring/schema/canonical.json",
                    "wellplot://authoring/schema/operations.json",
                    "wellplot://authoring/catalog/hierarchy.json",
                    "wellplot://authoring/catalog/track-kinds.json",
                    "wellplot://authoring/catalog/fill-kinds.json",
                    "wellplot://authoring/catalog/track-archetypes.json",
                    "wellplot://authoring/catalog/header-archetypes.json",
                    "wellplot://authoring/catalog/packet-blueprints.json",
                    "wellplot://authoring/catalog/style-presets.json",
                    "wellplot://authoring/catalog/header-fields.json",
                    "wellplot://authoring/catalog/header-key-aliases.json",
                    "wellplot://authoring/catalog/channel-aliases.json",
                ],
            )
            self.assertEqual(
                [prompt.name for prompt in prompts.prompts],
                [
                    "review_logfile",
                    "preview_logfile",
                    "start_from_example",
                    "author_plot_from_request",
                    "revise_plot_from_feedback",
                    "ingest_header_text",
                ],
            )
            self.assertGreaterEqual(len(templates.resourceTemplates), 1)
            self.assertFalse(source.isError, source.content)
            self.assertFalse(created.isError)
            self.assertFalse(inspected.isError)
            self.assertFalse(section_edit.isError, section_edit.content)
            self.assertFalse(track_edit.isError)
            self.assertFalse(binding_edit.isError)
            self.assertFalse(remarks_edit.isError)
            self.assertFalse(validation.isError)
            self.assertFalse(preview.isError)
            self.assertFalse(render.isError)
            self.assertTrue(draft_logfile.exists())
            self.assertTrue(rendered.exists())


if __name__ == "__main__":
    unittest.main()
