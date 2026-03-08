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
        key = (unit or "").strip().lower()
        return _UNIT_ALIASES.get(key, (unit or "").strip())

    def convert(self, value: float, from_unit: str | None, to_unit: str | None) -> float:
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
        self.convert(1.0, from_unit, to_unit)


DEFAULT_UNITS = SimpleUnitRegistry()
