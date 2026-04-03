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

import argparse
from pathlib import Path

from well_log_os import render_from_logfile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a well log from a log-file YAML configuration."
    )
    parser.add_argument(
        "logfile",
        nargs="?",
        default=Path(__file__).with_name("cbl_main.log.yaml"),
        type=Path,
        help="Path to log-file YAML (default: examples/cbl_main.log.yaml).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logfile_path = args.logfile.resolve()
    result = render_from_logfile(logfile_path)
    if result.output_path is not None:
        print(result.output_path)
    else:
        print("Render completed.")


if __name__ == "__main__":
    main()
