"""Offline decomposition of the frozen CM-56R6 semantic evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path

EXPERIMENT_VERSION = "CM-56R7"
BASELINE_SHA = "3ea8484"
SOURCE_EXPERIMENT = "CM-56R6"
DEFAULT_EVIDENCE_PATH = Path("/tmp/cm56r6-authoritative-qwen-rerun.jsonl")
DEFAULT_CORPUS_PATH = Path("tests/fixtures/typed_worker/cm56_shadow_cases.json")
EXPECTED_EVIDENCE_SHA256 = "bf59a618dbff03b4a529e0f3d484e22c04c74a6eb7203ac3410142c30d50a8ff"
EXPECTED_CORPUS_SHA256 = "4ebae0b37defbdf38bcb743f3332ed930b5d260bffc283473405cafdb4ea327e"
EXPECTED_CASE_COUNTS = {
    "scalar_linear": 3,
    "reverse_scale": 3,
    "generic_raster": 3,
    "waveform": 3,
    "cbl_continuity": 3,
    "vdl_sample_axis": 3,
}

VARIANTS = ("A", "C")
FAMILIES = (
    "labels",
    "source_grounding",
    "track_topology",
    "binding_topology",
    "track_scale",
    "binding_scale",
    "raster_profile",
    "sample_axis",
)
SCIENTIFIC_FAMILIES = frozenset({"track_scale", "binding_scale", "raster_profile", "sample_axis"})
TOPOLOGY_FAMILIES = frozenset({"track_topology", "binding_topology"})
LABEL_FAMILIES = frozenset({"labels"})
NON_SCIENTIFIC_FAMILIES = frozenset(
    {"labels", "source_grounding", "track_topology", "binding_topology"}
)


class EvidenceIntegrityError(ValueError):
    """The frozen R6 evidence cannot support deterministic analysis."""


def sha256_bytes(value: bytes) -> str:
    """Return a deterministic SHA-256 digest."""
    return hashlib.sha256(value).hexdigest()


def _rate(numerator: int, denominator: int) -> dict[str, object]:
    """Represent a rate with an explicit numerator and denominator."""
    return {
        "numerator": numerator,
        "denominator": denominator,
        "percent": round(100 * numerator / denominator, 2) if denominator else None,
    }


def _load_jsonl(path: Path) -> tuple[bytes, list[dict[str, object]]]:
    """Load JSONL without retaining or reconstructing provider content."""
    raw = path.read_bytes()
    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            raise EvidenceIntegrityError(f"Blank evidence line at {line_number}.")
        value = json.loads(line)
        if not isinstance(value, dict):
            raise EvidenceIntegrityError(f"Evidence line {line_number} is not an object.")
        rows.append(value)
    return raw, rows


def verify_evidence_integrity(
    evidence_path: Path,
    corpus_path: Path,
    *,
    expected_evidence_sha256: str = EXPECTED_EVIDENCE_SHA256,
    expected_corpus_sha256: str = EXPECTED_CORPUS_SHA256,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Verify every frozen input invariant before semantic analysis."""
    if not evidence_path.is_file():
        raise EvidenceIntegrityError(f"R6 evidence is missing: {evidence_path}")
    evidence_raw, rows = _load_jsonl(evidence_path)
    evidence_sha256 = sha256_bytes(evidence_raw)
    if evidence_sha256 != expected_evidence_sha256:
        raise EvidenceIntegrityError(
            f"R6 evidence SHA mismatch: expected {expected_evidence_sha256}, got {evidence_sha256}."
        )
    if len(rows) != 18:
        raise EvidenceIntegrityError(f"Expected 18 R6 rows, got {len(rows)}.")
    distribution = Counter(str(row.get("case_id")) for row in rows)
    if dict(distribution) != EXPECTED_CASE_COUNTS:
        raise EvidenceIntegrityError(f"Unexpected R6 case distribution: {dict(distribution)}.")
    for row in rows:
        if row.get("classification") != "PAIRED_TYPED_ATTEMPT":
            raise EvidenceIntegrityError("R6 contains a non-completed paired row.")
        if not isinstance(row.get("a"), dict) or not isinstance(row.get("c"), dict):
            raise EvidenceIntegrityError("Every completed R6 row must contain A and C results.")
    if not corpus_path.is_file():
        raise EvidenceIntegrityError(f"Frozen corpus is missing: {corpus_path}")
    corpus_raw = corpus_path.read_bytes()
    corpus_sha256 = sha256_bytes(corpus_raw)
    if corpus_sha256 != expected_corpus_sha256:
        raise EvidenceIntegrityError(
            f"Corpus SHA mismatch: expected {expected_corpus_sha256}, got {corpus_sha256}."
        )
    metadata = {
        "evidence_path": str(evidence_path),
        "evidence_sha256": evidence_sha256,
        "rows": len(rows),
        "case_distribution": dict(sorted(distribution.items())),
        "corpus_path": str(corpus_path),
        "corpus_sha256": corpus_sha256,
    }
    return rows, metadata


