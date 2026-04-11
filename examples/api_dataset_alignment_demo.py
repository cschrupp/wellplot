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

"""Show dataset alignment and reindexing before rendering a report."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from well_log_os import DatasetBuilder, LogBuilder, render_report


def build_aligned_dataset():
    """Build a dataset whose channels start on different sample grids."""
    depth_ft_desc = np.array([8460.0, 8440.0, 8420.0, 8400.0, 8380.0, 8360.0])
    gr_values = np.array([86.0, 78.0, 69.0, 62.0, 58.0, 55.0])
    cbl_depth_ft = np.array([8360.0, 8400.0, 8440.0, 8460.0])
    cbl_values = np.array([18.0, 24.0, 31.0, 29.0])
    sample_axis_us = np.array([200.0, 400.0, 600.0, 800.0])
    waveform = np.array(
        [
            [0.1, 0.3, 0.5, 0.4],
            [0.2, 0.4, 0.6, 0.5],
            [0.4, 0.6, 0.3, 0.2],
            [0.6, 0.5, 0.2, 0.1],
        ]
    )

    return (
        DatasetBuilder(name="alignment-demo")
        .add_curve(
            mnemonic="GR",
            values=gr_values,
            index=depth_ft_desc,
            index_unit="ft",
            value_unit="gAPI",
        )
        .add_curve(
            mnemonic="CBL",
            values=cbl_values,
            index=cbl_depth_ft,
            index_unit="ft",
            value_unit="mV",
        )
        .add_raster(
            mnemonic="VDL_SYN",
            values=waveform,
            index=cbl_depth_ft,
            index_unit="ft",
            sample_axis=sample_axis_us,
            sample_unit="us",
            value_unit="amplitude",
        )
        .sort_index(channels=["GR"], ascending=True)
        .reindex_to(channel="GR", channels=["CBL", "VDL_SYN"])
        .convert_index_unit("m")
        .build()
    )


def build_report(dataset):
    """Build a simple report that renders the aligned channels."""
    builder = LogBuilder(name="Dataset Alignment Demo")
    builder.set_render(
        backend="matplotlib",
        output_path="api_dataset_alignment_demo.pdf",
        dpi=144,
    )
    builder.set_page(size="A4", orientation="portrait", header_height_mm=0, footer_height_mm=0)
    builder.set_depth_axis(unit="m", scale=200, major_step=5, minor_step=1)
    depth_m = dataset.get_channel("GR").depth
    builder.set_depth_range(float(depth_m.min()), float(depth_m.max()))

    section = builder.add_section("main", dataset=dataset, title="Aligned Dataset")
    section.add_track(
        id="depth",
        title="",
        kind="reference",
        width_mm=16,
        reference={"axis": "depth", "define_layout": True, "unit": "m"},
    )
    section.add_track(id="combo", title="", kind="normal", width_mm=30)
    section.add_track(id="vdl", title="", kind="array", width_mm=26)
    section.add_curve(
        channel="GR",
        track_id="combo",
        label="Gamma Ray",
        scale={"kind": "linear", "min": 0, "max": 150},
        style={"color": "#228b22", "line_width": 0.8},
    )
    section.add_curve(
        channel="CBL",
        track_id="combo",
        label="CBL Amplitude",
        scale={"kind": "linear", "min": 0, "max": 40},
        style={"color": "#111111", "line_width": 0.8},
    )
    section.add_raster(
        channel="VDL_SYN",
        track_id="vdl",
        label="Synthetic VDL",
        profile="vdl",
        sample_axis={"unit": "us", "min": 200, "max": 800},
    )
    return builder.build()


def main() -> None:
    """Run the alignment demo and render the resulting PDF."""
    dataset = build_aligned_dataset()
    report = build_report(dataset)
    output_path = Path("workspace/renders/api_dataset_alignment_demo.pdf")
    render_report(report, output_path=output_path)

    print("Aligned dataset channels:")
    for mnemonic in ("GR", "CBL", "VDL_SYN"):
        channel = dataset.get_channel(mnemonic)
        print(f"  {mnemonic}: {channel.depth_unit}, samples={channel.depth.size}")

    print("Rendered:", output_path)


if __name__ == "__main__":
    main()
