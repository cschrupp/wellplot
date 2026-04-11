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

"""Render the legacy synthetic triple-combo document example."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from wellplot import RasterChannel, ScalarChannel, WellDataset, load_document
from wellplot.renderers import MatplotlibRenderer


def build_dataset() -> WellDataset:
    """Build the synthetic dataset used by the triple-combo example."""
    depth = np.linspace(1000.0, 1120.0, 600)
    azimuth = np.linspace(0.0, 360.0, 90)
    dataset = WellDataset(
        name="Synthetic Example",
        well_metadata={
            "WELL": "SYN-1",
            "UWI": "00-000-00000",
            "COMP": "Open Source Energy",
        },
    )
    dataset.add_channel(ScalarChannel("GR", depth, "m", "gAPI", values=80 + 25 * np.sin(depth / 8)))
    dataset.add_channel(
        ScalarChannel("CALI", depth, "m", "in", values=8.5 + 0.7 * np.cos(depth / 5))
    )
    dataset.add_channel(
        ScalarChannel("RT", depth, "m", "ohm.m", values=np.exp(np.sin(depth / 12) + 2.5))
    )
    dataset.add_channel(
        ScalarChannel("RHOB", depth, "m", "g/cc", values=2.35 + 0.08 * np.sin(depth / 6))
    )
    dataset.add_channel(
        ScalarChannel("NPHI", depth, "m", "v/v", values=0.22 + 0.07 * np.cos(depth / 7))
    )
    dataset.add_channel(
        ScalarChannel(
            "FRACTURE_INTENSITY",
            depth,
            "m",
            "deg",
            values=180 + 140 * np.sin(depth / 9),
        )
    )
    raster = np.sin(depth[:, None] / 12) * np.cos(np.deg2rad(azimuth))[None, :]
    dataset.add_channel(
        RasterChannel(
            "FMI",
            depth,
            "m",
            "amplitude",
            values=raster,
            sample_axis=azimuth,
            sample_unit="deg",
            sample_label="azimuth",
        )
    )
    return dataset


def main() -> None:
    """Load the example document, render it, and print the PDF path."""
    document = load_document(Path(__file__).with_name("triple_combo.yaml"))
    dataset = build_dataset()
    renderer = MatplotlibRenderer()
    output = Path("synthetic_triple_combo.pdf")
    renderer.render(document, dataset, output_path=output)
    print(output)


if __name__ == "__main__":
    main()
