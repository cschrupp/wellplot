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
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

try:
    from tests._mcp_fixtures import REPO_ROOT, McpFixturePaths, create_mcp_fixture_paths
except ModuleNotFoundError:  # pragma: no cover - exercised by unittest discovery mode
    from _mcp_fixtures import REPO_ROOT, McpFixturePaths, create_mcp_fixture_paths
from wellplot.errors import DependencyUnavailableError
from wellplot.mcp.server import create_mcp_server, main

MCP_AVAILABLE = importlib.util.find_spec("mcp") is not None
HAS_LAS = importlib.util.find_spec("lasio") is not None


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
class McpServerIntegrationTests(unittest.TestCase):
    """Verify the stdio MCP surface against the real SDK."""

    def test_stdio_server_exposes_tools_resources_and_prompts(self) -> None:
        """Start the stdio server and exercise its MCP contract."""
        import anyio

        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmpdir:
            anyio.run(
                self._exercise_stdio_server,
                create_mcp_fixture_paths(Path(tmpdir)),
            )

    async def _exercise_stdio_server(self, fixture_paths: McpFixturePaths) -> None:
        from mcp.client.session import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        export_dir = fixture_paths.fixture_dir / "exported-example"
        draft_logfile = fixture_paths.fixture_dir / "drafts" / "single-draft.log.yaml"
        saved_logfile = fixture_paths.fixture_dir / "saved.log.yaml"
        replacement_las = fixture_paths.fixture_dir / "replacement.las"
        replacement_las.write_text(
            fixture_paths.las_path.read_text(encoding="utf-8").replace(
                "MCP FIXTURE-01",
                "MCP REPLACEMENT-01",
            ),
            encoding="utf-8",
        )
        example_template = "examples/production/cbl_log_example/base.template.yaml"
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
            header_prompt = await session.get_prompt(
                "ingest_header_text",
                {
                    "logfile_path": str(draft_logfile),
                    "source_text": "Company: Acme Energy\nWell: Demo-01\nDirection: Up\n",
                    "source_description": "Copied field ticket header packet",
                },
            )
            validation = await session.call_tool(
                "validate_logfile",
                {"logfile_path": fixture_paths.single_logfile_relative},
            )
            source_inspection = await session.call_tool(
                "inspect_data_source",
                {"source_path": str(fixture_paths.las_path)},
            )
            channel_availability = await session.call_tool(
                "check_channel_availability",
                {
                    "requested_channels": ["gamma ray", "RT", "NPHI"],
                    "source_path": str(fixture_paths.las_path),
                },
            )
            cbl_main_inspection = await session.call_tool(
                "inspect_logfile",
                {"logfile_path": fixture_paths.single_logfile_relative},
            )
            section = cbl_main_inspection.structuredContent["sections"][0]
            multi_inspection = await session.call_tool(
                "inspect_logfile",
                {"logfile_path": fixture_paths.multi_logfile_relative},
            )
            multi_section = multi_inspection.structuredContent["sections"][0]
            preview = await session.call_tool(
                "preview_section_png",
                {
                    "logfile_path": fixture_paths.single_logfile_relative,
                    "section_id": section["id"],
                    "dpi": 72,
                },
            )
            preview_track = await session.call_tool(
                "preview_track_png",
                {
                    "logfile_path": fixture_paths.single_logfile_relative,
                    "section_id": section["id"],
                    "track_ids": [section["track_ids"][1]],
                    "dpi": 72,
                },
            )
            preview_window = await session.call_tool(
                "preview_window_png",
                {
                    "logfile_path": fixture_paths.multi_logfile_relative,
                    "depth_range": [
                        multi_section["depth_range"][0],
                        multi_section["depth_range"][0] + 8.0,
                    ],
                    "section_ids": [multi_section["id"]],
                    "dpi": 72,
                },
            )
            text_validation = await session.call_tool(
                "validate_logfile_text",
                {
                    "yaml_text": fixture_paths.single_logfile_text,
                    "base_dir": Path(
                        os.path.relpath(fixture_paths.fixture_dir, start=REPO_ROOT)
                    ).as_posix(),
                },
            )
            formatting = await session.call_tool(
                "format_logfile_text",
                {
                    "yaml_text": fixture_paths.single_logfile_text,
                    "base_dir": Path(
                        os.path.relpath(fixture_paths.fixture_dir, start=REPO_ROOT)
                    ).as_posix(),
                },
            )
            exported = await session.call_tool(
                "export_example_bundle",
                {
                    "example_id": "cbl_log_example",
                    "output_dir": str(export_dir),
                },
            )
            created_draft = await session.call_tool(
                "create_logfile_draft",
                {
                    "output_path": str(draft_logfile),
                    "source_logfile_path": fixture_paths.single_logfile_relative,
                },
            )
            updated_source = await session.call_tool(
                "set_section_data_source",
                {
                    "logfile_path": str(draft_logfile),
                    "section_id": "main",
                    "source_path": str(replacement_las),
                    "subtitle": "Replacement LAS Source",
                },
            )
            previous_draft_text = draft_logfile.read_text(encoding="utf-8")
            draft_summary = await session.call_tool(
                "summarize_logfile_draft",
                {
                    "logfile_path": str(draft_logfile),
                },
            )
            heading_slots = await session.call_tool(
                "inspect_heading_slots",
                {
                    "logfile_path": str(draft_logfile),
                },
            )
            template_heading_slots = await session.call_tool(
                "inspect_heading_slots",
                {
                    "template_path": example_template,
                },
            )
            authoring_vocab = await session.call_tool(
                "inspect_authoring_vocab",
                {
                    "logfile_path": str(draft_logfile),
                },
            )
            template_vocab = await session.call_tool(
                "inspect_authoring_vocab",
                {
                    "template_path": example_template,
                },
            )
            added_track = await session.call_tool(
                "add_track",
                {
                    "logfile_path": str(draft_logfile),
                    "section_id": "main",
                    "id": "porosity",
                    "title": "Porosity",
                    "kind": "normal",
                    "width_mm": 32.0,
                },
            )
            updated_track = await session.call_tool(
                "update_track",
                {
                    "logfile_path": str(draft_logfile),
                    "section_id": "main",
                    "track_id": "porosity",
                    "patch": {
                        "title": "Density / Neutron",
                        "width_mm": 30.0,
                    },
                },
            )
            bound_curve = await session.call_tool(
                "bind_curve",
                {
                    "logfile_path": str(draft_logfile),
                    "section_id": "main",
                    "track_id": "porosity",
                    "channel": "GR",
                    "label": "Gamma",
                    "style": {"color": "#008000"},
                },
            )
            updated_binding = await session.call_tool(
                "update_curve_binding",
                {
                    "logfile_path": str(draft_logfile),
                    "section_id": "main",
                    "track_id": "porosity",
                    "channel": "GR",
                    "patch": {
                        "label": "Gamma Ray",
                        "scale": {
                            "kind": "linear",
                            "min": 0.0,
                            "max": 150.0,
                        },
                    },
                },
            )
            moved_track = await session.call_tool(
                "move_track",
                {
                    "logfile_path": str(draft_logfile),
                    "section_id": "main",
                    "track_id": "porosity",
                    "after_track_id": "depth",
                },
            )
            removed_curve_binding = await session.call_tool(
                "remove_curve_binding",
                {
                    "logfile_path": str(draft_logfile),
                    "section_id": "main",
                    "track_id": "porosity",
                    "channel": "GR",
                },
            )
            removed_track = await session.call_tool(
                "remove_track",
                {
                    "logfile_path": str(draft_logfile),
                    "section_id": "main",
                    "track_id": "porosity",
                },
            )
            updated_heading = await session.call_tool(
                "set_heading_content",
                {
                    "logfile_path": str(draft_logfile),
                    "patch": {
                        "provider_name": "Company",
                        "general_fields": [
                            {
                                "key": "company",
                                "label": "Company",
                                "source_key": "COMP",
                            },
                            {
                                "key": "well",
                                "label": "Well",
                                "source_key": "WELL",
                            },
                            {
                                "key": "service_company",
                                "label": "Service Company",
                                "value": "Legacy Header Service",
                            },
                        ],
                        "service_titles": [
                            {
                                "value": "Legacy Title",
                                "alignment": "left",
                                "bold": True,
                            }
                        ],
                        "detail": {
                            "kind": "open_hole",
                            "rows": [
                                {
                                    "label": "Date",
                                    "values": [{"source_key": "DATE"}, ""],
                                },
                                {
                                    "label_cells": ["Run", "Direction"],
                                    "columns": [
                                        {"cells": [""]},
                                        {"cells": [""]},
                                    ],
                                },
                            ],
                        },
                        "tail_enabled": True,
                    },
                },
            )
            preview_mapping = await session.call_tool(
                "preview_header_mapping",
                {
                    "logfile_path": str(draft_logfile),
                    "values": {
                        "provider": "Acme Logging",
                        "company": "Acme Energy",
                        "well": "Demo-01",
                        "date": "2026-04-30",
                        "run": "ONE",
                        "direction": "Up",
                        "service_title_1": "Gamma Ray Review",
                    },
                },
            )
            applied_header_values = await session.call_tool(
                "apply_header_values",
                {
                    "logfile_path": str(draft_logfile),
                    "values": {
                        "provider": "Acme Logging",
                        "company": "Acme Energy",
                        "well": "Demo-01",
                        "date": "2026-04-30",
                        "run": "ONE",
                        "direction": "Up",
                        "service_title_1": "Gamma Ray Review",
                        "general_field.service_company": "Acme Wireline",
                    },
                    "overwrite_policy": "replace",
                },
            )
            parsed_header_text = await session.call_tool(
                "parse_key_value_text",
                {
                    "source_text": "Company: Acme Energy\nWell: Demo-01\nDirection: Up\n",
                },
            )
            style_presets = await session.call_tool(
                "inspect_style_presets",
                {
                    "preset_family": "cbl_vdl_variants",
                },
            )
            updated_remarks = await session.call_tool(
                "set_remarks_content",
                {
                    "logfile_path": str(draft_logfile),
                    "remarks": [
                        {
                            "title": "Generated Remarks",
                            "lines": ["Synthetic authoring note 1."],
                            "alignment": "center",
                        }
                    ],
                },
            )
            change_summary = await session.call_tool(
                "summarize_logfile_changes",
                {
                    "logfile_path": str(draft_logfile),
                    "previous_text": previous_draft_text,
                },
            )
            updated_draft_summary = await session.call_tool(
                "summarize_logfile_draft",
                {
                    "logfile_path": str(draft_logfile),
                },
            )
            saved = await session.call_tool(
                "save_logfile_text",
                {
                    "yaml_text": fixture_paths.single_logfile_text,
                    "output_path": str(saved_logfile),
                    "base_dir": Path(
                        os.path.relpath(fixture_paths.fixture_dir, start=REPO_ROOT)
                    ).as_posix(),
                },
            )

        self.assertEqual(
            [tool.name for tool in tools.tools],
            [
                "validate_logfile",
                "inspect_logfile",
                "inspect_data_source",
                "check_channel_availability",
                "preview_logfile_png",
                "preview_section_png",
                "preview_track_png",
                "preview_window_png",
                "render_logfile_to_file",
                "export_example_bundle",
                "create_logfile_draft",
                "summarize_logfile_draft",
                "set_section_data_source",
                "add_track",
                "update_track",
                "remove_track",
                "bind_curve",
                "update_curve_binding",
                "remove_curve_binding",
                "move_track",
                "set_heading_content",
                "set_remarks_content",
                "inspect_heading_slots",
                "preview_header_mapping",
                "apply_header_values",
                "parse_key_value_text",
                "inspect_style_presets",
                "inspect_authoring_vocab",
                "summarize_logfile_changes",
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
                "wellplot://authoring/schema/patch.json",
                "wellplot://authoring/catalog/track-kinds.json",
                "wellplot://authoring/catalog/fill-kinds.json",
                "wellplot://authoring/catalog/track-archetypes.json",
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
        self.assertEqual(
            [template.uriTemplate for template in templates.resourceTemplates],
            [
                "wellplot://examples/production/{example_id}/README.md",
                "wellplot://examples/production/{example_id}/base.template.yaml",
                "wellplot://examples/production/{example_id}/full_reconstruction.log.yaml",
                "wellplot://examples/production/{example_id}/data-notes.md",
            ],
        )
        self.assertEqual(len(header_prompt.messages), 1)
        self.assertEqual(header_prompt.messages[0].role, "user")
        self.assertIn(
            "Copied field ticket header packet",
            header_prompt.messages[0].content.text,
        )
        self.assertIn(
            'preview_header_mapping(logfile_path, values, overwrite_policy="fill_empty")',
            header_prompt.messages[0].content.text,
        )
        self.assertEqual(
            validation.structuredContent,
            {
                "valid": True,
                "message": "Valid logfile.",
                "name": "MCP Single Fixture",
                "render_backend": "matplotlib",
                "section_ids": ["main"],
            },
        )
        self.assertEqual(source_inspection.structuredContent["source_format_detected"], "las")
        self.assertEqual(source_inspection.structuredContent["channel_count"], 5)
        self.assertEqual(channel_availability.structuredContent["found_channels"], ["GR", "RT"])
        self.assertEqual(channel_availability.structuredContent["missing_channels"], ["NPHI"])
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
        self.assertEqual(formatting.structuredContent["name"], "MCP Single Fixture")
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
        self.assertEqual(created_draft.structuredContent["output_path"], str(draft_logfile))
        self.assertEqual(created_draft.structuredContent["name"], "MCP Single Fixture")
        self.assertEqual(created_draft.structuredContent["section_ids"], ["main"])
        self.assertEqual(created_draft.structuredContent["seed_kind"], "logfile")
        self.assertEqual(
            created_draft.structuredContent["seed_value"],
            str(fixture_paths.single_logfile),
        )
        self.assertEqual(updated_source.structuredContent["source_path"], str(replacement_las))
        self.assertEqual(updated_source.structuredContent["source_format"], "las")
        self.assertEqual(updated_source.structuredContent["subtitle"], "Replacement LAS Source")
        self.assertEqual(draft_summary.structuredContent["name"], "MCP Single Fixture")
        self.assertEqual(draft_summary.structuredContent["section_count"], 1)
        self.assertEqual(draft_summary.structuredContent["section_ids"], ["main"])
        self.assertTrue(draft_summary.structuredContent["sections"][0]["dataset_loaded"])
        self.assertIn("GR", draft_summary.structuredContent["sections"][0]["available_channels"])
        self.assertEqual(heading_slots.structuredContent["target_kind"], "logfile")
        self.assertTrue(heading_slots.structuredContent["has_heading"])
        self.assertEqual(
            template_heading_slots.structuredContent["target_kind"],
            "template",
        )
        self.assertTrue(template_heading_slots.structuredContent["detail_slots"]["enabled"])
        self.assertIn("reference", authoring_vocab.structuredContent["track_kinds"])
        self.assertEqual(
            authoring_vocab.structuredContent["target_summary"]["target_kind"], "logfile"
        )
        self.assertEqual(
            template_vocab.structuredContent["target_summary"]["target_kind"], "template"
        )
        self.assertEqual(added_track.structuredContent["track_id"], "porosity")
        self.assertEqual(added_track.structuredContent["track_count"], 7)
        self.assertEqual(added_track.structuredContent["track_ids"][-1], "porosity")
        self.assertEqual(updated_track.structuredContent["track"]["title"], "Density / Neutron")
        self.assertEqual(updated_track.structuredContent["track"]["width_mm"], 30.0)
        self.assertEqual(bound_curve.structuredContent["channel"], "GR")
        self.assertEqual(bound_curve.structuredContent["binding_kind"], "curve")
        self.assertEqual(bound_curve.structuredContent["binding_count"], 6)
        self.assertEqual(updated_binding.structuredContent["binding"]["label"], "Gamma Ray")
        self.assertEqual(
            updated_binding.structuredContent["binding"]["scale"]["max"],
            150.0,
        )
        self.assertEqual(
            moved_track.structuredContent["track_ids"],
            ["depth", "porosity", "cbl", "vdl", "gr", "cali", "rt"],
        )
        self.assertEqual(removed_curve_binding.structuredContent["binding_count"], 5)
        self.assertEqual(removed_track.structuredContent["track_count"], 6)
        self.assertEqual(
            removed_track.structuredContent["track_ids"],
            ["depth", "cbl", "vdl", "gr", "cali", "rt"],
        )
        self.assertEqual(
            updated_heading.structuredContent["heading"]["provider_name"],
            "Company",
        )
        self.assertEqual(updated_heading.structuredContent["heading"]["tail_enabled"], True)
        self.assertEqual(updated_heading.structuredContent["has_tail"], True)
        self.assertEqual(
            preview_mapping.structuredContent["resolved_assignments"][0]["target_key"],
            "company",
        )
        self.assertEqual(
            [
                entry["target_key"]
                for entry in preview_mapping.structuredContent["conflicting_values"]
            ],
            ["provider_name", "service_title_1"],
        )
        self.assertEqual(
            preview_mapping.structuredContent["predicted_heading_patch"]["general_fields"][0][
                "value"
            ],
            "Acme Energy",
        )
        self.assertEqual(
            [
                entry["target_key"]
                for entry in applied_header_values.structuredContent["applied_assignments"]
            ],
            [
                "provider_name",
                "company",
                "well",
                "Date",
                "Run",
                "Direction",
                "service_title_1",
                "service_company",
            ],
        )
        self.assertEqual(
            applied_header_values.structuredContent["heading_summary"]["current_values"]["heading"][
                "provider_name"
            ],
            "Acme Logging",
        )
        self.assertEqual(
            applied_header_values.structuredContent["heading_summary"]["current_values"]["heading"][
                "service_titles"
            ][0]["value"],
            "Gamma Ray Review",
        )
        self.assertEqual(parsed_header_text.structuredContent["format_detected"], "colon")
        self.assertEqual(
            [pair["key"] for pair in parsed_header_text.structuredContent["pairs"]],
            ["Company", "Well", "Direction"],
        )
        self.assertEqual(
            style_presets.structuredContent["selected_family"],
            "cbl_vdl_variants",
        )
        self.assertEqual(
            {preset["id"] for preset in style_presets.structuredContent["presets"]},
            {"cbl_vdl_high_contrast", "cbl_vdl_print_safe"},
        )
        self.assertEqual(updated_remarks.structuredContent["remarks_count"], 1)
        self.assertEqual(
            updated_remarks.structuredContent["remarks"][0]["title"],
            "Generated Remarks",
        )
        self.assertTrue(change_summary.structuredContent["changed"])
        self.assertTrue(change_summary.structuredContent["heading_changed"])
        self.assertTrue(change_summary.structuredContent["remarks_changed"])
        self.assertEqual(
            updated_draft_summary.structuredContent["sections"][0]["curve_binding_count"],
            5,
        )
        self.assertEqual(
            updated_draft_summary.structuredContent["sections"][0]["track_ids"][1],
            "cbl",
        )
        self.assertEqual(updated_draft_summary.structuredContent["has_tail"], True)
        self.assertEqual(saved.structuredContent["name"], "MCP Single Fixture")
        self.assertEqual(saved.structuredContent["output_path"], str(saved_logfile))
        self.assertTrue(draft_logfile.exists())
        self.assertTrue(export_dir.exists())
        self.assertTrue(saved_logfile.exists())


if __name__ == "__main__":
    unittest.main()
