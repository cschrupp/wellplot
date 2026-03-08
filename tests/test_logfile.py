from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from well_log_os.errors import TemplateValidationError
from well_log_os.logfile import build_document_for_logfile, logfile_from_mapping
from well_log_os.model import ScalarChannel, WellDataset


def build_mapping() -> dict:
    return {
        "version": 1,
        "name": "Test Logfile",
        "data": {"source_path": "sample.las", "source_format": "auto"},
        "render": {"backend": "matplotlib", "output_path": "out.pdf", "dpi": 300},
        "document": {
            "name": "{WELL} Layout",
            "page": {"size": "A4", "continuous": True},
            "depth": {"unit": "m", "scale": "1:200", "major_step": 20, "minor_step": 5},
            "header": {
                "title": "{WELL}",
                "subtitle": "{SOURCE_FILENAME}",
                "fields": [{"label": "Well", "source_key": "WELL"}],
            },
            "footer": {"lines": ["Generated from {SOURCE_FILENAME}"]},
            "markers": [],
            "zones": [],
        },
        "auto_tracks": {
            "on_missing": "skip",
            "max_tracks": 2,
            "depth_track": {"id": "depth", "title": "Depth", "width_mm": 16},
            "tracks": [
                {
                    "channel": "GR",
                    "configure": {
                        "id": "gr",
                        "width_mm": 28,
                        "title_template": "{mnemonic} [{unit}]",
                        "style": {
                            "color": "#1b5e20",
                            "line_width": 0.9,
                            "line_style": "-",
                            "opacity": 1.0,
                        },
                        "grid": {
                            "major": True,
                            "minor": True,
                            "major_alpha": 0.35,
                            "minor_alpha": 0.15,
                        },
                        "scale": {
                            "kind": "auto",
                            "percentile_low": 2,
                            "percentile_high": 98,
                            "log_ratio_threshold": 200,
                            "min_positive": 1e-6,
                        },
                    },
                },
                {
                    "channel": "RT",
                    "configure": {
                        "id": "rt",
                        "width_mm": 28,
                        "title_template": "{mnemonic} [{unit}]",
                        "style": {
                            "color": "#0d47a1",
                            "line_width": 0.9,
                            "line_style": "-",
                            "opacity": 1.0,
                        },
                        "grid": {
                            "major": True,
                            "minor": True,
                            "major_alpha": 0.35,
                            "minor_alpha": 0.15,
                        },
                        "scale": {
                            "kind": "auto",
                            "percentile_low": 2,
                            "percentile_high": 98,
                            "log_ratio_threshold": 200,
                            "min_positive": 1e-6,
                        },
                    },
                },
            ],
        },
    }


class LogFileTests(unittest.TestCase):
    def build_dataset(self) -> WellDataset:
        depth = np.linspace(1000.0, 1020.0, 50)
        dataset = WellDataset(name="sample", well_metadata={"WELL": "TEST-1"})
        dataset.add_channel(
            ScalarChannel("GR", depth, "m", "gAPI", values=np.linspace(20, 120, depth.size))
        )
        dataset.add_channel(
            ScalarChannel(
                "RT", depth, "m", "ohm.m", values=np.exp(np.linspace(0.1, 5.0, depth.size))
            )
        )
        return dataset

    def test_logfile_builds_document_without_hardcoded_tracks(self) -> None:
        spec = logfile_from_mapping(build_mapping())
        document = build_document_for_logfile(
            spec,
            self.build_dataset(),
            source_path=Path("example_input.las"),
        )
        self.assertEqual(document.name, "TEST-1 Layout")
        self.assertEqual(document.header.title, "TEST-1")
        self.assertEqual(document.header.subtitle, "example_input.las")
        self.assertEqual(len(document.tracks), 3)  # depth + 2 selected scalar tracks
        self.assertEqual(document.tracks[1].elements[0].channel, "GR")
        self.assertEqual(document.tracks[2].elements[0].channel, "RT")

    def test_invalid_logfile_configuration_raises(self) -> None:
        payload = build_mapping()
        del payload["auto_tracks"]["tracks"][0]["configure"]["style"]["color"]
        with self.assertRaises(TemplateValidationError):
            logfile_from_mapping(payload)


if __name__ == "__main__":
    unittest.main()