def load_expected_sections(corpus_path: Path) -> dict[str, Mapping[str, object]]:
    """Load one expected section per frozen analysis case."""
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    return {
        str(case["case_id"]): case["expected_sections"][0]
        for case in corpus["cases"]
        if case["case_id"] in EXPECTED_CASE_COUNTS
    }


def applicable_checks(expected: Mapping[str, object]) -> tuple[str, ...]:
    """Reconstruct the exact check names emitted by evaluate_semantic_draft."""
    checks = [
        "title_valid",
        "source_selection_valid",
        "track_count_valid",
        "track_order_valid",
        "track_titles_valid",
    ]
    for track_index, expected_track in enumerate(expected.get("tracks", ())):
        prefix = f"tracks[{track_index}]"
        if "x_scale" in expected_track:
            checks.append(f"{prefix}.x_scale")
        checks.extend(
            [
                f"{prefix}.binding_count",
                f"{prefix}.binding_order",
                f"{prefix}.binding_channels",
                f"{prefix}.binding_ids",
            ]
        )
        for binding_index, expected_binding in enumerate(expected_track.get("bindings", ())):
            binding_prefix = f"{prefix}.bindings[{binding_index}]"
            for field_name in ("scale", "profile", "sample_axis"):
                if field_name in expected_binding:
                    checks.append(f"{binding_prefix}.{field_name}")
    return tuple(checks)


def check_family(check: str) -> str:
    """Map one evaluator check to the frozen R7 semantic family."""
    if check in {"title_valid", "track_titles_valid"}:
        return "labels"
    if check == "source_selection_valid":
        return "source_grounding"
    if check in {"track_count_valid", "track_order_valid"}:
        return "track_topology"
    if any(
        check.endswith(f".{suffix}")
        for suffix in ("binding_count", "binding_order", "binding_channels", "binding_ids")
    ):
        return "binding_topology"
    if check.endswith(".x_scale"):
        return "track_scale"
    if check.endswith(".scale"):
        return "binding_scale"
    if check.endswith(".profile"):
        return "raster_profile"
    if check.endswith(".sample_axis"):
        return "sample_axis"
    raise ValueError(f"Unclassified evaluator check: {check}")


def unrequested_family(path: str) -> str:
    """Map one evaluator unrequested path to a diagnostic family."""
    if path.endswith(".x_scale"):
        return "track_scale"
    if path.endswith(".scale"):
        return "binding_scale"
    if path.endswith(".profile"):
        return "raster_profile"
    if path.endswith(".sample_axis"):
        return "sample_axis"
    return "other"


def _result_is_eligible(result: Mapping[str, object]) -> bool:
    """Return whether the semantic evaluator reached a comparable boundary."""
    return bool(
        result.get("structured_valid")
        and result.get("context_valid")
        and result.get("compiler_valid")
    )


def _result_omissions(result: Mapping[str, object]) -> frozenset[str]:
    """Read bounded evaluator omissions from one frozen result."""
    return frozenset(str(value) for value in result.get("omissions", ()))


def _result_unrequested(result: Mapping[str, object]) -> tuple[str, ...]:
    """Read bounded evaluator unrequested paths from one frozen result."""
    return tuple(str(value) for value in result.get("unrequested_semantics", ()))


