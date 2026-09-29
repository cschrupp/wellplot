"""Provider-free CM-59A system reevaluation gate tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest
from pydantic import BaseModel
from scripts import cm57p9_runtime_fingerprint as fingerprint
from scripts import cm59a_system_reevaluation as cm59

from wellplot.agent.code_mode.planner import ReportTask, SectionTask, SemanticPlan
from wellplot.agent.providers.base import (
    ProviderMetrics,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)

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
    return {
        name: {
            "status": "PASSED",
            "changed": False,
            "evidence": {"actions": []},
            "failure_code": None,
        }
        for name in cm59.POLICY_VERSIONS
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
                "raw_classification": "PLANNER_CONTRACT_OK" if valid else "MISMATCH",
                "raw_contract_ok": valid,
                "final_plan_projection": None,
                "final_work_unit_facts": facts,
                "final_classification": "PLANNER_CONTRACT_OK" if valid else "MISMATCH",
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
