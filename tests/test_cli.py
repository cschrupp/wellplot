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

"""CLI validation command tests."""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from wellplot.cli import main
from wellplot.errors import TemplateValidationError


class CLITests(unittest.TestCase):
    """Verify the CLI validation command behavior."""

    @patch("wellplot.cli.load_logfile")
    def test_validate_command_success(self, mock_load_logfile: Mock) -> None:
        """Return success when the logfile validates cleanly."""
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["validate", "examples/cbl_main.log.yaml"])

        self.assertEqual(code, 0)
        mock_load_logfile.assert_called_once_with(Path("examples/cbl_main.log.yaml"))
        self.assertIn("Valid logfile", stdout.getvalue())
        self.assertEqual("", stderr.getvalue())

    @patch("wellplot.cli.load_logfile")
    def test_validate_command_schema_error(self, mock_load_logfile: Mock) -> None:
        """Return failure when validation raises a template error."""
        mock_load_logfile.side_effect = TemplateValidationError("bad schema")
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["validate", "broken.log.yaml"])

        self.assertEqual(code, 1)
        self.assertEqual("", stdout.getvalue())
        self.assertIn("bad schema", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
