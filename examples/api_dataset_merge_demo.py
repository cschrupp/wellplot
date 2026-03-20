from __future__ import annotations

from well_log_os import DatasetBuilder, create_dataset


def build_raw_dataset():
    dataset = create_dataset(
        "raw",
        well_metadata={"WELL": "API Demo 1"},
        provenance={"source": "raw-file"},
    )
    dataset.add_curve(
        mnemonic="GR",
        values=[70.0, 74.0, 81.0],
        index=[8200.0, 8210.0, 8220.0],
        index_unit="ft",
        value_unit="gAPI",
        source="dlis",
    )
    dataset.add_curve(
        mnemonic="CBL",
        values=[18.0, 21.0, 24.0],
        index=[8200.0, 8210.0, 8220.0],
        index_unit="ft",
        value_unit="mV",
        source="dlis",
    )
    return dataset


def build_processed_dataset():
    dataset = create_dataset(
        "qc",
        provenance={"source": "notebook"},
    )
    dataset.add_curve(
        mnemonic="GR",
        values=[72.0, 76.0, 79.0],
        index=[8200.0, 8210.0, 8220.0],
        index_unit="ft",
        value_unit="gAPI",
        source="moving-average",
    )
    dataset.add_curve(
        mnemonic="CBL_QC",
        values=[1.0, 0.0, 1.0],
        index=[8200.0, 8210.0, 8220.0],
        index_unit="ft",
        value_unit="flag",
        source="qc-mask",
    )
    return dataset


def main() -> None:
    merged = (
        DatasetBuilder(name="merged")
        .merge(build_raw_dataset(), merge_well_metadata=True, merge_provenance=True)
        .merge(
            build_processed_dataset(),
            collision="rename",
            rename_template="{mnemonic}_{dataset}",
        )
        .build()
    )

    print("Merged channels:", sorted(merged.channels))
    print("Merge history:", merged.provenance["merge_history"])
    print(
        "Renamed channel metadata:",
        merged.get_channel("GR_qc").metadata,
    )


if __name__ == "__main__":
    main()
