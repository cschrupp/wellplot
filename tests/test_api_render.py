from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from well_log_os import LogBuilder, create_dataset, render_report
from well_log_os.api import build_documents


def _build_dataset(name: str, *, phase: float = 0.0):
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


def _build_report():
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


class ApiRenderTests(unittest.TestCase):
    def test_build_documents_from_programmatic_builder(self) -> None:
        report = _build_report()

        documents = build_documents(report)

        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].depth_axis.unit, "ft")
        self.assertEqual([track.id for track in documents[0].tracks], ["depth", "combo", "vdl"])

    def test_render_report_without_output_path_returns_figures(self) -> None:
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
        report = _build_report()

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "api_layout_render_demo.pdf"
            result = render_report(report, output_path=output_path)

            self.assertEqual(result.output_path, output_path.resolve())
            self.assertTrue(output_path.exists())
            self.assertGreater(output_path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
