"""CM-59A-E2 provider-free reevaluation harness.

This harness reuses the historical CM-59A execution/evaluation primitives but
binds them to the remediated production checkpoint and current safety-policy
versions. Live inference is intentionally not implemented in this slice.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import cm57p5_fresh_holdout as p5  # noqa: E402
from scripts import cm59a_system_reevaluation as historical  # noqa: E402
from wellplot.agent.code_mode.planner import (  # noqa: E402
    _PLANNER_SYSTEM_PROMPT,
)

BASELINE_SHA = "37234cb33b64c34291f96690a211150ce447b532"
CASE_PATH = REPO_ROOT / "tests/fixtures/typed_worker/cm59a_system_reevaluation_cases.json"
OUTPUT_PATH = Path("/tmp/cm59a-e2-system-reevaluation-qwen.jsonl")
ENDPOINT_PRE_PATH = Path("/tmp/cm59a-e2-endpoint-pre.json")
ENDPOINT_POST_PATH = Path("/tmp/cm59a-e2-endpoint-post.json")
SUMMARY_PATH = Path("/tmp/cm59a-e2-system-reevaluation-summary.json")
EXPERIMENT_VERSION = "CM-59A-E2"
CORPUS_VERSION = "cm59a.system-reevaluation.v1"
FROZEN_MODEL = historical.FROZEN_MODEL
PLANNER_TEMPERATURE = historical.PLANNER_TEMPERATURE
MAX_OUTPUT_TOKENS = historical.MAX_OUTPUT_TOKENS
MAX_TOKENS_PARAMETER = historical.MAX_TOKENS_PARAMETER
TIMEOUT_SECONDS = historical.TIMEOUT_SECONDS
ATTEMPTS = historical.ATTEMPTS
FAMILIES = historical.FAMILIES
PRODUCTION_ARTIFACTS = historical.PRODUCTION_ARTIFACTS
FROZEN_EXECUTION_CONTROLS = dict(historical.FROZEN_EXECUTION_CONTROLS)
SAFETY_LAYER_KEYS = historical.SAFETY_LAYER_KEYS
SAFETY_ACTION_KINDS = historical.SAFETY_ACTION_KINDS
INFRASTRUCTURE_CATEGORIES = historical.INFRASTRUCTURE_CATEGORIES
PATH_RE = historical.PATH_RE
CAPABILITY_IDS = historical.CAPABILITY_IDS
POLICY_VERSIONS = {
    "capability_safety": "cm58.reference-admissibility.v1",
    "report_boundary_safety": "cm58.report-boundary.v2",
    "section_leaf_safety": "cm58.section-leaf-admissibility.v1",
}
TARGET_CASES = {
    "FIG": "cm59-single-fig-05",
    "LINDEN": "cm59-reference-linden-10",
    "XENON": "cm59-mixed-xenon-21",
}
TARGET_EXPECTATIONS = {
    "cm59-single-fig-05": {
        "expected_report_capabilities": [],
        "expected_sections": [["section.log_plot", "track.normal", "binding.curve"]],
    },
    "cm59-reference-linden-10": {
        "expected_report_capabilities": [],
        "expected_sections": [
            [
                "section.log_plot",
                "track.reference",
                "track.normal",
                "binding.curve",
            ]
        ],
    },
    "cm59-mixed-xenon-21": {
        "expected_report_capabilities": ["report.standard"],
        "expected_sections": [["section.log_plot", "track.array", "binding.raster"]],
    },
}
CHECKPOINT_RE = re.compile(r"^[0-9a-f]{40}$")


def canonical_json(value: object) -> str:
    """Serialize JSON-shaped values deterministically."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(value: str) -> str:
    """Hash exact UTF-8 text bytes."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def artifact_sha256(path: Path) -> str:
    """Hash one repository artifact."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_output(*arguments: str) -> bytes:
    """Return exact output from a repository-local Git command."""
    return subprocess.check_output(["git", *arguments], cwd=REPO_ROOT, stderr=subprocess.STDOUT)


