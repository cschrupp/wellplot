from __future__ import annotations

import unittest

import numpy as np

from well_log_os import (
    ArrayChannel,
    DatasetValidationError,
    RasterChannel,
    ScalarChannel,
    WellDataset,
)


class ModelValidationTests(unittest.TestCase):
    def test_scalar_channel_rejects_empty_mnemonic(self) -> None:
        depth = np.array([1000.0, 1001.0], dtype=float)
        values = np.array([10.0, 11.0], dtype=float)

        with self.assertRaises(DatasetValidationError):
            ScalarChannel("", depth, "ft", "gAPI", values=values)

    def test_scalar_channel_rejects_missing_depth_unit(self) -> None:
        depth = np.array([1000.0, 1001.0], dtype=float)
        values = np.array([10.0, 11.0], dtype=float)

        with self.assertRaises(DatasetValidationError):
            ScalarChannel("GR", depth, "", "gAPI", values=values)

    def test_scalar_channel_validate_catches_post_init_length_drift(self) -> None:
        depth = np.array([1000.0, 1001.0, 1002.0], dtype=float)
        channel = ScalarChannel("GR", depth, "ft", "gAPI", values=np.array([10.0, 11.0, 12.0]))
        channel.values = np.array([10.0, 11.0], dtype=float)

        with self.assertRaises(DatasetValidationError):
            channel.validate()

    def test_array_channel_validate_catches_sample_axis_drift(self) -> None:
        depth = np.array([1000.0, 1001.0], dtype=float)
        channel = RasterChannel(
            "VDL",
            depth,
            "ft",
            "amplitude",
            values=np.array([[1.0, 2.0], [3.0, 4.0]], dtype=float),
            sample_axis=np.array([200.0, 300.0], dtype=float),
            sample_unit="us",
        )
        channel.sample_axis = np.array([200.0], dtype=float)

        with self.assertRaises(DatasetValidationError):
            channel.validate()

    def test_empty_dataset_is_valid(self) -> None:
        dataset = WellDataset(name="empty")
        dataset.validate()
        self.assertEqual(dataset.channels, {})

    def test_dataset_validate_catches_channel_key_mismatch(self) -> None:
        depth = np.array([1000.0, 1001.0], dtype=float)
        channel = ScalarChannel("GR", depth, "ft", "gAPI", values=np.array([10.0, 11.0]))
        dataset = WellDataset(name="sample")
        dataset.channels["BAD"] = channel

        with self.assertRaises(DatasetValidationError):
            dataset.validate()

    def test_add_channel_validates_before_insert(self) -> None:
        depth = np.array([1000.0, 1001.0], dtype=float)
        channel = ScalarChannel("GR", depth, "ft", "gAPI", values=np.array([10.0, 11.0]))
        channel.values = np.array([10.0], dtype=float)
        dataset = WellDataset(name="sample")

        with self.assertRaises(DatasetValidationError):
            dataset.add_channel(channel)

        self.assertEqual(dataset.channels, {})

    def test_dataset_validate_revalidates_existing_channels(self) -> None:
        depth = np.array([1000.0, 1001.0], dtype=float)
        channel = ScalarChannel("GR", depth, "ft", "gAPI", values=np.array([10.0, 11.0]))
        dataset = WellDataset(name="sample")
        dataset.add_channel(channel)
        channel.depth = np.array([1000.0, 999.0, 1001.0], dtype=float)

        with self.assertRaises(DatasetValidationError):
            dataset.validate()

    def test_array_channel_validation_accepts_raster_contract(self) -> None:
        depth = np.array([1000.0, 1001.0], dtype=float)
        channel = ArrayChannel(
            "WF",
            depth,
            "ft",
            "amplitude",
            values=np.array([[1.0, 2.0], [3.0, 4.0]], dtype=float),
            sample_axis=np.array([200.0, 300.0], dtype=float),
            sample_unit="us",
        )
        channel.validate()


if __name__ == "__main__":
    unittest.main()
