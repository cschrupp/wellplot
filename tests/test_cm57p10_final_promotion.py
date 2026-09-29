"""Provider-free CM-57P10 corpus, evaluator, and gate tests."""

# Test builders prioritize compact synthetic fixtures over public APIs.
# ruff: noqa: ANN001, D103

from __future__ import annotations

import asyncio
import copy
import json
from collections import Counter
from pathlib import Path

import pytest
from scripts import cm57p9_runtime_fingerprint as fingerprint
from scripts import cm57p10_final_promotion as p10

CHECKPOINT = "a" * 40


def _cases() -> tuple[dict[str, object], ...]:
    """Load the frozen P10 cases."""
    return p10.load_case_definitions()


def _endpoint_pair(*, raw_difference: bool = False) -> tuple[dict[str, object], dict[str, object]]:
    """Build valid normalized PRE/POST fingerprints for gate tests."""
    pre_payload = {"data": [{"id": "qwen3.6-35b-a3b", "created": 1}]}
    post_payload = {"data": [{"id": "qwen3.6-35b-a3b", "created": 2 if raw_difference else 1}]}
    pre = fingerprint.build_endpoint_fingerprint_v2(
        endpoint="http://host:8888/v1",
        model_api_label="qwen3.6-35b-a3b",
        models_payload=pre_payload,
    )
    post = fingerprint.build_endpoint_fingerprint_v2(
        endpoint="http://host:8888/v1",
        model_api_label="qwen3.6-35b-a3b",
        models_payload=post_payload,
    )
    for value in (pre, post):
        value["captured_at"] = "2026-01-01T00:00:00+00:00"
    return pre, post


def _facts(case: dict[str, object], *, valid: bool = True) -> dict[str, object]:
    """Build bounded synthetic facts with established gold shape."""
    signatures = [list(section) for section in case["expected_sections"]]
    return {
        "report_task_present": bool(case["expected_report_capabilities"]),
        "report_capability_ids": list(case["expected_report_capabilities"]),
        "section_task_count": len(signatures),
        "section_capability_signatures": signatures,
        "report_presence_correct": valid,
        "report_capabilities_exact": valid,
        "section_count_correct": valid,
        "section_multiset_exact": valid,
        "within_task_duplicates": [],
        "duplicate_capability_type": False,
        "parent_closure_valid": True,
        "unresolved_requirements_count": 0,
        "unresolved_correct": True,
    }


def _result(case: dict[str, object], *, passed: bool, attempt: int) -> dict[str, object]:
    """Build one synthetic arm result."""
    facts = _facts(case, valid=passed)
    return {
        "arm": "P",
        "prompt_sha256": p10._prompt_sha256("P"),
        "response_schema_sha256": p10._schema_sha256(),
        "provider_calls": 1,
        "program_calls": 0,
        "final_planner_success": True,
        "final_error_code": None,
        "provider_infrastructure_failure": False,
        "final_classification": "PLANNER_CONTRACT_OK" if passed else "SECTION_COUNT_MISMATCH",
        "final_work_unit_facts": facts,
        "final_contract_ok": passed,
        "semantic_correction_used": bool(attempt and not passed),
        "invalid_response_retry_used": False,
    }