def current_checkout_sha() -> str:
    """Return the current checkout SHA."""
    return _git_output("rev-parse", "HEAD").decode().strip()


def _baseline_blob(relative_path: str) -> bytes:
    """Read one protected artifact from the accepted E2 parent checkpoint."""
    return _git_output("show", f"{BASELINE_SHA}:{relative_path}")


def load_case_definitions(
    path: Path = CASE_PATH,
) -> tuple[dict[str, object], ...]:
    """Load the unchanged CM-59A corpus through the historical validator."""
    cases = historical.load_case_definitions(path)
    if path == CASE_PATH and artifact_sha256(path) != (
        "b6a605158e667e5250df99a53cb4ba521473f8146fad2022aed2dff77d5f551b"
    ):
        raise ValueError("CM-59A-E2 corpus hash drifted.")
    return cases


def _schema_sha256() -> str:
    """Hash the production SemanticPlan response schema."""
    return historical._schema_sha256()


def _source_summary() -> dict[str, object]:
    """Return the established bounded source summary."""
    return historical._source_summary()


def _source_summary_sha256() -> str:
    """Hash the established source summary."""
    return sha256_text(canonical_json(_source_summary()))


def _production_source_hashes() -> dict[str, str]:
    """Return exact hashes for protected production artifacts."""
    return {path: artifact_sha256(REPO_ROOT / path) for path in PRODUCTION_ARTIFACTS}


def _verify_production_matches_baseline() -> None:
    """Prove production bytes remain equal to the E2 parent checkpoint."""
    for relative_path in PRODUCTION_ARTIFACTS:
        if (REPO_ROOT / relative_path).read_bytes() != _baseline_blob(relative_path):
            raise RuntimeError(f"CM-59A-E2 production artifact drifted: {relative_path}")


def frozen_provenance() -> dict[str, object]:
    """Return provenance bound to every future E2 evidence row."""
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "design_baseline_sha": BASELINE_SHA,
        "harness_sha256": artifact_sha256(Path(__file__)),
        "corpus_sha256": artifact_sha256(CASE_PATH),
        "production_source_hashes": _production_source_hashes(),
        "P_prompt_sha256": sha256_text(_PLANNER_SYSTEM_PROMPT),
        "response_schema_sha256": _schema_sha256(),
        "source_summary_sha256": _source_summary_sha256(),
        "policy_versions": dict(POLICY_VERSIONS),
        "execution_controls": dict(FROZEN_EXECUTION_CONTROLS),
    }


def _validate_target_contract(cases: tuple[dict[str, object], ...]) -> None:
    """Verify the three E2 targets and their unchanged gold semantics."""
    by_id = {str(case["case_id"]): case for case in cases}
    if set(TARGET_CASES.values()) - set(by_id):
        raise ValueError("CM-59A-E2 target case set drifted.")
    for case_id, expected in TARGET_EXPECTATIONS.items():
        case = by_id[case_id]
        if case["expected_report_capabilities"] != expected["expected_report_capabilities"]:
            raise ValueError(f"CM-59A-E2 report gold drifted for {case_id}.")
        if case["expected_sections"] != expected["expected_sections"]:
            raise ValueError(f"CM-59A-E2 section gold drifted for {case_id}.")


