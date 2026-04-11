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

"""API serialization and round-trip coverage tests."""

from __future__ import annotations

import tempfile
import unittest
from io import StringIO
from pathlib import Path

from wellplot import (
    LogBuilder,
    create_dataset,
    document_from_dict,
    document_from_mapping,
    document_from_yaml,
    document_to_dict,
    document_to_yaml,
    load_document_yaml,
    load_report,
    report_from_dict,
    report_from_yaml,
    report_to_dict,
    report_to_yaml,
    save_document,
    save_report,
)


def _build_document():
    return document_from_mapping(
        {
            "name": "serialize-demo",
            "page": {
                "width_mm": 210,
                "height_mm": 297,
                "header_height_mm": 0,
                "footer_height_mm": 0,
                "track_header_height_mm": 12,
            },
            "depth": {
                "unit": "ft",
                "scale": 240,
                "major_step": 10,
                "minor_step": 2,
            },
            "depth_range": [8200, 8260],
            "tracks": [
                {
                    "id": "depth",
                    "title": "",
                    "kind": "reference",
                    "width_mm": 16,
                    "reference": {
                        "axis": "depth",
                        "define_layout": True,
                        "unit": "ft",
                        "scale_ratio": 240,
                        "major_step": 10,
                        "header": {
                            "display_unit": True,
                            "display_scale": True,
                            "display_annotations": False,
                        },
                    },
                },
                {
                    "id": "combo",
                    "title": "",
                    "kind": "normal",
                    "width_mm": 30,
                    "elements": [
                        {
                            "kind": "curve",
                            "channel": "GR",
                            "label": "Gamma Ray",
                            "scale": {"kind": "linear", "min": 0, "max": 150},
                            "header_display": {"wrap_name": True},
                        }
                    ],
                },
            ],
        }
    )


def _build_report():
    dataset = create_dataset("serialize-main")
    dataset.add_curve(
        mnemonic="GR",
        values=[70.0, 72.0, 74.0],
        index=[8200.0, 8210.0, 8220.0],
        index_unit="ft",
        value_unit="gAPI",
    )
    builder = LogBuilder(name="Serialize Report")
    builder.set_render(backend="matplotlib", output_path="serialize.pdf", dpi=120)
    builder.set_page(size="A4", orientation="portrait", header_height_mm=0, footer_height_mm=0)
    builder.set_depth_axis(unit="ft", scale=240, major_step=10, minor_step=2)
    builder.set_depth_range(8200, 8220)
    builder.set_heading(
        provider_name="Company",
        general_fields=[{"key": "well", "label": "Well", "value": "Serialize 1"}],
        service_titles=["Gamma Ray"],
        tail_enabled=True,
    )
    section = builder.add_section("main", dataset=dataset, title="Main", source_name="main.memory")
    section.add_track(
        id="depth",
        title="",
        kind="reference",
        width_mm=16,
        reference={"axis": "depth", "define_layout": True, "unit": "ft"},
    )
    section.add_track(id="combo", title="", kind="normal", width_mm=30)
    section.add_curve(
        channel="GR",
        track_id="combo",
        label="Gamma Ray",
        scale={"kind": "linear", "min": 0, "max": 150},
    )
    return builder.build()


class ApiSerializeTests(unittest.TestCase):
    """Verify document and report serialization helpers."""

    def test_document_dict_round_trip_uses_template_keys(self) -> None:
        """Round-trip document mappings through the public dict helpers."""
        document = _build_document()

        mapping = document_to_dict(document)
        rebuilt = document_from_dict(mapping)

        self.assertIn("depth", mapping)
        self.assertNotIn("depth_axis", mapping)
        self.assertIn("track_header", mapping["tracks"][1])
        self.assertEqual(rebuilt.name, document.name)
        self.assertEqual(rebuilt.depth_axis.unit, "ft")
        self.assertEqual([track.id for track in rebuilt.tracks], ["depth", "combo"])

    def test_document_yaml_round_trip_supports_string_and_path(self) -> None:
        """Round-trip document YAML through streams and filesystem paths."""
        document = _build_document()

        yaml_text = document_to_yaml(document)
        self.assertIsInstance(yaml_text, str)
        self.assertIn("tracks:", yaml_text)

        from_stream = document_from_yaml(StringIO(yaml_text))
        self.assertEqual(from_stream.name, document.name)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "document.yaml"
            document_to_yaml(document, path)
            from_path = document_from_yaml(path)
        self.assertEqual(from_path.depth_range, document.depth_range)

    def test_report_dict_round_trip_supports_programmatic_spec(self) -> None:
        """Round-trip programmatic report specs through dict helpers."""
        report = _build_report()

        mapping = report_to_dict(report)
        spec = report_from_dict(mapping)

        self.assertEqual(mapping["version"], 1)
        self.assertEqual(mapping["name"], "Serialize Report")
        self.assertEqual(spec.name, "Serialize Report")
        self.assertEqual(spec.render_backend, "matplotlib")
        self.assertEqual(
            [section["id"] for section in spec.document["layout"]["log_sections"]],
            ["main"],
        )

    def test_report_yaml_round_trip_supports_stream_and_path(self) -> None:
        """Round-trip report YAML through streams and filesystem paths."""
        report = _build_report()

        yaml_text = report_to_yaml(report)
        self.assertIsInstance(yaml_text, str)
        self.assertIn("render:", yaml_text)

        from_stream = report_from_yaml(StringIO(yaml_text))
        self.assertEqual(from_stream.name, "Serialize Report")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "report.yaml"
            report_to_yaml(report, path)
            from_path = report_from_yaml(path)
        self.assertEqual(from_path.render_output_path, "serialize.pdf")

    def test_save_and_load_convenience_wrappers_delegate_to_yaml_helpers(self) -> None:
        """Persist and reload documents and reports via convenience wrappers."""
        document = _build_document()
        report = _build_report()

        with tempfile.TemporaryDirectory() as tmpdir:
            document_path = Path(tmpdir) / "document.yaml"
            report_path = Path(tmpdir) / "report.yaml"

            save_document(document, document_path)
            save_report(report, report_path)

            loaded_document = load_document_yaml(document_path)
            loaded_report = load_report(report_path)

        self.assertEqual(loaded_document.name, document.name)
        self.assertEqual(loaded_report.name, "Serialize Report")

    def test_builder_save_yaml_and_section_source_path_persistence(self) -> None:
        """Preserve section source-path metadata in serialized report output."""
        dataset = create_dataset("source-persist")
        dataset.add_curve(
            mnemonic="GR",
            values=[45.0, 50.0],
            index=[1000.0, 1001.0],
            index_unit="ft",
            value_unit="gAPI",
        )
        builder = LogBuilder(name="Source Persist Demo")
        builder.set_render(backend="matplotlib", output_path="persist.pdf", dpi=120)
        builder.set_page(size="A4", orientation="portrait")
        builder.set_depth_axis(unit="ft", scale=240, major_step=10, minor_step=2)
        builder.add_section(
            "main",
            dataset=dataset,
            title="Main",
            source_path="workspace/data/demo.las",
            source_format="las",
        ).add_track(
            id="depth",
            title="",
            kind="reference",
            width_mm=16,
            reference={"axis": "depth", "define_layout": True, "unit": "ft"},
        )

        mapping = report_to_dict(builder)
        yaml_text = builder.save_yaml()

        self.assertEqual(
            mapping["document"]["layout"]["log_sections"][0]["data"],
            {"source_path": "workspace/data/demo.las", "source_format": "las"},
        )
        self.assertIn("workspace/data/demo.las", yaml_text)


if __name__ == "__main__":
    unittest.main()
