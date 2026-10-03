"""Derive the provider-free SI-V2R SR6 contract-bounded historical regrade."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from scripts.semantic_ir_v2r_sr5_contract_applicability import (
    build_artifacts as build_sr5_artifacts,
)

BASELINE_SHA = "d46b280bbe1326fa1664778c66377067beb2a557"
SR5_POLICY_BASELINE_SHA = "eb9736ddda9feb9e5e601760822da7e0e3933286"
SR5_CHECKPOINT = "d46b280bbe1326fa1664778c66377067beb2a557"
RAW_EVIDENCE_SHA256 = "9d175c3b80c2cb6a5d5f62195861d4c0070643a37ab4f99dd02559d018011f08"
DEFAULT_RAW_EVIDENCE = Path("/tmp/si-v2r-live.jsonl")
DEFAULT_OUTPUT_DIR = Path("tests/fixtures/semantic_ir_v2r_sr6")
SR5_ARTIFACT_DIR = Path("tests/fixtures/semantic_ir_v2r_sr5")
DIMENSIONS = (
    "report_presence",
    "report_content",
    "reference_admissibility",
    "reference_kind",
    "reference_target",
    "annotation_semantics",
    "constraint_scope",
    "unresolved_requirements",
)
RESIDUAL_TO_DIMENSION = {
    "REPORT_FALSE_POSITIVE": "report_presence",
    "REPORT_FALSE_NEGATIVE": "report_presence",
    "REPORT_MISSING": "report_presence",
    "REFERENCE_FALSE_POSITIVE": "reference_admissibility",
    "REFERENCE_FALSE_NEGATIVE": "reference_admissibility",
    "REFERENCE_KIND_ERROR": "reference_kind",
    "REFERENCE_TARGET_ERROR": "reference_target",
    "ANNOTATION_ERROR": "annotation_semantics",
    "CONSTRAINT_SCOPE_UNRESOLVED": "constraint_scope",
    "UNRESOLVED_REQUIREMENT_ERROR": "unresolved_requirements",
}
RESIDUAL_TAXONOMY = {
    "REPORT_CONTENT_ERROR",
    "REPORT_MISSING",
    "REFERENCE_UNSPECIFIED_POLICY_BLOCK",
    "REFERENCE_REPRESENTATION_CONFLICT",
    "REFERENCE_KIND_ERROR",
    "REFERENCE_TARGET_ERROR",
    "ANNOTATION_ERROR",
    "CONSTRAINT_SCOPE_UNRESOLVED",
    "UNRESOLVED_REQUIREMENT_ERROR",
    "FEATURE_KIND_ERROR",
    "FEATURE_MULTIPLICITY_ERROR",
    "SECTION_COUNT_ERROR",
    "SECTION_ORDER_ERROR",
    "REQUIRED_CONTEXT_OWNER_ERROR",
    "OTHER_MODEL_SEMANTIC_ERROR",
}
FAMILIES = (
    "REPORT_ONLY",
    "SINGLE_SECTION",
    "REFERENCE_REQUIRED",
    "MULTITRACK_SINGLE_SECTION",
    "MULTI_SECTION_ALLOCATION",
    "MIXED_REPORT_SECTION",
)
ANCHORS = {
    "Fig": "cm59-single-fig-05",
    "Linden": "cm59-reference-linden-10",
    "Kestrel": "cm59-report-kestrel-04",
    "Xenon": "cm59-mixed-xenon-21",
}


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _dump_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_raw_rows(raw_evidence: Path) -> list[dict[str, Any]]:
    if not raw_evidence.is_file():
        raise RuntimeError(f"SR6 raw evidence is missing: {raw_evidence}")
    actual_sha = hashlib.sha256(raw_evidence.read_bytes()).hexdigest()
    if actual_sha != RAW_EVIDENCE_SHA256:
        raise RuntimeError(f"SR6 raw evidence SHA mismatch: {actual_sha}")
    rows = [json.loads(line) for line in raw_evidence.read_text().splitlines() if line]
    keys = {(row["case_id"], row["attempt"]) for row in rows}
    if len(rows) != 48 or len(keys) != 48:
        raise RuntimeError("SR6 raw population must contain 48 unique rows")
    if {row["attempt"] for row in rows} != {0, 1}:
        raise RuntimeError("SR6 raw population must contain attempts 0 and 1")
    if len({row["case_id"] for row in rows}) != 24:
        raise RuntimeError("SR6 raw population must contain 24 cases")
    return rows


def _validate_frozen_inputs(raw_evidence: Path, repo_root: Path) -> None:
    """Verify that every upstream contract artifact is still the accepted one."""
    sr5_artifacts = build_sr5_artifacts(raw_evidence, repo_root)
    for filename, expected in sr5_artifacts.items():
        committed = _load_json(repo_root / SR5_ARTIFACT_DIR / filename)
        if committed != expected:
            raise RuntimeError(f"SR5 artifact drifted: {filename}")

    sr2 = _load_json(repo_root / "tests/fixtures/semantic_ir_v2r_sr2/result.json")
    if sr2["decision"] != "SI_V2R_SR2_REPORT_PRESENCE_RESOLVED":
        raise RuntimeError("SR2 decision drifted")
    if sr2["evidence"]["sha256"] != RAW_EVIDENCE_SHA256:
        raise RuntimeError("SR2 evidence binding drifted")

    sr3 = _load_json(repo_root / "tests/fixtures/semantic_ir_v2r_sr3/result.json")
    if sr3["decision"] != "SI_V2R_SR3_ROOT_MECHANISMS_RESOLVED":
        raise RuntimeError("SR3 decision drifted")

    sr4 = _load_json(repo_root / "tests/fixtures/semantic_ir_v2r_sr4/result.json")
    if sr4["decision"] != "SI_V2R_SR4_OWNERSHIP_CONTRACT_PARTIAL":
        raise RuntimeError("SR4 decision drifted")
    if sr4["depth_column_prohibition_scope"] != "UNRESOLVED":
        raise RuntimeError("SR4 depth-column scope is no longer unresolved")

    sr5 = _load_json(repo_root / SR5_ARTIFACT_DIR / "result.json")
    if sr5["baseline"] != SR5_POLICY_BASELINE_SHA:
        raise RuntimeError("SR5 policy baseline drifted")
    if sr5["decision"] != "SI_V2R_SR5_APPLICABILITY_MAP_COMPLETE":
        raise RuntimeError("SR5 decision drifted")
    if sr5["regrade_readiness"] != "RE_GRADE_PARTIALLY_READY":
        raise RuntimeError("SR5 regrade-readiness drifted")


def _model_residuals(sr2_row: dict[str, Any]) -> list[str]:
    """Reconstruct the frozen model residual view without changing its score."""
    residuals = list(sr2_row["non_report_failures"])
    if sr2_row["model_report_routing_overreach"]:
        residuals.append("REPORT_FALSE_POSITIVE")
    if sr2_row["model_report_missing"]:
        residuals.append("REPORT_MISSING")
    if sr2_row["model_report_content_correct"] is False:
        residuals.append("REPORT_CONTENT_ERROR")
    return sorted(set(residuals))


def _blocked_reference_residuals(sr5_row: dict[str, Any]) -> list[str]:
    state = sr5_row["reference_admissibility_applicability"]
    blockers = []
    if state == "BLOCKED_BY_REPRESENTATION_CONFLICT":
        blockers.append("REFERENCE_REPRESENTATION_CONFLICT")
    if "UNSPECIFIED_REFERENCE_POLICY" in sr5_row["applicability_blockers"]:
        blockers.append("REFERENCE_UNSPECIFIED_POLICY_BLOCK")
    if state in {"BLOCKED_BY_UNRESOLVED_CONTRACT", "FAIL_CLOSED"}:
        blockers.append("REFERENCE_UNSPECIFIED_POLICY_BLOCK")
    return blockers or ["OTHER_MODEL_SEMANTIC_ERROR"]


def _apply_contract_credit(
    model_residuals: list[str],
    sr5_row: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Remove only residuals whose exact SR5 dimension flag is true."""
    eligibility = sr5_row["system_credit_eligibility_by_dimension"]
    remaining: list[str] = []
    credited: list[str] = []
    for residual in model_residuals:
        dimension = RESIDUAL_TO_DIMENSION.get(residual)
        if dimension and eligibility.get(dimension) is True:
            credited.append(dimension)
            continue
        if residual == "REFERENCE_FALSE_POSITIVE":
            remaining.extend(_blocked_reference_residuals(sr5_row))
            continue
        if (
            residual == "REQUIRED_CONTEXT_OWNER_ERROR"
            and sr5_row["constraint_scope_applicability"] == "BLOCKED_BY_UNRESOLVED_CONTRACT"
        ):
            remaining.append("CONSTRAINT_SCOPE_UNRESOLVED")
            continue
        remaining.append(residual)
    remaining = sorted(set(remaining))
    credited = sorted(set(credited))
    if not set(remaining) <= RESIDUAL_TAXONOMY:
        raise RuntimeError(f"SR6 residual outside taxonomy: {remaining}")
    return remaining, credited


