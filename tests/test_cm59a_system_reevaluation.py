"""Provider-free CM-59A system reevaluation gate tests."""

from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from pydantic import BaseModel
from scripts import cm57p5_fresh_holdout as p5
from scripts import cm57p9_runtime_fingerprint as fingerprint
from scripts import cm59a_system_reevaluation as cm59

from wellplot.agent.code_mode.planner import ReportTask, SectionTask, SemanticPlan
from wellplot.agent.providers.base import (
    ProviderMetrics,
    ProviderRequestError,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from wellplot.capabilities import CapabilityRegistry

CHECKPOINT = "a" * 40


def _endpoint_pair() -> tuple[dict[str, object], dict[str, object]]:
    """Build equal, valid endpoint fingerprints without network access."""
    payload = {"data": [{"id": cm59.FROZEN_MODEL, "created": 1}]}
    pre = fingerprint.build_endpoint_fingerprint_v2(
        endpoint="http://endpoint.example/v1",
        model_api_label=cm59.FROZEN_MODEL,
        models_payload=payload,
    )
    post = dict(pre)
    return pre, post


def _facts(case: dict[str, object], *, valid: bool = True) -> dict[str, object]:
    """Build bounded evaluator facts for a synthetic decision population."""
    sections = [list(section) for section in case["expected_sections"]]
    return {
        "report_task_present": bool(case["expected_report_capabilities"]),
        "report_capability_ids": list(case["expected_report_capabilities"]),
        "section_task_count": len(sections),
        "section_capability_signatures": sections,
        "report_presence_correct": valid,
        "report_capabilities_exact": valid,
        "section_count_correct": valid,
        "section_multiset_exact": valid,
        "missing_section_signatures": [] if valid else sections,
        "extra_section_signatures": [],
        "within_task_duplicates": [],
        "duplicate_capability_type": False,
        "parent_closure_valid": True,
        "unresolved_requirements_count": 0,
        "unresolved_correct": valid,
    }


def _safety() -> dict[str, object]:
    """Build a no-op three-layer safety result."""
    policy_by_layer = {
        "cm58_1": cm59.POLICY_VERSIONS["capability_safety"],
        "cm58_2": cm59.POLICY_VERSIONS["report_boundary_safety"],
        "cm58_3": cm59.POLICY_VERSIONS["section_leaf_safety"],
    }
    return {
        name: {
            "status": "PASSED",
            "changed": False,
            "evidence": {
                "policy_version": policy_by_layer[name],
                "changed": False,
                "actions": [],
            },
            "failure_code": None,
        }
        for name in cm59.SAFETY_LAYER_KEYS
    }


def _rows(
    cases: tuple[dict[str, object], ...],
    *,
    invalid_case_ids: set[str] | None = None,
    worker_case_id: str | None = None,
) -> tuple[list[dict[str, object]], dict[str, object], dict[str, object]]:
    """Build a complete provider-free population for gate tests."""
    invalid_case_ids = invalid_case_ids or set()
    pre, post = _endpoint_pair()
    pre_hash = cm59.sha256_text(cm59.canonical_json(pre))
    rows: list[dict[str, object]] = []
    for case in cases:
        case_id = str(case["case_id"])
        valid = case_id not in invalid_case_ids
        facts = _facts(case, valid=valid)
        classification = p5.classify_facts(facts)
        for attempt_index in range(cm59.ATTEMPTS):
            planner = {
                "provider_calls": 1,
                "program_calls": 0,
                "call_trace": [{"call_kind": "INITIAL", "outcome": "structured_success"}],
                "response_schema_sha256": cm59._schema_sha256(),
                "initial_plan_available": True,
                "invalid_response_retry_used": False,
                "semantic_correction_used": False,
                "final_planner_success": True,
                "final_error_type": None,
                "final_error_code": None,
                "provider_infrastructure_failure": False,
                "raw_work_unit_facts": facts,
                "raw_classification": classification,
                "raw_contract_ok": valid,
                "final_plan_projection": None,
                "final_work_unit_facts": facts,
                "final_classification": classification,
                "final_contract_ok": valid,
                "final_plan_available": True,
                "terminal_stage": None,
                "terminal_failure_code": None,
                "safety_action_count": 0,
            }
            rows.append(
                {
                    **cm59.frozen_provenance(),
                    "authorized_checkpoint": CHECKPOINT,
                    "endpoint_pre_fingerprint_sha256": pre_hash,
                    "case_id": case_id,
                    "family": case["family"],
                    "residual_class": case["residual_class"],
                    "attempt_index": attempt_index,
                    "request_sha256": cm59.sha256_text(str(case["request"])),
                    "expected_report_capabilities": list(case["expected_report_capabilities"]),
                    "expected_sections": [list(section) for section in case["expected_sections"]],
                    "expected_unresolved_count": case["expected_unresolved_count"],
                    "planner": planner,
                    "safety": _safety(),
                    "final_system": {
                        "final_plan_available": True,
                        "final_plan_projection": None,
                        "final_work_unit_facts": facts,
                        "final_classification": planner["final_classification"],
                        "final_contract_ok": valid,
                        "terminal_stage": None,
                        "terminal_failure_code": None,
                    },
                    "program_calls": 1 if case_id == worker_case_id else 0,
                }
            )
    return rows, pre, post


def _plan_for_case(case: dict[str, object]) -> SemanticPlan:
    """Build a provider-free plan from corpus gold for backend-boundary tests."""
    report = case["expected_report_capabilities"]
    return SemanticPlan(
        summary="synthetic CM-59A plan",
        report_task=(
            ReportTask(goal="synthetic report", capability_ids=tuple(report)) if report else None
        ),
        section_tasks=tuple(
            SectionTask(goal="synthetic section", capability_ids=tuple(section))
            for section in case["expected_sections"]
        ),
    )


def _rows_for_case(rows: list[dict[str, object]], case_id: str) -> list[dict[str, object]]:
    """Return both attempts for one synthetic case."""
    return [row for row in rows if row["case_id"] == case_id]


def _set_safe_rejection(rows: list[dict[str, object]], case_ids: set[str]) -> None:
    """Mark cases as stable deterministic safety rejections."""
    for case_id in case_ids:
        for row in _rows_for_case(rows, case_id):
            raw_facts = copy.deepcopy(row["planner"]["raw_work_unit_facts"])
            raw_facts["section_count_correct"] = False
            raw_facts["section_multiset_exact"] = False
            planner = row["planner"]
            planner.update(
                {
                    "raw_work_unit_facts": raw_facts,
                    "raw_contract_ok": False,
                    "raw_classification": p5.classify_facts(raw_facts),
                    "final_contract_ok": False,
                    "final_plan_available": False,
                    "final_work_unit_facts": None,
                    "final_classification": "SAFE_REJECTION",
                    "terminal_stage": "section_leaf_safety",
                    "terminal_failure_code": "synthetic_safe_rejection",
                }
            )
            row["final_system"].update(
                {
                    "final_plan_available": False,
                    "final_work_unit_facts": None,
                    "final_classification": "SAFE_REJECTION",
                    "final_contract_ok": False,
                    "terminal_stage": "section_leaf_safety",
                    "terminal_failure_code": "synthetic_safe_rejection",
                }
            )
            row["safety"]["cm58_3"] = {
                "status": "FAILED",
                "changed": False,
                "evidence": None,
                "failure_code": "synthetic_safe_rejection",
            }


def _set_planner_failure(
    rows: list[dict[str, object]], case_id: str, *, infrastructure: bool = False
) -> None:
    """Mark both attempts as a stable planner or infrastructure failure."""
    for row in _rows_for_case(rows, case_id):
        planner = row["planner"]
        planner.update(
            {
                "raw_work_unit_facts": None,
                "raw_plan_projection": None,
                "final_planner_success": False,
                "final_error_type": "ProviderRequestError",
                "final_error_code": "timeout" if infrastructure else "invalid_response",
                "provider_infrastructure_failure": infrastructure,
                "raw_contract_ok": False,
                "raw_classification": "INFRA_FAILURE" if infrastructure else "PLANNER_FAILURE",
                "final_work_unit_facts": None,
                "final_contract_ok": False,
                "final_plan_available": False,
                "final_classification": "INFRA_FAILURE" if infrastructure else "PLANNER_FAILURE",
                "terminal_stage": "planner",
                "terminal_failure_code": "timeout" if infrastructure else "invalid_response",
            }
        )
        row["final_system"].update(
            {
                "final_plan_available": False,
                "final_work_unit_facts": None,
                "final_classification": "INFRA_FAILURE" if infrastructure else "PLANNER_FAILURE",
                "final_contract_ok": False,
                "terminal_stage": "planner",
                "terminal_failure_code": "timeout" if infrastructure else "invalid_response",
            }
        )


def _set_safety_regression(rows: list[dict[str, object]], case_id: str) -> None:
    """Mark a raw-pass case as a final semantic regression."""
    for row in _rows_for_case(rows, case_id):
        invalid_facts = copy.deepcopy(row["planner"]["raw_work_unit_facts"])
        invalid_facts["section_multiset_exact"] = False
        row["planner"].update(
            {
                "final_work_unit_facts": invalid_facts,
                "final_contract_ok": False,
                "final_classification": "SECTION_WORK_UNIT_MISMATCH",
                "final_plan_available": True,
            }
        )
        row["final_system"].update(
            {
                "final_work_unit_facts": invalid_facts,
                "final_contract_ok": False,
                "final_classification": "SECTION_WORK_UNIT_MISMATCH",
                "final_plan_available": True,
            }
        )


def _set_unnecessary_action(rows: list[dict[str, object]], case_id: str) -> None:
    """Mark a raw-pass case as changed by an unnecessary safety action."""
    for row in _rows_for_case(rows, case_id):
        row["planner"]["safety_action_count"] = 1
        row["safety"]["cm58_2"] = {
            "status": "REPAIRED",
            "changed": True,
            "evidence": {
                "policy_version": cm59.POLICY_VERSIONS["report_boundary_safety"],
                "changed": True,
                "actions": [
                    {
                        "kind": "add_report_standard",
                        "reason": "explicit_report_intent_missing_capability",
                    }
                ],
            },
            "failure_code": None,
        }


@dataclass
class _FakeBackend:
    """Return one prebuilt plan and record provider-free boundary calls."""

    plan: SemanticPlan
    calls: list[StructuredGenerationRequest] = field(default_factory=list)

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        self.calls.append(request)
        return StructuredGenerationResult(
            value=response_model.model_validate(self.plan.model_dump()),
            metrics=ProviderMetrics(total_tokens=1, latency_ms=1.0),
        )


class _PlannerFailureBackend:
    """Raise one stable provider error without contacting a provider."""

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        """Return the provider-neutral invalid-response failure used by the test."""
        raise ProviderRequestError(
            cm59.ProviderFailureCategory.INVALID_RESPONSE,
            "synthetic invalid response",
        )


def _assert_safe_rejection(
    result: dict[str, object],
    *,
    terminal_stage: str,
    failure_code: str,
) -> None:
    """Assert that a safety terminal cannot be scored as a final plan."""
    assert result["final_plan_available"] is False
    assert result["final_plan_projection"] is None
    assert result["final_work_unit_facts"] is None
    assert result["final_contract_ok"] is False
    assert result["final_classification"] == "SAFE_REJECTION"
    assert result["terminal_stage"] == terminal_stage
    assert result["terminal_failure_code"] == failure_code


def _safety_test_case() -> tuple[dict[str, object], SemanticPlan, CapabilityRegistry]:
    """Return a corpus gold plan suitable for provider-free safety tests."""
    case = cm59.load_case_definitions()[0]
    return case, _plan_for_case(case), cm59.create_builtin_registry()


def test_corpus_is_fresh_balanced_and_provider_safe() -> None:
    """The reevaluation corpus has the required topology and no leaked IDs."""
    cases = cm59.load_case_definitions()
    assert len(cases) == 24
    assert {case["family"] for case in cases} == set(cm59.FAMILIES)
    assert all(not cm59.PATH_RE.search(str(case["request"])) for case in cases)
    assert all(
        not any(term.casefold() in str(case["request"]).casefold() for term in cm59.CAPABILITY_IDS)
        for case in cases
    )


def test_prelive_report_is_provider_and_endpoint_free(monkeypatch: pytest.MonkeyPatch) -> None:
    """The pre-live audit cannot construct a provider or touch the endpoint."""

    def fail(*args: object, **kwargs: object) -> object:
        raise AssertionError("network/provider access is forbidden in pre-live audit")

    monkeypatch.setattr(cm59, "_provider_configuration", fail)
    monkeypatch.setattr(cm59.fingerprint, "capture_endpoint_fingerprint_v2", fail)
    # CM-59A is frozen against report-boundary v1; CM-59A-R1 intentionally
    # changes the current production policy to v2. This test isolates its
    # provider/endpoint-free property without rewriting historical hashes.
    monkeypatch.setattr(cm59, "_verify_production_matches_baseline", lambda: None)
    monkeypatch.setattr(
        cm59,
        "POLICY_VERSIONS",
        {
            "capability_safety": "cm58.reference-admissibility.v1",
            "report_boundary_safety": "cm58.report-boundary.v1",
            "section_leaf_safety": "cm58.section-leaf-admissibility.v1",
        },
    )
    report = cm59.prelive_report()
    assert report["status"] == "PRELIVE_READY"
    assert report["provider_calls"] == 0
    assert report["endpoint_calls"] == 0
    assert report["program_worker_calls"] == 0


def test_run_execution_uses_production_planner_and_three_safety_layers() -> None:
    """A fake structured result traverses the real planner/safety composition."""
    case = cm59.load_case_definitions()[0]
    backend = _FakeBackend(_plan_for_case(case))
    result = asyncio.run(
        cm59.run_execution(
            case,
            delegate=backend,
            registry=cm59.create_builtin_registry(),
        )
    )
    assert len(backend.calls) == 1
    assert result["provider_calls"] == 1
    assert result["program_calls"] == 0
    assert result["response_schema_sha256"] == cm59._schema_sha256()
    assert list(result["safety"]) == ["cm58_1", "cm58_2", "cm58_3"]
    assert result["final_plan_available"] is True
    assert isinstance(result["final_work_unit_facts"], dict)
    assert result["terminal_stage"] is None


def test_cm581_terminal_clears_transient_final_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CM-58.1 rejection is recorded without scoring its rejected plan."""
    case, plan, registry = _safety_test_case()

    def fail(**kwargs: object) -> object:
        raise cm59.CapabilitySafetyFailure("synthetic_cm581", "synthetic failure")

    monkeypatch.setattr(cm59, "enforce_capability_safety", fail)
    result = asyncio.run(cm59.run_execution(case, delegate=_FakeBackend(plan), registry=registry))

    _assert_safe_rejection(
        result,
        terminal_stage="capability_safety",
        failure_code="synthetic_cm581",
    )
    assert result["safety"]["cm58_1"]["status"] == "FAILED"
    assert result["safety"]["cm58_2"]["status"] == "NOT_RUN"
    assert result["safety"]["cm58_3"]["status"] == "NOT_RUN"


def test_cm582_terminal_clears_transient_final_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CM-58.2 rejection preserves completed-layer evidence and fails closed."""
    case, plan, registry = _safety_test_case()
    real_capability_safety = cm59.enforce_capability_safety

    def capability_pass(
        *, request: str, plan: SemanticPlan, registry: CapabilityRegistry
    ) -> object:
        return real_capability_safety(request=request, plan=plan, registry=registry)

    def fail(**kwargs: object) -> object:
        raise cm59.ReportBoundarySafetyFailure("synthetic_cm582", "synthetic failure")

    monkeypatch.setattr(cm59, "enforce_capability_safety", capability_pass)
    monkeypatch.setattr(cm59, "enforce_report_boundary_safety", fail)
    result = asyncio.run(cm59.run_execution(case, delegate=_FakeBackend(plan), registry=registry))

    _assert_safe_rejection(
        result,
        terminal_stage="report_boundary_safety",
        failure_code="synthetic_cm582",
    )
    assert result["safety"]["cm58_1"]["status"] == "PASSED"
    assert result["safety"]["cm58_2"]["status"] == "FAILED"
    assert result["safety"]["cm58_3"]["status"] == "NOT_RUN"


def test_cm583_terminal_clears_transient_final_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CM-58.3 rejection preserves both earlier layer results and fails closed."""
    case, plan, registry = _safety_test_case()
    real_capability_safety = cm59.enforce_capability_safety
    real_report_safety = cm59.enforce_report_boundary_safety

    def capability_pass(
        *, request: str, plan: SemanticPlan, registry: CapabilityRegistry
    ) -> object:
        return real_capability_safety(request=request, plan=plan, registry=registry)

    def report_pass(*, request: str, plan: SemanticPlan, registry: CapabilityRegistry) -> object:
        return real_report_safety(request=request, plan=plan, registry=registry)

    def fail(**kwargs: object) -> object:
        raise cm59.SectionLeafSafetyFailure("synthetic_cm583", "synthetic failure")

    monkeypatch.setattr(cm59, "enforce_capability_safety", capability_pass)
    monkeypatch.setattr(cm59, "enforce_report_boundary_safety", report_pass)
    monkeypatch.setattr(cm59, "enforce_section_leaf_safety", fail)
    result = asyncio.run(cm59.run_execution(case, delegate=_FakeBackend(plan), registry=registry))

    _assert_safe_rejection(
        result,
        terminal_stage="section_leaf_safety",
        failure_code="synthetic_cm583",
    )
    assert result["safety"]["cm58_1"]["status"] == "PASSED"
    assert result["safety"]["cm58_2"]["status"] == "PASSED"
    assert result["safety"]["cm58_3"]["status"] == "FAILED"


def test_safety_terminal_row_is_integrity_valid_and_stable_safe_reject(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A deterministic safety rejection serializes and classifies stably."""
    cases = cm59.load_case_definitions()
    case = cases[0]
    pre, _ = _endpoint_pair()
    pre_hash = cm59.sha256_text(cm59.canonical_json(pre))

    def fail(**kwargs: object) -> object:
        raise cm59.CapabilitySafetyFailure("synthetic_cm581", "synthetic failure")

    monkeypatch.setattr(cm59, "enforce_capability_safety", fail)
    rows, _, _ = _rows(cases)
    for attempt_index in range(cm59.ATTEMPTS):
        replacement = asyncio.run(
            cm59.run_row(
                case,
                attempt_index=attempt_index,
                delegate=_FakeBackend(_plan_for_case(case)),
                registry=cm59.create_builtin_registry(),
                authorized_checkpoint=CHECKPOINT,
                endpoint_pre_fingerprint_sha256=pre_hash,
            )
        )
        assert cm59._row_integrity_reasons(replacement) == []
        rows[attempt_index] = replacement

    assert cm59.case_statuses(rows, cases)[str(case["case_id"])] == "STABLE_SAFE_REJECT"


def test_planner_terminal_remains_distinct_from_safe_rejection() -> None:
    """A planner failure has no plan but retains its planner classification."""
    case, _, registry = _safety_test_case()
    result = asyncio.run(
        cm59.run_execution(case, delegate=_PlannerFailureBackend(), registry=registry)
    )

    assert result["final_plan_available"] is False
    assert result["final_plan_projection"] is None
    assert result["final_work_unit_facts"] is None
    assert result["final_contract_ok"] is False
    assert result["final_classification"] == "PLANNER_FAILURE"
    assert result["terminal_stage"] == "planner"


def test_historical_anchors_are_diagnostic_only() -> None:
    """The provider-free residual anchors expose both pass and mismatch shapes."""
    anchors = cm59.historical_anchor_diagnostics()
    assert anchors["decision_bearing"] is False
    assert anchors["historical_lichen_p_shape"]["status"] == "PASS"
    assert anchors["historical_lichen_rc_shape"]["status"] == "MISMATCH"
    assert anchors["historical_mariner_p_shape"]["status"] == "PASS"
    assert anchors["historical_mariner_rc"]["status"] == "NO_PLAN_ANCHOR"


def test_complete_population_is_accepted() -> None:
    """A fully stable population reaches the accepted terminal decision."""
    cases = cm59.load_case_definitions()
    rows, pre, post = _rows(cases)
    assert (
        cm59.decision(
            rows,
            cases,
            expected_checkpoint=CHECKPOINT,
            pre_fingerprint=pre,
            post_fingerprint=post,
        )
        == "SYSTEM_REEVALUATION_ACCEPTED"
    )


def test_valid_model_failure_is_rejected_not_inconclusive() -> None:
    """A stable non-infrastructure failure is a model result, not an infra gap."""
    cases = cm59.load_case_definitions()
    rows, pre, post = _rows(cases, invalid_case_ids={str(cases[0]["case_id"])})
    assert (
        cm59.decision(
            rows,
            cases,
            expected_checkpoint=CHECKPOINT,
            pre_fingerprint=pre,
            post_fingerprint=post,
        )
        == "SYSTEM_REEVALUATION_REJECTED"
    )


def test_missing_provenance_is_inconclusive() -> None:
    """Population or endpoint provenance corruption fails closed."""
    cases = cm59.load_case_definitions()
    rows, pre, post = _rows(cases)
    rows[0]["endpoint_pre_fingerprint_sha256"] = "0" * 64
    assert (
        cm59.decision(
            rows,
            cases,
            expected_checkpoint=CHECKPOINT,
            pre_fingerprint=pre,
            post_fingerprint=post,
        )
        == "INCONCLUSIVE_SYSTEM_REEVALUATION"
    )


def test_worker_calls_invalidate_population() -> None:
    """Any program/worker execution makes this planner-only gate inconclusive."""
    cases = cm59.load_case_definitions()
    rows, pre, _ = _rows(cases, worker_case_id=str(cases[0]["case_id"]))
    complete, reasons = cm59.population_integrity(
        rows,
        cases,
        expected_checkpoint=CHECKPOINT,
        pre_fingerprint=pre,
    )
    assert complete is False
    assert "worker_program_call" in reasons


@pytest.mark.parametrize(
    ("safe_rejection_count", "expected"),
    [(2, "SYSTEM_REEVALUATION_ACCEPTED"), (3, "SYSTEM_REEVALUATION_REJECTED")],
)
def test_stable_pass_floor_is_exact(safe_rejection_count: int, expected: str) -> None:
    """The 22/24 stable-pass floor is enforced without threshold drift."""
    cases = cm59.load_case_definitions()
    rows, pre, post = _rows(cases)
    rejection_indices = (2, 4) if safe_rejection_count == 2 else (2, 4, 5)
    rejected_ids = {str(cases[index]["case_id"]) for index in rejection_indices}
    _set_safe_rejection(rows, rejected_ids)
    assert (
        cm59.decision(
            rows,
            cases,
            expected_checkpoint=CHECKPOINT,
            pre_fingerprint=pre,
            post_fingerprint=post,
        )
        == expected
    )


def test_family_floor_rejects_two_of_four() -> None:
    """An adequate aggregate cannot hide a family below its 3/4 floor."""
    cases = cm59.load_case_definitions()
    rows, pre, post = _rows(cases)
    _set_safe_rejection(rows, {str(cases[4]["case_id"]), str(cases[5]["case_id"])})
    assert (
        cm59.decision(
            rows,
            cases,
            expected_checkpoint=CHECKPOINT,
            pre_fingerprint=pre,
            post_fingerprint=post,
        )
        == "SYSTEM_REEVALUATION_REJECTED"
    )


@pytest.mark.parametrize("residual_index", [0, 16])
def test_residual_class_floor_requires_both_cases(residual_index: int) -> None:
    """Both Lichen and Mariner residual classes are mandatory 2/2 gates."""
    cases = cm59.load_case_definitions()
    rows, pre, post = _rows(cases)
    _set_safe_rejection(rows, {str(cases[residual_index]["case_id"])})
    assert (
        cm59.decision(
            rows,
            cases,
            expected_checkpoint=CHECKPOINT,
            pre_fingerprint=pre,
            post_fingerprint=post,
        )
        == "SYSTEM_REEVALUATION_REJECTED"
    )


def test_terminal_invalid_response_is_rejected() -> None:
    """A stable valid-model invalid-response terminal is not infrastructure."""
    cases = cm59.load_case_definitions()
    rows, pre, post = _rows(cases)
    _set_planner_failure(rows, str(cases[0]["case_id"]))
    assert (
        cm59.decision(
            rows,
            cases,
            expected_checkpoint=CHECKPOINT,
            pre_fingerprint=pre,
            post_fingerprint=post,
        )
        == "SYSTEM_REEVALUATION_REJECTED"
    )


def test_provider_infrastructure_failure_is_inconclusive() -> None:
    """A timeout is an operational gap and must not become model rejection."""
    cases = cm59.load_case_definitions()
    rows, pre, post = _rows(cases)
    _set_planner_failure(rows, str(cases[0]["case_id"]), infrastructure=True)
    assert (
        cm59.decision(
            rows,
            cases,
            expected_checkpoint=CHECKPOINT,
            pre_fingerprint=pre,
            post_fingerprint=post,
        )
        == "INCONCLUSIVE_SYSTEM_REEVALUATION"
    )


def test_wrong_escape_and_safety_regression_are_rejected() -> None:
    """A final plan escape and a raw-pass regression are both hard failures."""
    cases = cm59.load_case_definitions()
    rows, pre, post = _rows(cases)
    _set_safety_regression(rows, str(cases[0]["case_id"]))
    assert (
        cm59.decision(
            rows,
            cases,
            expected_checkpoint=CHECKPOINT,
            pre_fingerprint=pre,
            post_fingerprint=post,
        )
        == "SYSTEM_REEVALUATION_REJECTED"
    )

    rows, pre, post = _rows(cases, invalid_case_ids={str(cases[1]["case_id"])})
    assert (
        cm59.decision(
            rows,
            cases,
            expected_checkpoint=CHECKPOINT,
            pre_fingerprint=pre,
            post_fingerprint=post,
        )
        == "SYSTEM_REEVALUATION_REJECTED"
    )


def test_unnecessary_raw_pass_action_is_rejected() -> None:
    """A safety mutation on a raw-pass plan violates the no-op invariant."""
    cases = cm59.load_case_definitions()
    rows, pre, post = _rows(cases)
    _set_unnecessary_action(rows, str(cases[0]["case_id"]))
    assert (
        cm59.decision(
            rows,
            cases,
            expected_checkpoint=CHECKPOINT,
            pre_fingerprint=pre,
            post_fingerprint=post,
        )
        == "SYSTEM_REEVALUATION_REJECTED"
    )


def test_unstable_final_attempt_is_rejected() -> None:
    """Different final facts across attempts are unstable, not accepted."""
    cases = cm59.load_case_definitions()
    rows, pre, post = _rows(cases)
    second = _rows_for_case(rows, str(cases[0]["case_id"]))[1]
    invalid_facts = copy.deepcopy(second["planner"]["final_work_unit_facts"])
    invalid_facts["section_multiset_exact"] = False
    second["planner"].update(
        {
            "final_work_unit_facts": invalid_facts,
            "final_contract_ok": False,
            "final_classification": "SECTION_WORK_UNIT_MISMATCH",
        }
    )
    second["final_system"].update(
        {
            "final_work_unit_facts": invalid_facts,
            "final_contract_ok": False,
            "final_classification": "SECTION_WORK_UNIT_MISMATCH",
        }
    )
    assert (
        cm59.decision(
            rows,
            cases,
            expected_checkpoint=CHECKPOINT,
            pre_fingerprint=pre,
            post_fingerprint=post,
        )
        == "SYSTEM_REEVALUATION_REJECTED"
    )


def test_endpoint_identity_mismatch_is_inconclusive() -> None:
    """PRE/POST normalized endpoint identity drift invalidates the run."""
    cases = cm59.load_case_definitions()
    rows, pre, _ = _rows(cases)
    post = fingerprint.build_endpoint_fingerprint_v2(
        endpoint="http://endpoint.example/v1",
        model_api_label=cm59.FROZEN_MODEL,
        models_payload={"data": [{"id": cm59.FROZEN_MODEL}, {"id": "other-model"}]},
    )
    assert (
        cm59.decision(
            rows,
            cases,
            expected_checkpoint=CHECKPOINT,
            pre_fingerprint=pre,
            post_fingerprint=post,
        )
        == "INCONCLUSIVE_SYSTEM_REEVALUATION"
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda row: row.__setitem__("P_prompt_sha256", "0" * 64),
        lambda row: row.__setitem__("response_schema_sha256", "0" * 64),
        lambda row: row.__setitem__("source_summary_sha256", "0" * 64),
        lambda row: row.__setitem__("policy_versions", {"drifted": "v0"}),
    ],
)
def test_frozen_provenance_drift_is_inconclusive(mutation: object) -> None:
    """Prompt, schema, source, and policy drift all fail population integrity."""
    cases = cm59.load_case_definitions()
    rows, pre, post = _rows(cases)
    mutation(rows[0])  # type: ignore[operator]
    assert (
        cm59.decision(
            rows,
            cases,
            expected_checkpoint=CHECKPOINT,
            pre_fingerprint=pre,
            post_fingerprint=post,
        )
        == "INCONCLUSIVE_SYSTEM_REEVALUATION"
    )


