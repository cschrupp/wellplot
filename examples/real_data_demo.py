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
