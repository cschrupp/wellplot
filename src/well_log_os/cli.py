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

"""Command-line entry points for well_log_os."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from .errors import TemplateValidationError
from .logfile import load_logfile
from .pipeline import render_from_logfile


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level command-line parser."""
    parser = argparse.ArgumentParser(
        prog="well-log-os", description="well_log_os command-line tools"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    render_parser = subparsers.add_parser("render", help="Render output from a log-file YAML")
    render_parser.add_argument("logfile", type=Path, help="Path to log-file YAML")
    render_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Optional output override path",
    )

    validate_parser = subparsers.add_parser("validate", help="Validate a log-file YAML")
    validate_parser.add_argument("logfile", type=Path, help="Path to log-file YAML")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface and return a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "render":
        result = render_from_logfile(args.logfile, output_path=args.output)
        if result.output_path is not None:
            print(result.output_path)
        else:
            print("Render completed.")
        return 0
    if args.command == "validate":
        try:
            load_logfile(args.logfile)
        except TemplateValidationError as exc:
            print(exc, file=sys.stderr)
            return 1
        except OSError as exc:
            print(f"Failed to read logfile: {exc}", file=sys.stderr)
            return 1
        print(f"Valid logfile: {args.logfile}")
        return 0
    parser.error(f"Unsupported command {args.command!r}.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