def test_population_shape_corruption_is_inconclusive() -> None:
    """Missing, duplicate, and wrong case-attempt populations fail closed."""
    cases = cm59.load_case_definitions()
    rows, pre, post = _rows(cases)
    rows.pop()
    for corrupted in (rows,):
        complete, reasons = cm59.population_integrity(
            corrupted,
            cases,
            expected_checkpoint=CHECKPOINT,
            pre_fingerprint=pre,
        )
        assert complete is False
        assert "wrong_row_count" in reasons

    rows, pre, post = _rows(cases)
    rows.append(copy.deepcopy(rows[0]))
    assert (
        cm59.decision(
            rows,
            cases,
            expected_checkpoint=CHECKPOINT,
            pre_fingerprint=pre,
            post_fingerprint=post,
        )
        == "INCONCLUSIVE_SYSTEM_REEVALUATION"
    )

    rows, pre, post = _rows(cases)
    rows[0]["attempt_index"] = 9
    assert (
        cm59.decision(
            rows,
            cases,
            expected_checkpoint=CHECKPOINT,
            pre_fingerprint=pre,
            post_fingerprint=post,
        )
        == "INCONCLUSIVE_SYSTEM_REEVALUATION"
    )


def test_live_artifacts_reject_stale_data_before_endpoint_access(tmp_path: Path) -> None:
    """A prior POST or summary cannot survive into a new live population."""
    stale_post = tmp_path / "post.json"
    stale_post.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="non-empty"):
        cm59._ensure_fresh_live_artifacts((tmp_path / "evidence.jsonl", stale_post))


