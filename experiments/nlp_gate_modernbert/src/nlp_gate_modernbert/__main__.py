"""CLI: python -m nlp_gate_modernbert mb01-publish"""

from __future__ import annotations

import json
import sys


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in {"-h", "--help"}:
        print("usage: python -m nlp_gate_modernbert mb01-publish")
        return 0
    cmd = argv[0]
    if cmd == "mb01-publish":
        from nlp_gate_modernbert.mb01_audit import publish_mb01_deliverables

        hashes = publish_mb01_deliverables()
        print(json.dumps({"status": "ok", "hashes": hashes}, indent=2))
        return 0
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
