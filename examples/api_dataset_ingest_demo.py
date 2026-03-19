from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from well_log_os import DatasetBuilder, create_dataset


def main() -> None:
    depth_ft = np.linspace(8200.0, 8460.0, 261)
    sample_axis_us = np.linspace(200.0, 1200.0, 128)

    gr = 70.0 + 18.0 * np.sin((depth_ft - depth_ft.min()) / 18.0)
    cbl = 22.0 + 9.0 * np.cos((depth_ft - depth_ft.min()) / 27.0)
    tt = 280.0 + 18.0 * np.sin((depth_ft - depth_ft.min()) / 32.0 + 0.6)

    wave = []
    depth_phase = (depth_ft - depth_ft.min()) / 48.0
    for phase in depth_phase:
        trace = (
            0.9 * np.sin(sample_axis_us / 31.0 + phase)
            + 0.35 * np.sin(sample_axis_us / 11.0 - phase * 1.7)
            + 0.15 * np.cos(sample_axis_us / 73.0 + phase * 0.8)
        )
        wave.append(trace)
    wave = np.asarray(wave, dtype=float)

    raw_frame = pd.DataFrame(
        {
            "DEPTH": depth_ft,
            "GR": gr,
            "CBL": cbl,
            "TT": tt,
        }
    )
    raw = create_dataset(
        "synthetic_raw",
        well_metadata={
            "WELL": "API Demo 1",
            "FIELD": "Notebook",
        },
        provenance={"source": "synthetic-demo"},
    )
    raw.add_dataframe(
        raw_frame,
        index_column="DEPTH",
        index_unit="ft",
        curves={
            "GR": {"value_unit": "gAPI", "description": "Gamma ray"},
            "CBL": {"value_unit": "mV", "description": "CBL amplitude"},
            "TT": {"value_unit": "us", "description": "Transit time"},
        },
    )

    cbl_norm_series = pd.Series(
        np.clip(cbl / 40.0, 0.0, 1.0),
        index=depth_ft,
        name="CBL_NORM",
    )

    processed = (
        DatasetBuilder(
            name="processed",
            provenance={"source": "derived-in-notebook"},
        )
        .add_series(
            series=cbl_norm_series,
            index_unit="ft",
            value_unit="fraction",
            description="Normalized CBL amplitude",
        )
        .add_raster(
            mnemonic="VDL_SYN",
            values=wave,
            index=depth_ft,
            index_unit="ft",
            sample_axis=sample_axis_us,
            sample_unit="us",
            value_unit="amplitude",
            description="Synthetic VDL-like panel",
            colormap="gray_r",
        )
        .build()
    )

    combined = create_dataset(
        "combined_demo",
        well_metadata=raw.well_metadata,
        provenance={"source": "merged-demo"},
    )
    combined.merge(raw, merge_well_metadata=True, merge_provenance=True)
    combined.merge(processed, replace=False, merge_provenance=True)
    combined.validate()

    print("Dataset:", combined.name)
    print("Channels:", ", ".join(sorted(combined.channels)))
    print("Depth range (ft):", combined.depth_range("ft"))

    fig, axes = plt.subplots(
        1,
        3,
        figsize=(8.5, 7.0),
        sharey=True,
        constrained_layout=True,
    )

    axes[0].plot(combined.get_channel("GR").values, depth_ft, color="forestgreen", linewidth=1.0)
    axes[0].set_title("GR")
    axes[0].set_xlabel("gAPI")
    axes[0].set_ylabel("Depth (ft)")
    axes[0].grid(True, alpha=0.2)

    axes[1].plot(combined.get_channel("CBL").values, depth_ft, color="black", linewidth=1.0)
    axes[1].plot(
        combined.get_channel("CBL_NORM").values * 40.0,
        depth_ft,
        color="royalblue",
        linewidth=1.0,
        linestyle="--",
    )
    axes[1].set_title("CBL / CBL_NORM")
    axes[1].set_xlabel("mV")
    axes[1].grid(True, alpha=0.2)

    raster = combined.get_channel("VDL_SYN")
    axes[2].imshow(
        raster.values,
        cmap=raster.colormap,
        aspect="auto",
        interpolation="nearest",
        extent=[
            raster.sample_axis.min(),
            raster.sample_axis.max(),
            depth_ft.max(),
            depth_ft.min(),
        ],
    )
    axes[2].set_title("VDL_SYN")
    axes[2].set_xlabel("Time (us)")

    for axis in axes:
        axis.invert_yaxis()

    output_path = Path("workspace/renders/api_dataset_ingest_demo.png")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)
    print("Saved:", output_path)


if __name__ == "__main__":
    main()