def test_gold_plans_survive_all_safety_layers_unchanged() -> None:
    """Every corpus gold plan is safe before any provider result exists."""
    cm59._validate_gold_plans_against_safety(cm59.load_case_definitions())


def test_tampered_derived_evidence_is_inconclusive() -> None:
    """Contradictory facts or safety counts invalidate the whole population."""
    cases = cm59.load_case_definitions()
    rows, pre, post = _rows(cases)
    row = rows[0]
    row["planner"]["final_contract_ok"] = False
    assert (
        cm59.decision(
            rows,
            cases,
            expected_checkpoint=CHECKPOINT,
            pre_fingerprint=pre,
            post_fingerprint=post,
        )
        == "INCONCLUSIVE_SYSTEM_REEVALUATION"
    )

    rows, pre, post = _rows(cases)
    row = rows[0]
    row["planner"]["raw_work_unit_facts"]["section_multiset_exact"] = False
    assert (
        cm59.decision(
            rows,
            cases,
            expected_checkpoint=CHECKPOINT,
            pre_fingerprint=pre,
            post_fingerprint=post,
        )
        == "INCONCLUSIVE_SYSTEM_REEVALUATION"
    )

    rows, pre, post = _rows(cases)
    row = rows[0]
    row["safety"]["cm58_1"]["evidence"]["actions"] = [{"kind": "remove_reference"}]
    assert (
        cm59.decision(
            rows,
            cases,
            expected_checkpoint=CHECKPOINT,
            pre_fingerprint=pre,
            post_fingerprint=post,
        )
        == "INCONCLUSIVE_SYSTEM_REEVALUATION"
    )
