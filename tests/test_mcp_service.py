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

"""Service-layer tests for the optional wellplot MCP support."""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

import yaml

try:
    from tests._mcp_fixtures import REPO_ROOT, create_mcp_fixture_paths
except ModuleNotFoundError:  # pragma: no cover - exercised by unittest discovery mode
    from _mcp_fixtures import REPO_ROOT, create_mcp_fixture_paths
from wellplot.errors import PathAccessError, TemplateValidationError
from wellplot.mcp import service

HAS_LAS = importlib.util.find_spec("lasio") is not None


class McpServiceTests(unittest.TestCase):
    """Verify the pure-Python MCP service helpers."""

    @classmethod
    def setUpClass(cls) -> None:
        """Create synthetic LAS-backed logfile fixtures once for the test class."""
        super().setUpClass()
        cls._fixture_tmpdir = tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="mcp-service-")
        cls._fixture_paths = create_mcp_fixture_paths(Path(cls._fixture_tmpdir.name))

    @classmethod
    def tearDownClass(cls) -> None:
        """Remove the shared synthetic fixture directory after all tests finish."""
        cls._fixture_tmpdir.cleanup()
        super().tearDownClass()

    def _seed_header_mapping_draft(self, draft_path: Path) -> None:
        """Create one draft with deterministic heading slots for ingestion tests."""
        service.create_logfile_draft(
            str(draft_path),
            source_logfile_path=self._fixture_paths.single_logfile_relative,
            root=REPO_ROOT,
        )
        service.set_heading_content(
            str(draft_path),
            patch={
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
                            "values": [
                                {"source_key": "DATE"},
                                "",
                            ],
                        },
                        {
                            "label_cells": ["Run", "Direction"],
                            "columns": [
                                {"cells": [""]},
                                {"cells": [""]},
                            ],
                        },
                        {
                            "label": "Service Company",
                            "values": ["Legacy Detail Service", ""],
                        },
                    ],
                },
            },
            root=REPO_ROOT,
        )

    @unittest.skipUnless(HAS_LAS, "lasio is not installed")
    def test_validate_logfile_success(self) -> None:
        """Validate a real example logfile under the repository root."""
        result = service.validate_logfile(
            self._fixture_paths.single_logfile_relative,
            root=REPO_ROOT,
        )

        self.assertTrue(result.valid)
        self.assertEqual(result.name, "MCP Single Fixture")
        self.assertEqual(result.render_backend, "matplotlib")
        self.assertEqual(result.section_ids, ["main"])

    def test_validate_logfile_returns_invalid_for_schema_error(self) -> None:
        """Return a structured invalid result for logfile/schema failures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            logfile_path = root / "broken.log.yaml"
            logfile_path.write_text("- not-a-mapping\n", encoding="utf-8")

            result = service.validate_logfile(str(logfile_path), root=root)

        self.assertFalse(result.valid)
        self.assertEqual(result.name, "")
        self.assertEqual(result.render_backend, "")
        self.assertEqual(result.section_ids, [])
        self.assertIn("root must be a mapping", result.message)

    @unittest.skipUnless(HAS_LAS, "lasio is not installed")
    def test_validate_logfile_text_success(self) -> None:
        """Validate unsaved logfile text relative to the provided base directory."""
        result = service.validate_logfile_text(
            self._fixture_paths.single_logfile_text,
            base_dir=self._fixture_paths.fixture_dir.relative_to(REPO_ROOT),
            root=REPO_ROOT,
        )

        self.assertTrue(result.valid)
        self.assertEqual(result.name, "MCP Single Fixture")
        self.assertEqual(result.render_backend, "matplotlib")
        self.assertEqual(result.section_ids, ["main"])

    def test_validate_logfile_text_returns_invalid_for_schema_error(self) -> None:
        """Return a structured invalid result for broken logfile text."""
        result = service.validate_logfile_text(
            "- not-a-mapping\n",
            root=REPO_ROOT,
        )

        self.assertFalse(result.valid)
        self.assertEqual(result.name, "")
        self.assertEqual(result.render_backend, "")
        self.assertEqual(result.section_ids, [])
        self.assertIn("root must be a mapping", result.message)

    def test_validate_logfile_blocks_template_outside_root(self) -> None:
        """Reject template inheritance paths that escape the allowed server root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            outside_template = Path(tempfile.gettempdir()) / "outside-template.log.yaml"
            logfile_path = root / "job.log.yaml"
            logfile_path.write_text(
                "\n".join(
                    [
                        "template:",
                        f"  path: {outside_template}",
                        "version: 1",
                        "name: Escaping template",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaises(PathAccessError):
                service.validate_logfile(str(logfile_path), root=root)

    @unittest.skipUnless(HAS_LAS, "lasio is not installed")
    def test_inspect_data_source_returns_channel_metadata(self) -> None:
        """Inspect one raw LAS source before draft authoring starts."""
        result = service.inspect_data_source(
            str(self._fixture_paths.las_path),
            root=REPO_ROOT,
        )

        self.assertEqual(result.source_path, str(self._fixture_paths.las_path))
        self.assertEqual(result.source_format_detected, "las")
        self.assertEqual(result.dataset_name, "MCP FIXTURE-01")
        self.assertEqual(result.index.depth_unit, "m")
        self.assertEqual(result.index.depth_min, 1000.0)
        self.assertEqual(result.index.depth_max, 1020.0)
        self.assertEqual(result.index.sample_count, 11)
        self.assertTrue(result.index.shared_axis)
        self.assertEqual(result.channel_count, 5)
        self.assertIn("COMP", result.metadata_keys)
        self.assertIn("FLD", result.metadata_keys)
        self.assertIn("WELL", result.metadata_keys)
        self.assertIn("source_path", result.provenance)
        gr_summary = next(channel for channel in result.channels if channel.mnemonic == "GR")
        self.assertEqual(gr_summary.kind, "scalar")
        self.assertEqual(gr_summary.value_shape, [11])
        self.assertEqual(gr_summary.value_unit, "gAPI")
        self.assertEqual(gr_summary.value_min, 70.0)
        self.assertEqual(gr_summary.value_max, 90.0)

    def test_inspect_data_source_blocks_path_outside_root(self) -> None:
        """Reject raw source inspection when the path escapes the server root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with self.assertRaises(PathAccessError):
                service.inspect_data_source("../outside.las", root=root)

    @unittest.skipUnless(HAS_LAS, "lasio is not installed")
    def test_check_channel_availability_from_source_supports_aliases(self) -> None:
        """Resolve exact and alias channel requests against one raw source."""
        result = service.check_channel_availability(
            ["GR", "gamma ray", "NPHI"],
            source_path=str(self._fixture_paths.las_path),
            root=REPO_ROOT,
        )

        self.assertEqual(result.target_kind, "source")
        self.assertEqual(result.source_format_detected, "las")
        self.assertEqual(result.available_channels, ["CBL", "VDL", "GR", "CALI", "RT"])
        self.assertEqual(result.found_channels, ["GR"])
        self.assertEqual(result.missing_channels, ["NPHI"])
        self.assertEqual(result.alias_matches[0]["requested_channel"], "gamma ray")
        self.assertEqual(result.alias_matches[0]["matched_channels"], ["GR"])
        self.assertEqual(result.resolutions[0].status, "exact")
        self.assertEqual(result.resolutions[1].status, "alias")
        self.assertEqual(result.resolutions[2].status, "missing")
        self.assertEqual(result.resolutions[2].canonical_alias_id, "neutron_porosity")

    @unittest.skipUnless(HAS_LAS, "lasio is not installed")
    def test_check_channel_availability_from_logfile_uses_section_dataset(self) -> None:
        """Resolve requested channels through one logfile-backed section dataset."""
        result = service.check_channel_availability(
            ["gamma ray", "RT"],
            logfile_path=self._fixture_paths.single_logfile_relative,
            root=REPO_ROOT,
        )

        self.assertEqual(result.target_kind, "logfile")
        self.assertEqual(result.logfile_path, str(self._fixture_paths.single_logfile))
        self.assertEqual(result.section_id, "main")
        self.assertEqual(result.found_channels, ["GR", "RT"])
        self.assertEqual(result.missing_channels, [])

    def test_check_channel_availability_requires_one_target(self) -> None:
        """Reject missing or conflicting target arguments for channel checks."""
        with self.assertRaises(ValueError):
            service.check_channel_availability(["GR"], root=REPO_ROOT)

        with self.assertRaises(ValueError):
            service.check_channel_availability(
                ["GR"],
                source_path=str(self._fixture_paths.las_path),
                logfile_path=self._fixture_paths.single_logfile_relative,
                root=REPO_ROOT,
            )

    @unittest.skipUnless(HAS_LAS, "lasio is not installed")
    def test_inspect_logfile_returns_multisection_metadata(self) -> None:
        """Inspect a multisection fixture and expose section/source summaries."""
        result = service.inspect_logfile(
            self._fixture_paths.multi_logfile_relative,
            root=REPO_ROOT,
        )

        self.assertEqual(result.name, "MCP Multi Fixture")
        self.assertEqual(result.render_backend, "matplotlib")
        self.assertEqual(result.section_ids, ["main_pass", "repeat_pass"])
        self.assertTrue(result.has_remarks)
        self.assertEqual(len(result.sections), 2)
        self.assertEqual(result.sections[0].id, "main_pass")
        self.assertEqual(result.sections[0].source_path, str(self._fixture_paths.las_path))
        self.assertIn("depth", result.sections[0].track_ids)

    @unittest.skipUnless(HAS_LAS, "lasio is not installed")
    def test_preview_logfile_png_returns_png_bytes(self) -> None:
        """Render a PNG preview from a real logfile path."""
        png_bytes = service.preview_logfile_png(
            self._fixture_paths.single_logfile_relative,
            dpi=96,
            root=REPO_ROOT,
        )

        self.assertTrue(png_bytes.startswith(b"\x89PNG\r\n\x1a\n"))

    @unittest.skipUnless(HAS_LAS, "lasio is not installed")
    def test_preview_section_png_returns_png_bytes(self) -> None:
        """Render a section-scoped PNG preview from a real logfile path."""
        png_bytes = service.preview_section_png(
            self._fixture_paths.single_logfile_relative,
            section_id="main",
            dpi=96,
            root=REPO_ROOT,
        )

        self.assertTrue(png_bytes.startswith(b"\x89PNG\r\n\x1a\n"))

    @unittest.skipUnless(HAS_LAS, "lasio is not installed")
    def test_preview_track_png_returns_png_bytes(self) -> None:
        """Render a track-scoped PNG preview from a real logfile path."""
        inspection = service.inspect_logfile(
            self._fixture_paths.single_logfile_relative,
            root=REPO_ROOT,
        )
        png_bytes = service.preview_track_png(
            self._fixture_paths.single_logfile_relative,
            section_id=inspection.sections[0].id,
            track_ids=[inspection.sections[0].track_ids[1]],
            dpi=96,
            root=REPO_ROOT,
        )

        self.assertTrue(png_bytes.startswith(b"\x89PNG\r\n\x1a\n"))

    @unittest.skipUnless(HAS_LAS, "lasio is not installed")
    def test_preview_window_png_returns_png_bytes(self) -> None:
        """Render a depth-window PNG preview from a real logfile path."""
        inspection = service.inspect_logfile(
            self._fixture_paths.multi_logfile_relative,
            root=REPO_ROOT,
        )
        top_depth = inspection.sections[0].depth_range[0]
        png_bytes = service.preview_window_png(
            self._fixture_paths.multi_logfile_relative,
            depth_range=(top_depth, top_depth + 8.0),
            section_ids=[inspection.sections[0].id],
            dpi=96,
            root=REPO_ROOT,
        )

        self.assertTrue(png_bytes.startswith(b"\x89PNG\r\n\x1a\n"))

    @unittest.skipUnless(HAS_LAS, "lasio is not installed")
    def test_preview_section_png_rejects_unknown_section(self) -> None:
        """Reject explicit section preview requests for missing section ids."""
        with self.assertRaises(TemplateValidationError):
            service.preview_section_png(
                self._fixture_paths.single_logfile_relative,
                section_id="missing",
                root=REPO_ROOT,
            )

    def test_preview_track_png_rejects_empty_track_selection(self) -> None:
        """Reject track-scoped preview requests without track ids."""
        with self.assertRaises(ValueError):
            service.preview_track_png(
                "examples/cbl_main.log.yaml",
                section_id="main",
                track_ids=[],
                root=REPO_ROOT,
            )

    def test_preview_window_png_rejects_zero_height_depth_range(self) -> None:
        """Reject depth-window previews whose interval has no height."""
        with self.assertRaises(ValueError):
            service.preview_window_png(
                "examples/cbl_main.log.yaml",
                depth_range=(100.0, 100.0),
                root=REPO_ROOT,
            )

    @unittest.skipUnless(HAS_LAS, "lasio is not installed")
    def test_render_logfile_to_file_writes_pdf(self) -> None:
        """Render a real logfile to an explicit output file path."""
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmpdir:
            output_path = Path(tmpdir) / "mcp-render.pdf"
            result = service.render_logfile_to_file(
                self._fixture_paths.single_logfile_relative,
                str(output_path),
                root=REPO_ROOT,
            )

            self.assertEqual(result.backend, "matplotlib")
            self.assertEqual(result.output_path, str(output_path))
            self.assertTrue(output_path.exists())
            self.assertGreater(output_path.stat().st_size, 0)

    def test_render_logfile_to_file_rejects_existing_path_without_overwrite(self) -> None:
        """Protect existing files unless overwrite is explicitly enabled."""
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmpdir:
            output_path = Path(tmpdir) / "mcp-render.pdf"
            output_path.write_bytes(b"existing")

            with self.assertRaises(FileExistsError):
                service.render_logfile_to_file(
                    "examples/cbl_main.log.yaml",
                    str(output_path),
                    root=REPO_ROOT,
                )

    def test_export_example_bundle_writes_packaged_files(self) -> None:
        """Export one packaged example bundle into a writable directory."""
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmpdir:
            output_dir = Path(tmpdir) / "example-bundle"
            result = service.export_example_bundle(
                "cbl_log_example",
                str(output_dir),
                root=REPO_ROOT,
            )

            self.assertEqual(result.example_id, "cbl_log_example")
            self.assertEqual(result.output_dir, str(output_dir))
            self.assertEqual(
                [Path(path).name for path in result.written_files],
                list(service.PRODUCTION_EXAMPLE_FILES),
            )
            for filename in service.PRODUCTION_EXAMPLE_FILES:
                self.assertTrue((output_dir / filename).exists())

    def test_export_example_bundle_rejects_existing_target_without_overwrite(self) -> None:
        """Protect example bundle writes unless overwrite is explicitly enabled."""
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmpdir:
            output_dir = Path(tmpdir) / "example-bundle"
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "README.md").write_text("existing\n", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                service.export_example_bundle(
                    "cbl_log_example",
                    str(output_dir),
                    root=REPO_ROOT,
                )

    def test_export_example_bundle_blocks_output_outside_root(self) -> None:
        """Reject example bundle writes that escape the configured server root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with self.assertRaises(PathAccessError):
                service.export_example_bundle(
                    "cbl_log_example",
                    "../outside",
                    root=root,
                )

    def test_create_logfile_draft_requires_exactly_one_seed_source(self) -> None:
        """Reject missing or conflicting draft seed arguments."""
        with self.assertRaises(ValueError):
            service.create_logfile_draft("draft.log.yaml", root=REPO_ROOT)

        with self.assertRaises(ValueError):
            service.create_logfile_draft(
                "draft.log.yaml",
                example_id="cbl_log_example",
                source_logfile_path=self._fixture_paths.single_logfile_relative,
                root=REPO_ROOT,
            )

    def test_create_logfile_draft_clones_existing_logfile(self) -> None:
        """Clone an existing logfile into a rebased normalized authoring draft."""
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmpdir:
            output_path = Path(tmpdir) / "drafts" / "single-draft.log.yaml"
            result = service.create_logfile_draft(
                str(output_path),
                source_logfile_path=self._fixture_paths.single_logfile_relative,
                root=REPO_ROOT,
            )

            self.assertEqual(result.output_path, str(output_path))
            self.assertEqual(result.name, "MCP Single Fixture")
            self.assertEqual(result.section_ids, ["main"])
            self.assertEqual(result.seed_kind, "logfile")
            self.assertEqual(result.seed_value, str(self._fixture_paths.single_logfile))
            self.assertTrue(output_path.exists())

            saved_text = output_path.read_text(encoding="utf-8")
            self.assertIn("version: 1", saved_text)
            self.assertNotIn("\ntemplate:\n", saved_text)
            expected_source_path = Path(
                os.path.relpath(self._fixture_paths.las_path, start=output_path.parent)
            ).as_posix()
            self.assertIn(f"source_path: {expected_source_path}", saved_text)

    def test_create_logfile_draft_from_packaged_example_writes_normalized_yaml(self) -> None:
        """Create one normalized draft logfile directly from a packaged example."""
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmpdir:
            output_path = Path(tmpdir) / "drafts" / "example-draft.log.yaml"
            result = service.create_logfile_draft(
                str(output_path),
                example_id="cbl_log_example",
                root=REPO_ROOT,
            )

            self.assertEqual(result.output_path, str(output_path))
            self.assertEqual(result.seed_kind, "example")
            self.assertEqual(result.seed_value, "cbl_log_example")
            self.assertTrue(output_path.exists())

            saved_text = output_path.read_text(encoding="utf-8")
            self.assertIn("CBL Log Example Full Reconstruction", saved_text)
            self.assertNotIn("\ntemplate:\n", saved_text)

    def test_summarize_logfile_draft_returns_authoring_metadata(self) -> None:
        """Summarize one draft logfile for deterministic authoring planning."""
        result = service.summarize_logfile_draft(
            self._fixture_paths.single_logfile_relative,
            root=REPO_ROOT,
        )

        self.assertEqual(result.name, "MCP Single Fixture")
        self.assertEqual(result.render_backend, "matplotlib")
        self.assertEqual(result.section_count, 1)
        self.assertEqual(result.section_ids, ["main"])
        section = result.sections[0]
        self.assertEqual(section.id, "main")
        self.assertEqual(section.curve_binding_count, 5)
        self.assertEqual(section.raster_binding_count, 0)
        self.assertIn("depth", section.track_ids)
        self.assertIn("gr", section.track_ids)
        if HAS_LAS:
            self.assertTrue(section.dataset_loaded)
            self.assertEqual(section.dataset_message, "")
            self.assertIn("GR", section.available_channels)
        else:
            self.assertFalse(section.dataset_loaded)
            self.assertIn("lasio", section.dataset_message)

    @unittest.skipUnless(HAS_LAS, "lasio is not installed")
    def test_add_track_appends_one_track_to_draft(self) -> None:
        """Append one track to a cloned draft and persist the updated order."""
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmpdir:
            draft_path = Path(tmpdir) / "draft.log.yaml"
            service.create_logfile_draft(
                str(draft_path),
                source_logfile_path=self._fixture_paths.single_logfile_relative,
                root=REPO_ROOT,
            )

            result = service.add_track(
                str(draft_path),
                section_id="main",
                id="porosity",
                title="Porosity",
                kind="normal",
                width_mm=32.0,
                root=REPO_ROOT,
            )

            self.assertEqual(result.logfile_path, str(draft_path))
            self.assertEqual(result.section_id, "main")
            self.assertEqual(result.track_id, "porosity")
            self.assertEqual(result.track_ids[-1], "porosity")
            self.assertEqual(result.track_count, 7)

            saved_mapping = yaml.safe_load(draft_path.read_text(encoding="utf-8"))
            tracks = saved_mapping["document"]["layout"]["log_sections"][0]["tracks"]
            self.assertEqual(tracks[-1]["id"], "porosity")
            self.assertEqual(tracks[-1]["position"], 7)

    @unittest.skipUnless(HAS_LAS, "lasio is not installed")
    def test_add_track_rejects_duplicate_track_id(self) -> None:
        """Reject duplicate track identifiers inside one draft section."""
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmpdir:
            draft_path = Path(tmpdir) / "draft.log.yaml"
            service.create_logfile_draft(
                str(draft_path),
                source_logfile_path=self._fixture_paths.single_logfile_relative,
                root=REPO_ROOT,
            )

            with self.assertRaises(TemplateValidationError):
                service.add_track(
                    str(draft_path),
                    section_id="main",
                    id="gr",
                    title="Duplicate GR",
                    kind="normal",
                    width_mm=24.0,
                    root=REPO_ROOT,
                )

    @unittest.skipUnless(HAS_LAS, "lasio is not installed")
    def test_bind_curve_adds_section_scoped_binding(self) -> None:
        """Add one curve binding to a draft track and persist the result."""
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmpdir:
            draft_path = Path(tmpdir) / "draft.log.yaml"
            service.create_logfile_draft(
                str(draft_path),
                source_logfile_path=self._fixture_paths.single_logfile_relative,
                root=REPO_ROOT,
            )
            service.add_track(
                str(draft_path),
                section_id="main",
                id="porosity",
                title="Porosity",
                kind="normal",
                width_mm=32.0,
                root=REPO_ROOT,
            )

            result = service.bind_curve(
                str(draft_path),
                section_id="main",
                track_id="porosity",
                channel="GR",
                label="Gamma",
                style={"color": "#008000"},
                root=REPO_ROOT,
            )

            self.assertEqual(result.logfile_path, str(draft_path))
            self.assertEqual(result.section_id, "main")
            self.assertEqual(result.track_id, "porosity")
            self.assertEqual(result.channel, "GR")
            self.assertEqual(result.binding_kind, "curve")
            self.assertEqual(result.binding_count, 6)

            saved_mapping = yaml.safe_load(draft_path.read_text(encoding="utf-8"))
            bindings = saved_mapping["document"]["bindings"]["channels"]
            matching = [
                binding
                for binding in bindings
                if binding.get("section") == "main"
                and binding.get("track_id") == "porosity"
                and binding.get("channel") == "GR"
            ]
            self.assertEqual(len(matching), 1)
            self.assertEqual(matching[0]["label"], "Gamma")
            self.assertEqual(matching[0]["style"]["color"], "#008000")

    @unittest.skipUnless(HAS_LAS, "lasio is not installed")
    def test_update_curve_binding_merges_patch_and_persists(self) -> None:
        """Patch one existing curve binding and persist the normalized result."""
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmpdir:
            draft_path = Path(tmpdir) / "draft.log.yaml"
            service.create_logfile_draft(
                str(draft_path),
                source_logfile_path=self._fixture_paths.single_logfile_relative,
                root=REPO_ROOT,
            )

            result = service.update_curve_binding(
                str(draft_path),
                section_id="main",
                track_id="gr",
                channel="GR",
                patch={
                    "label": "Gamma Ray",
                    "style": {
                        "color": "#00aa00",
                        "line_width": 1.6,
                    },
                    "scale": {
                        "kind": "linear",
                        "min": 0.0,
                        "max": 150.0,
                    },
                },
                root=REPO_ROOT,
            )

            self.assertEqual(result.logfile_path, str(draft_path))
            self.assertEqual(result.section_id, "main")
            self.assertEqual(result.track_id, "gr")
            self.assertEqual(result.channel, "GR")
            self.assertEqual(result.binding["label"], "Gamma Ray")
            self.assertEqual(result.binding["style"]["color"], "#00aa00")
            self.assertEqual(result.binding["scale"]["max"], 150.0)

            saved_mapping = yaml.safe_load(draft_path.read_text(encoding="utf-8"))
            bindings = saved_mapping["document"]["bindings"]["channels"]
            matching = [
                binding
                for binding in bindings
                if binding.get("track_id") == "gr" and binding.get("channel") == "GR"
            ]
            self.assertEqual(len(matching), 1)
            self.assertEqual(matching[0]["label"], "Gamma Ray")
            self.assertEqual(matching[0]["style"]["line_width"], 1.6)
            self.assertEqual(matching[0]["scale"]["max"], 150.0)

    @unittest.skipUnless(HAS_LAS, "lasio is not installed")
    def test_update_curve_binding_rejects_unknown_patch_key(self) -> None:
        """Reject curve-binding patches outside the supported editable surface."""
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmpdir:
            draft_path = Path(tmpdir) / "draft.log.yaml"
            service.create_logfile_draft(
                str(draft_path),
                source_logfile_path=self._fixture_paths.single_logfile_relative,
                root=REPO_ROOT,
            )

            with self.assertRaises(TemplateValidationError):
                service.update_curve_binding(
                    str(draft_path),
                    section_id="main",
                    track_id="gr",
                    channel="GR",
                    patch={"unsupported": True},
                    root=REPO_ROOT,
                )

    def test_move_track_requires_exactly_one_target_selector(self) -> None:
        """Reject ambiguous track-move requests before draft mutation starts."""
        with self.assertRaises(ValueError):
            service.move_track(
                "draft.log.yaml",
                section_id="main",
                track_id="gr",
                before_track_id="depth",
                position=1,
                root=REPO_ROOT,
            )

    @unittest.skipUnless(HAS_LAS, "lasio is not installed")
    def test_move_track_reorders_tracks_and_positions(self) -> None:
        """Move one track inside a draft and persist the normalized order."""
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmpdir:
            draft_path = Path(tmpdir) / "draft.log.yaml"
            service.create_logfile_draft(
                str(draft_path),
                source_logfile_path=self._fixture_paths.single_logfile_relative,
                root=REPO_ROOT,
            )
            service.add_track(
                str(draft_path),
                section_id="main",
                id="porosity",
                title="Porosity",
                kind="normal",
                width_mm=32.0,
                root=REPO_ROOT,
            )

            result = service.move_track(
                str(draft_path),
                section_id="main",
                track_id="porosity",
                after_track_id="depth",
                root=REPO_ROOT,
            )

            self.assertEqual(result.logfile_path, str(draft_path))
            self.assertEqual(result.section_id, "main")
            self.assertEqual(result.track_id, "porosity")
            self.assertEqual(
                result.track_ids,
                ["depth", "porosity", "cbl", "vdl", "gr", "cali", "rt"],
            )
            self.assertEqual(result.track_count, 7)

            saved_mapping = yaml.safe_load(draft_path.read_text(encoding="utf-8"))
            tracks = saved_mapping["document"]["layout"]["log_sections"][0]["tracks"]
            self.assertEqual(
                [track["id"] for track in tracks],
                ["depth", "porosity", "cbl", "vdl", "gr", "cali", "rt"],
            )
            self.assertEqual(
                [track["position"] for track in tracks],
                [1, 2, 3, 4, 5, 6, 7],
            )

    def test_set_heading_content_rejects_unknown_patch_key(self) -> None:
        """Reject heading patches outside the supported editable surface."""
        with self.assertRaises(TemplateValidationError):
            service.set_heading_content(
                "draft.log.yaml",
                patch={"unsupported": True},
                root=REPO_ROOT,
            )

    @unittest.skipUnless(HAS_LAS, "lasio is not installed")
    def test_set_heading_content_persists_heading_and_tail_toggle(self) -> None:
        """Patch heading content and materialize the tail toggle on save."""
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmpdir:
            draft_path = Path(tmpdir) / "draft.log.yaml"
            service.create_logfile_draft(
                str(draft_path),
                source_logfile_path=self._fixture_paths.single_logfile_relative,
                root=REPO_ROOT,
            )

            result = service.set_heading_content(
                str(draft_path),
                patch={
                    "provider_name": "Acme Logging",
                    "general_fields": [
                        {
                            "key": "well",
                            "label": "Well",
                            "value": "MCP FIXTURE-01",
                        }
                    ],
                    "service_titles": [
                        {
                            "value": "Gamma Ray",
                            "alignment": "left",
                            "bold": True,
                        }
                    ],
                    "detail": {
                        "kind": "open_hole",
                        "rows": [
                            {
                                "label": "Logged Depth",
                                "values": ["1000 m", "1020 m"],
                            }
                        ],
                    },
                    "tail_enabled": True,
                },
                root=REPO_ROOT,
            )

            self.assertEqual(result.logfile_path, str(draft_path))
            self.assertTrue(result.has_heading)
            self.assertTrue(result.has_tail)
            self.assertEqual(result.heading["enabled"], True)
            self.assertEqual(result.heading["provider_name"], "Acme Logging")
            self.assertEqual(result.heading["general_fields"][0]["key"], "well")
            self.assertEqual(result.heading["service_titles"][0]["value"], "Gamma Ray")
            self.assertEqual(result.heading["detail"]["kind"], "open_hole")
            self.assertEqual(result.heading["tail_enabled"], True)

            saved_mapping = yaml.safe_load(draft_path.read_text(encoding="utf-8"))
            layout = saved_mapping["document"]["layout"]
            self.assertEqual(layout["heading"]["provider_name"], "Acme Logging")
            self.assertEqual(layout["heading"]["general_fields"][0]["value"], "MCP FIXTURE-01")
            self.assertEqual(layout["heading"]["service_titles"][0]["value"], "Gamma Ray")
            self.assertEqual(layout["heading"]["detail"]["kind"], "open_hole")
            self.assertEqual(layout["heading"]["tail_enabled"], True)
            self.assertEqual(layout["tail"]["enabled"], True)

    @unittest.skipUnless(HAS_LAS, "lasio is not installed")
    def test_set_remarks_content_replaces_remarks(self) -> None:
        """Replace the first-page remarks block and persist the new content."""
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmpdir:
            draft_path = Path(tmpdir) / "draft.log.yaml"
            service.create_logfile_draft(
                str(draft_path),
                source_logfile_path=self._fixture_paths.single_logfile_relative,
                root=REPO_ROOT,
            )

            result = service.set_remarks_content(
                str(draft_path),
                remarks=[
                    {
                        "title": "Generated Remarks",
                        "lines": [
                            "Synthetic authoring note 1.",
                            "Synthetic authoring note 2.",
                        ],
                        "alignment": "center",
                    }
                ],
                root=REPO_ROOT,
            )

            self.assertEqual(result.logfile_path, str(draft_path))
            self.assertEqual(result.remarks_count, 1)
            self.assertEqual(result.remarks[0]["title"], "Generated Remarks")
            self.assertEqual(result.remarks[0]["alignment"], "center")

            saved_mapping = yaml.safe_load(draft_path.read_text(encoding="utf-8"))
            remarks = saved_mapping["document"]["layout"]["remarks"]
            self.assertEqual(len(remarks), 1)
            self.assertEqual(remarks[0]["title"], "Generated Remarks")
            self.assertEqual(
                remarks[0]["lines"],
                ["Synthetic authoring note 1.", "Synthetic authoring note 2."],
            )

    @unittest.skipUnless(HAS_LAS, "lasio is not installed")
    def test_inspect_heading_slots_with_logfile_exposes_precise_slots(self) -> None:
        """Expose provider, field, detail, and remarks slots for one draft/logfile target."""
        result = service.inspect_heading_slots(
            logfile_path=self._fixture_paths.single_logfile_relative,
            root=REPO_ROOT,
        )

        self.assertEqual(result.target_kind, "logfile")
        self.assertEqual(result.target_path, str(self._fixture_paths.single_logfile))
        self.assertTrue(result.has_heading)
        self.assertTrue(result.has_remarks)
        self.assertTrue(result.has_tail)
        self.assertEqual(result.provider_slots[0]["key"], "provider_name")
        self.assertEqual(result.general_field_slots, [])
        self.assertEqual(result.service_title_slots, [])
        self.assertFalse(result.detail_slots["enabled"])
        self.assertEqual(result.remarks_capabilities["existing_block_count"], 1)
        self.assertIn("heading", result.current_values)
        self.assertIn("wellplot://authoring/catalog/header-fields.json", result.resource_uris)
        self.assertIn(
            "wellplot://authoring/catalog/header-key-aliases.json",
            result.resource_uris,
        )

    def test_inspect_heading_slots_with_template_exposes_dataset_backed_fields(self) -> None:
        """Expose source-key backed report slots from one packaged template."""
        result = service.inspect_heading_slots(
            template_path="examples/production/forge16b_porosity_example/base.template.yaml",
            root=REPO_ROOT,
        )

        self.assertEqual(result.target_kind, "template")
        self.assertTrue(result.has_heading)
        self.assertTrue(result.has_remarks)
        self.assertTrue(result.has_tail)
        self.assertEqual(result.provider_slots[0]["current_value"], "Company")
        self.assertEqual(result.general_field_slots[0]["key"], "company")
        self.assertEqual(
            result.general_field_slots[0]["value_slot"]["source_key"],
            "COMP",
        )
        self.assertEqual(result.service_title_slots[0]["value_slot"]["value"], "Open Hole Density")
        self.assertEqual(result.detail_slots["kind"], "open_hole")
        self.assertGreater(result.detail_slots["row_count"], 0)
        self.assertEqual(
            result.detail_slots["rows"][0]["column_slots"][0][0]["source_key"],
            "DATE",
        )

    def test_inspect_heading_slots_rejects_conflicting_targets(self) -> None:
        """Reject simultaneous logfile and template targets."""
        with self.assertRaises(ValueError):
            service.inspect_heading_slots(
                logfile_path=self._fixture_paths.single_logfile_relative,
                template_path="examples/production/forge16b_porosity_example/base.template.yaml",
                root=REPO_ROOT,
            )

    @unittest.skipUnless(HAS_LAS, "lasio is not installed")
    def test_preview_header_mapping_resolves_fillable_heading_slots(self) -> None:
        """Dry-run provider, field, detail, and explicit title assignments."""
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmpdir:
            draft_path = Path(tmpdir) / "draft.log.yaml"
            self._seed_header_mapping_draft(draft_path)

            result = service.preview_header_mapping(
                str(draft_path),
                values={
                    "provider": "Acme Logging",
                    "company": "Acme Energy",
                    "well": "Demo-01",
                    "date": "2026-04-30",
                    "run": "ONE",
                    "direction": "Up",
                    "service_title_1": "Gamma Ray Review",
                    "unknown_header_key": "ignored",
                },
                root=REPO_ROOT,
            )

            self.assertEqual(result.logfile_path, str(draft_path))
            self.assertEqual(result.overwrite_policy, "fill_empty")
            self.assertEqual(
                [entry["target_key"] for entry in result.resolved_assignments],
                ["company", "well", "Date", "Run", "Direction"],
            )
            self.assertEqual(
                result.unmatched_values,
                [
                    {
                        "input_key": "unknown_header_key",
                        "input_value": "ignored",
                    }
                ],
            )
            self.assertEqual(
                [entry["target_key"] for entry in result.conflicting_values],
                ["provider_name", "service_title_1"],
            )
            self.assertEqual(
                result.predicted_heading_patch["general_fields"][0]["value"],
                "Acme Energy",
            )
            self.assertNotIn(
                "source_key",
                result.predicted_heading_patch["general_fields"][0],
            )
            self.assertEqual(
                result.predicted_heading_patch["detail"]["rows"][0]["values"][0],
                "2026-04-30",
            )
            self.assertEqual(
                result.predicted_heading_patch["detail"]["rows"][1]["columns"][0]["cells"][0],
                "ONE",
            )
            self.assertEqual(
                result.predicted_heading_patch["detail"]["rows"][1]["columns"][1]["cells"][0],
                "Up",
            )

    @unittest.skipUnless(HAS_LAS, "lasio is not installed")
    def test_preview_header_mapping_reports_ambiguous_matches(self) -> None:
        """Report ambiguous human-readable keys instead of guessing one slot."""
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmpdir:
            draft_path = Path(tmpdir) / "draft.log.yaml"
            self._seed_header_mapping_draft(draft_path)

            result = service.preview_header_mapping(
                str(draft_path),
                values={"service company": "Acme Wireline"},
                root=REPO_ROOT,
            )

            self.assertEqual(result.resolved_assignments, [])
            self.assertEqual(result.unmatched_values, [])
            self.assertEqual(len(result.conflicting_values), 1)
            self.assertEqual(
                result.conflicting_values[0]["reason"],
                "Ambiguous header key. Use an explicit prefixed key.",
            )
            self.assertEqual(
                {
                    candidate["target_kind"]
                    for candidate in result.conflicting_values[0]["candidate_targets"]
                },
                {"general_field", "detail_field"},
            )
            self.assertEqual(result.predicted_heading_patch, {})

    @unittest.skipUnless(HAS_LAS, "lasio is not installed")
    def test_preview_header_mapping_replace_overwrites_literal_values(self) -> None:
        """Allow explicit literal replacement when overwrite_policy requests it."""
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmpdir:
            draft_path = Path(tmpdir) / "draft.log.yaml"
            self._seed_header_mapping_draft(draft_path)

            result = service.preview_header_mapping(
                str(draft_path),
                values={
                    "service_title_1": "Gamma Ray Review",
                    "general_field.service_company": "Acme Wireline",
                },
                overwrite_policy="replace",
                root=REPO_ROOT,
            )

            self.assertEqual(len(result.conflicting_values), 0)
            self.assertEqual(
                [entry["action"] for entry in result.resolved_assignments],
                ["replace", "replace"],
            )
            self.assertEqual(
                result.predicted_heading_patch["service_titles"][0]["value"],
                "Gamma Ray Review",
            )
            self.assertEqual(
                result.predicted_heading_patch["general_fields"][2]["value"],
                "Acme Wireline",
            )

    def test_inspect_authoring_vocab_returns_static_catalogs(self) -> None:
        """Expose stable authoring vocabularies even without a target draft."""
        result = service.inspect_authoring_vocab(root=REPO_ROOT)

        self.assertIn("reference", result.track_kinds)
        self.assertIn("normal", result.track_kinds)
        self.assertIn("array", result.track_kinds)
        self.assertIn("annotation", result.track_kinds)
        self.assertIn("linear", result.scale_kinds)
        self.assertIn("log", result.scale_kinds)
        self.assertIn("between_curves", result.curve_fill_kinds)
        self.assertIn("open_hole", result.report_detail_kinds)
        self.assertIn("title", result.track_header_object_kinds)
        self.assertIn("provider_name", result.heading_patch_keys)
        self.assertIn("fill", result.curve_binding_patch_keys)
        self.assertIn("after_track_id", result.move_track_selectors)
        self.assertTrue(result.track_archetypes)
        self.assertIn(
            "wellplot://authoring/catalog/track-archetypes.json",
            result.resource_uris,
        )
        self.assertIn(
            "wellplot://authoring/catalog/header-key-aliases.json",
            result.resource_uris,
        )
        self.assertIn(
            "wellplot://authoring/catalog/channel-aliases.json",
            result.resource_uris,
        )
        self.assertIsNone(result.target_summary)

    @unittest.skipUnless(HAS_LAS, "lasio is not installed")
    def test_inspect_authoring_vocab_with_logfile_exposes_target_context(self) -> None:
        """Expose section, track, and channel context for one draft logfile."""
        result = service.inspect_authoring_vocab(
            logfile_path=self._fixture_paths.single_logfile_relative,
            root=REPO_ROOT,
        )

        self.assertEqual(result.target_summary["target_kind"], "logfile")
        self.assertEqual(result.target_summary["section_ids"], ["main"])
        self.assertIn("gr", result.target_summary["track_ids_by_section"]["main"])
        self.assertIn("GR", result.target_summary["available_channels_by_section"]["main"])

    def test_inspect_authoring_vocab_with_template_exposes_heading_context(self) -> None:
        """Expose heading-field expectations from one packaged example template."""
        result = service.inspect_authoring_vocab(
            template_path="examples/production/cbl_log_example/base.template.yaml",
            root=REPO_ROOT,
        )

        self.assertEqual(result.target_summary["target_kind"], "template")
        self.assertTrue(result.target_summary["has_heading"])
        self.assertIn("company", result.target_summary["heading_general_field_keys"])

    def test_summarize_logfile_changes_without_previous_text_returns_hint(self) -> None:
        """Explain how to use change summaries when no prior snapshot is provided."""
        result = service.summarize_logfile_changes(
            self._fixture_paths.single_logfile_relative,
            root=REPO_ROOT,
        )

        self.assertFalse(result.changed)
        self.assertEqual(result.section_ids, ["main"])
        self.assertIn("No previous_text snapshot", result.message)
        self.assertEqual(len(result.summary_lines), 1)

    @unittest.skipUnless(HAS_LAS, "lasio is not installed")
    def test_summarize_logfile_changes_detects_authoring_edits(self) -> None:
        """Summarize reordered tracks, binding edits, and report-text changes."""
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmpdir:
            draft_path = Path(tmpdir) / "draft.log.yaml"
            service.create_logfile_draft(
                str(draft_path),
                source_logfile_path=self._fixture_paths.single_logfile_relative,
                root=REPO_ROOT,
            )
            previous_text = draft_path.read_text(encoding="utf-8")

            service.add_track(
                str(draft_path),
                section_id="main",
                id="porosity",
                title="Porosity",
                kind="normal",
                width_mm=32.0,
                root=REPO_ROOT,
            )
            service.bind_curve(
                str(draft_path),
                section_id="main",
                track_id="porosity",
                channel="GR",
                label="Gamma",
                root=REPO_ROOT,
            )
            service.update_curve_binding(
                str(draft_path),
                section_id="main",
                track_id="gr",
                channel="GR",
                patch={"label": "Gamma Ray"},
                root=REPO_ROOT,
            )
            service.move_track(
                str(draft_path),
                section_id="main",
                track_id="gr",
                after_track_id="depth",
                root=REPO_ROOT,
            )
            service.set_heading_content(
                str(draft_path),
                patch={"provider_name": "Acme Logging", "tail_enabled": True},
                root=REPO_ROOT,
            )
            service.set_remarks_content(
                str(draft_path),
                remarks=[
                    {
                        "title": "Generated Remarks",
                        "lines": ["Synthetic authoring note 1."],
                        "alignment": "center",
                    }
                ],
                root=REPO_ROOT,
            )

            result = service.summarize_logfile_changes(
                str(draft_path),
                previous_text=previous_text,
                root=REPO_ROOT,
            )

            self.assertTrue(result.changed)
            self.assertEqual(result.added_tracks_by_section["main"], ["porosity"])
            self.assertEqual(result.reordered_tracks_by_section["main"], ["gr"])
            self.assertEqual(result.added_curve_bindings[0]["track_id"], "porosity")
            self.assertEqual(result.updated_curve_bindings[0]["track_id"], "gr")
            self.assertTrue(result.heading_changed)
            self.assertTrue(result.remarks_changed)
            self.assertTrue(
                any(line == "Heading content changed." for line in result.summary_lines)
            )

    @unittest.skipUnless(HAS_LAS, "lasio is not installed")
    def test_format_logfile_text_returns_normalized_yaml(self) -> None:
        """Return canonical logfile YAML text through the serializer path."""
        result = service.format_logfile_text(
            self._fixture_paths.single_logfile_text,
            base_dir=self._fixture_paths.fixture_dir.relative_to(REPO_ROOT),
            root=REPO_ROOT,
        )

        self.assertEqual(result.name, "MCP Single Fixture")
        self.assertEqual(result.render_backend, "matplotlib")
        self.assertEqual(result.section_ids, ["main"])
        self.assertIn("version: 1", result.yaml_text)
        self.assertIn("render:", result.yaml_text)
        self.assertNotIn("\ntemplate:\n", result.yaml_text)

    @unittest.skipUnless(HAS_LAS, "lasio is not installed")
    def test_save_logfile_text_writes_rebased_normalized_yaml(self) -> None:
        """Write normalized logfile YAML that still validates from the new location."""
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmpdir:
            output_path = Path(tmpdir) / "saved" / "normalized.log.yaml"
            result = service.save_logfile_text(
                self._fixture_paths.single_logfile_text,
                str(output_path),
                base_dir=self._fixture_paths.fixture_dir.relative_to(REPO_ROOT),
                root=REPO_ROOT,
            )

            self.assertEqual(result.name, "MCP Single Fixture")
            self.assertEqual(result.output_path, str(output_path))
            self.assertTrue(output_path.exists())
            saved_text = output_path.read_text(encoding="utf-8")
            self.assertIn("version: 1", saved_text)
            self.assertNotIn("\ntemplate:\n", saved_text)
            validated = service.validate_logfile(str(output_path), root=REPO_ROOT)
            self.assertTrue(validated.valid)

    def test_save_logfile_text_rejects_existing_path_without_overwrite(self) -> None:
        """Protect saved logfile writes unless overwrite is explicitly enabled."""
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmpdir:
            output_path = Path(tmpdir) / "normalized.log.yaml"
            output_path.write_text("existing\n", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                service.save_logfile_text(
                    self._fixture_paths.single_logfile_text,
                    str(output_path),
                    base_dir=self._fixture_paths.fixture_dir.relative_to(REPO_ROOT),
                    root=REPO_ROOT,
                )

    def test_schema_resource_is_json(self) -> None:
        """Expose the packaged schema resource as JSON text."""
        resource = service.schema_resource()
        payload = json.loads(resource.text)

        self.assertEqual(resource.mime_type, "application/json")
        self.assertIsInstance(payload, dict)
        self.assertIn("$schema", payload)

    def test_production_example_manifest_lists_examples(self) -> None:
        """Expose the packaged production example manifest."""
        resource = service.production_example_manifest_resource()
        payload = json.loads(resource.text)

        self.assertEqual(resource.mime_type, "application/json")
        example_ids = [item["id"] for item in payload["examples"]]
        self.assertEqual(example_ids, list(service.PRODUCTION_EXAMPLE_IDS))

    def test_production_example_resource_returns_packaged_text(self) -> None:
        """Load packaged example assets through the resource helper."""
        resource = service.production_example_resource("cbl_log_example", "README.md")

        self.assertEqual(resource.mime_type, "text/markdown")
        self.assertIn("CBL/VDL Reconstruction Example", resource.text)

    def test_authoring_catalog_resources_are_json(self) -> None:
        """Expose authoring catalog resources as JSON payloads."""
        patch_resource = service.authoring_patch_schema_resource()
        fill_resource = service.authoring_fill_kinds_resource()
        header_resource = service.authoring_header_fields_resource()
        header_alias_resource = service.authoring_header_key_aliases_resource()
        channel_alias_resource = service.authoring_channel_aliases_resource()

        self.assertEqual(patch_resource.mime_type, "application/json")
        self.assertIn("heading_patch_keys", json.loads(patch_resource.text))
        self.assertEqual(fill_resource.mime_type, "application/json")
        self.assertIn("curve_fill_kinds", json.loads(fill_resource.text))
        self.assertEqual(header_resource.mime_type, "application/json")
        self.assertIn("general_field_keys", json.loads(header_resource.text))
        self.assertEqual(header_alias_resource.mime_type, "application/json")
        self.assertIn("provider_aliases", json.loads(header_alias_resource.text))
        self.assertEqual(channel_alias_resource.mime_type, "application/json")
        self.assertIn("channel_aliases", json.loads(channel_alias_resource.text))

    def test_start_from_example_prompt_embeds_goal_and_example(self) -> None:
        """Embed the requested goal and packaged example resources in the prompt."""
        prompt = service.start_from_example_prompt(
            "forge16b_porosity_example",
            "Create a variant with simplified headers.",
        )

        self.assertIn("Create a variant with simplified headers.", prompt)
        self.assertIn("base.template.yaml", prompt)
        self.assertIn("full_reconstruction.log.yaml", prompt)

    def test_author_plot_from_request_prompt_mentions_authoring_tools(self) -> None:
        """Guide clients toward deterministic authoring tools for freeform requests."""
        prompt = service.author_plot_from_request_prompt(
            "Add a porosity track and simplify the header.",
            logfile_path="drafts/demo.log.yaml",
            example_id="forge16b_porosity_example",
        )

        self.assertIn("summarize_logfile_draft(logfile_path)", prompt)
        self.assertIn("inspect_data_source(source_path)", prompt)
        self.assertIn("check_channel_availability(...)", prompt)
        self.assertIn("inspect_authoring_vocab(...)", prompt)
        self.assertIn("summarize_logfile_changes(logfile_path, previous_text=...)", prompt)

    def test_revise_plot_from_feedback_prompt_mentions_change_summary(self) -> None:
        """Guide revision workflows toward previews and structural change summaries."""
        prompt = service.revise_plot_from_feedback_prompt(
            "drafts/demo.log.yaml",
            "Move caliper next to depth and shorten the remarks.",
        )

        self.assertIn("summarize_logfile_draft(logfile_path)", prompt)
        self.assertIn("inspect_authoring_vocab(logfile_path=logfile_path)", prompt)
        self.assertIn("summarize_logfile_changes(logfile_path, previous_text=...)", prompt)


if __name__ == "__main__":
    unittest.main()
