from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
