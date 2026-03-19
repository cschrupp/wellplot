from __future__ import annotations

from pathlib import Path

from api_layout_render_demo import build_dataset, build_report
from well_log_os import render_section, render_track, render_window


def main() -> None:
    dataset = build_dataset()
    report = build_report(dataset)

    output_dir = Path("workspace/renders")
    output_dir.mkdir(parents=True, exist_ok=True)

    section_path = output_dir / "api_partial_section_demo.pdf"
    track_path = output_dir / "api_partial_track_demo.pdf"
    window_path = output_dir / "api_partial_window_demo.pdf"

    section_result = render_section(report, section_id="main", output_path=section_path)
    track_result = render_track(
        report,
        section_id="main",
        track_ids=["combo"],
        output_path=track_path,
    )
    window_result = render_window(
        report,
        depth_range=(8300.0, 8400.0),
        depth_range_unit="ft",
        output_path=window_path,
    )

    print("Section pages:", section_result.page_count)
    print("Track pages:", track_result.page_count)
    print("Window pages:", window_result.page_count)
    print("Saved:", section_path)
    print("Saved:", track_path)
    print("Saved:", window_path)


if __name__ == "__main__":
    main()
