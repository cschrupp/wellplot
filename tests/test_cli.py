from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from well_log_os.cli import main
from well_log_os.errors import TemplateValidationError


class CLITests(unittest.TestCase):
    @patch("well_log_os.cli.load_logfile")
    def test_validate_command_success(self, mock_load_logfile) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["validate", "examples/cbl_main.log.yaml"])

        self.assertEqual(code, 0)
        mock_load_logfile.assert_called_once_with(Path("examples/cbl_main.log.yaml"))
        self.assertIn("Valid logfile", stdout.getvalue())
        self.assertEqual("", stderr.getvalue())

    @patch("well_log_os.cli.load_logfile")
    def test_validate_command_schema_error(self, mock_load_logfile) -> None:
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
