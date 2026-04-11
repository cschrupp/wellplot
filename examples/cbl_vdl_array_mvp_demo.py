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

"""Render the legacy CBL and VDL array MVP example from a log YAML file."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from well_log_os import RasterChannel, ScalarChannel, WellDataset
from well_log_os.logfile import build_documents_for_logfile, load_logfile
from well_log_os.renderers import MatplotlibRenderer


def build_synthetic_dataset() -> WellDataset:
    """Build a synthetic dataset that matches the CBL and VDL example YAML."""
    depth = np.linspace(1000.0, 1120.0, 700)
    azimuth = np.linspace(0.0, 360.0, 96)
    dataset = WellDataset(
        name="Synthetic CBL/VDL",
        well_metadata={
            "WELL": "SYN-CBL-1",
            "UWI": "00-000-ARRAY",
            "COMP": "well_log_os",
        },
    )
    dataset.add_channel(
        ScalarChannel("CBL", depth, "m", "mV", values=55 + 22 * np.sin(depth / 7.0))
    )
    dataset.add_channel(
        ScalarChannel(
            "TT",
            depth,
            "m",
            "us",
            values=180 + 110 * np.sin(depth / 10.0 + 0.7),
        )
    )
    vdl = np.sin(depth[:, None] / 6.5) * np.cos(np.deg2rad(azimuth))[None, :]
    dataset.add_channel(
        RasterChannel(
            "VDL",
            depth,
            "m",
            "amplitude",
            values=vdl,
            sample_axis=azimuth,
            sample_unit="deg",
            sample_label="azimuth",
            colormap="bone",
        )
    )
    return dataset


def resolve_output(logfile_path: Path, configured_output: str) -> Path:
    """Resolve the configured output path relative to the example log file."""
    output = Path(configured_output)
    if not output.is_absolute():
        output = (logfile_path.parent / output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


def main() -> None:
    """Load the YAML example, render it, and print the output path."""
    logfile_path = Path(__file__).with_name("cbl_vdl_array_mvp.log.yaml").resolve()
    spec = load_logfile(logfile_path)
    dataset = build_synthetic_dataset()

    documents = build_documents_for_logfile(
        spec,
        dataset,
        source_path=Path("synthetic_cbl_vdl.dlis"),
    )

    renderer_kwargs: dict[str, object] = {"dpi": spec.render_dpi}
    if spec.render_continuous_strip_page_height_mm is not None:
        renderer_kwargs["continuous_strip_page_height_mm"] = (
            spec.render_continuous_strip_page_height_mm
        )
    style = spec.render_matplotlib.get("style")
    if style is not None:
        renderer_kwargs["style"] = style

    renderer = MatplotlibRenderer(**renderer_kwargs)
    output_path = resolve_output(logfile_path, spec.render_output_path)
    renderer.render_documents(documents, dataset, output_path=output_path)
    print(output_path)


if __name__ == "__main__":
    main()
