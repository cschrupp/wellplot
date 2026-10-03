"""Provider-free SI-V2R SR2 ownership-adjusted historical regrade."""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.semantic_ir_v2r_br1_boundary_audit import _dimension_flags
from scripts.semantic_ir_v2r_sr1_report_routing_audit import (
    DEFAULT_EVIDENCE,
    EVIDENCE_SHA256,
    REPO_ROOT,
    _gold_scope,
    _load_cases,
    _load_gold,
    _recompute_cm58,
    _report_work,
    _stored_cm58,
    authenticate_evidence,
)
from wellplot.agent.code_mode.report_boundary_safety import classify_report_boundary_intent

BASELINE_SHA = "e97ae4d53ed82c724a014d7fc5b52598f9ca201d"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "tests/fixtures/semantic_ir_v2r_sr2"
TAXONOMY_VERSION = "si-v2r-sr2.ownership-regrade.v1"
ORIGINAL_DECISION = "SI_V2R_PROVIDER_BOUNDARY_REJECTED"
ORIGINAL_SEMANTIC_PASSES = 28
ORIGINAL_STABLE_PASSES = 14
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
PROTECTED_PATHS = (
    "src/wellplot/agent/code_mode/semantic_ir_v2r.py",
    "src/wellplot/agent/code_mode/semantic_ir_v2r_compiler.py",
    "src/wellplot/agent/code_mode/semantic_ir_v2_registry.py",
    "src/wellplot/agent/code_mode/capability_safety.py",
    "src/wellplot/agent/code_mode/report_boundary_safety.py",
    "src/wellplot/agent/code_mode/section_leaf_safety.py",
    "src/wellplot/agent/code_mode/planner.py",
    "src/wellplot/agent/providers/base.py",
    "src/wellplot/agent/providers/openai_compat_v2.py",
    "scripts/si_v2r_model_qualification.py",
    "tests/fixtures/typed_worker/cm59a_system_reevaluation_cases.json",
    "tests/fixtures/semantic_ir_v2r/cm59a_semantic_intents_v2r.json",
)
NON_REPORT_DIMENSIONS = (
    ("section_count_correct", "SECTION_COUNT_ERROR"),
    ("section_order_correct", "SECTION_ORDER_ERROR"),
    ("feature_kinds_correct", "FEATURE_KIND_ERROR"),
    ("feature_multiplicity_correct", "FEATURE_MULTIPLICITY_ERROR"),
    ("reference_kind_correct", "REFERENCE_KIND_ERROR"),
    ("reference_target_correct", "REFERENCE_TARGET_ERROR"),
    ("annotation_correct", "ANNOTATION_ERROR"),
    ("required_context_correct", "REQUIRED_CONTEXT_OWNER_ERROR"),
    ("unresolved_requirement_correct", "UNRESOLVED_REQUIREMENT_ERROR"),
)


def _report_content_matches(model: dict[str, Any], gold: dict[str, Any]) -> bool:
    """Grade report-owned requirements and constraints independently."""
    generated = _report_work(model)
    expected = gold.get("report_work")
    if expected is None or generated is None:
        return expected is None and generated is None
    generated_values = [
        str(generated["goal"]).casefold(),
        *(str(value).casefold() for value in generated["requirements"]),
        *(str(value).casefold() for value in generated["constraints"]),
    ]
    for field in ("requirements", "constraints"):
        for value in expected.get(field, []):
            if value.casefold() and not any(
                value.casefold() in candidate for candidate in generated_values
            ):
                return False
    return True


def _non_report_failures(flags: dict[str, bool], provider: dict[str, Any]) -> list[str]:
    """Return frozen non-report semantic failures without ownership adjustment."""
    failures: list[str] = []
    if not flags["reference_presence_correct"]:
        expected_refs = [
            section.get("reference_intent")
            for section in provider["expected_semantic_projection"].get("sections", [])
        ]
        actual_refs = [
            section.get("reference_intent")
            for section in provider["semantic_projection"].get("sections", [])
        ]
        failures.append(
            "REFERENCE_FALSE_POSITIVE"
            if any(value is not None for value in actual_refs)
            and not any(value is not None for value in expected_refs)
            else "REFERENCE_FALSE_NEGATIVE"
        )
    for flag, mechanism in NON_REPORT_DIMENSIONS:
        if flag == "reference_kind_correct" and not flags["reference_presence_correct"]:
            continue
        if not flags[flag]:
            failures.append(mechanism)
    if not flags["required_context_correct"] and provider.get("required_context_misses"):
        failures = [value for value in failures if value != "REQUIRED_CONTEXT_OWNER_ERROR"]
        failures.append("REQUIRED_CONTEXT_OWNER_ERROR")
    return failures


