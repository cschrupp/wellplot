#!/usr/bin/env python3
"""Export split-aware SFT JSONL from gold cases (development/validation only).

SLM-03: only trainable support levels
(d5_current, d5_context_lowerable, envelope_only) are emitted.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from benchmark.fixture_loader import load_fixture  # noqa: E402

TRAINABLE = frozenset({"d5_current", "d5_context_lowerable", "envelope_only"})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["development", "validation"], default="development")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--include-all-support-levels",
        action="store_true",
        help="Disable trainable-only filter (debug).",
    )
    args = parser.parse_args()

    split_ids = set(
        json.loads((ROOT / "benchmark" / "splits" / f"{args.split}.json").read_text())["case_ids"]
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    skipped_support = 0
    with args.out.open("w", encoding="utf-8") as out_fh:
        for line in (ROOT / "benchmark" / "gold" / "cases.jsonl").open(encoding="utf-8"):
            case = json.loads(line)
            if case["case_id"] not in split_ids:
                continue
            level = (case.get("grounding") or {}).get("support_level")
            if not args.include_all_support_levels and level not in TRAINABLE:
                skipped_support += 1
                continue
            fix = load_fixture(case["fixture"])
            for utt in case["utterances"]:
                row = {
                    "case_id": case["case_id"],
                    "split": args.split,
                    "support_level": level,
                    "semantic_family": case.get("semantic_family"),
                    "utterance": utt["text"],
                    "workspace": fix["workspace"],
                    "d0": fix["d0"],
                    "output": case["gold"],
                }
                out_fh.write(json.dumps(row, sort_keys=True) + "\n")
                n += 1
    print(
        json.dumps(
            {
                "split": args.split,
                "rows": n,
                "skipped_non_trainable_cases": skipped_support,
                "out": str(args.out),
            }
        )
    )


if __name__ == "__main__":
    main()
