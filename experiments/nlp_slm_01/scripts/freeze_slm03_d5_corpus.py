#!/usr/bin/env python3
"""Freeze SLM-03 D5-grounded 300 corpus (gold, schema, fixtures, splits).

Does not train. Archives of 1.0 artifacts must already exist under
benchmark/archive/slm01_well_ir_1_0/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
EXPORTS = ROOT / "artifacts" / "exports"
ZIP_DEFAULT = EXPORTS / "wellplot_slm01_d5_grounded_300_r1.zip"
EXTRACT = EXPORTS / "_d5_r1_extract"

TRAINABLE = frozenset({"d5_current", "d5_context_lowerable", "envelope_only"})
D5_SHA = "560ec48d2b2809ed2feb55467da15195f527ec44"
SPLIT_SEED = 20251013


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def support_level(case: dict[str, Any], gap_by_id: dict[str, dict[str, Any]]) -> str | None:
    g = case.get("grounding")
    if isinstance(g, dict) and g.get("support_level"):
        return str(g["support_level"])
    gap = case.get("gap")
    if isinstance(gap, dict) and gap.get("support_level"):
        return str(gap["support_level"])
    alt = gap_by_id.get(case["case_id"])
    if alt:
        gg = alt.get("gap") or {}
        if gg.get("support_level"):
            return str(gg["support_level"])
    return None


def normalize_case(
    case: dict[str, Any], gap_by_id: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Ensure every row has grounding.support_level; fold gap metadata when needed."""
    out = dict(case)
    gap_src = out.get("gap") if isinstance(out.get("gap"), dict) else None
    if gap_src is None and case["case_id"] in gap_by_id:
        gap_src = gap_by_id[case["case_id"]].get("gap")
        if gap_src and "gap" not in out:
            out["gap"] = gap_src
        # Prefer gap file fields that may be richer
        for key in ("leakage_group", "provenance"):
            if key not in out and key in gap_by_id[case["case_id"]]:
                out[key] = gap_by_id[case["case_id"]][key]

    level = support_level(out, gap_by_id)
    grounding = dict(out["grounding"]) if isinstance(out.get("grounding"), dict) else {}
    grounding.setdefault("audit_revision", "d5-grounded-300-r1")
    grounding.setdefault("d5_ref", "d5/single-engine-convergence")
    grounding.setdefault("d5_sha", D5_SHA)
    if level:
        grounding["support_level"] = level
    if gap_src and gap_src.get("lowering_contract"):
        grounding.setdefault("lowering_contract", gap_src["lowering_contract"])
    if case["case_id"].startswith("D5GAP"):
        grounding.setdefault("fixture_validation", "state_validated_against_d5_manifest")
    else:
        grounding.setdefault(
            "fixture_validation", "contract_audited_original_fixture_manifest_unavailable"
        )
    out["grounding"] = grounding
    return out


def extract_zip(zip_path: Path) -> Path:
    EXTRACT.mkdir(parents=True, exist_ok=True)
    with ZipFile(zip_path) as zf:
        zf.extractall(EXTRACT)
    return EXTRACT