def _safe_cm58(request: str, model: dict[str, Any]) -> dict[str, Any]:
    """Recompute CM-58.2 while preserving failures as explicit evidence."""
    try:
        result = _recompute_cm58(request, model)
    except Exception as error:  # noqa: BLE001 - bounded provider-free audit evidence
        return {
            "failure": type(error).__name__,
            "failure_message": str(error),
            "intent": None,
            "actions": [],
            "changed": False,
            "final_report_present": None,
        }
    return {"failure": None, **result}


def _row_grade(
    row: dict[str, Any],
    case: dict[str, Any],
    gold: dict[str, Any],
) -> dict[str, Any]:
    """Produce model diagnostics and ownership-adjusted grading for one row."""
    provider = row["provider"]
    frozen_status = provider.get("semantic_status")
    model = provider.get("semantic_model")
    if model is None or provider.get("semantic_projection") is None:
        return {
            "case_id": row["case_id"],
            "family": row["family"],
            "attempt": row["attempt"],
            "frozen_semantic_status": frozen_status,
            "ownership_adjusted_semantic_status": "NOT_EVALUABLE",
            "structurally_evaluable": False,
            "model_report_presence_correct": "NOT_EVALUABLE",
            "model_report_routing_overreach": False,
            "model_report_missing": False,
            "model_report_content_correct": "NOT_EVALUABLE",
            "system_report_scope_correct": "NOT_EVALUABLE",
            "system_report_present": "NOT_EVALUABLE",
            "cm58_2_changed": "NOT_EVALUABLE",
            "cm58_2_action": [],
            "cm58_2_failure": provider.get("structural_failure_reason"),
            "cm58_2_reconciled": "NOT_EVALUABLE",
            "non_report_failures": [],
            "adjusted_residual_mechanisms": [],
        }

    expected_model = {key: value for key, value in gold.items() if key != "case_id"}
    flags = _dimension_flags(
        expected_model,
        model,
        provider["expected_semantic_projection"],
        provider["semantic_projection"],
        provider,
    )
    scope = _gold_scope(case)
    report = _report_work(model)
    expected_report = scope != "SECTION_ONLY"
    model_report_present = report is not None
    model_report_content = (
        _report_content_matches(model, gold) if expected_report else "NOT_APPLICABLE"
    )
    cm58 = _safe_cm58(case["request"], model)
    classifier_scope = classify_report_boundary_intent(case["request"]).value.upper()
    system_scope_correct = (
        cm58["failure"] is None
        and classifier_scope == scope
        and cm58["final_report_present"] == expected_report
    )
    non_report_failures = _non_report_failures(flags, provider)
    stored_cm58 = _stored_cm58(row)
    cm58_reconciled = (
        cm58["failure"] is None
        and cm58["intent"] == stored_cm58["evidence"]["intent"]
        and cm58["actions"] == stored_cm58["actions"]
        and cm58["changed"] == stored_cm58["changed"]
    )
    adjusted_residuals = list(non_report_failures)
    if not system_scope_correct:
        adjusted_residuals.append("REPORT_MISSING" if expected_report else "OTHER")
    if expected_report and model_report_content is False:
        adjusted_residuals.append("REPORT_CONTENT_ERROR")
    adjusted_pass = not adjusted_residuals
    return {
        "case_id": row["case_id"],
        "family": row["family"],
        "attempt": row["attempt"],
        "frozen_semantic_status": frozen_status,
        "ownership_adjusted_semantic_status": "PASS" if adjusted_pass else "FAIL",
        "structurally_evaluable": True,
        "model_report_presence_correct": flags["report_scope_correct"],
        "model_report_routing_overreach": scope == "SECTION_ONLY" and model_report_present,
        "model_report_missing": expected_report and not model_report_present,
        "model_report_content_correct": model_report_content,
        "system_report_scope_correct": system_scope_correct,
        "system_report_present": cm58["final_report_present"],
        "cm58_2_changed": cm58["changed"],
        "cm58_2_action": cm58["actions"],
        "cm58_2_failure": cm58["failure"],
        "cm58_2_reconciled": cm58_reconciled,
        "non_report_failures": non_report_failures,
        "adjusted_residual_mechanisms": adjusted_residuals,
    }