def verify_frozen_contract() -> dict[str, object]:
    """Run all provider-free E2 corpus, policy, and production checks."""
    cases = load_case_definitions()
    _validate_target_contract(cases)
    _verify_production_matches_baseline()
    historical._validate_gold_plans_against_safety(cases)
    prompt_sha = sha256_text(_PLANNER_SYSTEM_PROMPT)
    schema_sha = _schema_sha256()
    source_sha = _source_summary_sha256()
    if prompt_sha != p5.EXPECTED_BASE_PROMPT_SHA256:
        raise RuntimeError("CM-59A-E2 production planner prompt drifted.")
    if schema_sha != "3a331166ccc570a74056dea7770d04b16f8fa32dc3641d6c37de6c26cf81d9e3":
        raise RuntimeError("CM-59A-E2 SemanticPlan schema drifted.")
    if source_sha != "ec6147a1b5e1ac6374e34ae3d66d11275542c6b340337cb26d3ae1d06240532e":
        raise RuntimeError("CM-59A-E2 source summary drifted.")
    if p5._catalog_sha256() != "b1b9c85db961cb8b97f1c8b6f914a6a75f5bf57cf49ca4413c64d35311b80d37":
        raise RuntimeError("CM-59A-E2 capability catalogue drifted.")
    if POLICY_VERSIONS != {
        "capability_safety": "cm58.reference-admissibility.v1",
        "report_boundary_safety": "cm58.report-boundary.v2",
        "section_leaf_safety": "cm58.section-leaf-admissibility.v1",
    }:
        raise RuntimeError("CM-59A-E2 safety policy versions drifted.")
    return {
        "case_count": len(cases),
        "family_counts": dict(Counter(str(case["family"]) for case in cases)),
        "residual_counts": dict(Counter(str(case["residual_class"]) for case in cases)),
        "corpus_sha256": artifact_sha256(CASE_PATH),
        "harness_sha256": artifact_sha256(Path(__file__)),
        "P_prompt_sha256": prompt_sha,
        "response_schema_sha256": schema_sha,
        "source_summary_sha256": source_sha,
        "production_source_hashes": _production_source_hashes(),
        "policy_versions": dict(POLICY_VERSIONS),
        "target_cases": dict(TARGET_CASES),
    }


def prelive_report() -> dict[str, object]:
    """Return the provider-free E2 implementation audit."""
    contract = verify_frozen_contract()
    cases = load_case_definitions()
    return {
        "status": "PRELIVE_READY",
        "experiment_version": EXPERIMENT_VERSION,
        "design_baseline_sha": BASELINE_SHA,
        "current_checkout_sha": current_checkout_sha(),
        "live_inference": "NOT_AUTHORIZED",
        "provider_calls": 0,
        "endpoint_calls": 0,
        "program_worker_calls": 0,
        "production_source_changes": 0,
        "production_adoption": "NOT_AUTHORIZED",
        "CM-59A": "COMPLETE / VALID REJECTION",
        "CM-57D": "BLOCKED",
        "future_controls": {**FROZEN_EXECUTION_CONTROLS, "attempts": ATTEMPTS},
        "future_population": {
            "cases": len(cases),
            "families": len(FAMILIES),
            "planner_executions": len(cases) * ATTEMPTS,
            "provider_calls_min": len(cases) * ATTEMPTS,
            "provider_calls_max": len(cases) * ATTEMPTS * 3,
            "future_populations_remaining": 1,
        },
        "remediation_targets": {
            label: {"case_id": case_id, "required_status": "STABLE_PASS"}
            for label, case_id in TARGET_CASES.items()
        },
        "historical_anchor_diagnostics": historical.historical_anchor_diagnostics(),
        "acceptance_thresholds": {
            "stable_passes_minimum": 22,
            "family_stable_passes_minimum": 3,
            "lichen_stable_passes": 2,
            "mariner_stable_passes": 2,
            "target_case_stable_passes": 3,
            "wrong_final_plan_escapes_maximum": 0,
            "safety_regressions_maximum": 0,
            "unstable_cases_maximum": 0,
            "planner_terminal_failures_maximum": 0,
        },
        "output_paths": {
            "evidence": str(OUTPUT_PATH),
            "endpoint_pre": str(ENDPOINT_PRE_PATH),
            "endpoint_post": str(ENDPOINT_POST_PATH),
            "summary": str(SUMMARY_PATH),
        },
        **contract,
    }


async def run_execution(*args: object, **kwargs: object) -> dict[str, object]:
    """Run the current production planner and all CM-58 safety layers."""
    return await historical.run_execution(*args, **kwargs)


