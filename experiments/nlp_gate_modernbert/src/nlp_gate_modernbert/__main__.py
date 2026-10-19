"""CLI: python -m nlp_gate_modernbert <command>"""

from __future__ import annotations

import json
import sys


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in {"-h", "--help"}:
        print(
            "usage: python -m nlp_gate_modernbert "
            "{mb01-publish|mb02-normalize|mb02-replay}"
        )
        return 0
    cmd = argv[0]
    if cmd == "mb01-publish":
        from nlp_gate_modernbert.mb01_audit import publish_mb01_deliverables

        hashes = publish_mb01_deliverables()
        print(json.dumps({"status": "ok", "hashes": hashes}, indent=2))
        return 0
    if cmd == "mb02-normalize":
        from nlp_gate_modernbert.mb02.normalize.generate import generate_normalized_requests

        print(json.dumps(generate_normalized_requests(), indent=2))
        return 0
    if cmd == "mb02-replay":
        from nlp_gate_modernbert.mb02.replay import run_replay

        print(json.dumps(run_replay(), indent=2))
        return 0
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
