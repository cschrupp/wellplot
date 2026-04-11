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

"""Strict unit conversion helpers used by layout and dataset alignment."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import UnitConversionError

_UNIT_ALIASES = {
    "": "",
    "1": "1",
    "m": "m",
    "meter": "m",
    "meters": "m",
    "metre": "m",
    "metres": "m",
    "ft": "ft",
    "foot": "ft",
    "feet": "ft",
    "in": "in",
    "inch": "in",
    "inches": "in",
    "cm": "cm",
    "centimeter": "cm",
    "centimeters": "cm",
    "centimetre": "cm",
    "centimetres": "cm",
    "mm": "mm",
    "millimeter": "mm",
    "millimeters": "mm",
    "millimetre": "mm",
    "millimetres": "mm",
}

_LENGTH_TO_MM = {
    "mm": 1.0,
    "cm": 10.0,
    "m": 1000.0,
    "in": 25.4,
    "ft": 304.8,
}


@dataclass(slots=True)
class SimpleUnitRegistry:
    """Small strict registry for physical layout and depth conversions.

    The registry only converts known length units. Any unsupported conversion
    fails loudly instead of guessing.
    """

    def normalize(self, unit: str | None) -> str:
        """Return the canonical symbol for a known unit alias."""
        key = (unit or "").strip().lower()
        return _UNIT_ALIASES.get(key, (unit or "").strip())

    def convert(self, value: float, from_unit: str | None, to_unit: str | None) -> float:
        """Convert a scalar value between supported units."""
        source = self.normalize(from_unit)
        target = self.normalize(to_unit)
        if source == target:
            return value
        if source in _LENGTH_TO_MM and target in _LENGTH_TO_MM:
            return value * _LENGTH_TO_MM[source] / _LENGTH_TO_MM[target]
        raise UnitConversionError(
            f"Unsupported conversion from {from_unit!r} to {to_unit!r}. "
            "Only known length conversions are enabled in the core package."
        )

    def ensure_compatible(self, from_unit: str | None, to_unit: str | None) -> None:
        """Raise if two units cannot be converted by the registry."""
        self.convert(1.0, from_unit, to_unit)


DEFAULT_UNITS = SimpleUnitRegistry()