def _case_status(statuses: list[str]) -> str:
    if statuses == ["NOT_EVALUABLE", "NOT_EVALUABLE"]:
        return "STRUCTURAL_UNAVAILABLE"
    if "NOT_EVALUABLE" in statuses:
        return "PARTIALLY_EVALUABLE"
    if statuses == ["PASS", "PASS"]:
        return "STABLE_PASS"
    if statuses == ["FAIL", "FAIL"]:
        return "STABLE_FAIL"
    return "UNSTABLE"


def _build_rows(
    raw_rows: list[dict[str, Any]],
    sr2_rows: list[dict[str, Any]],
    sr5_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    raw_by_key = {(row["case_id"], row["attempt"]): row for row in raw_rows}
    sr2_by_key = {(row["case_id"], row["attempt"]): row for row in sr2_rows}
    sr5_by_key = {(row["case_id"], row["attempt"]): row for row in sr5_rows}
    output = []
    for key in sorted(raw_by_key):
        raw = raw_by_key[key]
        provider = raw["provider"]
        sr2 = sr2_by_key[key]
        sr5 = sr5_by_key[key]
        frozen_model_status = provider["semantic_status"]
        structurally_evaluable = provider["semantic_model"] is not None
        model_residuals = _model_residuals(sr2) if structurally_evaluable else []
        if not structurally_evaluable:
            system_status = "NOT_EVALUABLE"
            remaining = []
            credited = []
        else:
            remaining, credited = _apply_contract_credit(model_residuals, sr5)
            system_status = "PASS" if not remaining else "FAIL"
            if frozen_model_status == "SEMANTIC_PASS" and system_status != "PASS":
                raise RuntimeError(f"SR6 unexpected pass regression: {key}")
        output.append(
            {
                "case_id": key[0],
                "attempt": key[1],
                "family": raw["family"],
                "structurally_evaluable": structurally_evaluable,
                "frozen_structural_status": provider["structural_status"],
                "frozen_model_semantic_status": frozen_model_status,
                "sr2_status": sr2["ownership_adjusted_semantic_status"],
                "sr5_applicability_dimensions": sr5["applicability_dimensions"],
                "sr5_blockers": sr5["applicability_blockers"],
                "sr5_system_credit_eligibility": sr5["system_credit_eligibility_by_dimension"],
                "frozen_model_residuals": model_residuals,
                "system_credit_applied_dimensions": credited,
                "remaining_system_residuals": remaining,
                "contract_bounded_system_status": system_status,
            }
        )
    return output


def _group_status(records: list[dict[str, Any]], field: str) -> str:
    return _case_status([record[field] for record in sorted(records, key=lambda x: x["attempt"])])


def _build_cases(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_case[row["case_id"]].append(row)
    cases = []
    for case_id, attempts in sorted(by_case.items()):
        ordered = sorted(attempts, key=lambda row: row["attempt"])
        enriched = [
            {
                **row,
                "model_status": (
                    "PASS"
                    if row["frozen_model_semantic_status"] == "SEMANTIC_PASS"
                    else "NOT_EVALUABLE"
                    if not row["structurally_evaluable"]
                    else "FAIL"
                ),
            }
            for row in ordered
        ]
        cases.append(
            {
                "case_id": case_id,
                "family": ordered[0]["family"],
                "attempts": len(ordered),
                "model_case_status": _group_status(enriched, "model_status"),
                "sr2_case_status": _case_status(
                    [
                        "NOT_EVALUABLE"
                        if row["sr2_status"] == "NOT_EVALUABLE"
                        else row["sr2_status"]
                        for row in ordered
                    ]
                ),
                "contract_bounded_case_status": _group_status(
                    [
                        {
                            **row,
                            "system_status": row["contract_bounded_system_status"],
                        }
                        for row in ordered
                    ],
                    "system_status",
                ),
                "attempt_statuses": [
                    {
                        "attempt": row["attempt"],
                        "model_status": enriched[index]["model_status"],
                        "sr2_status": row["sr2_status"],
                        "contract_bounded_system_status": row["contract_bounded_system_status"],
                        "remaining_system_residuals": row["remaining_system_residuals"],
                    }
                    for index, row in enumerate(ordered)
                ],
                "remaining_system_residuals": sorted(
                    {residual for row in ordered for residual in row["remaining_system_residuals"]}
                ),
            }
        )
    return cases


def _stable_count(cases: list[dict[str, Any]], status: str) -> int:
    return sum(case["contract_bounded_case_status"] == status for case in cases)


def _family_metrics(rows: list[dict[str, Any]], cases: list[dict[str, Any]]) -> dict[str, Any]:
    result = {}
    for family in FAMILIES:
        family_rows = [row for row in rows if row["family"] == family]
        family_cases = [case for case in cases if case["family"] == family]
        result[family] = {
            "evaluable_attempts": sum(
                row["contract_bounded_system_status"] != "NOT_EVALUABLE" for row in family_rows
            ),
            "system_passes": sum(
                row["contract_bounded_system_status"] == "PASS" for row in family_rows
            ),
            "system_failures": sum(
                row["contract_bounded_system_status"] == "FAIL" for row in family_rows
            ),
            "not_evaluable_attempts": sum(
                row["contract_bounded_system_status"] == "NOT_EVALUABLE" for row in family_rows
            ),
            "stable_pass_cases": sum(
                case["contract_bounded_case_status"] == "STABLE_PASS" for case in family_cases
            ),
            "stable_fail_cases": sum(
                case["contract_bounded_case_status"] == "STABLE_FAIL" for case in family_cases
            ),
            "unstable_cases": sum(
                case["contract_bounded_case_status"] == "UNSTABLE" for case in family_cases
            ),
            "structural_unavailable_cases": sum(
                case["contract_bounded_case_status"] == "STRUCTURAL_UNAVAILABLE"
                for case in family_cases
            ),
            "partially_evaluable_cases": sum(
                case["contract_bounded_case_status"] == "PARTIALLY_EVALUABLE"
                for case in family_cases
            ),
            "case_count": len(family_cases),
        }
    return result


def _residual_summary(rows: list[dict[str, Any]], cases: list[dict[str, Any]]) -> dict[str, Any]:
    transitions = Counter()
    residual_counts = Counter()
    blocked = Counter()
    for row in rows:
        transitions[
            f"{row['frozen_model_semantic_status']} -> {row['contract_bounded_system_status']}"
        ] += 1
        residual_counts.update(row["remaining_system_residuals"])
        if not row["structurally_evaluable"]:
            blocked["STRUCTURAL_FAILURE"] += 1
        for residual in row["remaining_system_residuals"]:
            blocked[residual] += 1
    return {
        "schema_version": "si-v2r.sr6.residual-summary.v1",
        "transitions": dict(sorted(transitions.items())),
        "remaining_system_residual_counts": dict(sorted(residual_counts.items())),
        "blocked_opportunity_counts": dict(sorted(blocked.items())),
        "stable_system_case_status_counts": dict(
            sorted(Counter(case["contract_bounded_case_status"] for case in cases).items())
        ),
    }


def _build_result(
    rows: list[dict[str, Any]], cases: list[dict[str, Any]], residual_summary: dict[str, Any]
) -> dict[str, Any]:
    model_passes = sum(row["frozen_model_semantic_status"] == "SEMANTIC_PASS" for row in rows)
    sr2_passes = sum(row["sr2_status"] == "PASS" for row in rows)
    system_passes = sum(row["contract_bounded_system_status"] == "PASS" for row in rows)
    model_stable = sum(case["model_case_status"] == "STABLE_PASS" for case in cases)
    sr2_stable = sum(case["sr2_case_status"] == "STABLE_PASS" for case in cases)
    system_stable = _stable_count(cases, "STABLE_PASS")
    additional_changes = sum(
        row["contract_bounded_system_status"]
        != ("NOT_EVALUABLE" if row["sr2_status"] == "NOT_EVALUABLE" else row["sr2_status"])
        for row in rows
    )
    recovered_attempts = sum(
        row["frozen_model_semantic_status"] == "SEMANTIC_FAIL"
        and row["contract_bounded_system_status"] == "PASS"
        for row in rows
    )
    recovered_cases = sum(
        case["model_case_status"] != "STABLE_PASS"
        and case["contract_bounded_case_status"] == "STABLE_PASS"
        for case in cases
    )
    partially_regradable = any(
        row["structurally_evaluable"]
        and any(
            state
            in {
                "MODEL_OWNED",
                "BLOCKED_BY_REPRESENTATION_CONFLICT",
                "BLOCKED_BY_UNRESOLVED_CONTRACT",
                "FAIL_CLOSED",
            }
            for state in row["sr5_applicability_dimensions"].values()
        )
        for row in rows
    )
    decision = (
        "SI_V2R_SR6_NO_ADDITIONAL_SYSTEM_RECOVERY"
        if additional_changes == 0
        else "SI_V2R_SR6_PARTIAL_REGRADE_COMPLETE"
    )
    return {
        "schema_version": "si-v2r.sr6.result.v1",
        "decision": decision,
        "baseline": BASELINE_SHA,
        "evidence": {"sha256": RAW_EVIDENCE_SHA256, "rows": 48, "cases": 24, "attempts": 2},
        "frozen_historical_facts": {
            "decision": "SI_V2R_PROVIDER_BOUNDARY_REJECTED",
            "semantic_passes": 28,
            "stable_semantic_passes": 14,
            "terminal_structural_failures": 6,
        },
        "sr2_historical_facts": {
            "decision": "SI_V2R_SR2_REPORT_PRESENCE_RESOLVED",
            "adjusted_semantic_passes": 34,
            "adjusted_stable_passes": 17,
        },
        "sr5_historical_facts": {
            "checkpoint": SR5_CHECKPOINT,
            "policy_baseline": SR5_POLICY_BASELINE_SHA,
            "decision": "SI_V2R_SR5_APPLICABILITY_MAP_COMPLETE",
            "regrade_readiness": "RE_GRADE_PARTIALLY_READY",
        },
        "metrics": {
            "model_semantic_passes": model_passes,
            "sr2_adjusted_semantic_passes": sr2_passes,
            "sr6_system_semantic_passes": system_passes,
            "model_stable_passes": model_stable,
            "sr2_stable_passes": sr2_stable,
            "sr6_system_stable_passes": system_stable,
            "newly_system_recovered_attempts_vs_model": recovered_attempts,
            "newly_system_recovered_cases_vs_model": recovered_cases,
            "additional_sr6_changes_vs_sr2": additional_changes,
            "structural_not_evaluable_attempts": sum(
                row["contract_bounded_system_status"] == "NOT_EVALUABLE" for row in rows
            ),
        },
        "family_metrics": _family_metrics(rows, cases),
        "anchor_metrics": {
            label: next(
                {
                    "case_id": case["case_id"],
                    "model_status": case["model_case_status"],
                    "sr2_status": case["sr2_case_status"],
                    "sr6_system_status": case["contract_bounded_case_status"],
                    "remaining_system_residuals": case["remaining_system_residuals"],
                }
                for case in cases
                if case["case_id"] == case_id
            )
            for label, case_id in ANCHORS.items()
        },
        "residual_summary": residual_summary,
        "regrade_completeness": "PARTIALLY_REGRADABLE"
        if partially_regradable
        else "FULLY_REGRADABLE",
        "historical_provider_decision": "SI_V2R_PROVIDER_BOUNDARY_REJECTED",
        "provider_inference_calls": 0,
        "endpoint_calls": 0,
        "worker_program_calls": 0,
        "production_behavior_changed": False,
        "adr_cm57": "UNCHANGED",
    }


def build_artifacts(raw_evidence: Path, repo_root: Path) -> dict[str, Any]:
    """Authenticate frozen inputs and derive all four SR6 artifacts."""
    _validate_frozen_inputs(raw_evidence, repo_root)
    raw_rows = _load_raw_rows(raw_evidence)
    sr2_rows = _load_json(repo_root / "tests/fixtures/semantic_ir_v2r_sr2/adjusted_rows.json")
    sr5_rows = _load_json(repo_root / SR5_ARTIFACT_DIR / "applicability_rows.json")
    rows = _build_rows(raw_rows, sr2_rows, sr5_rows)
    cases = _build_cases(rows)
    residual_summary = _residual_summary(rows, cases)
    result = _build_result(rows, cases, residual_summary)
    return {
        "regraded_rows.json": rows,
        "regraded_cases.json": cases,
        "residual_summary.json": residual_summary,
        "result.json": result,
    }


def _write_or_check(artifacts: dict[str, Any], output_dir: Path, *, check: bool) -> None:
    for filename, value in artifacts.items():
        path = output_dir / filename
        if check:
            if not path.is_file() or _load_json(path) != value:
                raise RuntimeError(f"SR6 artifact mismatch: {path}")
        else:
            output_dir.mkdir(parents=True, exist_ok=True)
            _dump_json(path, value)


def main() -> None:
    """Run the SR6 provider-free derivation or verify its artifacts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-evidence", type=Path, default=DEFAULT_RAW_EVIDENCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    _write_or_check(
        build_artifacts(args.raw_evidence, repo_root), args.output_dir, check=args.check
    )


if __name__ == "__main__":
    main()
