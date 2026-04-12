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

"""Show programmatic report layout construction and rendering."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from wellplot import LogBuilder, ProgrammaticLogSpec, WellDataset, create_dataset, render_report


def build_dataset() -> WellDataset:
    """Build the synthetic dataset used by the layout render demo."""
    depth_ft = np.linspace(8200.0, 8460.0, 261)
    sample_axis_us = np.linspace(200.0, 1200.0, 128)

    dataset = create_dataset(
        "synthetic_layout_demo",
        well_metadata={
            "WELL": "API Demo 1",
            "FIELD": "Notebook",
        },
        provenance={"source": "programmatic-layout-demo"},
    )
    dataset.add_curve(
        mnemonic="GR",
        values=70.0 + 18.0 * np.sin((depth_ft - depth_ft.min()) / 18.0),
        index=depth_ft,
        index_unit="ft",
        value_unit="gAPI",
        description="Gamma ray",
    )
    dataset.add_curve(
        mnemonic="CBL",
        values=22.0 + 9.0 * np.cos((depth_ft - depth_ft.min()) / 27.0),
        index=depth_ft,
        index_unit="ft",
        value_unit="mV",
        description="CBL amplitude",
    )

    wave = []
    for phase in (depth_ft - depth_ft.min()) / 48.0:
        wave.append(
            0.9 * np.sin(sample_axis_us / 31.0 + phase)
            + 0.35 * np.sin(sample_axis_us / 11.0 - phase * 1.7)
            + 0.15 * np.cos(sample_axis_us / 73.0 + phase * 0.8)
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
        description="Synthetic VDL panel",
    )
    return dataset


def build_report(dataset: WellDataset) -> ProgrammaticLogSpec:
    """Build the programmatic report for the synthetic layout dataset."""
    builder = LogBuilder(name="Programmatic Layout Demo")
    builder.set_render(
        backend="matplotlib",
        output_path="workspace/renders/api_layout_render_demo.pdf",
        dpi=180,
        continuous_strip_page_height_mm=297,
    )
    builder.set_page(
        size="A4",
        orientation="portrait",
        margin_left_mm=0,
        margin_right_mm=8,
        margin_top_mm=0,
        margin_bottom_mm=0,
        header_height_mm=0,
        track_header_height_mm=20,
        footer_height_mm=0,
        track_gap_mm=0,
    )
    builder.set_depth_axis(unit="ft", scale=240, major_step=10, minor_step=2)
    builder.set_depth_range(8200, 8460)

    section = builder.add_section(
        "main",
        dataset=dataset,
        title="Main Pass",
        subtitle="Programmatic in-memory layout render",
        source_name="api-layout-demo.memory",
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
        width_mm=44,
        position=2,
    )
    section.add_track(
        id="vdl",
        title="",
        kind="array",
        width_mm=48,
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


def main() -> None:
    """Render the layout demo PDF and print the saved output path."""
    dataset = build_dataset()
    report = build_report(dataset)
    output_path = Path("workspace/renders/api_layout_render_demo.pdf")
    result = render_report(report, output_path=output_path)
    print("Pages:", result.page_count)
    print("Saved:", output_path)


if __name__ == "__main__":
    main()
