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

"""Layout engine pagination and frame geometry tests."""

from __future__ import annotations

import unittest

import numpy as np

from wellplot import LayoutEngine, ScalarChannel, WellDataset, document_from_mapping
from wellplot.errors import LayoutError


class LayoutTests(unittest.TestCase):
    """Verify page layout and pagination behavior."""

    def build_dataset(self) -> WellDataset:
        """Create a small synthetic dataset used across layout tests."""
        depth = np.linspace(1000.0, 1105.0, 300)
        dataset = WellDataset(name="synthetic")
        dataset.add_channel(
            ScalarChannel("GR", depth, "m", "gAPI", values=np.linspace(20, 120, depth.size))
        )
        return dataset

    def test_layout_paginates_depth_range(self) -> None:
        """Paginate layouts when the document depth exceeds one page."""
        document = document_from_mapping(
            {
                "name": "paginate",
                "page": {"size": "A4"},
                "depth": {"unit": "m", "scale": "1:200"},
                "tracks": [
                    {"id": "depth", "title": "Depth", "kind": "depth", "width_mm": 16},
                    {
                        "id": "gr",
                        "title": "GR",
                        "kind": "curve",
                        "width_mm": 25,
                        "x_scale": {"kind": "linear", "min": 0, "max": 150},
                        "elements": [{"kind": "curve", "channel": "GR"}],
                    },
                ],
            }
        )
        layout = LayoutEngine().layout(document, self.build_dataset())
        self.assertGreaterEqual(len(layout), 2)
        self.assertEqual(layout[0].track_frames[1].track.id, "gr")

    def test_pagination_keeps_constant_depth_scale_on_last_page(self) -> None:
        """Keep the configured depth scale on first, middle, and last pages."""
        document = document_from_mapping(
            {
                "name": "constant scale",
                "page": {"size": "A4"},
                "depth": {"unit": "m", "scale": "1:200"},
                "tracks": [
                    {"id": "depth", "title": "Depth", "kind": "depth", "width_mm": 16},
                    {"id": "gr", "title": "GR", "kind": "curve", "width_mm": 25, "elements": []},
                ],
            }
        )
        dataset = self.build_dataset()
        engine = LayoutEngine()
        windows = engine.paginate(document, dataset)
        self.assertGreaterEqual(len(windows), 2)

        span_first = engine._depth_span_for_page(
            document,
            document.page,
            reserve_top_track_header=True,
            reserve_bottom_track_header=False,
        )
        span_middle = engine._depth_span_for_page(
            document,
            document.page,
            reserve_top_track_header=False,
            reserve_bottom_track_header=False,
        )
        span_last = engine._depth_span_for_page(
            document,
            document.page,
            reserve_top_track_header=False,
            reserve_bottom_track_header=True,
        )
        self.assertAlmostEqual(windows[0].stop - windows[0].start, span_first, places=6)
        if len(windows) > 2:
            for window in windows[1:-1]:
                self.assertAlmostEqual(window.stop - window.start, span_middle, places=6)
        self.assertAlmostEqual(windows[-1].stop - windows[-1].start, span_last, places=6)

    def test_default_page_spacing_starts_tracks_at_page_origin(self) -> None:
        """Start tracks at the page origin when no margins or gaps are set."""
        document = document_from_mapping(
            {
                "name": "defaults",
                "page": {"size": "A4"},
                "depth": {"unit": "m", "scale": "1:200"},
                "tracks": [
                    {"id": "depth", "title": "Depth", "kind": "depth", "width_mm": 16},
                    {"id": "gr", "title": "GR", "kind": "curve", "width_mm": 25, "elements": []},
                ],
            }
        )
        frame_depth, frame_gr = LayoutEngine().track_frames(document)
        self.assertAlmostEqual(frame_depth.frame.x_mm, 0.0)
        self.assertAlmostEqual(frame_gr.frame.x_mm, 16.0)

    def test_page_spacing_is_configurable_from_yaml(self) -> None:
        """Honor left margins and track gaps parsed from template YAML."""
        document = document_from_mapping(
            {
                "name": "spacing config",
                "page": {
                    "size": "A4",
                    "margin_left_mm": 3.0,
                    "track_gap_mm": 2.5,
                },
                "depth": {"unit": "m", "scale": "1:200"},
                "tracks": [
                    {"id": "depth", "title": "Depth", "kind": "depth", "width_mm": 16},
                    {"id": "gr", "title": "GR", "kind": "curve", "width_mm": 25, "elements": []},
                ],
            }
        )
        frame_depth, frame_gr = LayoutEngine().track_frames(document)
        self.assertAlmostEqual(frame_depth.frame.x_mm, 3.0)
        self.assertAlmostEqual(frame_gr.frame.x_mm, 21.5)

    def test_track_width_overflow_raises(self) -> None:
        """Raise when requested track widths exceed the usable page width."""
        document = document_from_mapping(
            {
                "name": "overflow",
                "page": {"size": "A4", "margin_left_mm": 5, "margin_right_mm": 5},
                "depth": {"unit": "m", "scale": "1:200"},
                "tracks": [
                    {"id": "depth", "title": "Depth", "kind": "depth", "width_mm": 50},
                    {"id": "a", "title": "A", "kind": "curve", "width_mm": 100, "elements": []},
                    {"id": "b", "title": "B", "kind": "curve", "width_mm": 100, "elements": []},
                ],
            }
        )
        with self.assertRaises(LayoutError):
            LayoutEngine().track_frames(document)

    def test_continuous_mode_produces_single_tall_page(self) -> None:
        """Collapse continuous layouts into one tall strip page."""
        document = document_from_mapping(
            {
                "name": "continuous",
                "page": {"size": "A4", "continuous": True},
                "depth": {"unit": "m", "scale": "1:200"},
                "tracks": [
                    {"id": "depth", "title": "Depth", "kind": "depth", "width_mm": 16},
                    {
                        "id": "gr",
                        "title": "GR",
                        "kind": "curve",
                        "width_mm": 25,
                        "x_scale": {"kind": "linear", "min": 0, "max": 150},
                        "elements": [{"kind": "curve", "channel": "GR"}],
                    },
                ],
            }
        )
        layout = LayoutEngine().layout(document, self.build_dataset())
        self.assertEqual(len(layout), 1)
        self.assertGreater(layout[0].page.height_mm, 500)
        self.assertAlmostEqual(layout[0].depth_window.start, 1000.0, places=3)
        self.assertAlmostEqual(layout[0].depth_window.stop, 1105.0, places=3)

    def test_track_header_frames_align_with_track_frames(self) -> None:
        """Align top track header frames with their corresponding track frames."""
        document = document_from_mapping(
            {
                "name": "headers",
                "page": {"size": "A4", "header_height_mm": 20, "track_header_height_mm": 9},
                "depth": {"unit": "m", "scale": "1:200"},
                "tracks": [
                    {"id": "depth", "title": "Depth", "kind": "depth", "width_mm": 16},
                    {"id": "gr", "title": "GR", "kind": "curve", "width_mm": 25, "elements": []},
                ],
            }
        )
        page_layout = LayoutEngine().layout(document, self.build_dataset())[0]
        self.assertEqual(len(page_layout.track_header_frames), len(page_layout.track_frames))
        self.assertAlmostEqual(
            page_layout.track_header_frames[0].frame.y_mm,
            page_layout.page.margin_top_mm + page_layout.page.header_height_mm,
        )
        self.assertAlmostEqual(
            page_layout.track_header_frames[0].frame.height_mm,
            page_layout.page.track_header_height_mm,
        )
        self.assertAlmostEqual(
            page_layout.track_header_frames[1].frame.x_mm,
            page_layout.track_frames[1].frame.x_mm,
        )
        self.assertAlmostEqual(
            page_layout.track_header_frames[1].frame.width_mm,
            page_layout.track_frames[1].frame.width_mm,
        )

    def test_track_headers_only_render_on_layout_start_and_end(self) -> None:
        """Render track headers only on the first and last paginated pages."""
        document = document_from_mapping(
            {
                "name": "headers once",
                "page": {"size": "A4", "header_height_mm": 20, "track_header_height_mm": 9},
                "depth": {"unit": "m", "scale": "1:200"},
                "tracks": [
                    {"id": "depth", "title": "Depth", "kind": "depth", "width_mm": 16},
                    {"id": "gr", "title": "GR", "kind": "curve", "width_mm": 25, "elements": []},
                ],
            }
        )
        layouts = LayoutEngine().layout(document, self.build_dataset())
        self.assertGreaterEqual(len(layouts), 2)

        first = layouts[0]
        last = layouts[-1]
        self.assertEqual(len(first.track_header_top_frames), len(first.track_frames))
        self.assertEqual(len(first.track_header_bottom_frames), 0)
        self.assertEqual(len(last.track_header_bottom_frames), len(last.track_frames))

        if len(layouts) > 2:
            middle = layouts[1]
            self.assertEqual(len(middle.track_header_top_frames), 0)
            self.assertEqual(len(middle.track_header_bottom_frames), 0)

    def test_continuous_layout_can_disable_bottom_track_headers(self) -> None:
        """Allow continuous layouts to suppress bottom track headers."""
        document = document_from_mapping(
            {
                "name": "continuous headers",
                "page": {
                    "size": "A4",
                    "continuous": True,
                    "bottom_track_header_enabled": False,
                    "header_height_mm": 0,
                    "footer_height_mm": 0,
                    "track_header_height_mm": 9,
                },
                "depth": {"unit": "m", "scale": "1:200"},
                "tracks": [
                    {"id": "depth", "title": "Depth", "kind": "depth", "width_mm": 16},
                    {"id": "gr", "title": "GR", "kind": "curve", "width_mm": 25, "elements": []},
                ],
            }
        )

        layouts = LayoutEngine().layout(document, self.build_dataset())

        self.assertEqual(len(layouts), 1)
        page_layout = layouts[0]
        self.assertEqual(len(page_layout.track_header_top_frames), len(page_layout.track_frames))
        self.assertEqual(len(page_layout.track_header_bottom_frames), 0)

    def test_continuous_layout_keeps_bottom_track_headers_by_default(self) -> None:
        """Keep bottom track headers enabled by default in continuous mode."""
        document = document_from_mapping(
            {
                "name": "continuous headers default",
                "page": {
                    "size": "A4",
                    "continuous": True,
                    "header_height_mm": 0,
                    "footer_height_mm": 0,
                    "track_header_height_mm": 9,
                },
                "depth": {"unit": "m", "scale": "1:200"},
                "tracks": [
                    {"id": "depth", "title": "Depth", "kind": "depth", "width_mm": 16},
                    {"id": "gr", "title": "GR", "kind": "curve", "width_mm": 25, "elements": []},
                ],
            }
        )

        layouts = LayoutEngine().layout(document, self.build_dataset())

        self.assertEqual(len(layouts), 1)
        page_layout = layouts[0]
        self.assertEqual(len(page_layout.track_header_top_frames), len(page_layout.track_frames))
        self.assertEqual(len(page_layout.track_header_bottom_frames), len(page_layout.track_frames))


if __name__ == "__main__":
    unittest.main()