def _rows(
    cases: tuple[dict[str, object], ...],
    *,
    p_pass: set[str],
    rc_pass: set[str],
    rc_unstable: set[str] | None = None,
    reference_override: str | None = None,
    structural_failure: str | None = None,
    infrastructure: bool = False,
) -> list[dict[str, object]]:
    """Build complete synthetic rows for decision and integrity tests."""
    rc_unstable = rc_unstable or set()
    pre_fingerprint, _ = _endpoint_pair()
    pre_fingerprint_sha256 = p10.endpoint_fingerprint_sha256(pre_fingerprint)
    rows: list[dict[str, object]] = []
    for case in cases:
        case_id = str(case["case_id"])
        for attempt in range(p10.ATTEMPTS):
            row = {
                **p10.frozen_provenance(),
                "authorized_checkpoint": CHECKPOINT,
                "endpoint_pre_fingerprint_sha256": pre_fingerprint_sha256,
                "case_id": case_id,
                "family": case["family"],
                "attempt_index": attempt,
                "request_sha256": p10.sha256_text(str(case["request"])),
                "expected_report_capabilities": list(case["expected_report_capabilities"]),
                "expected_sections": [list(section) for section in case["expected_sections"]],
                "expected_unresolved_count": 0,
                "arms": {},
            }
            p_value = case_id in p_pass
            rc_value = case_id in rc_pass
            if case_id in rc_unstable and attempt == 1:
                rc_value = not rc_value
            for arm, passed in (("P", p_value), ("RC", rc_value)):
                result = _result(case, passed=passed, attempt=attempt)
                result["arm"] = arm
                result["prompt_sha256"] = p10._prompt_sha256(arm)
                if infrastructure and arm == "RC":
                    result["provider_infrastructure_failure"] = True
                    result["final_planner_success"] = False
                    result["final_classification"] = "PROVIDER_INFRA_FAILURE"
                    result["final_contract_ok"] = False
                    result["final_work_unit_facts"] = None
                if reference_override and arm == "RC":
                    facts = result["final_work_unit_facts"]
                    if reference_override == "unexpected":
                        facts["section_capability_signatures"] = [
                            ["section.log_plot", "track.reference", "track.normal", "binding.curve"]
                        ]
                    elif reference_override == "missing":
                        facts["section_capability_signatures"] = [
                            ["section.log_plot", "track.normal", "binding.curve"]
                        ]
                if structural_failure and arm == "RC":
                    facts = result["final_work_unit_facts"]
                    facts[structural_failure] = structural_failure != "parent_closure_valid"
                row["arms"][arm] = result
            rows.append(row)
    return rows


def test_corpus_has_six_families_and_four_fresh_cases_each() -> None:
    cases = _cases()
    assert len(cases) == 24
    assert Counter(case["family"] for case in cases) == Counter(dict.fromkeys(p10.FAMILIES, 4))
    assert len({case["case_id"] for case in cases}) == 24


def test_corpus_requests_are_fresh_and_provider_safe() -> None:
    cases = _cases()
    requests = [str(case["request"]) for case in cases]
    assert len({p10.sha256_text(request) for request in requests}) == 24
    assert all(not p10.PATH_RE.search(request) for request in requests)
    request_text = json.dumps(requests, sort_keys=True)
    assert not any(term in request_text for term in p10.FORBIDDEN_REQUEST_TERMS)
    assert not any(value in request_text for value in p10.CAPABILITY_IDS)


def test_gold_is_checked_against_builtin_registry() -> None:
    registry = p10.create_builtin_registry()
    for case in _cases():
        p10.p5._validate_report_gold(
            case["expected_report_capabilities"], registry, case["case_id"]
        )
        for section in case["expected_sections"]:
            p10.p5._validate_section_gold(section, registry, case["case_id"])


def test_pre_live_report_is_provider_free_and_exactly_sized() -> None:
    real_artifact_sha256 = p10.artifact_sha256
    provider_path = (p10.REPO_ROOT / "src/wellplot/agent/providers/openai_compat_v2.py").resolve()

    def historical_artifact_sha256(path: Path) -> str:
        if Path(path).resolve() == provider_path:
            return p10.EXPECTED_PROVIDER_OPENAI_COMPAT_SHA256
        return real_artifact_sha256(path)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(p10, "artifact_sha256", historical_artifact_sha256)
    try:
        report = p10.prelive_report()
    finally:
        monkeypatch.undo()
    assert report["provider_calls"] == 0
    assert report["future_population"] == {
        "cases": 24,
        "families": 6,
        "cases_per_family": 4,
        "arms": ["P", "RC"],
        "planner_executions": 96,
        "provider_calls_min": 96,
        "provider_calls_max": 192,
    }


def test_historical_provider_drift_still_fails_closed() -> None:
    """The frozen promotion gate rejects a changed current adapter."""
    real_artifact_sha256 = p10.artifact_sha256
    provider_path = (p10.REPO_ROOT / "src/wellplot/agent/providers/openai_compat_v2.py").resolve()

    def drifted_artifact_sha256(path: Path) -> str:
        if Path(path).resolve() == provider_path:
            return "0" * 64
        return real_artifact_sha256(path)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(p10, "artifact_sha256", drifted_artifact_sha256)
    try:
        with pytest.raises(RuntimeError, match="CM-57P10 frozen artifact drifted"):
            p10.prelive_report()
    finally:
        monkeypatch.undo()


