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