async def run_row(
    case: dict[str, object],
    *,
    attempt_index: int,
    delegate: object,
    registry: object,
    authorized_checkpoint: str,
    endpoint_pre_fingerprint_sha256: str,
) -> dict[str, object]:
    """Build one E2 evidence row from the current production execution."""
    result = await run_execution(case, delegate=delegate, registry=registry)
    provenance = frozen_provenance()
    return {
        **provenance,
        "authorized_checkpoint": authorized_checkpoint,
        "endpoint_pre_fingerprint_sha256": endpoint_pre_fingerprint_sha256,
        "case_id": case["case_id"],
        "family": case["family"],
        "residual_class": case["residual_class"],
        "attempt_index": attempt_index,
        "request_sha256": sha256_text(str(case["request"])),
        "expected_report_capabilities": list(case["expected_report_capabilities"]),
        "expected_sections": [list(section) for section in case["expected_sections"]],
        "expected_unresolved_count": case["expected_unresolved_count"],
        "planner": {key: value for key, value in result.items() if key != "safety"},
        "safety": result["safety"],
        "final_system": {
            "final_plan_available": result["final_plan_available"],
            "final_plan_projection": result["final_plan_projection"],
            "final_work_unit_facts": result["final_work_unit_facts"],
            "final_classification": result["final_classification"],
            "final_contract_ok": result["final_contract_ok"],
            "terminal_stage": result["terminal_stage"],
            "terminal_failure_code": result["terminal_failure_code"],
        },
        "program_calls": result["program_calls"],
    }


def _row_planner(row: dict[str, object]) -> dict[str, object]:
    """Return one bounded planner result."""
    return historical._row_planner(row)


def _row_final(row: dict[str, object]) -> dict[str, object]:
    """Return one bounded final-system result."""
    return historical._row_final(row)


def _final_facts(row: dict[str, object]) -> dict[str, object] | None:
    """Return final facts when a final plan exists."""
    return historical._final_facts(row)


def population_integrity(
    rows: list[dict[str, object]],
    cases: tuple[dict[str, object], ...],
    *,
    expected_checkpoint: str | None = None,
    pre_fingerprint: dict[str, object] | None = None,
) -> tuple[bool, list[str]]:
    """Fail closed on E2 rows, provenance, controls, and worker isolation."""
    reasons: set[str] = set()
    expected_ids = {str(case["case_id"]) for case in cases}
    pairs = [(str(row.get("case_id")), row.get("attempt_index")) for row in rows]
    if len(rows) != len(cases) * ATTEMPTS:
        reasons.add("wrong_row_count")
    if len(set(pairs)) != len(pairs):
        reasons.add("duplicate_case_attempt")
    if {case_id for case_id, _ in pairs} != expected_ids:
        reasons.add("case_set_mismatch")
    by_case: dict[str, set[object]] = {}
    for case_id, attempt in pairs:
        by_case.setdefault(case_id, set()).add(attempt)
    if any(attempts != set(range(ATTEMPTS)) for attempts in by_case.values()):
        reasons.add("attempt_index_mismatch")
    checkpoints = {row.get("authorized_checkpoint") for row in rows}
    if None in checkpoints or len(checkpoints) != 1:
        reasons.add("checkpoint_missing_or_mixed")
    elif expected_checkpoint is not None and checkpoints != {expected_checkpoint}:
        reasons.add("checkpoint_mismatch")
    if pre_fingerprint is None:
        reasons.add("pre_fingerprint_missing")
    else:
        expected_pre = sha256_text(canonical_json(pre_fingerprint))
        if any(row.get("endpoint_pre_fingerprint_sha256") != expected_pre for row in rows):
            reasons.add("pre_fingerprint_mismatch")
    expected_cases = {str(case["case_id"]): case for case in cases}
    provenance = frozen_provenance()
    for row in rows:
        case = expected_cases.get(str(row.get("case_id")))
        if case is None:
            continue
        for key, value in provenance.items():
            if row.get(key) != value:
                reasons.add(f"{key}_mismatch")
        if row.get("family") != case["family"]:
            reasons.add("family_mismatch")
        if row.get("residual_class") != case["residual_class"]:
            reasons.add("residual_class_mismatch")
        if row.get("request_sha256") != sha256_text(str(case["request"])):
            reasons.add("request_hash_mismatch")
        for field in (
            "expected_report_capabilities",
            "expected_sections",
            "expected_unresolved_count",
        ):
            if row.get(field) != case[field]:
                reasons.add(f"{field}_mismatch")
        planner = _row_planner(row)
        if planner.get("response_schema_sha256") != _schema_sha256():
            reasons.add("planner_schema_mismatch")
        if int(row.get("program_calls", 0)) != 0 or int(planner.get("program_calls", 0)) != 0:
            reasons.add("worker_program_call")
        if int(planner.get("provider_calls", -1)) != len(planner.get("call_trace", [])):
            reasons.add("provider_call_trace_mismatch")
        if set(row.get("safety", {})) != set(SAFETY_LAYER_KEYS):
            reasons.add("safety_layer_set_mismatch")
        reasons.update(historical._row_integrity_reasons(row))
    return not reasons, sorted(reasons)