def test_shared_row_preserves_p_then_rc_order_without_workers() -> None:
    case = _cases()[0]
    backend = p10.p5._DeterministicBackend(invalid_first=True)
    pre_fingerprint, _ = _endpoint_pair()
    row = asyncio.run(
        p10.run_shared_row(
            case,
            attempt_index=0,
            delegate=backend,
            registry=p10.create_builtin_registry(),
            authorized_checkpoint=CHECKPOINT,
            pre_fingerprint_sha256=p10.endpoint_fingerprint_sha256(pre_fingerprint),
        )
    )
    assert list(row["arms"]) == ["P", "RC"]
    assert all(result["program_calls"] == 0 for result in row["arms"].values())
    assert len(backend.calls) == 3
    assert backend.calls[0].system_prompt == p10.p5._PLANNER_SYSTEM_PROMPT
    assert backend.calls[2].system_prompt == p10.p5.RC_PROMPT


@pytest.mark.parametrize(
    ("p_pass", "rc_pass", "expected"),
    [
        (set(), set(), "STABLE_FAIL"),
        ({"p10-report-aurora-01"}, {"p10-report-aurora-01"}, "STABLE_PASS"),
    ],
)
def test_case_arm_stable_statuses(p_pass, rc_pass, expected) -> None:
    cases = _cases()
    rows = _rows(cases, p_pass=set(p_pass), rc_pass=set(rc_pass))
    assert p10.case_arm_statuses(rows, cases)["p10-report-aurora-01"]["P"] == expected


def test_unstable_case_arm_is_not_a_gain() -> None:
    cases = _cases()
    rows = _rows(
        cases,
        p_pass=set(),
        rc_pass={"p10-report-aurora-01"},
        rc_unstable={"p10-report-aurora-01"},
    )
    statuses = p10.case_arm_statuses(rows, cases)
    assert statuses["p10-report-aurora-01"]["RC"] == "UNSTABLE"
    assert (
        p10.decision(
            rows,
            cases,
            expected_checkpoint=CHECKPOINT,
            pre_fingerprint=_endpoint_pair()[0],
            post_fingerprint=_endpoint_pair()[1],
            p9c_stable=True,
        )
        == "FINAL_PROMOTION_RC_REJECTED"
    )


def test_all_promotion_gates_accept_valid_candidate() -> None:
    cases = _cases()
    p_pass = {str(case["case_id"]) for case in cases[3:]}
    rc_pass = {str(case["case_id"]) for case in cases}
    rows = _rows(cases, p_pass=p_pass, rc_pass=rc_pass)
    pre, post = _endpoint_pair()
    assert (
        p10.decision(
            rows,
            cases,
            expected_checkpoint=CHECKPOINT,
            pre_fingerprint=pre,
            post_fingerprint=post,
            p9c_stable=True,
        )
        == "FINAL_PROMOTION_RC_ACCEPTED"
    )


def test_candidate_without_three_gains_is_rejected() -> None:
    cases = _cases()
    p_pass = {str(case["case_id"]) for case in cases[2:]}
    rows = _rows(cases, p_pass=p_pass, rc_pass={str(case["case_id"]) for case in cases})
    pre, post = _endpoint_pair()
    assert (
        p10.decision(
            rows,
            cases,
            expected_checkpoint=CHECKPOINT,
            pre_fingerprint=pre,
            post_fingerprint=post,
            p9c_stable=True,
        )
        == "FINAL_PROMOTION_RC_REJECTED"
    )


def test_protected_regression_dominates_candidate_gain() -> None:
    cases = _cases()
    p_pass = {str(case["case_id"]) for case in cases[3:]}
    rc_pass = {str(case["case_id"]) for case in cases if case is not cases[3]}
    rows = _rows(cases, p_pass=p_pass, rc_pass=rc_pass)
    pre, post = _endpoint_pair()
    assert (
        p10.decision(
            rows,
            cases,
            expected_checkpoint=CHECKPOINT,
            pre_fingerprint=pre,
            post_fingerprint=post,
            p9c_stable=True,
        )
        == "FINAL_PROMOTION_RC_REJECTED"
    )