def install_schema(src_dir: Path) -> Path:
    schema_src = src_dir / "well_ir_1_2_candidate.schema.json"
    dest = ROOT / "benchmark" / "schema" / "well_ir_1_2_candidate.schema.json"
    dest.write_text(schema_src.read_text(encoding="utf-8"), encoding="utf-8")
    # Sole active schema pointer used by tooling that still looks for well_ir_v1.json name
    active = ROOT / "benchmark" / "schema" / "well_ir_v1.json"
    active.write_text(
        json.dumps(
            {
                "comment": "SLM-03 freeze: active schema is well_ir_1_2_candidate.schema.json",
                "active_schema": "well_ir_1_2_candidate.schema.json",
                "well_ir_version": "1.2-candidate",
                "d5_sha": D5_SHA,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return dest


def install_fixtures(src_dir: Path) -> list[str]:
    man = json.loads((src_dir / "wellplot_slm01_d5_fixture_manifest_r1.json").read_text())
    fixtures = man["fixtures"]
    out_ids: list[str] = []
    fx_dir = ROOT / "benchmark" / "fixtures"
    for fid, payload in fixtures.items():
        dest = fx_dir / f"{fid}.json"
        # As authored, plus thin wrapper markers for loaders
        body = {
            "fixture_format": "d5_semantic_manifest_r1",
            "d5_ref": man.get("d5_ref"),
            "d5_sha": man.get("d5_sha"),
            "manifest": payload,
        }
        dest.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        out_ids.append(fid)
    return sorted(out_ids)


def install_gold(src_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    gap_by_id = {
        r["case_id"]: r
        for r in (
            json.loads(l)
            for l in (src_dir / "wellplot_slm01_d5_gap_cases_148_r1.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if l.strip()
        )
    }
    rows = [
        normalize_case(json.loads(l), gap_by_id)
        for l in (src_dir / "wellplot_slm01_d5_grounded_300_r1.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if l.strip()
    ]
    assert len(rows) == 300, len(rows)
    gold_path = ROOT / "benchmark" / "gold" / "cases.jsonl"
    with gold_path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")

    levels = Counter(r["grounding"]["support_level"] for r in rows)
    families = Counter(r["semantic_family"] for r in rows)
    statuses = Counter(r["gold"]["status"] for r in rows)
    meta = {
        "revision": "d5-grounded-300-r1",
        "n_cases": 300,
        "well_ir_version": "1.2-candidate",
        "d5_ref": "d5/single-engine-convergence",
        "d5_sha": D5_SHA,
        "support_levels": dict(levels),
        "families": dict(families),
        "statuses": dict(statuses),
        "trainable_support_levels": sorted(TRAINABLE),
        "n_trainable": sum(levels[k] for k in TRAINABLE),
        "gold_sha256": sha256_file(gold_path),
    }
    (ROOT / "benchmark" / "gold" / "corpus_meta.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return rows, meta


def stratified_splits(
    rows: list[dict[str, Any]], *, seed: int = SPLIT_SEED
) -> dict[str, list[str]]:
    """~70% / 15% / 15% by (semantic_family, support_level)."""
    rng = random.Random(seed)
    buckets: dict[tuple[str, str], list[str]] = defaultdict(list)
    for r in rows:
        key = (r["semantic_family"], r["grounding"]["support_level"])
        buckets[key].append(r["case_id"])

    splits = {"development": [], "validation": [], "held_out": []}
    for key, ids in sorted(buckets.items()):
        rng.shuffle(ids)
        n = len(ids)
        if n == 1:
            # Prefer development for singleton strata
            splits["development"].append(ids[0])
            continue
        if n == 2:
            splits["development"].append(ids[0])
            splits["held_out"].append(ids[1])
            continue
        n_val = max(1, round(n * 0.15))
        n_hold = max(1, round(n * 0.15))
        # Keep development majority; shrink val/hold if needed
        while n_val + n_hold >= n:
            if n_val >= n_hold and n_val > 1:
                n_val -= 1
            elif n_hold > 1:
                n_hold -= 1
            else:
                n_hold = 0
                break
        n_dev = n - n_val - n_hold
        splits["development"].extend(ids[:n_dev])
        splits["validation"].extend(ids[n_dev : n_dev + n_val])
        splits["held_out"].extend(ids[n_dev + n_val :])

    for name in splits:
        splits[name] = sorted(splits[name])
    assert sum(len(v) for v in splits.values()) == 300
    assert len(set(splits["development"]) & set(splits["validation"])) == 0
    assert len(set(splits["development"]) & set(splits["held_out"])) == 0
    assert len(set(splits["validation"]) & set(splits["held_out"])) == 0
    return splits


def write_splits(splits: dict[str, list[str]]) -> None:
    split_dir = ROOT / "benchmark" / "splits"
    for name, ids in splits.items():
        path = split_dir / f"{name}.json"
        path.write_text(
            json.dumps({"split": name, "case_ids": ids, "n": len(ids)}, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", type=Path, default=ZIP_DEFAULT)
    args = parser.parse_args()
    if not args.zip.exists():
        raise SystemExit(f"missing zip: {args.zip}")

    src = extract_zip(args.zip)
    schema_path = install_schema(src)
    fixture_ids = install_fixtures(src)
    rows, meta = install_gold(src)
    splits = stratified_splits(rows)
    write_splits(splits)

    # Copy coverage + review beside gold for provenance
    for name in (
        "wellplot_slm01_d5_coverage_matrix_r1.json",
        "wellplot_slm01_d5_300_review.md",
        "wellplot_slm01_d5_fixture_manifest_r1.json",
    ):
        (ROOT / "benchmark" / "gold" / name).write_text(
            (src / name).read_text(encoding="utf-8"), encoding="utf-8"
        )

    summary = {
        "ok": True,
        "meta": meta,
        "schema": str(schema_path),
        "fixtures_installed": fixture_ids,
        "splits": {k: len(v) for k, v in splits.items()},
        "trainable_in_splits": {
            split: sum(
                1
                for r in rows
                if r["case_id"] in set(splits[split])
                and r["grounding"]["support_level"] in TRAINABLE
            )
            for split in splits
        },
        "zip_sha256": sha256_file(args.zip),
    }
    out = EXPORTS / "slm03_freeze_summary.json"
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