def _case_statuses(
    rows: list[dict[str, object]], cases: tuple[dict[str, object], ...]
) -> dict[str, str]:
    """Classify each case from its two final-system attempts."""
    return historical.case_statuses(rows, cases)


def _endpoint_status(
    pre: dict[str, object] | None,
    post: dict[str, object] | None,
) -> tuple[bool, list[str]]:
    """Validate and compare normalized endpoint identity."""
    return historical._endpoint_status(pre, post)


def decision(
    rows: list[dict[str, object]],
    cases: tuple[dict[str, object], ...],
    *,
    expected_checkpoint: str | None = None,
    pre_fingerprint: dict[str, object] | None = None,
    post_fingerprint: dict[str, object] | None = None,
) -> str:
    """Apply CM-59A acceptance plus the three E2 target hard gates."""
    complete, _ = population_integrity(
        rows,
        cases,
        expected_checkpoint=expected_checkpoint,
        pre_fingerprint=pre_fingerprint,
    )
    endpoint_ok, _ = _endpoint_status(pre_fingerprint, post_fingerprint)
    if not complete or not endpoint_ok:
        return "INCONCLUSIVE_SYSTEM_REEVALUATION"
    if any(bool(_row_planner(row).get("provider_infrastructure_failure")) for row in rows):
        return "INCONCLUSIVE_SYSTEM_REEVALUATION"
    statuses = _case_statuses(rows, cases)
    if any(status in {"UNAVAILABLE", "UNSTABLE"} for status in statuses.values()):
        return "SYSTEM_REEVALUATION_REJECTED"
    if any(statuses[case_id] != "STABLE_PASS" for case_id in TARGET_CASES.values()):
        return "SYSTEM_REEVALUATION_REJECTED"
    stable_passes = sum(status == "STABLE_PASS" for status in statuses.values())
    family_passes = {
        family: sum(
            statuses[str(case["case_id"])] == "STABLE_PASS"
            for case in cases
            if case["family"] == family
        )
        for family in FAMILIES
    }
    residual_passes = {
        residual: sum(
            statuses[str(case["case_id"])] == "STABLE_PASS"
            for case in cases
            if case["residual_class"] == residual
        )
        for residual in ("LICHEN_CLASS", "MARINER_CLASS")
    }
    planner_terminal_failures = sum(
        not bool(_row_planner(row).get("final_planner_success")) for row in rows
    )
    wrong_escapes = sum(status == "STABLE_WRONG_ESCAPE" for status in statuses.values())
    safety_regressions = sum(
        bool(_row_planner(row).get("raw_contract_ok"))
        and not bool(_row_final(row).get("final_contract_ok"))
        for row in rows
    )
    unnecessary_actions = sum(
        bool(_row_planner(row).get("raw_contract_ok"))
        and int(_row_planner(row).get("safety_action_count", 0)) > 0
        for row in rows
    )
    reference = historical._reference_safety(rows, cases)
    structural = historical._structural_safety(rows)
    if (
        stable_passes < 22
        or any(value < 3 for value in family_passes.values())
        or residual_passes["LICHEN_CLASS"] != 2
        or residual_passes["MARINER_CLASS"] != 2
        or planner_terminal_failures
        or wrong_escapes
        or safety_regressions
        or unnecessary_actions
        or reference["unexpected_reference"]
        or reference["missing_required_reference"]
        or structural["parent_closure_invalid"]
        or structural["duplicate_capability_type"]
    ):
        return "SYSTEM_REEVALUATION_REJECTED"
    return "SYSTEM_REEVALUATION_ACCEPTED"


