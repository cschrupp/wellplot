from __future__ import annotations

import unittest

from well_log_os.errors import UnitConversionError
from well_log_os.units import DEFAULT_UNITS


class UnitRegistryTests(unittest.TestCase):
    def test_length_conversion_ft_to_m(self) -> None:
        converted = DEFAULT_UNITS.convert(100.0, "ft", "m")
        self.assertAlmostEqual(converted, 30.48, places=6)

    def test_unknown_conversion_raises(self) -> None:
        with self.assertRaises(UnitConversionError):
            DEFAULT_UNITS.convert(1.0, "gAPI", "m")


if __name__ == "__main__":
    unittest.main()
