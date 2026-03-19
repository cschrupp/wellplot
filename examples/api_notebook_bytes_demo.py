from __future__ import annotations

from pathlib import Path

from api_layout_render_demo import build_dataset, build_report
from well_log_os import render_section_png, render_svg_bytes, render_window_png


def main() -> None:
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