def _row_profile(
    row: Mapping[str, object],
    *,
    variant: str,
    expected: Mapping[str, object],
) -> dict[str, object]:
    """Derive diagnostic row facts without reconstructing a generated draft."""
    result = row[variant.lower()]
    assert isinstance(result, Mapping)
    checks = applicable_checks(expected)
    omissions = _result_omissions(result)
    failed_checks = tuple(check for check in checks if check in omissions)
    failed_families = tuple(sorted({check_family(check) for check in failed_checks}))
    unrequested = _result_unrequested(result)
    science_failed = any(family in SCIENTIFIC_FAMILIES for family in failed_families)
    topology_failed = any(family in TOPOLOGY_FAMILIES for family in failed_families)
    label_failed = "labels" in failed_families
    label_only = label_failed and not science_failed and not topology_failed and not unrequested
    expected_checks_pass = not failed_checks
    unrequested_only = expected_checks_pass and bool(unrequested)
    scientific_checks = tuple(
        check for check in checks if check_family(check) in SCIENTIFIC_FAMILIES
    )
    topology_checks = tuple(
        check for check in checks if check_family(check) in {"track_topology", "binding_topology"}
    )
    scientific_only_pass = all(check not in omissions for check in scientific_checks)
    topology_pass = all(check not in omissions for check in topology_checks)
    if bool(result.get("semantic_accepted")):
        failure_class = "ACCEPTED"
    elif label_only:
        failure_class = "LABEL_ONLY_REJECTION"
    elif unrequested_only:
        failure_class = "UNREQUESTED_ONLY_REJECTION"
    elif science_failed and len(failed_families) > 1:
        failure_class = "MIXED_SEMANTIC_FAILURE"
    elif science_failed:
        failure_class = "SCIENTIFIC_SEMANTIC_FAILURE"
    else:
        failure_class = "NONSCIENTIFIC_SEMANTIC_FAILURE"
    return {
        "case_id": row["case_id"],
        "attempt_index": row["attempt_index"],
        "variant": variant,
        "evaluation_eligible": True,
        "semantic_accepted": bool(result.get("semantic_accepted")),
        "failed_check_count": len(failed_checks),
        "failed_checks": list(failed_checks),
        "failed_families": list(failed_families),
        "unrequested_count": len(unrequested),
        "unrequested_families": sorted({unrequested_family(path) for path in unrequested}),
        "scientific_failure_present": science_failed,
        "topology_failure_present": topology_failed,
        "scientific_only_pass": scientific_only_pass,
        "topology_pass": topology_pass,
        "label_only_rejection": label_only,
        "unrequested_only_rejection": unrequested_only,
        "failure_class": failure_class,
        "context_error_code": result.get("error_code"),
        "input_sufficiency": row.get("input_sufficiency"),
        "source_original_request_access": variant == "C",
        "_checks": checks,
    }


