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

"""Run an end-to-end dataset, layout, and rendering workflow demo."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from wellplot import (
    DatasetBuilder,
    LogBuilder,
    render_report,
    render_window_png,
    save_report,
)


def _smoothed(values: np.ndarray, window: int = 7) -> np.ndarray:
    """Return a simple moving-average smoothing of a one-dimensional array."""
    kernel = np.ones(window, dtype=float) / float(window)
    padded = np.pad(values, (window // 2, window // 2), mode="edge")
    return np.convolve(padded, kernel, mode="valid")


def build_raw_dataset():
    """Build the raw synthetic dataset used by the end-to-end demo."""
    depth_ft_desc = np.linspace(8460.0, 8200.0, 131)
    sample_axis_us = np.linspace(200.0, 1200.0, 96)
    gr = 68.0 + 16.0 * np.sin((depth_ft_desc - 8200.0) / 20.0)
    cbl = 24.0 + 8.0 * np.cos((depth_ft_desc - 8200.0) / 31.0)
    raw_frame = pd.DataFrame({"GR": gr, "CBL": cbl}, index=depth_ft_desc)

    wave = []
    for phase in (depth_ft_desc - depth_ft_desc.min()) / 46.0:
        wave.append(
            0.95 * np.sin(sample_axis_us / 32.0 + phase)
            + 0.25 * np.sin(sample_axis_us / 11.0 - phase * 1.5)
        )

    return (
        DatasetBuilder(
            name="raw",
            well_metadata={
                "WELL": "API Demo 1",
                "FIELD": "Notebook Field",
                "COMPANY": "Company",
            },
            provenance={"source": "synthetic-raw"},
        )
        .add_dataframe(
            raw_frame,
            use_index=True,
            index_unit="ft",
            curves={
                "GR": {"value_unit": "gAPI", "description": "Raw gamma ray"},
                "CBL": {"value_unit": "mV", "description": "Raw CBL amplitude"},
            },
        )
        .add_raster(
            mnemonic="VDL_SYN",
            values=np.asarray(wave, dtype=float),
            index=depth_ft_desc,
            index_unit="ft",
            sample_axis=sample_axis_us,
            sample_unit="us",
            value_unit="amplitude",
            colormap="gray_r",
            description="Synthetic VDL",
        )
        .sort_index()
        .build()
    )


def build_processed_dataset(raw):
    """Build processed channels derived from the raw dataset."""
    raw_depth_ft = raw.get_channel("GR").depth
    coarse_depth_ft = raw_depth_ft[::6]
    raw_gr = raw.get_channel("GR").values
    raw_cbl = raw.get_channel("CBL").values

    gr_proc = _smoothed(raw_gr)[::6]
    cbl_filt = _smoothed(raw_cbl, window=9)[::6]

    return (
        DatasetBuilder(
            name="processed",
            provenance={"source": "notebook"},
        )
        .add_curve(
            mnemonic="GR",
            values=gr_proc,
            index=coarse_depth_ft * 0.3048,
            index_unit="m",
            value_unit="gAPI",
            source="rolling-average",
            description="Notebook-smoothed gamma ray",
        )
        .add_curve(
            mnemonic="CBL_FILT",
            values=cbl_filt,
            index=coarse_depth_ft * 0.3048,
            index_unit="m",
            value_unit="mV",
            source="rolling-average",
            description="Filtered CBL amplitude",
        )
        .convert_index_unit("ft")
        .reindex_to(index=raw_depth_ft, index_unit="ft")
        .build()
    )


def build_working_dataset():
    """Merge the raw and processed datasets into one working dataset."""
    raw = build_raw_dataset()
    processed = build_processed_dataset(raw)
    return (
        DatasetBuilder(name="working")
        .merge(raw, merge_well_metadata=True, merge_provenance=True)
        .merge(
            processed,
            collision="rename",
            rename_template="{mnemonic}_proc",
        )
        .build()
    )


def build_report(dataset):
    """Build the report layout used by the end-to-end API demo."""
    builder = LogBuilder(name="API End-to-End Demo")
    builder.set_render(
        backend="matplotlib",
        output_path="workspace/renders/api_end_to_end_demo.pdf",
        dpi=180,
    )
    builder.set_page(
        size="A4",
        orientation="portrait",
        continuous=True,
        bottom_track_header_enabled=False,
        margin_left_mm=0,
        margin_top_mm=0,
        margin_bottom_mm=0,
        header_height_mm=0,
        footer_height_mm=0,
        track_header_height_mm=20,
        track_gap_mm=0,
        margin_right_mm=8,
    )
    builder.set_depth_axis(unit="ft", scale=240, major_step=10, minor_step=2)
    builder.set_depth_range(8320, 8450)

    section = builder.add_section(
        "main",
        dataset=dataset,
        title="Main Pass",
        subtitle="Raw and processed channels aligned in one layout",
        source_name="api-end-to-end.memory",
    )
    section.add_track(
        id="depth",
        title="",
        kind="reference",
        width_mm=16,
        reference={"axis": "depth", "define_layout": True, "unit": "ft"},
    )
    section.add_track(id="gr", title="", kind="normal", width_mm=34)
    section.add_track(id="cbl", title="", kind="normal", width_mm=34)
    section.add_track(
        id="vdl",
        title="",
        kind="array",
        width_mm=40,
        x_scale={"kind": "linear", "min": 200, "max": 1200},
        grid={"vertical": {"main": {"visible": False}, "secondary": {"visible": False}}},
    )
    section.add_curve(
        channel="GR",
        track_id="gr",
        label="Gamma Ray",
        style={"color": "#15803d", "line_width": 0.8},
        scale={"kind": "linear", "min": 0, "max": 150},
    )
    section.add_curve(
        channel="GR_proc",
        track_id="gr",
        label="Gamma Ray Smoothed",
        style={"color": "#d97706", "line_width": 0.9, "line_style": "--"},
        scale={"kind": "linear", "min": 0, "max": 150},
        header_display={"wrap_name": True},
    )
    section.add_curve(
        channel="CBL",
        track_id="cbl",
        label="CBL Amplitude",
        style={"color": "#111111", "line_width": 0.8},
        scale={"kind": "linear", "min": 0, "max": 40},
    )
    section.add_curve(
        channel="CBL_FILT",
        track_id="cbl",
        label="CBL Filtered",
        style={"color": "#1d4ed8", "line_width": 0.9, "line_style": "--"},
        scale={"kind": "linear", "min": 0, "max": 40},
    )
    section.add_raster(
        channel="VDL_SYN",
        track_id="vdl",
        label="Synthetic VDL",
        profile="vdl",
        colorbar={"enabled": True, "label": "Amplitude", "position": "header"},
        sample_axis={"enabled": True, "unit": "us", "min": 200, "max": 1200, "ticks": 5},
    )
    return builder.build()


def main() -> None:
    """Render the end-to-end demo outputs and print a short summary."""
    dataset = build_working_dataset()
    report = build_report(dataset)

    pdf_path = Path("workspace/renders/api_end_to_end_demo.pdf")
    yaml_path = Path("workspace/renders/api_end_to_end_demo.yaml")
    png_path = Path("workspace/renders/api_end_to_end_window.png")

    render_report(report, output_path=pdf_path)
    window_png = render_window_png(report, depth_range=(8340, 8400), depth_range_unit="ft")
    png_path.write_bytes(window_png)
    save_report(report, yaml_path)

    print("Channels:", sorted(dataset.channels))
    print("Merge history:", dataset.provenance.get("merge_history", []))
    print("Saved PDF:", pdf_path)
    print("Saved YAML:", yaml_path)
    print("Saved window PNG:", png_path)


if __name__ == "__main__":
    main()