def _case_status(records: list[dict[str, Any]]) -> str:
    """Aggregate two attempts without turning unavailable into a pass."""
    statuses = [record["ownership_adjusted_semantic_status"] for record in records]
    if all(status == "NOT_EVALUABLE" for status in statuses):
        return "STRUCTURAL_UNAVAILABLE"
    if any(status == "NOT_EVALUABLE" for status in statuses):
        return "PARTIAL_STRUCTURAL_AVAILABILITY"
    if statuses == ["PASS", "PASS"]:
        return "STABLE_PASS"
    if statuses == ["FAIL", "FAIL"]:
        return "STABLE_FAIL"
    return "UNSTABLE"


def _family_metrics(case_records: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize adjusted and frozen statuses by frozen family."""
    metrics: dict[str, Any] = {}
    for family in FAMILIES:
        records = [record for record in case_records if record["family"] == family]
        attempts = [attempt for record in records for attempt in record["attempts"]]
        evaluable = [
            attempt
            for attempt in attempts
            if attempt["ownership_adjusted_semantic_status"] != "NOT_EVALUABLE"
        ]
        metrics[family] = {
            "adjusted_attempt_passes": sum(
                attempt["ownership_adjusted_semantic_status"] == "PASS" for attempt in evaluable
            ),
            "adjusted_structurally_evaluable_attempts": len(evaluable),
            "frozen_attempt_passes": sum(
                attempt["frozen_semantic_status"] == "SEMANTIC_PASS" for attempt in attempts
            ),
            "adjusted_stable_passes": sum(
                record["adjusted_case_status"] == "STABLE_PASS" for record in records
            ),
            "adjusted_stable_failures": sum(
                record["adjusted_case_status"] == "STABLE_FAIL" for record in records
            ),
            "unstable_cases": sum(
                record["adjusted_case_status"] == "UNSTABLE" for record in records
            ),
            "structural_unavailable_cases": sum(
                record["adjusted_case_status"] == "STRUCTURAL_UNAVAILABLE" for record in records
            ),
            "case_count": len(records),
        }
    return metrics


def analyze_evidence(evidence_path: Path = DEFAULT_EVIDENCE) -> dict[str, Any]:
    """Regrade authenticated LQ0 rows under the SR1 ownership contract."""
    evidence = authenticate_evidence(evidence_path)
    cases = _load_cases()
    gold = _load_gold()
    rows = json.loads(
        "["
        + ",".join(
            line for line in evidence_path.read_text(encoding="utf-8").splitlines() if line.strip()
        )
        + "]"
    )
    rows_by_case: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        rows_by_case.setdefault(str(row["case_id"]), []).append(row)

    row_records = []
    for case_id in sorted(cases):
        for row in sorted(rows_by_case[case_id], key=lambda value: int(value["attempt"])):
            row_records.append(_row_grade(row, cases[case_id], gold[case_id]))
    by_case: dict[str, list[dict[str, Any]]] = {}
    for record in row_records:
        by_case.setdefault(record["case_id"], []).append(record)

    case_records = []
    for case_id in sorted(by_case):
        records = by_case[case_id]
        case_records.append(
            {
                "case_id": case_id,
                "family": records[0]["family"],
                "frozen_stable_pass": all(
                    record["frozen_semantic_status"] == "SEMANTIC_PASS" for record in records
                ),
                "adjusted_case_status": _case_status(records),
                "attempts": records,
            }
        )

    transitions = Counter()
    for record in row_records:
        frozen = record["frozen_semantic_status"]
        adjusted = record["ownership_adjusted_semantic_status"]
        if adjusted == "NOT_EVALUABLE":
            transitions["NOT_EVALUABLE → NOT_EVALUABLE"] += 1
        elif frozen == "SEMANTIC_PASS":
            transitions[f"FROZEN_PASS → ADJUSTED_{adjusted}"] += 1
        else:
            transitions[f"FROZEN_FAIL → ADJUSTED_{adjusted}"] += 1

    model_overreach = [record for record in row_records if record["model_report_routing_overreach"]]
    reconciled_overreach = [
        record
        for record in model_overreach
        if record["system_report_scope_correct"]
        and any(action.get("kind") == "remove_report_task" for action in record["cm58_2_action"])
    ]
    only_report_failure = [
        record
        for record in model_overreach
        if record["frozen_semantic_status"] != "SEMANTIC_PASS"
        and not record["non_report_failures"]
        and not record["adjusted_residual_mechanisms"]
    ]
    report_plus_other = [record for record in model_overreach if record not in only_report_failure]
    report_content_failures = [
        record for record in row_records if record["model_report_content_correct"] is False
    ]
    adjusted_residuals = Counter(
        mechanism for record in row_records for mechanism in record["adjusted_residual_mechanisms"]
    )
    model_residuals = Counter()
    for record in row_records:
        if record["model_report_routing_overreach"]:
            model_residuals["REPORT_FALSE_POSITIVE"] += 1
        for mechanism in record["non_report_failures"]:
            model_residuals[mechanism] += 1
        if record["model_report_missing"]:
            model_residuals["REPORT_MISSING"] += 1
        if record["model_report_content_correct"] is False:
            model_residuals["REPORT_CONTENT_ERROR"] += 1

    scope_matrix = Counter()
    for _case_id, case in cases.items():
        scope_matrix[
            (_gold_scope(case), classify_report_boundary_intent(case["request"]).value.upper())
        ] += 1
    scope_reproduced = {
        "REPORT_ONLY": scope_matrix[("REPORT_ONLY", "REPORT_ONLY")] == 4,
        "SECTION_ONLY": scope_matrix[("SECTION_ONLY", "SECTION_ONLY")] == 16,
        "MIXED": scope_matrix[("MIXED", "MIXED")] == 4,
        "total": sum(
            count for (expected, actual), count in scope_matrix.items() if expected == actual
        )
        == 24,
    }
    cm58_comparable = [record for record in row_records if record["structurally_evaluable"]]
    cm58_matches = sum(record["cm58_2_reconciled"] is True for record in cm58_comparable)
    original_passes = sum(
        record["frozen_semantic_status"] == "SEMANTIC_PASS" for record in row_records
    )
    adjusted_passes = sum(
        record["ownership_adjusted_semantic_status"] == "PASS" for record in row_records
    )
    stable_passes = sum(record["adjusted_case_status"] == "STABLE_PASS" for record in case_records)
    anchor_metrics = {
        name: {
            "case_id": case_id,
            "frozen_attempt_statuses": [
                record["frozen_semantic_status"] for record in by_case[case_id]
            ],
            "adjusted_attempt_statuses": [
                record["ownership_adjusted_semantic_status"] for record in by_case[case_id]
            ],
            "adjusted_case_status": _case_status(by_case[case_id]),
        }
        for name, case_id in ANCHORS.items()
    }
    return {
        "version": TAXONOMY_VERSION,
        "baseline": BASELINE_SHA,
        "evidence": evidence,
        "frozen_historical_facts": {
            "decision": ORIGINAL_DECISION,
            "semantic_passes": ORIGINAL_SEMANTIC_PASSES,
            "stable_semantic_passes": ORIGINAL_STABLE_PASSES,
            "terminal_structural_failures": 6,
            "raw_evidence_sha256": EVIDENCE_SHA256,
        },
        "scope_reproduction": scope_reproduced,
        "cm58_reconciliation": {
            "comparable_rows": len(cm58_comparable),
            "matching_rows": cm58_matches,
            "mismatches": len(cm58_comparable) - cm58_matches,
        },
        "metrics": {
            "raw_rows": len(row_records),
            "structurally_evaluable_rows": len(cm58_comparable),
            "frozen_semantic_passes": original_passes,
            "ownership_adjusted_semantic_passes": adjusted_passes,
            "frozen_stable_semantic_passes": ORIGINAL_STABLE_PASSES,
            "ownership_adjusted_stable_passes": stable_passes,
            "newly_recovered_attempt_passes": transitions["FROZEN_FAIL → ADJUSTED_PASS"],
            "newly_recovered_stable_cases": sum(
                record["adjusted_case_status"] == "STABLE_PASS" and not record["frozen_stable_pass"]
                for record in case_records
            ),
            "model_report_overreach_rows": len(model_overreach),
            "cm58_reconciled_overreach_rows": len(reconciled_overreach),
            "rows_only_report_presence_failure": len(only_report_failure),
            "rows_report_presence_plus_additional_errors": len(report_plus_other),
            "remaining_system_report_scope_failures": sum(
                record["system_report_scope_correct"] is False for record in cm58_comparable
            ),
            "report_content_failures": len(report_content_failures),
            "remaining_adjusted_semantic_failures": sum(
                record["ownership_adjusted_semantic_status"] == "FAIL" for record in row_records
            ),
        },
        "transitions": dict(sorted(transitions.items())),
        "stable_case_status_counts": dict(
            sorted(Counter(record["adjusted_case_status"] for record in case_records).items())
        ),
        "model_residual_counts": dict(sorted(model_residuals.items())),
        "ownership_adjusted_system_residual_counts": dict(sorted(adjusted_residuals.items())),
        "report_safety_accounting": {
            "report_removals": sum(
                any(
                    action.get("kind") == "remove_report_task" for action in record["cm58_2_action"]
                )
                for record in row_records
            ),
            "report_additions": sum(
                any(
                    action.get("kind") == "add_report_standard"
                    for action in record["cm58_2_action"]
                )
                for record in row_records
            ),
            "report_boundary_rejections": sum(
                record["cm58_2_failure"] is not None for record in row_records
            ),
            "unchanged_report_scopes": sum(
                not record["cm58_2_changed"]
                for record in row_records
                if record["cm58_2_changed"] != "NOT_EVALUABLE"
            ),
        },
        "family_metrics": _family_metrics(case_records),
        "anchor_metrics": anchor_metrics,
        "decision": (
            "SI_V2R_SR2_REPORT_PRESENCE_RESOLVED"
            if len(reconciled_overreach) == len(model_overreach)
            and not report_content_failures
            and scope_reproduced["total"]
            else "SI_V2R_SR2_OWNERSHIP_CONTRACT_CONFLICT"
        ),
        "provider_inference_calls": 0,
        "endpoint_calls": 0,
        "worker_program_calls": 0,
        "rows": row_records,
        "cases": case_records,
    }


def _protected_unchanged() -> bool:
    """Verify SR2 has no protected source or historical artifact changes."""
    return (
        subprocess.run(
            ["git", "diff", "--quiet", BASELINE_SHA, "--", *PROTECTED_PATHS],
            cwd=REPO_ROOT,
            check=False,
        ).returncode
        == 0
    )


def write_artifacts(result: dict[str, Any], output_dir: Path = DEFAULT_OUTPUT_DIR) -> None:
    """Write bounded SR2 row, case, residual, and result projections."""
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = result["rows"]
    cases = result["cases"]
    safe_result = {key: value for key, value in result.items() if key not in {"rows", "cases"}}
    safe_result["evidence"] = {
        key: value for key, value in result["evidence"].items() if key != "path"
    }
    payloads = {
        "adjusted_rows.json": rows,
        "adjusted_cases.json": cases,
        "residual_summary.json": {
            "version": result["version"],
            "transitions": result["transitions"],
            "model_residual_counts": result["model_residual_counts"],
            "ownership_adjusted_system_residual_counts": result[
                "ownership_adjusted_system_residual_counts"
            ],
            "report_safety_accounting": result["report_safety_accounting"],
            "metrics": result["metrics"],
            "stable_case_status_counts": result["stable_case_status_counts"],
        },
        "result.json": safe_result,
    }
    for name, payload in payloads.items():
        (output_dir / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


def main() -> int:
    """Run SR2 and optionally write its provider-free artifacts."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    result = analyze_evidence(args.evidence)
    if not _protected_unchanged():
        raise SystemExit("Protected production or historical artifact changed.")
    if args.write:
        write_artifacts(result, args.output_dir)
    printable = {key: value for key, value in result.items() if key not in {"rows", "cases"}}
    print(json.dumps(printable, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
