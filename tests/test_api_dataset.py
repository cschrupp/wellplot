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

from __future__ import annotations

import importlib.util
import unittest

import numpy as np

from well_log_os import (
    ArrayChannel,
    DatasetBuilder,
    DatasetValidationError,
    RasterChannel,
    ScalarChannel,
    WellDataset,
    create_dataset,
)

HAS_PANDAS = importlib.util.find_spec("pandas") is not None
if HAS_PANDAS:
    import pandas as pd


class DatasetApiTests(unittest.TestCase):
    def test_create_dataset_copies_metadata_and_provenance(self) -> None:
        well_metadata = {"WELL": "Example-1"}
        provenance = {"source": "notebook"}

        dataset = create_dataset(
            "processed",
            well_metadata=well_metadata,
            provenance=provenance,
        )

        self.assertIsInstance(dataset, WellDataset)
        self.assertEqual(dataset.name, "processed")
        self.assertEqual(dataset.well_metadata, well_metadata)
        self.assertEqual(dataset.provenance, provenance)
        self.assertIsNot(dataset.well_metadata, well_metadata)
        self.assertIsNot(dataset.provenance, provenance)

    def test_dataset_add_curve_uses_index_contract(self) -> None:
        dataset = create_dataset("processed")

        channel = dataset.add_curve(
            mnemonic="PHIE",
            values=[0.12, 0.18, 0.22],
            index=[1000.0, 1000.5, 1001.0],
            index_unit="ft",
            value_unit="v/v",
            description="Effective porosity",
        )

        self.assertIsInstance(channel, ScalarChannel)
        self.assertIs(dataset.get_channel("PHIE"), channel)
        np.testing.assert_allclose(channel.depth, [1000.0, 1000.5, 1001.0])
        np.testing.assert_allclose(channel.values, [0.12, 0.18, 0.22])
        self.assertEqual(channel.depth_unit, "ft")
        self.assertEqual(channel.value_unit, "v/v")

    def test_dataset_add_array_and_raster_create_expected_channel_types(self) -> None:
        dataset = create_dataset("processed")

        array_channel = dataset.add_array(
            mnemonic="WF",
            values=[[1.0, 2.0], [3.0, 4.0]],
            index=[1000.0, 1001.0],
            index_unit="ft",
            sample_axis=[200.0, 300.0],
            sample_unit="us",
            value_unit="amplitude",
        )
        raster_channel = dataset.add_raster(
            mnemonic="VDL",
            values=[[10.0, 20.0], [30.0, 40.0]],
            index=[1000.0, 1001.0],
            index_unit="ft",
            sample_axis=[200.0, 300.0],
            sample_unit="us",
            value_unit="amplitude",
            colormap="gray_r",
        )

        self.assertIsInstance(array_channel, ArrayChannel)
        self.assertEqual(array_channel.sample_unit, "us")
        self.assertIsInstance(raster_channel, RasterChannel)
        self.assertEqual(raster_channel.colormap, "gray_r")

    def test_dataset_add_channel_can_reject_duplicates(self) -> None:
        dataset = create_dataset("processed")
        dataset.add_curve(
            mnemonic="GR",
            values=[10.0, 11.0],
            index=[1000.0, 1001.0],
            index_unit="ft",
            value_unit="gAPI",
        )

        with self.assertRaises(DatasetValidationError):
            dataset.add_curve(
                mnemonic="GR",
                values=[12.0, 13.0],
                index=[1000.0, 1001.0],
                index_unit="ft",
                value_unit="gAPI",
                replace=False,
            )

    def test_dataset_add_or_replace_channel_overwrites_existing(self) -> None:
        dataset = create_dataset("processed")
        dataset.add_curve(
            mnemonic="GR",
            values=[10.0, 11.0],
            index=[1000.0, 1001.0],
            index_unit="ft",
            value_unit="gAPI",
        )
        replacement = ScalarChannel(
            mnemonic="GR",
            depth=np.array([1000.0, 1001.0], dtype=float),
            depth_unit="ft",
            values=np.array([99.0, 100.0], dtype=float),
            value_unit="gAPI",
        )

        dataset.add_or_replace_channel(replacement)

        np.testing.assert_allclose(dataset.get_channel("GR").values, [99.0, 100.0])

    def test_dataset_rename_channel_updates_lookup_key_and_mnemonic(self) -> None:
        dataset = create_dataset("processed")
        dataset.add_curve(
            mnemonic="GR",
            values=[10.0, 11.0],
            index=[1000.0, 1001.0],
            index_unit="ft",
            value_unit="gAPI",
        )

        channel = dataset.rename_channel("GR", "GR_PROC")

        self.assertIs(dataset.get_channel("GR_PROC"), channel)
        self.assertEqual(channel.mnemonic, "GR_PROC")
        self.assertNotIn("GR", dataset.channels)

    def test_dataset_merge_copies_channels_and_can_merge_metadata(self) -> None:
        source = create_dataset(
            "source",
            well_metadata={"FIELD": "North"},
            provenance={"source": "processed"},
        )
        source_channel = source.add_curve(
            mnemonic="GR",
            values=[10.0, 11.0],
            index=[1000.0, 1001.0],
            index_unit="ft",
            value_unit="gAPI",
        )
        target = create_dataset("target", well_metadata={"WELL": "Example-1"})

        target.merge(
            source,
            merge_well_metadata=True,
            merge_provenance=True,
        )
        source_channel.values[0] = 999.0

        np.testing.assert_allclose(target.get_channel("GR").values, [10.0, 11.0])
        self.assertEqual(target.well_metadata["FIELD"], "North")
        self.assertEqual(target.provenance["source"], "processed")
        self.assertEqual(target.provenance["merge_history"][0]["dataset"], "source")

    def test_dataset_merge_rejects_duplicate_channel_without_replace(self) -> None:
        left = create_dataset("left")
        left.add_curve(
            mnemonic="GR",
            values=[10.0, 11.0],
            index=[1000.0, 1001.0],
            index_unit="ft",
            value_unit="gAPI",
        )
        right = create_dataset("right")
        right.add_curve(
            mnemonic="GR",
            values=[20.0, 21.0],
            index=[1000.0, 1001.0],
            index_unit="ft",
            value_unit="gAPI",
        )

        with self.assertRaises(DatasetValidationError):
            left.merge(right, replace=False)

    def test_dataset_merge_can_rename_conflicting_channels_and_record_history(self) -> None:
        left = create_dataset("left")
        left.add_curve(
            mnemonic="GR",
            values=[10.0, 11.0],
            index=[1000.0, 1001.0],
            index_unit="ft",
            value_unit="gAPI",
        )
        right = create_dataset("processed")
        right.add_curve(
            mnemonic="GR",
            values=[20.0, 21.0],
            index=[1000.0, 1001.0],
            index_unit="ft",
            value_unit="gAPI",
        )

        left.merge(right, collision="rename")

        renamed = left.get_channel("GR_processed")
        np.testing.assert_allclose(renamed.values, [20.0, 21.0])
        self.assertEqual(renamed.metadata["merged_from_dataset"], "processed")
        self.assertEqual(renamed.metadata["original_mnemonic"], "GR")
        self.assertEqual(
            left.provenance["merge_history"][0]["renamed"],
            {"GR": "GR_processed"},
        )

    def test_dataset_merge_can_skip_conflicting_channels(self) -> None:
        left = create_dataset("left")
        left.add_curve(
            mnemonic="GR",
            values=[10.0, 11.0],
            index=[1000.0, 1001.0],
            index_unit="ft",
            value_unit="gAPI",
        )
        right = create_dataset("right")
        right.add_curve(
            mnemonic="GR",
            values=[20.0, 21.0],
            index=[1000.0, 1001.0],
            index_unit="ft",
            value_unit="gAPI",
        )
        right.add_curve(
            mnemonic="CBL",
            values=[30.0, 31.0],
            index=[1000.0, 1001.0],
            index_unit="ft",
            value_unit="mV",
        )

        left.merge(right, collision="skip")

        np.testing.assert_allclose(left.get_channel("GR").values, [10.0, 11.0])
        np.testing.assert_allclose(left.get_channel("CBL").values, [30.0, 31.0])
        self.assertEqual(left.provenance["merge_history"][0]["skipped"], ["GR"])

    def test_dataset_builder_merge_supports_collision_policy_and_rename(self) -> None:
        left = create_dataset("left")
        left.add_curve(
            mnemonic="GR",
            values=[10.0, 11.0],
            index=[1000.0, 1001.0],
            index_unit="ft",
            value_unit="gAPI",
        )
        right = create_dataset("qc")
        right.add_curve(
            mnemonic="GR",
            values=[20.0, 21.0],
            index=[1000.0, 1001.0],
            index_unit="ft",
            value_unit="gAPI",
        )

        dataset = (
            DatasetBuilder(name="processed")
            .merge(left)
            .merge(right, collision="rename", rename_template="{mnemonic}_{dataset}")
            .build()
        )

        self.assertIn("GR", dataset.channels)
        self.assertIn("GR_qc", dataset.channels)

    def test_dataset_sort_index_reorders_scalar_and_raster_channels(self) -> None:
        dataset = create_dataset("processed")
        dataset.add_curve(
            mnemonic="GR",
            values=[45.0, 50.0, 55.0],
            index=[1002.0, 1001.0, 1000.0],
            index_unit="ft",
            value_unit="gAPI",
        )
        dataset.add_raster(
            mnemonic="VDL",
            values=[[3.0, 30.0], [2.0, 20.0], [1.0, 10.0]],
            index=[1002.0, 1001.0, 1000.0],
            index_unit="ft",
            sample_axis=[200.0, 300.0],
            sample_unit="us",
            value_unit="amplitude",
        )

        dataset.sort_index()

        np.testing.assert_allclose(dataset.get_channel("GR").depth, [1000.0, 1001.0, 1002.0])
        np.testing.assert_allclose(dataset.get_channel("GR").values, [55.0, 50.0, 45.0])
        np.testing.assert_allclose(
            dataset.get_channel("VDL").values,
            [[1.0, 10.0], [2.0, 20.0], [3.0, 30.0]],
        )

    def test_dataset_convert_index_unit_updates_all_channels(self) -> None:
        dataset = create_dataset("processed")
        dataset.add_curve(
            mnemonic="GR",
            values=[45.0, 50.0],
            index=[1000.0, 1001.0],
            index_unit="ft",
            value_unit="gAPI",
        )

        dataset.convert_index_unit("m")

        channel = dataset.get_channel("GR")
        self.assertEqual(channel.depth_unit, "m")
        np.testing.assert_allclose(channel.depth, [304.8, 305.1048])

    def test_dataset_reindex_to_channel_resamples_scalar_and_array(self) -> None:
        dataset = create_dataset("processed")
        dataset.add_curve(
            mnemonic="BASE",
            values=[10.0, 20.0, 30.0],
            index=[1000.0, 1001.0, 1002.0],
            index_unit="ft",
            value_unit="gAPI",
        )
        dataset.add_curve(
            mnemonic="MID",
            values=[100.0, 200.0],
            index=[1000.0, 1002.0],
            index_unit="ft",
            value_unit="mV",
        )
        dataset.add_raster(
            mnemonic="WF",
            values=[[1.0, 10.0], [3.0, 30.0]],
            index=[1000.0, 1002.0],
            index_unit="ft",
            sample_axis=[200.0, 300.0],
            sample_unit="us",
            value_unit="amplitude",
        )

        dataset.reindex_to(channel="BASE", channels=["MID", "WF"])

        np.testing.assert_allclose(dataset.get_channel("MID").depth, [1000.0, 1001.0, 1002.0])
        np.testing.assert_allclose(dataset.get_channel("MID").values, [100.0, 150.0, 200.0])
        np.testing.assert_allclose(
            dataset.get_channel("WF").values,
            [[1.0, 10.0], [2.0, 20.0], [3.0, 30.0]],
        )

    def test_dataset_builder_exposes_alignment_helpers(self) -> None:
        dataset = (
            DatasetBuilder(name="processed")
            .add_curve(
                mnemonic="GR",
                values=[45.0, 50.0],
                index=[1001.0, 1000.0],
                index_unit="ft",
                value_unit="gAPI",
            )
            .sort_index()
            .convert_index_unit("m")
            .build()
        )

        self.assertEqual(dataset.get_channel("GR").depth_unit, "m")
        np.testing.assert_allclose(dataset.get_channel("GR").depth, [304.8, 305.1048])

    def test_dataset_builder_supports_fluent_ingestion(self) -> None:
        dataset = (
            DatasetBuilder(
                name="processed",
                well_metadata={"WELL": "Example-1"},
                provenance={"source": "notebook"},
            )
            .add_curve(
                mnemonic="PHIE",
                values=[0.12, 0.18],
                index=[1000.0, 1001.0],
                index_unit="ft",
                value_unit="v/v",
            )
            .add_raster(
                mnemonic="VDL",
                values=[[1.0, 2.0], [3.0, 4.0]],
                index=[1000.0, 1001.0],
                index_unit="ft",
                sample_axis=[200.0, 300.0],
                sample_unit="us",
                value_unit="amplitude",
            )
            .build()
        )

        self.assertIsInstance(dataset, WellDataset)
        self.assertIn("PHIE", dataset.channels)
        self.assertIn("VDL", dataset.channels)
        self.assertEqual(dataset.well_metadata["WELL"], "Example-1")
        self.assertEqual(dataset.provenance["source"], "notebook")

    @unittest.skipUnless(HAS_PANDAS, "pandas is not installed")
    def test_dataset_add_series_uses_series_index_by_default(self) -> None:
        dataset = create_dataset("processed")
        series = pd.Series([45.0, 50.0, 55.0], index=[1000.0, 1000.5, 1001.0], name="GR")

        channel = dataset.add_series(
            series=series,
            index_unit="ft",
            value_unit="gAPI",
            description="Gamma ray",
        )

        self.assertIsInstance(channel, ScalarChannel)
        self.assertEqual(channel.mnemonic, "GR")
        np.testing.assert_allclose(channel.depth, [1000.0, 1000.5, 1001.0])
        np.testing.assert_allclose(channel.values, [45.0, 50.0, 55.0])

    @unittest.skipUnless(HAS_PANDAS, "pandas is not installed")
    def test_dataset_add_series_requires_mnemonic_when_series_name_missing(self) -> None:
        dataset = create_dataset("processed")
        series = pd.Series([1.0, 2.0], index=[1000.0, 1001.0])

        with self.assertRaises(DatasetValidationError):
            dataset.add_series(series=series, index_unit="ft")

    @unittest.skipUnless(HAS_PANDAS, "pandas is not installed")
    def test_dataset_add_dataframe_uses_named_index_column(self) -> None:
        dataset = create_dataset("processed")
        frame = pd.DataFrame(
            {
                "DEPTH": [1000.0, 1000.5, 1001.0],
                "GR": [45.0, 50.0, 55.0],
                "PHIE": [0.12, 0.18, 0.2],
            }
        )

        channels = dataset.add_dataframe(
            frame,
            index_column="DEPTH",
            index_unit="ft",
            curves={
                "GR": {"value_unit": "gAPI"},
                "PHIE": {"value_unit": "v/v", "description": "Effective porosity"},
            },
        )

        self.assertEqual([channel.mnemonic for channel in channels], ["GR", "PHIE"])
        np.testing.assert_allclose(dataset.get_channel("GR").depth, [1000.0, 1000.5, 1001.0])
        self.assertEqual(dataset.get_channel("PHIE").description, "Effective porosity")

    @unittest.skipUnless(HAS_PANDAS, "pandas is not installed")
    def test_dataset_add_dataframe_can_use_dataframe_index(self) -> None:
        dataset = create_dataset("processed")
        frame = pd.DataFrame({"GR": [45.0, 50.0], "CBL": [10.0, 12.0]}, index=[1000.0, 1001.0])

        dataset.add_dataframe(
            frame,
            use_index=True,
            index_unit="ft",
            curves={
                "GR": {"value_unit": "gAPI"},
                "CBL": {"value_unit": "mV", "mnemonic": "CBL_RAW"},
            },
        )

        self.assertIn("GR", dataset.channels)
        self.assertIn("CBL_RAW", dataset.channels)
        np.testing.assert_allclose(dataset.get_channel("CBL_RAW").depth, [1000.0, 1001.0])

    @unittest.skipUnless(HAS_PANDAS, "pandas is not installed")
    def test_dataset_add_dataframe_requires_explicit_index_selection(self) -> None:
        dataset = create_dataset("processed")
        frame = pd.DataFrame({"DEPTH": [1000.0, 1001.0], "GR": [45.0, 50.0]})

        with self.assertRaises(DatasetValidationError):
            dataset.add_dataframe(frame, index_unit="ft")

        with self.assertRaises(DatasetValidationError):
            dataset.add_dataframe(frame, index_unit="ft", use_index=True, index_column="DEPTH")

    @unittest.skipUnless(HAS_PANDAS, "pandas is not installed")
    def test_dataset_builder_supports_series_and_dataframe_ingestion(self) -> None:
        series = pd.Series([45.0, 50.0], index=[1000.0, 1001.0], name="GR")
        frame = pd.DataFrame(
            {
                "DEPTH": [1000.0, 1001.0],
                "PHIE": [0.12, 0.18],
            }
        )

        dataset = (
            DatasetBuilder(name="processed")
            .add_series(series=series, index_unit="ft", value_unit="gAPI")
            .add_dataframe(
                frame,
                index_column="DEPTH",
                index_unit="ft",
                curves={"PHIE": {"value_unit": "v/v"}},
            )
            .build()
        )

        self.assertIn("GR", dataset.channels)
        self.assertIn("PHIE", dataset.channels)


if __name__ == "__main__":
    unittest.main()
