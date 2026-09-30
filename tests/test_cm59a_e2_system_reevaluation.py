"""Provider-free CM-59A-E2 remediated stack tests."""

from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass, field

import pytest
from pydantic import BaseModel
from scripts import cm57p5_fresh_holdout as p5
from scripts import cm57p9_runtime_fingerprint as fingerprint
from scripts import cm59a_e2_system_reevaluation as e2
from scripts import cm59a_system_reevaluation as historical

from wellplot.agent.code_mode.planner import ReportTask, SectionTask, SemanticPlan
from wellplot.agent.providers.base import (
    ProviderMetrics,
    ProviderRequestError,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)

CHECKPOINT = "a" * 40


def _endpoint_pair() -> tuple[dict[str, object], dict[str, object]]:
    """Build equal valid endpoint fingerprints without network access."""
    payload = {"data": [{"id": e2.FROZEN_MODEL, "created": 1}]}
    pre = fingerprint.build_endpoint_fingerprint_v2(
        endpoint="http://endpoint.example/v1",
        model_api_label=e2.FROZEN_MODEL,
        models_payload=payload,
    )
    return pre, dict(pre)


def _facts(case: dict[str, object], *, valid: bool = True) -> dict[str, object]:
    """Build bounded evaluator facts for synthetic population tests."""
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
    """Build a no-op safety result with the current policy versions."""
    policy_by_layer = {
        "cm58_1": e2.POLICY_VERSIONS["capability_safety"],
        "cm58_2": e2.POLICY_VERSIONS["report_boundary_safety"],
        "cm58_3": e2.POLICY_VERSIONS["section_leaf_safety"],
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
        for name in e2.SAFETY_LAYER_KEYS
    }


def _rows(
    cases: tuple[dict[str, object], ...],
    *,
    invalid_case_ids: set[str] | None = None,
    worker_case_id: str | None = None,
) -> tuple[list[dict[str, object]], dict[str, object], dict[str, object]]:
    """Build a complete provider-free E2 population."""
    invalid_case_ids = invalid_case_ids or set()
    pre, post = _endpoint_pair()
    pre_hash = e2.sha256_text(e2.canonical_json(pre))
    rows: list[dict[str, object]] = []
    for case in cases:
        case_id = str(case["case_id"])
        valid = case_id not in invalid_case_ids
        facts = _facts(case, valid=valid)
        classification = p5.classify_facts(facts)
        for attempt_index in range(e2.ATTEMPTS):
            planner = {
                "provider_calls": 1,
                "program_calls": 0,
                "call_trace": [{"call_kind": "INITIAL", "outcome": "structured_success"}],
                "response_schema_sha256": e2._schema_sha256(),
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
                "raw_plan_projection": None,
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
                    **e2.frozen_provenance(),
                    "authorized_checkpoint": CHECKPOINT,
                    "endpoint_pre_fingerprint_sha256": pre_hash,
                    "case_id": case_id,
                    "family": case["family"],
                    "residual_class": case["residual_class"],
                    "attempt_index": attempt_index,
                    "request_sha256": e2.sha256_text(str(case["request"])),
                    "expected_report_capabilities": list(case["expected_report_capabilities"]),
                    "expected_sections": [list(section) for section in case["expected_sections"]],
                    "expected_unresolved_count": case["expected_unresolved_count"],
                    "planner": planner,
                    "safety": _safety(),
                    "final_system": {
                        "final_plan_available": True,
                        "final_plan_projection": None,
                        "final_work_unit_facts": facts,
                        "final_classification": classification,
                        "final_contract_ok": valid,
                        "terminal_stage": None,
                        "terminal_failure_code": None,
                    },
                    "program_calls": 1 if case_id == worker_case_id else 0,
                }
            )
    return rows, pre, post


def _rows_for_case(rows: list[dict[str, object]], case_id: str) -> list[dict[str, object]]:
    """Return both attempts for one case."""
    return [row for row in rows if row["case_id"] == case_id]


def _set_safe_rejection(rows: list[dict[str, object]], case_id: str) -> None:
    """Mark both attempts as a stable deterministic safety rejection."""
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


@dataclass
class _FakeBackend:
    """Return one prebuilt plan and record structured requests."""

    plan: SemanticPlan
    calls: list[StructuredGenerationRequest] = field(default_factory=list)

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        """Return the fixed plan through the production response boundary."""
        self.calls.append(request)
        return StructuredGenerationResult(
            value=response_model.model_validate(self.plan.model_dump()),
            metrics=ProviderMetrics(total_tokens=1, latency_ms=1.0),
        )

    async def generate_program(self, request: object) -> object:
        """Reject accidental program-worker execution."""
        raise AssertionError(f"Unexpected program request: {request!r}")