def summarize_population(
    rows: list[dict[str, object]],
    cases: tuple[dict[str, object], ...],
    *,
    authorized_checkpoint: str | None = None,
    pre_fingerprint: dict[str, object] | None = None,
    post_fingerprint: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build bounded E2 evidence and target-gate results."""
    complete, reasons = population_integrity(
        rows,
        cases,
        expected_checkpoint=authorized_checkpoint,
        pre_fingerprint=pre_fingerprint,
    )
    statuses = _case_statuses(rows, cases)
    endpoint_ok, endpoint_reasons = _endpoint_status(pre_fingerprint, post_fingerprint)
    final_decision = decision(
        rows,
        cases,
        expected_checkpoint=authorized_checkpoint,
        pre_fingerprint=pre_fingerprint,
        post_fingerprint=post_fingerprint,
    )
    family_passes = {
        family: sum(
            statuses[str(case["case_id"])] == "STABLE_PASS"
            for case in cases
            if case["family"] == family
        )
        for family in FAMILIES
    }
    residual_passes = {
        residual: sum(
            statuses[str(case["case_id"])] == "STABLE_PASS"
            for case in cases
            if case["residual_class"] == residual
        )
        for residual in ("LICHEN_CLASS", "MARINER_CLASS")
    }
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "authorized_checkpoint": authorized_checkpoint,
        "decision": final_decision,
        "population": {
            "expected_rows": len(cases) * ATTEMPTS,
            "actual_rows": len(rows),
            "cases": len(cases),
            "attempts_per_case": ATTEMPTS,
            "planner_executions": len(rows),
            "provider_calls": sum(int(_row_planner(row).get("provider_calls", 0)) for row in rows),
            "program_worker_calls": sum(int(row.get("program_calls", 0)) for row in rows),
            "complete": complete,
            "integrity_reasons": reasons,
        },
        "case_statuses": statuses,
        "target_case_statuses": {
            label: statuses.get(case_id, "UNAVAILABLE") for label, case_id in TARGET_CASES.items()
        },
        "family_stable_passes": family_passes,
        "residual_stable_passes": residual_passes,
        "raw_to_final_transitions": historical._transition_counts(rows),
        "planner_metrics": {
            "successful_executions": sum(
                bool(_row_planner(row).get("final_planner_success")) for row in rows
            ),
            "invalid_response_retries": sum(
                bool(_row_planner(row).get("invalid_response_retry_used")) for row in rows
            ),
            "semantic_corrections": sum(
                bool(_row_planner(row).get("semantic_correction_used")) for row in rows
            ),
            "terminal_planner_failures": sum(
                not bool(_row_planner(row).get("final_planner_success")) for row in rows
            ),
            "provider_infrastructure_failures": sum(
                bool(_row_planner(row).get("provider_infrastructure_failure")) for row in rows
            ),
        },
        "reference_safety": historical._reference_safety(rows, cases),
        "structural_safety": historical._structural_safety(rows),
        "safety_regressions": sum(
            bool(_row_planner(row).get("raw_contract_ok"))
            and not bool(_row_final(row).get("final_contract_ok"))
            for row in rows
        ),
        "wrong_final_plan_escapes": sum(
            status == "STABLE_WRONG_ESCAPE" for status in statuses.values()
        ),
        "endpoint_provenance": {
            "valid_and_equal": endpoint_ok,
            "reasons": endpoint_reasons,
            "pre_normalized_identity_sha256": (
                pre_fingerprint.get("normalized_identity_sha256") if pre_fingerprint else None
            ),
            "post_normalized_identity_sha256": (
                post_fingerprint.get("normalized_identity_sha256") if post_fingerprint else None
            ),
        },
        "provenance": frozen_provenance(),
        "acceptance_thresholds": {
            "stable_passes_minimum": 22,
            "family_stable_passes_minimum": 3,
            "lichen_stable_passes": 2,
            "mariner_stable_passes": 2,
            "target_case_status": "STABLE_PASS",
            "wrong_final_plan_escapes_maximum": 0,
            "safety_regressions_maximum": 0,
            "unstable_cases_maximum": 0,
            "planner_terminal_failures_maximum": 0,
        },
        "production_adoption": "NOT_AUTHORIZED",
        "CM-57D": "BLOCKED",
    }


def verify_reviewed_checkout(checkpoint: str) -> None:
    """Require the exact E2 implementation checkpoint for future finalization."""
    if CHECKPOINT_RE.fullmatch(checkpoint) is None or current_checkout_sha() != checkpoint:
        raise RuntimeError("CM-59A-E2 checkout does not match the authorized checkpoint.")
    guarded = (
        "scripts/cm59a_e2_system_reevaluation.py",
        "scripts/cm59a_system_reevaluation.py",
        "tests/fixtures/typed_worker/cm59a_system_reevaluation_cases.json",
        "tests/test_cm59a_system_reevaluation.py",
        "docs/evaluations/agent-code-mode/CM-59A-development-memory.md",
        *PRODUCTION_ARTIFACTS,
    )
    for relative_path in guarded:
        path = REPO_ROOT / relative_path
        if not path.exists() or path.read_bytes() != _git_output(
            "show", f"{checkpoint}:{relative_path}"
        ):
            raise RuntimeError(f"CM-59A-E2 guarded artifact drifted: {relative_path}")


def finalize(
    *,
    evidence_path: Path,
    pre_path: Path,
    post_path: Path,
    authorized_checkpoint: str,
) -> dict[str, object]:
    """Finalize a future population without constructing a provider."""
    verify_reviewed_checkout(authorized_checkpoint)
    verify_frozen_contract()
    cases = load_case_definitions()
    rows = historical._load_jsonl(evidence_path)
    pre = historical._load_fingerprint(pre_path)
    post = historical._load_fingerprint(post_path)
    return summarize_population(
        rows,
        cases,
        authorized_checkpoint=authorized_checkpoint,
        pre_fingerprint=pre,
        post_fingerprint=post,
    )


def _parser() -> argparse.ArgumentParser:
    """Build the provider-free command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--finalize", action="store_true")
    parser.add_argument("--authorized-checkpoint")
    parser.add_argument("--evidence-path", default=str(OUTPUT_PATH))
    parser.add_argument("--endpoint-fingerprint-pre", default=str(ENDPOINT_PRE_PATH))
    parser.add_argument("--endpoint-fingerprint-post", default=str(ENDPOINT_POST_PATH))
    parser.add_argument("--summary-path", default=str(SUMMARY_PATH))
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the provider-free audit or future provider-free finalization."""
    args = _parser().parse_args(argv)
    if args.finalize:
        if not args.authorized_checkpoint:
            raise SystemExit("--finalize requires --authorized-checkpoint")
        summary = finalize(
            evidence_path=Path(args.evidence_path),
            pre_path=Path(args.endpoint_fingerprint_pre),
            post_path=Path(args.endpoint_fingerprint_post),
            authorized_checkpoint=args.authorized_checkpoint,
        )
        Path(args.summary_path).write_text(canonical_json(summary) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    if args.authorized_checkpoint:
        raise SystemExit("--authorized-checkpoint requires --finalize")
    print(json.dumps(prelive_report(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