@pytest.mark.parametrize("override", ["unexpected", "missing"])
def test_reference_safety_gate_rejects_violation(override: str) -> None:
    cases = _cases()
    reference_case = next(case for case in cases if case["family"] == "REFERENCE_REQUIRED")
    if override == "unexpected":
        reference_case = next(
            case for case in cases if case["family"] == "SINGLE_SECTION_NO_REFERENCE"
        )
    p_pass = {str(case["case_id"]) for case in cases[3:]}
    rows = _rows(
        cases,
        p_pass=p_pass,
        rc_pass={str(case["case_id"]) for case in cases},
        reference_override=override,
    )
    pre, post = _endpoint_pair()
    assert (
        p10.decision(
            rows,
            cases,
            expected_checkpoint=CHECKPOINT,
            pre_fingerprint=pre,
            post_fingerprint=post,
            p9c_stable=True,
        )
        == "FINAL_PROMOTION_RC_REJECTED"
    )
    assert reference_case["family"] in {"REFERENCE_REQUIRED", "SINGLE_SECTION_NO_REFERENCE"}


@pytest.mark.parametrize("field", ["parent_closure_valid", "duplicate_capability_type"])
def test_structural_safety_gate_rejects_violation(field: str) -> None:
    cases = _cases()
    p_pass = {str(case["case_id"]) for case in cases[3:]}
    rows = _rows(
        cases,
        p_pass=p_pass,
        rc_pass={str(case["case_id"]) for case in cases},
        structural_failure=field,
    )
    pre, post = _endpoint_pair()
    assert (
        p10.decision(
            rows,
            cases,
            expected_checkpoint=CHECKPOINT,
            pre_fingerprint=pre,
            post_fingerprint=post,
            p9c_stable=True,
        )
        == "FINAL_PROMOTION_RC_REJECTED"
    )


def test_infrastructure_failure_is_inconclusive() -> None:
    cases = _cases()
    rows = _rows(
        cases,
        p_pass={str(case["case_id"]) for case in cases[3:]},
        rc_pass={str(case["case_id"]) for case in cases},
        infrastructure=True,
    )
    pre, post = _endpoint_pair()
    assert (
        p10.decision(
            rows,
            cases,
            expected_checkpoint=CHECKPOINT,
            pre_fingerprint=pre,
            post_fingerprint=post,
            p9c_stable=True,
        )
        == "INCONCLUSIVE_FINAL_PROMOTION_EVALUATION"
    )


def test_endpoint_identity_change_is_inconclusive_but_raw_catalog_change_is_not() -> None:
    cases = _cases()
    p_pass = {str(case["case_id"]) for case in cases[3:]}
    rows = _rows(cases, p_pass=p_pass, rc_pass={str(case["case_id"]) for case in cases})
    pre, post = _endpoint_pair(raw_difference=True)
    assert (
        p10.decision(
            rows,
            cases,
            expected_checkpoint=CHECKPOINT,
            pre_fingerprint=pre,
            post_fingerprint=post,
            p9c_stable=True,
        )
        == "FINAL_PROMOTION_RC_ACCEPTED"
    )
    changed_post = copy.deepcopy(post)
    changed_post["endpoint"] = "http://other:8888/v1"
    changed_post["normalized_identity_sha256"] = fingerprint.build_endpoint_fingerprint_v2(
        endpoint="http://other:8888/v1",
        model_api_label="qwen3.6-35b-a3b",
        models_payload={"data": [{"id": "qwen3.6-35b-a3b"}]},
    )["normalized_identity_sha256"]
    assert (
        p10.decision(
            rows,
            cases,
            expected_checkpoint=CHECKPOINT,
            pre_fingerprint=pre,
            post_fingerprint=changed_post,
            p9c_stable=True,
        )
        == "INCONCLUSIVE_FINAL_PROMOTION_EVALUATION"
    )


def test_population_integrity_accepts_exact_pre_fingerprint_binding() -> None:
    cases = _cases()
    rows = _rows(cases, p_pass=set(), rc_pass=set())
    pre, _ = _endpoint_pair()
    complete, reasons = p10.population_integrity(
        rows,
        cases,
        expected_checkpoint=CHECKPOINT,
        pre_fingerprint=pre,
    )
    assert complete
    assert reasons == []


