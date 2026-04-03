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

from pathlib import Path

import numpy as np

from ..errors import DependencyUnavailableError
from ..model import ScalarChannel, WellDataset

_DEPTH_MNEMONICS = {"DEPT", "DEPTH", "MD", "TDEP"}


def load_las(path: str | Path) -> WellDataset:
    try:
        import lasio
    except ImportError as exc:
        raise DependencyUnavailableError(
            "LAS ingestion requires lasio. Install well-log-os[las]."
        ) from exc

    las_path = Path(path)
    las = lasio.read(str(las_path))
    depth = np.asarray(las.index, dtype=float)
    depth_unit = getattr(getattr(las, "index_unit", None), "strip", lambda: "")() or getattr(
        las.curves[0], "unit", "m"
    )

    well_metadata = {}
    if "Well" in las.sections:
        for item in las.sections["Well"]:
            well_metadata[item.mnemonic] = item.value

    dataset = WellDataset(
        name=str(well_metadata.get("WELL") or las_path.stem),
        well_metadata=well_metadata,
        provenance={"source_path": str(las_path), "format": "LAS"},
    )

    for curve in las.curves:
        mnemonic = curve.mnemonic
        values = np.asarray(las[curve.mnemonic], dtype=float)
        if mnemonic.upper() in _DEPTH_MNEMONICS and np.allclose(values, depth, equal_nan=True):
            continue
        dataset.add_channel(
            ScalarChannel(
                mnemonic=mnemonic,
                depth=depth,
                depth_unit=depth_unit or "m",
                values=values,
                value_unit=curve.unit or None,
                description=curve.descr or "",
                null_value=getattr(las, "null", None),
                source=str(las_path),
                metadata={"original_mnemonic": mnemonic},
            )
        )

    return dataset