class _PlannerFailureBackend:
    """Raise one stable provider-neutral planner failure without network access."""

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        """Return a non-infrastructure invalid-response failure."""
        raise ProviderRequestError(
            historical.ProviderFailureCategory.INVALID_RESPONSE,
            "synthetic invalid response",
        )


def _plan_for_case(case: dict[str, object]) -> SemanticPlan:
    """Build a provider-free plan from corpus gold."""
    return historical._gold_plan(case)


def test_corpus_and_targets_are_frozen() -> None:
    """E2 reuses the exact 24-case corpus and target gold."""
    cases = e2.load_case_definitions()
    assert len(cases) == 24
    assert {case["family"] for case in cases} == set(e2.FAMILIES)
    assert set(e2.TARGET_CASES.values()) == set(e2.TARGET_EXPECTATIONS)
    e2._validate_target_contract(cases)
    assert all(not e2.PATH_RE.search(str(case["request"])) for case in cases)
    assert all(
        not any(term.casefold() in str(case["request"]).casefold() for term in e2.CAPABILITY_IDS)
        for case in cases
    )


def test_prelive_report_is_provider_and_endpoint_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The E2 pre-live audit performs no provider or endpoint calls."""

    def fail(*args: object, **kwargs: object) -> object:
        raise AssertionError("provider or endpoint access is forbidden pre-live")

    monkeypatch.setattr(historical, "_provider_configuration", fail)
    monkeypatch.setattr(fingerprint, "capture_endpoint_fingerprint_v2", fail)
    report = e2.prelive_report()
    assert report["status"] == "PRELIVE_READY"
    assert report["provider_calls"] == 0
    assert report["endpoint_calls"] == 0
    assert report["program_worker_calls"] == 0
    assert report["remediation_targets"]["FIG"]["required_status"] == "STABLE_PASS"


def test_frozen_contract_accepts_current_v2_stack() -> None:
    """The current production bytes and three safety policy versions are frozen."""
    contract = e2.verify_frozen_contract()
    assert contract["policy_versions"] == e2.POLICY_VERSIONS
    assert contract["policy_versions"]["report_boundary_safety"] == "cm58.report-boundary.v2"
    assert contract["corpus_sha256"] == (
        "b6a605158e667e5250df99a53cb4ba521473f8146fad2022aed2dff77d5f551b"
    )


def test_execution_uses_current_planner_and_three_safety_layers() -> None:
    """A provider-free plan crosses the current planner/safety composition."""
    case = e2.load_case_definitions()[0]
    backend = _FakeBackend(_plan_for_case(case))
    result = asyncio.run(
        e2.run_execution(
            case,
            delegate=backend,
            registry=historical.create_builtin_registry(),
        )
    )
    assert len(backend.calls) == 1
    assert result["provider_calls"] == 1
    assert result["program_calls"] == 0
    assert result["final_plan_available"] is True
    assert result["safety"]["cm58_2"]["evidence"]["policy_version"] == ("cm58.report-boundary.v2")


def test_fig_report_boundary_repair_is_included_in_e2_stack() -> None:
    """The remediated scalar-display boundary is exercised provider-free."""
    case = next(
        case for case in e2.load_case_definitions() if case["case_id"] == e2.TARGET_CASES["FIG"]
    )
    plan = SemanticPlan(
        summary="synthetic Fig plan",
        report_task=ReportTask(goal="scalar display", capability_ids=("report.standard",)),
        section_tasks=(
            SectionTask(
                goal="scalar display",
                capability_ids=("section.log_plot", "track.normal", "binding.curve"),
            ),
        ),
    )
    result = asyncio.run(
        e2.run_execution(
            case,
            delegate=_FakeBackend(plan),
            registry=historical.create_builtin_registry(),
        )
    )
    assert result["safety"]["cm58_2"]["status"] == "REPAIRED"
    assert result["final_contract_ok"] is True


def test_complete_population_is_accepted_with_target_passes() -> None:
    """A complete stable population passes only when all E2 targets pass."""
    cases = e2.load_case_definitions()
    rows, pre, post = _rows(cases)
    assert (
        e2.decision(
            rows,
            cases,
            expected_checkpoint=CHECKPOINT,
            pre_fingerprint=pre,
            post_fingerprint=post,
        )
        == "SYSTEM_REEVALUATION_ACCEPTED"
    )


def test_target_safe_rejection_rejects_even_within_general_allowance() -> None:
    """A targeted stable safe rejection cannot consume the two-case allowance."""
    cases = e2.load_case_definitions()
    rows, pre, post = _rows(cases)
    _set_safe_rejection(rows, e2.TARGET_CASES["FIG"])
    _set_safe_rejection(rows, str(cases[0]["case_id"]))
    assert (
        e2.decision(
            rows,
            cases,
            expected_checkpoint=CHECKPOINT,
            pre_fingerprint=pre,
            post_fingerprint=post,
        )
        == "SYSTEM_REEVALUATION_REJECTED"
    )


def test_missing_target_population_is_inconclusive() -> None:
    """An incomplete target population cannot be interpreted as rejection or pass."""
    cases = e2.load_case_definitions()
    rows, pre, post = _rows(cases)
    rows = [row for row in rows if row["case_id"] != e2.TARGET_CASES["LINDEN"]]
    assert (
        e2.decision(
            rows,
            cases,
            expected_checkpoint=CHECKPOINT,
            pre_fingerprint=pre,
            post_fingerprint=post,
        )
        == "INCONCLUSIVE_SYSTEM_REEVALUATION"
    )


def test_worker_calls_invalidate_population() -> None:
    """The planner-only E2 gate rejects any worker/program call."""
    cases = e2.load_case_definitions()
    rows, pre, _ = _rows(cases, worker_case_id=str(cases[0]["case_id"]))
    complete, reasons = e2.population_integrity(
        rows,
        cases,
        expected_checkpoint=CHECKPOINT,
        pre_fingerprint=pre,
    )
    assert complete is False
    assert "worker_program_call" in reasons


def test_provider_infrastructure_failure_is_inconclusive() -> None:
    """A provider-free analogue of a terminal infrastructure failure is inconclusive."""
    cases = e2.load_case_definitions()
    rows, pre, post = _rows(cases)
    for row in _rows_for_case(rows, str(cases[0]["case_id"])):
        planner = row["planner"]
        planner.update(
            {
                "provider_infrastructure_failure": True,
                "final_planner_success": False,
                "final_plan_available": False,
                "final_work_unit_facts": None,
                "final_contract_ok": False,
                "final_classification": "INFRA_FAILURE",
                "terminal_stage": "planner",
                "terminal_failure_code": "timeout",
                "raw_work_unit_facts": None,
                "raw_contract_ok": False,
                "raw_classification": "INFRA_FAILURE",
            }
        )
        row["final_system"].update(
            {
                "final_plan_available": False,
                "final_work_unit_facts": None,
                "final_contract_ok": False,
                "final_classification": "INFRA_FAILURE",
                "terminal_stage": "planner",
                "terminal_failure_code": "timeout",
            }
        )
    assert (
        e2.decision(
            rows,
            cases,
            expected_checkpoint=CHECKPOINT,
            pre_fingerprint=pre,
            post_fingerprint=post,
        )
        == "INCONCLUSIVE_SYSTEM_REEVALUATION"
    )


def test_planner_failure_is_not_mistaken_for_safe_rejection() -> None:
    """A valid-model planner failure remains a model rejection."""
    case = e2.load_case_definitions()[0]
    result = asyncio.run(
        e2.run_execution(
            case,
            delegate=_PlannerFailureBackend(),
            registry=historical.create_builtin_registry(),
        )
    )
    assert result["final_classification"] == "PLANNER_FAILURE"
    assert result["terminal_stage"] == "planner"


def test_population_provenance_drift_is_inconclusive() -> None:
    """Changing the E2 policy provenance invalidates the population."""
    cases = e2.load_case_definitions()
    rows, pre, post = _rows(cases)
    rows[0]["policy_versions"] = {"report_boundary_safety": "cm58.report-boundary.v1"}
    assert (
        e2.decision(
            rows,
            cases,
            expected_checkpoint=CHECKPOINT,
            pre_fingerprint=pre,
            post_fingerprint=post,
        )
        == "INCONCLUSIVE_SYSTEM_REEVALUATION"
    )


def test_report_boundary_policy_is_not_historically_rewritten() -> None:
    """The E2 harness uses v2 while leaving the historical module untouched."""
    historical_path = "scripts/cm59a_system_reevaluation.py"
    assert e2._baseline_blob(historical_path) == (e2.REPO_ROOT / historical_path).read_bytes()
    assert e2.POLICY_VERSIONS["report_boundary_safety"] == "cm58.report-boundary.v2"
