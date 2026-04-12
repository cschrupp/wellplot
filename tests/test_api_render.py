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

"""Programmatic rendering API tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from wellplot import (
    DatasetBuilder,
    LogBuilder,
    ProgrammaticLogSpec,
    WellDataset,
    create_dataset,
    render_png_bytes,
    render_report,
    render_section,
    render_section_png,
    render_svg_bytes,
    render_track,
    render_track_png,
    render_window,
    render_window_png,
    save_report,
)
from wellplot.api import build_documents
from wellplot.errors import TemplateValidationError


def _build_dataset(name: str, *, phase: float = 0.0) -> WellDataset:
    depth_ft = np.linspace(8200.0, 8460.0, 261)
    sample_axis_us = np.linspace(200.0, 1200.0, 96)
    dataset = create_dataset(
        name,
        well_metadata={"WELL": "API Demo 1", "FIELD": "Notebook"},
        provenance={"source": "test"},
    )
    dataset.add_curve(
        mnemonic="GR",
        values=70.0 + 18.0 * np.sin((depth_ft - depth_ft.min()) / 18.0 + phase),
        index=depth_ft,
        index_unit="ft",
        value_unit="gAPI",
    )
    dataset.add_curve(
        mnemonic="CBL",
        values=22.0 + 9.0 * np.cos((depth_ft - depth_ft.min()) / 27.0 + phase),
        index=depth_ft,
        index_unit="ft",
        value_unit="mV",
    )
    wave = []
    for row_phase in (depth_ft - depth_ft.min()) / 48.0:
        wave.append(
            0.9 * np.sin(sample_axis_us / 31.0 + row_phase + phase)
            + 0.35 * np.sin(sample_axis_us / 11.0 - row_phase * 1.7)
        )
    dataset.add_raster(
        mnemonic="VDL_SYN",
        values=np.asarray(wave, dtype=float),
        index=depth_ft,
        index_unit="ft",
        sample_axis=sample_axis_us,
        sample_unit="us",
        value_unit="amplitude",
        colormap="gray_r",
    )
    return dataset


def _build_report() -> ProgrammaticLogSpec:
    dataset = _build_dataset("main")
    builder = LogBuilder(name="Programmatic layout demo")
    builder.set_render(backend="matplotlib", output_path="api_layout_render_demo.pdf", dpi=140)
    builder.set_page(
        size="A4",
        orientation="portrait",
        margin_left_mm=0,
        margin_right_mm=8,
        margin_top_mm=0,
        margin_bottom_mm=0,
        header_height_mm=0,
        track_header_height_mm=18,
        footer_height_mm=0,
        track_gap_mm=0,
    )
    builder.set_depth_axis(unit="ft", scale=240, major_step=10, minor_step=2)
    builder.set_depth_range(8200, 8460)
    section = builder.add_section(
        "main",
        dataset=dataset,
        title="Main",
        subtitle="In-memory dataset render",
        source_name="main.memory",
    )
    section.add_track(
        id="depth",
        title="",
        kind="reference",
        width_mm=16,
        position=1,
        reference={
            "axis": "depth",
            "define_layout": True,
            "unit": "ft",
            "scale_ratio": 240,
            "major_step": 10,
            "secondary_grid": {"display": True, "line_count": 5},
            "header": {
                "display_unit": True,
                "display_scale": True,
                "display_annotations": False,
            },
            "number_format": {"format": "automatic", "precision": 0},
        },
    )
    section.add_track(
        id="combo",
        title="",
        kind="normal",
        width_mm=42,
        position=2,
    )
    section.add_track(
        id="vdl",
        title="",
        kind="array",
        width_mm=44,
        position=3,
        x_scale={"kind": "linear", "min": 200, "max": 1200},
        grid={
            "vertical": {
                "main": {"visible": False},
                "secondary": {"visible": False},
            }
        },
    )
    section.add_curve(
        channel="GR",
        track_id="combo",
        label="Gamma Ray",
        style={"color": "#15803d", "line_width": 0.8},
        scale={"kind": "linear", "min": 0, "max": 150},
    )
    section.add_curve(
        channel="CBL",
        track_id="combo",
        label="CBL Amplitude",
        style={"color": "#111111", "line_width": 0.8},
        scale={"kind": "linear", "min": 0, "max": 40},
    )
    section.add_raster(
        channel="VDL_SYN",
        track_id="vdl",
        label="Synthetic VDL",
        profile="vdl",
        normalization="auto",
        colorbar={"enabled": True, "label": "Amplitude", "position": "header"},
        sample_axis={
            "enabled": True,
            "unit": "us",
            "min": 200,
            "max": 1200,
            "ticks": 5,
        },
    )
    return builder.build()


def _build_report_with_heading() -> ProgrammaticLogSpec:
    dataset = _build_dataset("main")
    builder = LogBuilder(name="Programmatic report demo")
    builder.set_render(backend="matplotlib", output_path="api_layout_render_demo.pdf", dpi=140)
    builder.set_page(
        size="A4",
        orientation="portrait",
        header_height_mm=0,
        footer_height_mm=0,
        track_header_height_mm=18,
        track_gap_mm=0,
    )
    builder.set_depth_axis(unit="ft", scale=240, major_step=10, minor_step=2)
    builder.set_depth_range(8200, 8460)
    builder.set_heading(
        provider_name="Company",
        general_fields=[
            {"key": "well", "label": "Well", "value": "API Demo 1"},
            {"key": "field", "label": "Field", "value": "Notebook"},
        ],
        service_titles=["Cement Bond Log"],
        tail_enabled=True,
    )
    builder.set_remarks([{"title": "Remarks", "text": "Notebook preview"}])
    section = builder.add_section(
        "main",
        dataset=dataset,
        title="Main",
        source_name="main.memory",
    )
    section.add_track(
        id="depth",
        title="",
        kind="reference",
        width_mm=16,
        reference={"axis": "depth", "define_layout": True, "unit": "ft"},
    )
    section.add_track(id="combo", title="", kind="normal", width_mm=35)
    section.add_curve(
        channel="GR",
        track_id="combo",
        label="Gamma Ray",
        scale={"kind": "linear", "min": 0, "max": 150},
    )
    return builder.build()


class ApiRenderTests(unittest.TestCase):
    """Verify scoped rendering helpers and programmatic report building."""

    def test_build_documents_from_programmatic_builder(self) -> None:
        """Build a document list from a programmatic report builder."""
        report = _build_report()

        documents = build_documents(report)

        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].depth_axis.unit, "ft")
        self.assertEqual([track.id for track in documents[0].tracks], ["depth", "combo", "vdl"])

    def test_render_report_without_output_path_returns_figures(self) -> None:
        """Return in-memory figures when no output path is provided."""
        report = _build_report()

        result = render_report(report)

        self.assertEqual(result.backend, "matplotlib")
        self.assertGreater(result.page_count, 0)
        self.assertIsNone(result.output_path)
        self.assertIsInstance(result.artifact, list)
        self.assertGreater(len(result.artifact), 0)
        for figure in result.artifact:
            figure.clf()

    def test_render_report_can_filter_to_selected_sections(self) -> None:
        """Restrict document building to an explicit subset of sections."""
        builder = LogBuilder(name="Multisection programmatic layout")
        builder.set_render(backend="matplotlib", output_path="filtered.pdf", dpi=120)
        builder.set_page(size="A4", orientation="portrait", header_height_mm=0, footer_height_mm=0)
        builder.set_depth_axis(unit="ft", scale=240, major_step=10, minor_step=2)
        builder.set_depth_range(8200, 8460)

        main = builder.add_section(
            "main",
            dataset=_build_dataset("main"),
            source_name="main.memory",
        )
        repeat = builder.add_section(
            "repeat",
            dataset=_build_dataset("repeat", phase=0.6),
            source_name="repeat.memory",
        )
        for section in (main, repeat):
            section.add_track(
                id="depth",
                title="",
                kind="reference",
                width_mm=16,
                reference={"axis": "depth", "define_layout": True, "unit": "ft"},
            )
            section.add_track(id="combo", title="", kind="normal", width_mm=35)
            section.add_curve(
                channel="GR",
                track_id="combo",
                label="Gamma Ray",
                scale={"kind": "linear", "min": 0, "max": 150},
            )

        report = builder.build()
        documents = build_documents(report, section_ids=["repeat"])

        self.assertEqual(len(documents), 1)
        self.assertEqual(
            documents[0].metadata["layout_sections"]["active_section"]["id"],
            "repeat",
        )

    def test_render_report_writes_pdf_when_output_path_is_provided(self) -> None:
        """Write a PDF artifact when an explicit output path is supplied."""
        report = _build_report()

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "api_layout_render_demo.pdf"
            result = render_report(report, output_path=output_path)

            self.assertEqual(result.output_path, output_path.resolve())
            self.assertTrue(output_path.exists())
            self.assertGreater(output_path.stat().st_size, 0)

    def test_build_documents_can_filter_tracks_within_section(self) -> None:
        """Restrict built documents to selected tracks within a section."""
        report = _build_report()

        documents = build_documents(
            report,
            track_ids_by_section={"main": ["vdl"]},
            include_report_pages=False,
        )

        self.assertEqual(len(documents), 1)
        self.assertEqual([track.id for track in documents[0].tracks], ["vdl"])

    def test_build_documents_can_override_depth_range_for_window(self) -> None:
        """Override the report depth window at build time."""
        report = _build_report()

        documents = build_documents(
            report,
            depth_range=(8300.0, 8400.0),
            depth_range_unit="ft",
            include_report_pages=False,
        )

        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].depth_range, (8300.0, 8400.0))

    def test_build_documents_can_suppress_report_pages_for_partial_scopes(self) -> None:
        """Omit heading and tail pages for partial document scopes."""
        report = _build_report_with_heading()

        full_documents = build_documents(report)
        partial_documents = build_documents(report, include_report_pages=False)

        self.assertIsNotNone(full_documents[0].header.report)
        self.assertIsNone(partial_documents[0].header.report)

    def test_render_section_returns_selected_section_only(self) -> None:
        """Render only the requested section in a multisection report."""
        builder = LogBuilder(name="Multisection programmatic layout")
        builder.set_render(backend="matplotlib", output_path="filtered.pdf", dpi=120)
        builder.set_page(size="A4", orientation="portrait", header_height_mm=0, footer_height_mm=0)
        builder.set_depth_axis(unit="ft", scale=240, major_step=10, minor_step=2)
        builder.set_depth_range(8200, 8460)

        main = builder.add_section(
            "main",
            dataset=_build_dataset("main"),
            source_name="main.memory",
        )
        repeat = builder.add_section(
            "repeat",
            dataset=_build_dataset("repeat", phase=0.6),
            source_name="repeat.memory",
        )
        for section in (main, repeat):
            section.add_track(
                id="depth",
                title="",
                kind="reference",
                width_mm=16,
                reference={"axis": "depth", "define_layout": True, "unit": "ft"},
            )
            section.add_track(id="combo", title="", kind="normal", width_mm=35)
            section.add_curve(
                channel="GR",
                track_id="combo",
                label="Gamma Ray",
                scale={"kind": "linear", "min": 0, "max": 150},
            )

        report = builder.build()
        result = render_section(report, section_id="repeat")

        self.assertEqual(result.backend, "matplotlib")
        self.assertGreater(result.page_count, 0)
        self.assertIsInstance(result.artifact, list)
        self.assertEqual(len(result.artifact), result.page_count)
        for figure in result.artifact:
            figure.clf()

    def test_render_track_and_window_return_figures(self) -> None:
        """Render scoped track and depth-window selections as figures."""
        report = _build_report()

        track_result = render_track(report, section_id="main", track_ids="vdl")
        self.assertEqual(track_result.backend, "matplotlib")
        self.assertGreater(track_result.page_count, 0)
        self.assertIsInstance(track_result.artifact, list)
        self.assertEqual(len(track_result.artifact), track_result.page_count)
        for figure in track_result.artifact:
            figure.clf()

        window_result = render_window(
            report,
            depth_range=(8300.0, 8400.0),
            depth_range_unit="ft",
        )
        self.assertEqual(window_result.backend, "matplotlib")
        self.assertEqual(window_result.page_count, 1)
        self.assertIsInstance(window_result.artifact, list)
        self.assertEqual(len(window_result.artifact), 1)
        for figure in window_result.artifact:
            figure.clf()

    def test_end_to_end_workflow_can_align_merge_render_and_serialize(self) -> None:
        """Exercise dataset alignment, merging, rendering, and serialization together."""
        raw = create_dataset(
            "raw",
            well_metadata={"WELL": "API Demo 1", "FIELD": "Notebook Field", "COMPANY": "Company"},
            provenance={"source": "raw"},
        )
        depth_ft = np.array([8200.0, 8210.0, 8220.0, 8230.0, 8240.0], dtype=float)
        raw.add_curve(
            mnemonic="GR",
            values=[70.0, 72.0, 75.0, 78.0, 76.0],
            index=depth_ft,
            index_unit="ft",
            value_unit="gAPI",
        )
        raw.add_curve(
            mnemonic="CBL",
            values=[18.0, 20.0, 23.0, 25.0, 24.0],
            index=depth_ft,
            index_unit="ft",
            value_unit="mV",
        )
        raw.add_raster(
            mnemonic="VDL_SYN",
            values=np.asarray(
                [
                    [0.1, 0.2, 0.3],
                    [0.2, 0.3, 0.4],
                    [0.3, 0.4, 0.5],
                    [0.4, 0.3, 0.2],
                    [0.3, 0.2, 0.1],
                ],
                dtype=float,
            ),
            index=depth_ft,
            index_unit="ft",
            sample_axis=[200.0, 400.0, 600.0],
            sample_unit="us",
            value_unit="amplitude",
        )
        processed = (
            DatasetBuilder(name="processed", provenance={"source": "notebook"})
            .add_curve(
                mnemonic="GR",
                values=[71.0, 77.0, 75.0],
                index=[8200.0 * 0.3048, 8220.0 * 0.3048, 8240.0 * 0.3048],
                index_unit="m",
                value_unit="gAPI",
                source="rolling-average",
            )
            .add_curve(
                mnemonic="CBL_FILT",
                values=[19.0, 24.0, 23.5],
                index=[8200.0 * 0.3048, 8220.0 * 0.3048, 8240.0 * 0.3048],
                index_unit="m",
                value_unit="mV",
                source="rolling-average",
            )
            .convert_index_unit("ft")
            .reindex_to(index=depth_ft, index_unit="ft")
            .build()
        )
        working = (
            DatasetBuilder(name="working")
            .merge(raw, merge_well_metadata=True, merge_provenance=True)
            .merge(processed, collision="rename", rename_template="{mnemonic}_proc")
            .build()
        )

        builder = LogBuilder(name="End-to-End Workflow")
        builder.set_render(backend="matplotlib", output_path="workflow.pdf", dpi=120)
        builder.set_page(size="A4", orientation="portrait", header_height_mm=0, footer_height_mm=0)
        builder.set_depth_axis(unit="ft", scale=240, major_step=10, minor_step=2)
        builder.set_depth_range(8200, 8240)
        builder.set_heading(
            provider_name="Company",
            general_fields=[{"key": "well", "label": "Well", "value": "API Demo 1"}],
            service_titles=["Workflow Demo"],
            tail_enabled=True,
        )
        builder.set_remarks([{"title": "Remarks", "text": "Combined workflow"}])
        section = builder.add_section("main", dataset=working, title="Main")
        section.add_track(
            id="depth",
            title="",
            kind="reference",
            width_mm=16,
            reference={"axis": "depth", "define_layout": True, "unit": "ft"},
        )
        section.add_track(id="gr", title="", kind="normal", width_mm=24)
        section.add_track(id="cbl", title="", kind="normal", width_mm=24)
        section.add_track(id="vdl", title="", kind="array", width_mm=28)
        section.add_curve(
            channel="GR",
            track_id="gr",
            label="Gamma Ray",
            scale={"kind": "linear", "min": 0, "max": 150},
        )
        section.add_curve(
            channel="GR_proc",
            track_id="gr",
            label="Gamma Ray Proc",
            scale={"kind": "linear", "min": 0, "max": 150},
        )
        section.add_curve(
            channel="CBL",
            track_id="cbl",
            label="CBL",
            scale={"kind": "linear", "min": 0, "max": 40},
        )
        section.add_curve(
            channel="CBL_FILT",
            track_id="cbl",
            label="CBL Filt",
            scale={"kind": "linear", "min": 0, "max": 40},
        )
        section.add_raster(
            channel="VDL_SYN",
            track_id="vdl",
            label="VDL",
            profile="vdl",
            sample_axis={"enabled": True, "unit": "us", "min": 200, "max": 600},
        )
        report = builder.build()

        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "workflow.pdf"
            yaml_path = Path(tmpdir) / "workflow.yaml"
            result = render_report(report, output_path=pdf_path)
            png_bytes = render_window_png(report, depth_range=(8210, 8230), depth_range_unit="ft")
            save_report(report, yaml_path)

            self.assertTrue(pdf_path.exists())
            self.assertTrue(yaml_path.exists())
            self.assertGreater(len(png_bytes), 100)

        self.assertEqual(result.page_count, 3)
        self.assertIn("GR_proc", working.channels)
        self.assertEqual(
            working.provenance["merge_history"][-1]["renamed"],
            {"GR": "GR_proc"},
        )

    def test_render_png_and_svg_bytes_return_image_payloads(self) -> None:
        """Return PNG and SVG byte payloads for rendered pages."""
        report = _build_report()

        png_bytes = render_png_bytes(report, page_index=0, dpi=120)
        svg_bytes = render_svg_bytes(report, page_index=0)

        self.assertIsInstance(png_bytes, bytes)
        self.assertGreater(len(png_bytes), 0)
        self.assertTrue(png_bytes.startswith(b"\x89PNG\r\n\x1a\n"))

        self.assertIsInstance(svg_bytes, bytes)
        self.assertGreater(len(svg_bytes), 0)
        self.assertIn(b"<svg", svg_bytes)

    def test_scoped_png_helpers_return_bytes(self) -> None:
        """Return PNG byte payloads for scoped section, track, and window renders."""
        report = _build_report()

        section_png = render_section_png(report, section_id="main", page_index=0, dpi=120)
        track_png = render_track_png(
            report,
            section_id="main",
            track_ids="vdl",
            page_index=0,
            dpi=120,
        )
        window_png = render_window_png(
            report,
            depth_range=(8300.0, 8400.0),
            depth_range_unit="ft",
            page_index=0,
            dpi=120,
        )

        for payload in (section_png, track_png, window_png):
            self.assertIsInstance(payload, bytes)
            self.assertTrue(payload.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_render_png_bytes_rejects_invalid_page_index(self) -> None:
        """Reject page indices outside the rendered page range."""
        report = _build_report()

        with self.assertRaisesRegex(TemplateValidationError, "page_index"):
            render_png_bytes(report, page_index=99)


if __name__ == "__main__":
    unittest.main()