def test_population_integrity_rejects_wrong_pre_fingerprint_binding() -> None:
    cases = _cases()
    rows = _rows(cases, p_pass=set(), rc_pass=set())
    rows[0]["endpoint_pre_fingerprint_sha256"] = "f" * 64
    pre, _ = _endpoint_pair()
    complete, reasons = p10.population_integrity(
        rows,
        cases,
        expected_checkpoint=CHECKPOINT,
        pre_fingerprint=pre,
    )
    assert not complete
    assert "pre_fingerprint_mismatch" in reasons


def test_population_integrity_rejects_mixed_pre_fingerprint_hashes() -> None:
    cases = _cases()
    rows = _rows(cases, p_pass=set(), rc_pass=set())
    _, alternate = _endpoint_pair(raw_difference=True)
    rows[-1]["endpoint_pre_fingerprint_sha256"] = p10.endpoint_fingerprint_sha256(alternate)
    pre, _ = _endpoint_pair()
    complete, reasons = p10.population_integrity(
        rows,
        cases,
        expected_checkpoint=CHECKPOINT,
        pre_fingerprint=pre,
    )
    assert not complete
    assert "pre_fingerprint_mismatch" in reasons


def test_population_integrity_rejects_workers_and_wrong_checkpoint() -> None:
    cases = _cases()
    rows = _rows(cases, p_pass=set(), rc_pass=set())
    pre, _ = _endpoint_pair()
    rows[0]["arms"]["RC"]["program_calls"] = 1
    complete, reasons = p10.population_integrity(
        rows,
        cases,
        expected_checkpoint=CHECKPOINT,
        pre_fingerprint=pre,
    )
    assert not complete
    assert "worker_program_call" in reasons
    assert "checkpoint_mismatch" not in reasons
    rows[0]["authorized_checkpoint"] = "b" * 40
    complete, reasons = p10.population_integrity(
        rows,
        cases,
        expected_checkpoint=CHECKPOINT,
        pre_fingerprint=pre,
    )
    assert not complete
    assert "checkpoint_missing_or_mixed" in reasons


@pytest.mark.parametrize(
    "scenario",
    ["accepted", "rejected", "inconclusive"],
)
def test_summary_records_p_series_closure_for_terminal_decisions(scenario) -> None:
    cases = _cases()
    all_case_ids = {str(case["case_id"]) for case in cases}
    if scenario == "accepted":
        p_pass = {str(case["case_id"]) for case in cases[3:]}
        rc_pass = all_case_ids
        infrastructure = False
        expected_decision = "FINAL_PROMOTION_RC_ACCEPTED"
        expected_closed = True
    elif scenario == "rejected":
        p_pass = set()
        rc_pass = set()
        infrastructure = False
        expected_decision = "FINAL_PROMOTION_RC_REJECTED"
        expected_closed = True
    else:
        p_pass = set()
        rc_pass = set()
        infrastructure = True
        expected_decision = "INCONCLUSIVE_FINAL_PROMOTION_EVALUATION"
        expected_closed = False
    rows = _rows(cases, p_pass=p_pass, rc_pass=rc_pass, infrastructure=infrastructure)
    pre, post = _endpoint_pair()
    summary = p10.summarize_population(
        rows,
        cases,
        authorized_checkpoint=CHECKPOINT,
        pre_fingerprint=pre,
        post_fingerprint=post,
    )
    assert summary["decision"] == expected_decision
    assert summary["CM57P_closed_after_valid_result"] is expected_closed
    assert summary["prompt_revisions_remaining"] == (0 if expected_closed else None)
    assert summary["fresh_promotion_holdouts_remaining"] == (0 if expected_closed else None)
    assert summary["additional_prompt_experiments_authorized"] is False


def test_non_empty_evidence_is_rejected_before_live_setup(tmp_path: Path) -> None:
    output = tmp_path / "population.jsonl"
    output.write_text("partial\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="non-empty"):
        p10._ensure_empty_evidence(output)
    empty = tmp_path / "empty.jsonl"
    p10._ensure_empty_evidence(empty)
