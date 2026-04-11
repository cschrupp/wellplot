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

"""Dataset and channel validation tests."""

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
    """Verify normalized dataset validation rules."""

    def test_scalar_channel_rejects_empty_mnemonic(self) -> None:
        """Reject scalar channels without a mnemonic."""
        depth = np.array([1000.0, 1001.0], dtype=float)
        values = np.array([10.0, 11.0], dtype=float)

        with self.assertRaises(DatasetValidationError):
            ScalarChannel("", depth, "ft", "gAPI", values=values)

    def test_scalar_channel_rejects_missing_depth_unit(self) -> None:
        """Reject scalar channels without a declared index unit."""
        depth = np.array([1000.0, 1001.0], dtype=float)
        values = np.array([10.0, 11.0], dtype=float)

        with self.assertRaises(DatasetValidationError):
            ScalarChannel("GR", depth, "", "gAPI", values=values)

    def test_scalar_channel_validate_catches_post_init_length_drift(self) -> None:
        """Fail validation when scalar values drift away from depth length."""
        depth = np.array([1000.0, 1001.0, 1002.0], dtype=float)
        channel = ScalarChannel("GR", depth, "ft", "gAPI", values=np.array([10.0, 11.0, 12.0]))
        channel.values = np.array([10.0, 11.0], dtype=float)

        with self.assertRaises(DatasetValidationError):
            channel.validate()

    def test_array_channel_validate_catches_sample_axis_drift(self) -> None:
        """Fail validation when raster sample axes no longer match samples."""
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
        """Allow empty datasets to pass validation."""
        dataset = WellDataset(name="empty")
        dataset.validate()
        self.assertEqual(dataset.channels, {})

    def test_dataset_validate_catches_channel_key_mismatch(self) -> None:
        """Fail validation when channel storage keys do not match mnemonics."""
        depth = np.array([1000.0, 1001.0], dtype=float)
        channel = ScalarChannel("GR", depth, "ft", "gAPI", values=np.array([10.0, 11.0]))
        dataset = WellDataset(name="sample")
        dataset.channels["BAD"] = channel

        with self.assertRaises(DatasetValidationError):
            dataset.validate()

    def test_add_channel_validates_before_insert(self) -> None:
        """Reject invalid channels before inserting them into the dataset."""
        depth = np.array([1000.0, 1001.0], dtype=float)
        channel = ScalarChannel("GR", depth, "ft", "gAPI", values=np.array([10.0, 11.0]))
        channel.values = np.array([10.0], dtype=float)
        dataset = WellDataset(name="sample")

        with self.assertRaises(DatasetValidationError):
            dataset.add_channel(channel)

        self.assertEqual(dataset.channels, {})

    def test_dataset_validate_revalidates_existing_channels(self) -> None:
        """Revalidate already-added channels when dataset validation runs."""
        depth = np.array([1000.0, 1001.0], dtype=float)
        channel = ScalarChannel("GR", depth, "ft", "gAPI", values=np.array([10.0, 11.0]))
        dataset = WellDataset(name="sample")
        dataset.add_channel(channel)
        channel.depth = np.array([1000.0, 999.0, 1001.0], dtype=float)

        with self.assertRaises(DatasetValidationError):
            dataset.validate()

    def test_array_channel_validation_accepts_raster_contract(self) -> None:
        """Accept array channels that satisfy the raster data contract."""
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
