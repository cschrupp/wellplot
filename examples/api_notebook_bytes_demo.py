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

"""Show byte-oriented rendering helpers for notebook-style workflows."""

from __future__ import annotations

from pathlib import Path

from api_layout_render_demo import build_dataset, build_report
from well_log_os import render_section_png, render_svg_bytes, render_window_png


def main() -> None:
    """Render PNG and SVG bytes and write them to the workspace render folder."""
    dataset = build_dataset()
    report = build_report(dataset)

    output_dir = Path("workspace/renders")
    output_dir.mkdir(parents=True, exist_ok=True)

    section_png = render_section_png(report, section_id="main", page_index=0, dpi=140)
    window_png = render_window_png(
        report,
        depth_range=(8300.0, 8400.0),
        depth_range_unit="ft",
        page_index=0,
        dpi=140,
    )
    report_svg = render_svg_bytes(report, page_index=0)

    section_png_path = output_dir / "api_notebook_section.png"
    window_png_path = output_dir / "api_notebook_window.png"
    report_svg_path = output_dir / "api_notebook_report_page.svg"

    section_png_path.write_bytes(section_png)
    window_png_path.write_bytes(window_png)
    report_svg_path.write_bytes(report_svg)

    print("Saved:", section_png_path)
    print("Saved:", window_png_path)
    print("Saved:", report_svg_path)


if __name__ == "__main__":
    main()
