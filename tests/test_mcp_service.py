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
import tempfile
import unittest
from pathlib import Path

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

    def test_start_from_example_prompt_embeds_goal_and_example(self) -> None:
        """Embed the requested goal and packaged example resources in the prompt."""
        prompt = service.start_from_example_prompt(
            "forge16b_porosity_example",
            "Create a variant with simplified headers.",
        )

        self.assertIn("Create a variant with simplified headers.", prompt)
        self.assertIn("base.template.yaml", prompt)
        self.assertIn("full_reconstruction.log.yaml", prompt)


if __name__ == "__main__":
    unittest.main()
