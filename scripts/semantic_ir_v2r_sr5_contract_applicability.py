"""Derive and audit the provider-free SI-V2R SR5 applicability map."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

BASELINE_SHA = "eb9736ddda9feb9e5e601760822da7e0e3933286"
RAW_EVIDENCE_SHA256 = "9d175c3b80c2cb6a5d5f62195861d4c0070643a37ab4f99dd02559d018011f08"
DEFAULT_RAW_EVIDENCE = Path("/tmp/si-v2r-live.jsonl")
DEFAULT_OUTPUT_DIR = Path("tests/fixtures/semantic_ir_v2r_sr5")
APPLICABILITY_STATES = {
    "CONTRACT_APPLICABLE",
    "MODEL_OWNED",
    "BLOCKED_BY_REPRESENTATION_CONFLICT",
    "BLOCKED_BY_UNRESOLVED_CONTRACT",
    "FAIL_CLOSED",
    "NOT_APPLICABLE",
    "NOT_EVALUABLE",
}
DIMENSIONS = {
    "report_presence",
    "report_content",
    "reference_admissibility",
    "reference_kind",
    "reference_target",
    "annotation_semantics",
    "constraint_scope",
    "unresolved_requirements",
}
POLICY = {
    "CONFLICTING": "FAIL_CLOSED",
    "EXPLICITLY_FORBIDDEN": "CONTRACT_APPLICABLE_IF_REPRESENTATIONS_ARE_CONSISTENT",
    "EXPLICITLY_REQUESTED": ("CONTRACT_APPLICABLE_FOR_PRESENCE; KIND_AND_TARGET_MODEL_OWNED"),
    "UNSPECIFIED_WITH_MODEL_REFERENCE": "BLOCKED_BY_UNRESOLVED_CONTRACT",
}


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _dump_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_raw_rows(raw_evidence: Path) -> list[dict[str, Any]]:
    if not raw_evidence.is_file():
        raise RuntimeError(f"SR5 raw evidence is missing: {raw_evidence}")
    actual_sha = hashlib.sha256(raw_evidence.read_bytes()).hexdigest()
    if actual_sha != RAW_EVIDENCE_SHA256:
        raise RuntimeError(f"SR5 raw evidence SHA mismatch: {actual_sha}")
    rows = [json.loads(line) for line in raw_evidence.read_text().splitlines() if line]
    if len(rows) != 48:
        raise RuntimeError(f"SR5 expected 48 raw rows, found {len(rows)}")
    keys = {(row["case_id"], row["attempt"]) for row in rows}
    if len(keys) != 48 or {row["attempt"] for row in rows} != {0, 1}:
        raise RuntimeError("SR5 raw population has duplicate or missing attempts")
    if len({row["case_id"] for row in rows}) != 24:
        raise RuntimeError("SR5 raw population does not contain 24 cases")
    return rows


def _validate_frozen_inputs(repo_root: Path) -> None:
    """Validate the upstream SR2/SR3/SR4 records used by the derivation."""
    sr2_result = _load_json(repo_root / "tests/fixtures/semantic_ir_v2r_sr2/result.json")
    if sr2_result["decision"] != "SI_V2R_SR2_REPORT_PRESENCE_RESOLVED":
        raise RuntimeError("SR2 decision drifted")
    if sr2_result["evidence"]["sha256"] != RAW_EVIDENCE_SHA256:
        raise RuntimeError("SR2 evidence binding drifted")

    sr3_result = _load_json(repo_root / "tests/fixtures/semantic_ir_v2r_sr3/result.json")
    if sr3_result["decision"] != "SI_V2R_SR3_ROOT_MECHANISMS_RESOLVED":
        raise RuntimeError("SR3 decision drifted")
    if sr3_result["evidence"]["sha256"] != RAW_EVIDENCE_SHA256:
        raise RuntimeError("SR3 evidence binding drifted")

    sr4_dir = repo_root / "tests/fixtures/semantic_ir_v2r_sr4"
    sr4_result = _load_json(sr4_dir / "result.json")
    if sr4_result["decision"] != "SI_V2R_SR4_OWNERSHIP_CONTRACT_PARTIAL":
        raise RuntimeError("SR4 decision drifted")
    if sr4_result["depth_column_prohibition_scope"] != "UNRESOLVED":
        raise RuntimeError("SR4 depth-column scope policy drifted")
    ownership = _load_json(sr4_dir / "ownership_matrix.json")
    constraint = next(row for row in ownership["rows"] if row["dimension"] == "constraint_scope")
    if constraint["owner"] != "UNRESOLVED":
        raise RuntimeError("SR4 constraint ownership drifted")
    representation = _load_json(sr4_dir / "representation_matrix.json")
    if representation["selected_model"] != "EXPLICIT_PRE_POST_WRAPPERS":
        raise RuntimeError("SR4 representation lifecycle drifted")
    if representation["conflict_rule"]["code"] != "REFERENCE_REPRESENTATION_CONFLICT":
        raise RuntimeError("SR4 representation conflict policy drifted")


def _state_for_reference(row: dict[str, Any], structurally_evaluable: bool) -> str:
    if not structurally_evaluable:
        return "NOT_EVALUABLE"
    provider = row["provider"]
    intent = provider["cm58"]["cm58_1"]["evidence"]["reference_intent"]
    references = provider["compiled_reference_projection"] or []
    has_model_reference = any(reference is not None for reference in references)
    consistency = provider["reference_metadata_consistency"]
    if consistency is False:
        return "BLOCKED_BY_REPRESENTATION_CONFLICT"
    if intent == "conflicting":
        return "FAIL_CLOSED"
    if intent == "explicitly_forbidden":
        return "CONTRACT_APPLICABLE"
    if intent == "explicitly_requested":
        return "CONTRACT_APPLICABLE"
    if intent == "unspecified" and has_model_reference:
        return "BLOCKED_BY_UNRESOLVED_CONTRACT"
    return "NOT_APPLICABLE"


def _safe_reference_projection(provider: dict[str, Any]) -> list[dict[str, str]]:
    """Keep only bounded reference semantics in the committed projection."""
    references = provider.get("compiled_reference_projection") or []
    return [
        {
            "kind": reference["kind"],
            **(
                {"target_semantic_id": reference["target_semantic_id"]}
                if reference.get("target_semantic_id")
                else {}
            ),
        }
        for reference in references
        if reference is not None
    ]


def _derive_rows(
    raw_rows: list[dict[str, Any]],
    repo_root: Path,
) -> list[dict[str, Any]]:
    cases = {
        item["case_id"]: item
        for item in _load_json(
            repo_root / "tests/fixtures/typed_worker/cm59a_system_reevaluation_cases.json"
        )["cases"]
    }
    gold = {
        item["case_id"]: item
        for item in _load_json(
            repo_root / "tests/fixtures/semantic_ir_v2r/cm59a_semantic_intents_v2r.json"
        )["cases"]
    }
    sr2_rows = {
        (item["case_id"], item["attempt"]): item
        for item in _load_json(repo_root / "tests/fixtures/semantic_ir_v2r_sr2/adjusted_rows.json")
    }
    sr3 = {
        item["case_id"]: item
        for item in _load_json(
            repo_root / "tests/fixtures/semantic_ir_v2r_sr3/case_decompositions.json"
        )
    }
    if set(cases) != set(gold) or len(cases) != 24:
        raise RuntimeError("SR5 request/gold corpus does not contain the same 24 cases")

    projections = []
    for row in raw_rows:
        case_id = row["case_id"]
        provider = row["provider"]
        model = provider.get("semantic_model")
        structurally_evaluable = model is not None
        sr2_row = sr2_rows[(case_id, row["attempt"])]
        case_gold = gold[case_id]
        report_scope = (
            "MIXED"
            if case_gold["report_work"] and case_gold["sections"]
            else "REPORT_ONLY"
            if case_gold["report_work"]
            else "SECTION_ONLY"
        )
        roots = sr3.get(case_id, {}).get("root_set", [])
        reference_projection = _safe_reference_projection(provider)
        references_present = bool(reference_projection)
        reference_state = _state_for_reference(row, structurally_evaluable)
        report_state = "CONTRACT_APPLICABLE" if structurally_evaluable else "NOT_EVALUABLE"
        annotation_state = (
            "NOT_EVALUABLE"
            if not structurally_evaluable
            else "MODEL_OWNED"
            if "ANNOTATION_WRONG_OWNER" in roots
            else "NOT_APPLICABLE"
        )
        constraint_state = (
            "NOT_EVALUABLE"
            if not structurally_evaluable
            else "BLOCKED_BY_UNRESOLVED_CONTRACT"
            if "CONSTRAINT_OWNER_MISPLACEMENT" in roots
            else "NOT_APPLICABLE"
        )
        unresolved_state = (
            "NOT_EVALUABLE"
            if not structurally_evaluable
            else "MODEL_OWNED"
            if "UNRESOLVED_PROMOTION" in roots
            else "NOT_APPLICABLE"
        )
        consistency = (
            "NOT_EVALUABLE"
            if not structurally_evaluable
            else "CONFLICT"
            if provider["reference_metadata_consistency"] is False
            else "CONSISTENT"
        )
        final_signature = provider.get("final_signature")
        post_reference = (
            None
            if not structurally_evaluable
            else any(
                "track.reference" in section
                for section in (final_signature or {}).get("sections", [])
            )
        )
        intent = (
            "NOT_EVALUABLE"
            if not structurally_evaluable
            else provider["cm58"]["cm58_1"]["evidence"]["reference_intent"].upper()
        )
        actions = provider["cm58"]["cm58_1"].get("actions", [])
        blockers = []
        if consistency == "CONFLICT":
            blockers.append("REFERENCE_REPRESENTATION_CONFLICT")
        if intent == "UNSPECIFIED" and references_present:
            blockers.append("UNSPECIFIED_REFERENCE_POLICY")
        if constraint_state == "BLOCKED_BY_UNRESOLVED_CONTRACT":
            blockers.append("DEPTH_COLUMN_SCOPE_UNRESOLVED")
        if provider.get("reference_metadata_consistency") is None and structurally_evaluable:
            blockers.append("REFERENCE_REPRESENTATION_NOT_ESTABLISHED")
        dimensions = {
            "report_presence": report_state,
            "report_content": (
                "NOT_EVALUABLE"
                if not structurally_evaluable
                else "MODEL_OWNED"
                if report_scope != "SECTION_ONLY"
                else "NOT_APPLICABLE"
            ),
            "reference_admissibility": reference_state,
            "reference_kind": (
                "NOT_EVALUABLE"
                if not structurally_evaluable
                else "MODEL_OWNED"
                if references_present or intent == "EXPLICITLY_REQUESTED"
                else "NOT_APPLICABLE"
            ),
            "reference_target": (
                "NOT_EVALUABLE"
                if not structurally_evaluable
                else "MODEL_OWNED"
                if references_present or intent == "EXPLICITLY_REQUESTED"
                else "NOT_APPLICABLE"
            ),
            "annotation_semantics": annotation_state,
            "constraint_scope": constraint_state,
            "unresolved_requirements": unresolved_state,
        }
        if set(dimensions) != DIMENSIONS or not set(dimensions.values()) <= APPLICABILITY_STATES:
            raise RuntimeError(f"SR5 row cannot be classified: {case_id}/{row['attempt']}")
        projections.append(
            {
                "case_id": case_id,
                "attempt": row["attempt"],
                "family": row["family"],
                "structurally_evaluable": structurally_evaluable,
                "frozen_structural_status": provider["structural_status"],
                "frozen_model_semantic_status": provider["semantic_status"],
                "sr2_status": sr2_row["ownership_adjusted_semantic_status"],
                "request_report_scope": report_scope,
                "model_report_present": model is not None and model.get("report_work") is not None,
                "model_report_routing_overreach": bool(sr2_row["model_report_routing_overreach"]),
                "model_report_missing": bool(sr2_row["model_report_missing"]),
                "cm58_2_changed": provider["cm58"]["cm58_2"]["changed"],
                "cm58_2_actions": provider["cm58"]["cm58_2"].get("actions", []),
                "report_presence_applicability": report_state,
                "report_content_owner": dimensions["report_content"],
                "reference_request_intent": intent,
                "model_reference_present": references_present,
                "model_reference_projection": reference_projection,
                "reference_kind_status": dimensions["reference_kind"],
                "reference_target_status": dimensions["reference_target"],
                "cm58_1_actions": actions,
                "post_cm58_reference_present": post_reference,
                "reference_representation_status": consistency,
                "reference_admissibility_applicability": reference_state,
                "annotation_applicability": annotation_state,
                "constraint_scope_applicability": constraint_state,
                "unresolved_requirement_applicability": unresolved_state,
                "system_credit_eligibility_by_dimension": {
                    dimension: (state == "CONTRACT_APPLICABLE" and dimension == "report_presence")
                    or (
                        state == "CONTRACT_APPLICABLE"
                        and dimension == "reference_admissibility"
                        and consistency == "CONSISTENT"
                    )
                    for dimension, state in dimensions.items()
                },
                "applicability_dimensions": dimensions,
                "applicability_blockers": sorted(set(blockers)),
                "sr3_root_mechanisms": roots,
                "reference_safety_regression": bool(
                    intent == "EXPLICITLY_REQUESTED" and actions and not references_present
                ),
            }
        )
    return projections


def _grouped_counts(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    grouped = defaultdict(lambda: defaultdict(Counter))
    for row in rows:
        group = str(row[key])
        for dimension, state in row["applicability_dimensions"].items():
            grouped[group][dimension][state] += 1
    return {
        group: {dimension: dict(sorted(counts.items())) for dimension, counts in dimensions.items()}
        for group, dimensions in sorted(grouped.items())
    }


def _derive_artifacts(raw_rows: list[dict[str, Any]], repo_root: Path) -> dict[str, Any]:
    projections = _derive_rows(raw_rows, repo_root)
    cases = {
        item["case_id"]: item
        for item in _load_json(
            repo_root / "tests/fixtures/typed_worker/cm59a_system_reevaluation_cases.json"
        )["cases"]
    }
    dimensions = sorted(DIMENSIONS)
    case_artifacts = []
    for case_id in sorted(cases):
        case_rows = [row for row in projections if row["case_id"] == case_id]
        case_artifacts.append(
            {
                "case_id": case_id,
                "family": case_rows[0]["family"],
                "attempts": len(case_rows),
                "structurally_evaluable_attempts": sum(
                    row["structurally_evaluable"] for row in case_rows
                ),
                "applicability_by_dimension": {
                    dimension: dict(
                        sorted(
                            Counter(
                                row["applicability_dimensions"][dimension] for row in case_rows
                            ).items()
                        )
                    )
                    for dimension in dimensions
                },
                "blockers": sorted(
                    {blocker for row in case_rows for blocker in row["applicability_blockers"]}
                ),
                "sr3_root_mechanisms": sorted(
                    {root for row in case_rows for root in row["sr3_root_mechanisms"]}
                ),
            }
        )
    summary = {
        "schema_version": "si-v2r.sr5.applicability-summary.v1",
        "baseline": BASELINE_SHA,
        "raw_evidence_sha256": RAW_EVIDENCE_SHA256,
        "population": {"rows": 48, "cases": 24, "attempts_per_case": 2},
        "reference_intent_policy": POLICY,
        "counts_are_multidimensional": True,
        "counts_by_dimension": {
            dimension: dict(
                sorted(
                    Counter(
                        row["applicability_dimensions"][dimension] for row in projections
                    ).items()
                )
            )
            for dimension in dimensions
        },
        "counts_by_attempt": _grouped_counts(projections, "attempt"),
        "counts_by_case": _grouped_counts(projections, "case_id"),
        "counts_by_family": _grouped_counts(projections, "family"),
        "blocker_counts": dict(
            sorted(
                Counter(
                    blocker for row in projections for blocker in row["applicability_blockers"]
                ).items()
            )
        ),
        "report_presence_contract_applicable_interventions": sum(
            row["cm58_2_changed"] for row in projections
        ),
        "reference_explicitly_forbidden_rows": sum(
            row["reference_request_intent"] == "EXPLICITLY_FORBIDDEN" for row in projections
        ),
        "reference_unspecified_overreach_rows": sum(
            row["reference_request_intent"] == "UNSPECIFIED" and row["model_reference_present"]
            for row in projections
        ),
        "reference_representation_conflict_rows": sum(
            row["reference_representation_status"] == "CONFLICT" for row in projections
        ),
        "reference_rows_eligible_for_system_credit": sum(
            row["system_credit_eligibility_by_dimension"]["reference_admissibility"]
            for row in projections
        ),
        "depth_column_scope_blocked_rows": sum(
            row["constraint_scope_applicability"] == "BLOCKED_BY_UNRESOLVED_CONTRACT"
            for row in projections
        ),
        "annotation_model_owned_residual_rows": sum(
            row["annotation_applicability"] == "MODEL_OWNED" for row in projections
        ),
        "unresolved_requirement_model_owned_residual_rows": sum(
            row["unresolved_requirement_applicability"] == "MODEL_OWNED" for row in projections
        ),
        "regrade_readiness": "RE_GRADE_PARTIALLY_READY",
    }
    result = {
        "schema_version": "si-v2r.sr5.result.v1",
        "decision": "SI_V2R_SR5_APPLICABILITY_MAP_COMPLETE",
        "baseline": BASELINE_SHA,
        "raw_evidence_sha256": RAW_EVIDENCE_SHA256,
        "population": {"rows": 48, "cases": 24, "attempts_per_case": 2},
        "structural_not_evaluable_attempts": 6,
        "applicability_map": "COMPLETE",
        "regrade_readiness": "RE_GRADE_PARTIALLY_READY",
        "historical_scores_recalculated": False,
        "counterfactual_repairs": 0,
        "scoring_changed": False,
        "provider_inference_calls": 0,
        "endpoint_calls": 0,
        "worker_program_calls": 0,
        "production_behavior_changed": False,
        "adr_cm57": "UNCHANGED",
        "next": (
            "A separately authorized historical regrade may apply only the eligible "
            "SR4 dimensions and must preserve all blocked/model-owned states."
        ),
    }
    return {
        "applicability_rows.json": projections,
        "applicability_cases.json": case_artifacts,
        "applicability_summary.json": summary,
        "result.json": result,
    }


def build_artifacts(raw_evidence: Path, repo_root: Path) -> dict[str, Any]:
    """Authenticate frozen inputs and derive all four SR5 artifacts."""
    _validate_frozen_inputs(repo_root)
    return _derive_artifacts(_load_raw_rows(raw_evidence), repo_root)


def _write_or_check(artifacts: dict[str, Any], output_dir: Path, *, check: bool) -> None:
    for filename, value in artifacts.items():
        path = output_dir / filename
        if check:
            if not path.is_file() or _load_json(path) != value:
                raise RuntimeError(f"SR5 artifact mismatch: {path}")
        else:
            output_dir.mkdir(parents=True, exist_ok=True)
            _dump_json(path, value)


def main() -> None:
    """Run the SR5 derivation and write or verify its artifacts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-evidence", type=Path, default=DEFAULT_RAW_EVIDENCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    artifacts = build_artifacts(args.raw_evidence, repo_root)
    _write_or_check(artifacts, args.output_dir, check=args.check)


if __name__ == "__main__":
    main()