def _check_statistics(
    rows: Sequence[Mapping[str, object]],
    *,
    variant: str,
    expected_by_case: Mapping[str, Mapping[str, object]],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Calculate per-check and per-row statistics for one variant."""
    per_check: dict[str, dict[str, int]] = defaultdict(lambda: {"applicable": 0, "pass": 0})
    profiles: list[dict[str, object]] = []
    for row in rows:
        result = row[variant.lower()]
        assert isinstance(result, Mapping)
        if not _result_is_eligible(result):
            continue
        expected = expected_by_case[str(row["case_id"])]
        profile = _row_profile(row, variant=variant, expected=expected)
        profiles.append(profile)
        omissions = _result_omissions(result)
        for check in applicable_checks(expected):
            per_check[check]["applicable"] += 1
            if check not in omissions:
                per_check[check]["pass"] += 1
    stats = {}
    for check, counts in sorted(per_check.items()):
        applicable = counts["applicable"]
        passed = counts["pass"]
        stats[check] = {
            "applicable_rows": applicable,
            "pass_rows": passed,
            "fail_rows": applicable - passed,
            "pass_rate": _rate(passed, applicable),
            "fail_rate": _rate(applicable - passed, applicable),
            "family": check_family(check),
        }
    return stats, profiles


def _family_statistics(
    check_stats: Mapping[str, Mapping[str, object]],
    profiles: Sequence[Mapping[str, object]],
) -> dict[str, dict[str, object]]:
    """Aggregate per-check results into the frozen semantic families."""
    output: dict[str, dict[str, object]] = {}
    for family in FAMILIES:
        family_checks = [check for check, stat in check_stats.items() if stat["family"] == family]
        applicable = sum(int(check_stats[check]["applicable_rows"]) for check in family_checks)
        passed = sum(int(check_stats[check]["pass_rows"]) for check in family_checks)
        rows_with_family = sum(
            any(family == check_family(check) for check in profile["_checks"])
            for profile in profiles
        )
        rows_with_failure = sum(family in profile["failed_families"] for profile in profiles)
        rows_all_pass = sum(
            any(family == check_family(check) for check in profile["_checks"])
            and family not in profile["failed_families"]
            for profile in profiles
        )
        output[family] = {
            "applicable_check_instances": applicable,
            "passed_check_instances": passed,
            "failed_check_instances": applicable - passed,
            "pass_rate": _rate(passed, applicable),
            "fail_rate": _rate(applicable - passed, applicable),
            "eligible_rows_with_family_applicable": rows_with_family,
            "rows_with_any_family_failure": rows_with_failure,
            "rows_with_all_family_checks_passing": rows_all_pass,
        }
    return output


def _pair_bucket() -> dict[str, int]:
    """Create one bounded A/C pairwise bucket."""
    return {"both_pass": 0, "a_fail_c_pass": 0, "a_pass_c_fail": 0, "both_fail": 0}


def _add_pair(bucket: dict[str, int], a_pass: bool, c_pass: bool) -> None:
    """Increment one pairwise outcome."""
    if a_pass and c_pass:
        bucket["both_pass"] += 1
    elif not a_pass and c_pass:
        bucket["a_fail_c_pass"] += 1
    elif a_pass and not c_pass:
        bucket["a_pass_c_fail"] += 1
    else:
        bucket["both_fail"] += 1


def _pairwise_statistics(
    rows: Sequence[Mapping[str, object]],
    *,
    expected_by_case: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    """Compare A/C at individual checks, families, cases, and overall."""
    by_check: dict[str, dict[str, int]] = defaultdict(_pair_bucket)
    by_family: dict[str, dict[str, int]] = defaultdict(_pair_bucket)
    by_case: dict[str, dict[str, int]] = defaultdict(_pair_bucket)
    overall = _pair_bucket()
    for row in rows:
        a_result = row["a"]
        c_result = row["c"]
        assert isinstance(a_result, Mapping) and isinstance(c_result, Mapping)
        if not (_result_is_eligible(a_result) and _result_is_eligible(c_result)):
            continue
        expected = expected_by_case[str(row["case_id"])]
        checks = applicable_checks(expected)
        a_omissions = _result_omissions(a_result)
        c_omissions = _result_omissions(c_result)
        for check in checks:
            a_pass = check not in a_omissions
            c_pass = check not in c_omissions
            _add_pair(by_check[check], a_pass, c_pass)
            _add_pair(by_family[check_family(check)], a_pass, c_pass)
            _add_pair(by_case[str(row["case_id"])], a_pass, c_pass)
            _add_pair(overall, a_pass, c_pass)
    recoveries = {
        family: {
            "c_recoveries": bucket["a_fail_c_pass"],
            "c_regressions": bucket["a_pass_c_fail"],
            "net_delta": bucket["a_fail_c_pass"] - bucket["a_pass_c_fail"],
        }
        for family, bucket in sorted(by_family.items())
    }
    return {
        "by_check": {key: by_check[key] for key in sorted(by_check)},
        "by_family": {key: by_family[key] for key in sorted(by_family)},
        "by_case": {key: by_case[key] for key in sorted(by_case)},
        "overall": overall,
        "improvement_by_family": recoveries,
    }


def _case_matrix(
    rows: Sequence[Mapping[str, object]],
    *,
    profiles_by_variant: Mapping[str, Sequence[Mapping[str, object]]],
) -> dict[str, object]:
    """Build the required per-case A/C diagnostic matrix."""
    result: dict[str, object] = {}
    for case_id in EXPECTED_CASE_COUNTS:
        case_result: dict[str, object] = {}
        for variant in VARIANTS:
            raw_rows = [row for row in rows if row["case_id"] == case_id]
            variant_rows = [
                row for row in profiles_by_variant[variant] if row["case_id"] == case_id
            ]
            source_results = [row[variant.lower()] for row in raw_rows]
            context_invalid = [
                row
                for row in source_results
                if not _result_is_eligible(row)  # type: ignore[arg-type]
            ]
            family_failure_rows = {
                family: sum(family in row["failed_families"] for row in variant_rows)
                for family in FAMILIES
            }
            case_result[variant] = {
                "rows": len(raw_rows),
                "evaluation_eligible": len(variant_rows),
                "context_invalid": len(context_invalid),
                "semantic_accepted": sum(row["semantic_accepted"] for row in variant_rows),
                "family_failure_rows": family_failure_rows,
                "unrequested_semantic_rows": sum(
                    bool(row["unrequested_count"]) for row in variant_rows
                ),
                "scientific_failure_rows": sum(
                    bool(row["scientific_failure_present"]) for row in variant_rows
                ),
            }
        result[case_id] = case_result
    return result


def _diagnostic_projections(
    profiles_by_variant: Mapping[str, Sequence[Mapping[str, object]]],
) -> dict[str, object]:
    """Build row-level diagnostic projections without raw provider content."""
    output: dict[str, object] = {}
    for variant, profiles in profiles_by_variant.items():
        output[variant] = {
            "scientific_only_pass": {
                "rows": sum(row["scientific_only_pass"] for row in profiles),
                "eligible_rows": len(profiles),
            },
            "topology_pass": {
                "rows": sum(row["topology_pass"] for row in profiles),
                "eligible_rows": len(profiles),
            },
            "label_only_rejections": sum(row["label_only_rejection"] for row in profiles),
            "unrequested_only_rejections": sum(
                row["unrequested_only_rejection"] for row in profiles
            ),
            "failure_class_counts": dict(Counter(str(row["failure_class"]) for row in profiles)),
            "row_profiles": [
                {key: value for key, value in row.items() if key != "_checks"} for row in profiles
            ],
        }
    return output


def _top_level_decision(profiles_by_variant: Mapping[str, Sequence[Mapping[str, object]]]) -> str:
    """Apply the locked topology-based R7 decision rule."""
    rejected = [
        row
        for profiles in profiles_by_variant.values()
        for row in profiles
        if not row["semantic_accepted"]
    ]
    if not rejected:
        return "NONSCIENTIFIC_ACCEPTANCE_DOMINANT"
    scientific = [row for row in rejected if row["scientific_failure_present"]]
    non_scientific = [row for row in rejected if not row["scientific_failure_present"]]
    if scientific and not non_scientific:
        return "SCIENTIFIC_SEMANTICS_SYSTEMIC"
    if non_scientific and not scientific:
        return "NONSCIENTIFIC_ACCEPTANCE_DOMINANT"
    return "MIXED_SEMANTIC_FAILURE_TOPOLOGY"


def _systemic_families(
    families_by_variant: Mapping[str, Mapping[str, Mapping[str, object]]],
) -> list[dict[str, object]]:
    """Find families with zero passing applicable check instances."""
    findings: list[dict[str, object]] = []
    for family in SCIENTIFIC_FAMILIES:
        for variant in VARIANTS:
            stats = families_by_variant[variant][family]
            applicable = int(stats["applicable_check_instances"])
            failed = int(stats["failed_check_instances"])
            if applicable and failed == applicable:
                findings.append(
                    {
                        "variant": variant,
                        "family": family,
                        "failed": failed,
                        "applicable": applicable,
                        "pass_rate": stats["pass_rate"],
                    }
                )
    return sorted(findings, key=lambda item: (item["variant"], item["family"]))


def _vdl_attribution(
    rows: Sequence[Mapping[str, object]],
    profiles_by_variant: Mapping[str, Sequence[Mapping[str, object]]],
) -> dict[str, object]:
    """Attribute VDL sample-axis failures according to the frozen R7 policy."""
    output: dict[str, object] = {}
    for variant in VARIANTS:
        profiles = [
            row for row in profiles_by_variant[variant] if row["case_id"] == "vdl_sample_axis"
        ]
        sample_axis_failures = sum("sample_axis" in row["failed_families"] for row in profiles)
        upstream = 0
        worker = 0
        for row in profiles:
            if "sample_axis" not in row["failed_families"]:
                continue
            original = next(
                source
                for source in rows
                if source["case_id"] == row["case_id"]
                and source["attempt_index"] == row["attempt_index"]
            )
            missing = set(original.get("input_sufficiency", {}).get("missing_fact_ids", ()))
            if variant == "A" and "axis" in missing:
                upstream += 1
            elif variant == "C":
                worker += 1
        output[variant] = {
            "evaluation_eligible": len(profiles),
            "sample_axis_failure_rows": sample_axis_failures,
            "UPSTREAM_FACT_NOT_PRESERVED": upstream,
            "worker_semantic_failure": worker,
        }
    return output


def analyze_evidence(
    evidence_path: Path = DEFAULT_EVIDENCE_PATH,
    corpus_path: Path = DEFAULT_CORPUS_PATH,
    *,
    expected_evidence_sha256: str = EXPECTED_EVIDENCE_SHA256,
    expected_corpus_sha256: str = EXPECTED_CORPUS_SHA256,
) -> dict[str, object]:
    """Analyze frozen R6 evidence and return a JSON-serializable summary."""
    rows, integrity = verify_evidence_integrity(
        evidence_path,
        corpus_path,
        expected_evidence_sha256=expected_evidence_sha256,
        expected_corpus_sha256=expected_corpus_sha256,
    )
    expected_by_case = load_expected_sections(corpus_path)
    check_stats_by_variant: dict[str, dict[str, object]] = {}
    profiles_by_variant: dict[str, list[dict[str, object]]] = {}
    eligibility: dict[str, object] = {}
    families: dict[str, object] = {}
    context_invalid: dict[str, object] = {}
    for variant in VARIANTS:
        stats, profiles = _check_statistics(
            rows,
            variant=variant,
            expected_by_case=expected_by_case,
        )
        check_stats_by_variant[variant] = stats
        profiles_by_variant[variant] = profiles
        variant_rows = [row[variant.lower()] for row in rows]
        invalid_rows = [row for row in variant_rows if not _result_is_eligible(row)]
        invalid_counts = Counter(
            str(row.get("error_code")) for row in invalid_rows if row.get("error_code")
        )
        eligibility[variant] = {
            "rows": len(rows),
            "evaluation_eligible": len(profiles),
            "context_invalid": len(invalid_rows),
        }
        context_invalid[variant] = dict(sorted(invalid_counts.items()))
        families[variant] = _family_statistics(stats, profiles)
    decision = _top_level_decision(profiles_by_variant)
    return {
        "experiment": EXPERIMENT_VERSION,
        "baseline": BASELINE_SHA,
        "source_experiment": SOURCE_EXPERIMENT,
        "provider_calls": 0,
        "evidence": integrity,
        "eligibility": eligibility,
        "context_invalid": context_invalid,
        "check_statistics": check_stats_by_variant,
        "families": families,
        "cases": _case_matrix(rows, profiles_by_variant=profiles_by_variant),
        "pairwise": _pairwise_statistics(rows, expected_by_case=expected_by_case),
        "diagnostic_projections": _diagnostic_projections(profiles_by_variant),
        "systemic_families": _systemic_families(families),
        "vdl_attribution": _vdl_attribution(rows, profiles_by_variant),
        "decision": decision,
        "production_changes": 0,
        "cm57_started": False,
    }


def _parser() -> argparse.ArgumentParser:
    """Build the offline analyzer CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE_PATH)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS_PATH)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> None:
    """Analyze frozen CM-56R6 evidence without provider access."""
    args = _parser().parse_args()
    summary = analyze_evidence(args.evidence, args.corpus)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":  # pragma: no cover
    main()
