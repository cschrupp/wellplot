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

from wellplot.errors import DependencyUnavailableError
from wellplot.mcp.server import create_mcp_server, main

MCP_AVAILABLE = importlib.util.find_spec("mcp") is not None
HAS_LAS = importlib.util.find_spec("lasio") is not None
HAS_DLIS = importlib.util.find_spec("dlisio") is not None
REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_LOGFILE_TEXT = (REPO_ROOT / "examples" / "cbl_main.log.yaml").read_text(encoding="utf-8")
CBL_MAIN_LOGFILE = "examples/cbl_main.log.yaml"
PRODUCTION_LOGFILE = "examples/production/cbl_log_example/full_reconstruction.log.yaml"


@unittest.skipIf(MCP_AVAILABLE, "optional mcp dependency is installed")
class McpServerDependencyTests(unittest.TestCase):
    """Verify the graceful behavior when the optional SDK is unavailable."""

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
@unittest.skipUnless(HAS_DLIS, "dlisio is not installed")
class McpServerIntegrationTests(unittest.TestCase):
    """Verify the stdio MCP surface against the real SDK."""

    def test_stdio_server_exposes_tools_resources_and_prompts(self) -> None:
        """Start the stdio server and exercise its MCP contract."""
        import anyio

        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmpdir:
            anyio.run(self._exercise_stdio_server, Path(tmpdir))

    async def _exercise_stdio_server(self, tmpdir: Path) -> None:
        from mcp.client.session import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        export_dir = tmpdir / "exported-example"
        saved_logfile = tmpdir / "saved.log.yaml"
        server = StdioServerParameters(
            command=sys.executable,
            args=["-m", "wellplot.mcp.server"],
            cwd=str(REPO_ROOT),
        )
        async with stdio_client(server) as streams, ClientSession(*streams) as session:
            await session.initialize()

            tools = await session.list_tools()
            resources = await session.list_resources()
            prompts = await session.list_prompts()
            templates = await session.list_resource_templates()
            validation = await session.call_tool(
                "validate_logfile",
                {"logfile_path": CBL_MAIN_LOGFILE},
            )
            cbl_main_inspection = await session.call_tool(
                "inspect_logfile",
                {"logfile_path": CBL_MAIN_LOGFILE},
            )
            section = cbl_main_inspection.structuredContent["sections"][0]
            preview = await session.call_tool(
                "preview_section_png",
                {
                    "logfile_path": CBL_MAIN_LOGFILE,
                    "section_id": section["id"],
                    "dpi": 72,
                },
            )
            preview_track = await session.call_tool(
                "preview_track_png",
                {
                    "logfile_path": CBL_MAIN_LOGFILE,
                    "section_id": section["id"],
                    "track_ids": [section["track_ids"][1]],
                    "dpi": 72,
                },
            )
            preview_window = await session.call_tool(
                "preview_window_png",
                {
                    "logfile_path": PRODUCTION_LOGFILE,
                    "depth_range": [100.0, 200.0],
                    "section_ids": ["main_pass"],
                    "dpi": 72,
                },
            )
            text_validation = await session.call_tool(
                "validate_logfile_text",
                {
                    "yaml_text": EXAMPLE_LOGFILE_TEXT,
                    "base_dir": "examples",
                },
            )
            formatting = await session.call_tool(
                "format_logfile_text",
                {
                    "yaml_text": EXAMPLE_LOGFILE_TEXT,
                    "base_dir": "examples",
                },
            )
            exported = await session.call_tool(
                "export_example_bundle",
                {
                    "example_id": "cbl_log_example",
                    "output_dir": str(export_dir),
                },
            )
            saved = await session.call_tool(
                "save_logfile_text",
                {
                    "yaml_text": EXAMPLE_LOGFILE_TEXT,
                    "output_path": str(saved_logfile),
                    "base_dir": "examples",
                },
            )

        self.assertEqual(
            [tool.name for tool in tools.tools],
            [
                "validate_logfile",
                "inspect_logfile",
                "preview_logfile_png",
                "preview_section_png",
                "preview_track_png",
                "preview_window_png",
                "render_logfile_to_file",
                "export_example_bundle",
                "validate_logfile_text",
                "format_logfile_text",
                "save_logfile_text",
            ],
        )
        self.assertEqual(
            [str(resource.uri) for resource in resources.resources],
            [
                "wellplot://schema/logfile.json",
                "wellplot://examples/production/index.json",
            ],
        )
        self.assertEqual(
            [prompt.name for prompt in prompts.prompts],
            [
                "review_logfile",
                "preview_logfile",
                "start_from_example",
            ],
        )
        self.assertEqual(
            [template.uriTemplate for template in templates.resourceTemplates],
            [
                "wellplot://examples/production/{example_id}/README.md",
                "wellplot://examples/production/{example_id}/base.template.yaml",
                "wellplot://examples/production/{example_id}/full_reconstruction.log.yaml",
                "wellplot://examples/production/{example_id}/data-notes.md",
            ],
        )
        self.assertEqual(
            validation.structuredContent,
            {
                "valid": True,
                "message": "Valid logfile.",
                "name": "CBL Main Configuration",
                "render_backend": "matplotlib",
                "section_ids": ["main"],
            },
        )
        self.assertEqual(len(preview.content), 1)
        self.assertEqual(preview.content[0].type, "image")
        self.assertEqual(getattr(preview.content[0], "mimeType", None), "image/png")
        self.assertEqual(len(preview_track.content), 1)
        self.assertEqual(preview_track.content[0].type, "image")
        self.assertEqual(getattr(preview_track.content[0], "mimeType", None), "image/png")
        self.assertEqual(len(preview_window.content), 1)
        self.assertEqual(preview_window.content[0].type, "image")
        self.assertEqual(getattr(preview_window.content[0], "mimeType", None), "image/png")
        self.assertEqual(text_validation.structuredContent["valid"], True)
        self.assertEqual(text_validation.structuredContent["section_ids"], ["main"])
        self.assertEqual(formatting.structuredContent["name"], "CBL Main Configuration")
        self.assertIn("version: 1", formatting.structuredContent["yaml_text"])
        self.assertNotIn("\ntemplate:\n", formatting.structuredContent["yaml_text"])
        self.assertEqual(exported.structuredContent["example_id"], "cbl_log_example")
        self.assertEqual(
            [Path(path).name for path in exported.structuredContent["written_files"]],
            [
                "README.md",
                "base.template.yaml",
                "full_reconstruction.log.yaml",
                "data-notes.md",
            ],
        )
        self.assertEqual(saved.structuredContent["name"], "CBL Main Configuration")
        self.assertEqual(saved.structuredContent["output_path"], str(saved_logfile))
        self.assertTrue(export_dir.exists())
        self.assertTrue(saved_logfile.exists())


if __name__ == "__main__":
    unittest.main()
