"""Provider-free CM-59A-E2 remediated stack tests."""

from __future__ import annotations

import asyncio
import copy
from argparse import Namespace
from dataclasses import dataclass, field
from pathlib import Path

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
from wellplot.agent.providers.response_diagnostics import (
    ProviderResponseFailureReason,
    StructuredResponseProviderError,
)

CHECKPOINT = "a" * 40


def _endpoint_pair() -> tuple[dict[str, object], dict[str, object]]:
    """Build equal valid endpoint fingerprints without network access."""
    payload = {"data": [{"id": e2.FROZEN_MODEL, "created": 1}]}
    pre = fingerprint.build_endpoint_fingerprint_v2(
        endpoint="http://192.168.2.140:8888/v1",
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


@dataclass
class _SequenceBackend:
    """Return configured plans or provider failures in sequence."""

    responses: list[object]

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        """Return or raise the next configured response."""
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return StructuredGenerationResult(
            value=response_model.model_validate(response.model_dump()),  # type: ignore[union-attr]
            metrics=ProviderMetrics(total_tokens=1, latency_ms=1.0),
        )

    async def generate_program(self, request: object) -> object:
        """Reject accidental worker/program execution."""
        raise AssertionError(f"Unexpected program request: {request!r}")


def _schema_error() -> StructuredResponseProviderError:
    """Build one bounded schema-validation provider failure."""
    return StructuredResponseProviderError(
        "safe schema failure",
        response_reason=ProviderResponseFailureReason.SCHEMA_VALIDATION,
    )


def _invalid_json_error() -> StructuredResponseProviderError:
    """Build one bounded invalid-JSON provider failure."""
    return StructuredResponseProviderError(
        "safe invalid-json failure",
        response_reason=ProviderResponseFailureReason.INVALID_JSON,
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
    summary = e2.summarize_population(
        rows,
        cases,
        authorized_checkpoint=CHECKPOINT,
        pre_fingerprint=pre,
        post_fingerprint=post,
    )
    assert summary["population_integrity"] is True
    assert summary["population_integrity_reasons"] == []
    assert summary["endpoint_integrity"] is True
    assert summary["endpoint_integrity_reasons"] == []
    assert summary["expected_normalized_endpoint_identity"] == (
        e2.EXPECTED_NORMALIZED_ENDPOINT_IDENTITY
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
    assert result["call_trace"][0]["response_reason"] is None


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


def test_pre_live_budget_and_target_projection_are_exact() -> None:
    """The future population is 48 executions with a strict two-call ceiling."""
    report = e2.prelive_report()
    assert report["future_population"]["planner_executions"] == 48
    assert report["future_population"]["provider_calls_min"] == 48
    assert report["future_population"]["provider_calls_max"] == 96
    assert report["target_intents"] == {
        "FIG": "SECTION_ONLY",
        "LINDEN": "SECTION_ONLY",
        "XENON": "MIXED",
    }
    assert report["expected_normalized_endpoint_identity"] == (
        e2.EXPECTED_NORMALIZED_ENDPOINT_IDENTITY
    )


def test_three_call_row_fails_population_integrity() -> None:
    """A third provider call is always an E2 population-integrity failure."""
    cases = e2.load_case_definitions()
    rows, pre, _ = _rows(cases)
    planner = rows[0]["planner"]
    planner["provider_calls"] = 3
    planner["call_trace"] = [
        {"call_kind": "INITIAL", "outcome": "structured_success"},
        {"call_kind": "INVALID_RESPONSE_RETRY", "outcome": "structured_success"},
        {"call_kind": "INVALID_RESPONSE_RETRY", "outcome": "structured_success"},
    ]
    complete, reasons = e2.population_integrity(
        rows,
        cases,
        expected_checkpoint=CHECKPOINT,
        pre_fingerprint=pre,
    )
    assert complete is False
    assert "provider_call_budget_exceeded" in reasons


def test_schema_correction_is_recorded_without_response_leakage() -> None:
    """R2B schema recovery records only its bounded reason and call kind."""
    case = e2.load_case_definitions()[0]
    backend = _SequenceBackend([_schema_error(), _plan_for_case(case)])
    result = asyncio.run(
        e2.run_execution(
            case,
            delegate=backend,
            registry=historical.create_builtin_registry(),
        )
    )
    trace = result["call_trace"]
    assert [call["call_kind"] for call in trace] == ["INITIAL", "SCHEMA_CORRECTION"]
    assert trace[0]["response_reason"] == "schema_validation"
    assert trace[1]["outcome"] == "structured_success"
    assert result["schema_correction_used"] is True
    assert all("safe_message" not in call for call in trace)
    assert all("response_text" not in call for call in trace)


def test_recording_backend_blocks_third_call_before_delegate() -> None:
    """The E2 recorder enforces its two-call ceiling before provider dispatch."""
    case = e2.load_case_definitions()[0]
    delegate = _FakeBackend(_plan_for_case(case))
    recorder = e2.RecordingBackend(delegate=delegate, calls=[], plans=[])
    request = StructuredGenerationRequest(
        system_prompt="system",
        user_prompt="user",
        timeout_seconds=1.0,
    )

    async def exercise() -> None:
        for _ in range(2):
            await recorder.generate_structured(request, response_model=SemanticPlan)
        with pytest.raises(RuntimeError, match="before provider invocation"):
            await recorder.generate_structured(request, response_model=SemanticPlan)

    asyncio.run(exercise())
    assert len(delegate.calls) == 2
    assert len(recorder.calls) == 2


def test_schema_metrics_are_row_local_and_reason_specific() -> None:
    """Schema terminal metrics do not leak across rows or response reasons."""
    cases = e2.load_case_definitions()
    rows, _, _ = _rows(cases)
    case_id = str(cases[0]["case_id"])
    selected = _rows_for_case(rows, case_id)
    terminal_trace = [
        {
            "call_kind": "INITIAL",
            "outcome": "provider_failure",
            "response_reason": "schema_validation",
        },
        {
            "call_kind": "SCHEMA_CORRECTION",
            "outcome": "provider_failure",
            "response_reason": "schema_validation",
        },
    ]
    success_trace = [
        {
            "call_kind": "INITIAL",
            "outcome": "provider_failure",
            "response_reason": "schema_validation",
        },
        {
            "call_kind": "SCHEMA_CORRECTION",
            "outcome": "structured_success",
            "response_reason": None,
        },
    ]
    selected[0]["planner"]["call_trace"] = terminal_trace
    selected[1]["planner"]["call_trace"] = success_trace
    metrics = e2._schema_metrics(rows, case_id=case_id)
    assert metrics == {
        "initial_schema_validation_events": 2,
        "schema_correction_calls": 2,
        "schema_correction_structured_successes": 1,
        "schema_correction_terminal_failures": 1,
        "terminal_schema_validation_failures": 1,
    }

    selected[0]["planner"]["call_trace"][1]["response_reason"] = "invalid_json"
    metrics = e2._schema_metrics(rows, case_id=case_id)
    assert metrics["schema_correction_terminal_failures"] == 1
    assert metrics["terminal_schema_validation_failures"] == 0


def test_schema_correction_trigger_and_non_schema_retry_rules() -> None:
    """Schema failures require schema correction; invalid JSON uses generic retry."""
    cases = e2.load_case_definitions()
    rows, pre, _ = _rows(cases)
    rows[0]["planner"]["call_trace"] = [
        {
            "call_kind": "INITIAL",
            "outcome": "provider_failure",
            "provider_category": "invalid_response",
            "response_reason": "schema_validation",
        },
        {"call_kind": "INVALID_RESPONSE_RETRY", "outcome": "structured_success"},
    ]
    rows[0]["planner"]["provider_calls"] = 2
    complete, reasons = e2.population_integrity(
        rows,
        cases,
        expected_checkpoint=CHECKPOINT,
        pre_fingerprint=pre,
    )
    assert complete is False
    assert "schema_validation_used_generic_retry" in reasons

    rows, pre, _ = _rows(cases)
    rows[0]["planner"]["call_trace"] = [
        {
            "call_kind": "INITIAL",
            "outcome": "provider_failure",
            "provider_category": "invalid_response",
            "response_reason": "invalid_json",
        },
        {"call_kind": "SCHEMA_CORRECTION", "outcome": "structured_success"},
    ]
    rows[0]["planner"]["provider_calls"] = 2
    complete, reasons = e2.population_integrity(
        rows,
        cases,
        expected_checkpoint=CHECKPOINT,
        pre_fingerprint=pre,
    )
    assert complete is False
    assert "schema_correction_trigger_reason_invalid" in reasons

    rows, pre, _ = _rows(cases)
    rows[0]["planner"]["call_trace"] = [
        {
            "call_kind": "INITIAL",
            "outcome": "provider_failure",
            "provider_category": "invalid_response",
            "response_reason": "schema_validation",
        }
    ]
    rows[0]["planner"]["provider_calls"] = 1
    complete, reasons = e2.population_integrity(
        rows,
        cases,
        expected_checkpoint=CHECKPOINT,
        pre_fingerprint=pre,
    )
    assert complete is False
    assert "schema_correction_missing" in reasons


def test_semantic_correction_call_kind_is_accepted() -> None:
    """A structured initial result may take exactly one semantic correction."""
    cases = e2.load_case_definitions()
    rows, pre, _ = _rows(cases)
    rows[0]["planner"]["call_trace"] = [
        {"call_kind": "INITIAL", "outcome": "structured_success"},
        {"call_kind": "SEMANTIC_CORRECTION", "outcome": "structured_success"},
    ]
    rows[0]["planner"]["provider_calls"] = 2
    complete, reasons = e2.population_integrity(
        rows,
        cases,
        expected_checkpoint=CHECKPOINT,
        pre_fingerprint=pre,
    )
    assert complete is True
    assert reasons == []


@pytest.mark.parametrize("mutation", ["pre_post", "wrong_expected", "invalid_pre", "invalid_post"])
def test_endpoint_identity_is_fail_closed(mutation: str) -> None:
    """PRE/POST endpoint identity must be valid, equal, and expected."""
    pre, post = _endpoint_pair()
    if mutation == "pre_post":
        post = fingerprint.build_endpoint_fingerprint_v2(
            endpoint="http://192.168.2.141:8888/v1",
            model_api_label=e2.FROZEN_MODEL,
            models_payload={"data": [{"id": e2.FROZEN_MODEL}]},
        )
    elif mutation == "wrong_expected":
        pre = fingerprint.build_endpoint_fingerprint_v2(
            endpoint="http://192.168.2.142:8888/v1",
            model_api_label=e2.FROZEN_MODEL,
            models_payload={"data": [{"id": e2.FROZEN_MODEL}]},
        )
        post = dict(pre)
    elif mutation == "invalid_pre":
        pre = dict(pre)
        pre["normalized_identity_sha256"] = "0" * 64
    else:
        post = dict(post)
        post["normalized_identity_sha256"] = "0" * 64
    valid, reasons = e2._endpoint_status(pre, post)
    assert valid is False
    assert reasons


def test_endpoint_identity_expected_pair_is_eligible() -> None:
    """The authorized endpoint identity passes provider-free endpoint validation."""
    pre, post = _endpoint_pair()
    assert e2._endpoint_status(pre, post) == (True, [])


def test_summary_endpoint_integrity_is_explicit_and_fail_closed() -> None:
    """Endpoint integrity is explicit in the summary and gates the decision."""
    cases = e2.load_case_definitions()
    rows, pre, post = _rows(cases)
    post = fingerprint.build_endpoint_fingerprint_v2(
        endpoint="http://192.168.2.141:8888/v1",
        model_api_label=e2.FROZEN_MODEL,
        models_payload={"data": [{"id": e2.FROZEN_MODEL}]},
    )
    summary = e2.summarize_population(
        rows,
        cases,
        authorized_checkpoint=CHECKPOINT,
        pre_fingerprint=pre,
        post_fingerprint=post,
    )
    assert summary["endpoint_integrity"] is False
    assert summary["endpoint_integrity_reasons"]
    assert summary["expected_normalized_endpoint_identity"] == (
        e2.EXPECTED_NORMALIZED_ENDPOINT_IDENTITY
    )
    assert summary["decision"] == "INCONCLUSIVE_SYSTEM_REEVALUATION"


@pytest.mark.parametrize("label", ["FIG", "LINDEN", "XENON"])
def test_each_target_safe_rejection_is_a_hard_failure(label: str) -> None:
    """No remediation target may consume the general safe-rejection allowance."""
    cases = e2.load_case_definitions()
    rows, pre, post = _rows(cases)
    _set_safe_rejection(rows, e2.TARGET_CASES[label])
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


def _set_wrong_escape(rows: list[dict[str, object]], case_id: str) -> None:
    """Mark both attempts as stable final semantic wrong escapes."""
    for row in _rows_for_case(rows, case_id):
        facts = copy.deepcopy(row["planner"]["final_work_unit_facts"])
        facts["section_multiset_exact"] = False
        facts["missing_section_signatures"] = facts["section_capability_signatures"]
        classification = p5.classify_facts(facts)
        row["planner"].update(
            {
                "final_work_unit_facts": facts,
                "final_classification": classification,
                "final_contract_ok": False,
                "final_plan_available": True,
            }
        )
        row["final_system"].update(
            {
                "final_work_unit_facts": facts,
                "final_classification": classification,
                "final_contract_ok": False,
                "final_plan_available": True,
            }
        )


@pytest.mark.parametrize("label", ["FIG", "LINDEN", "XENON"])
def test_each_target_wrong_escape_is_a_hard_failure(label: str) -> None:
    """A target wrong escape also rejects E2 regardless of aggregate floors."""
    cases = e2.load_case_definitions()
    rows, pre, post = _rows(cases)
    _set_wrong_escape(rows, e2.TARGET_CASES[label])
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


def test_two_non_target_safe_rejections_preserve_22_of_24_acceptance() -> None:
    """The historical two-case allowance remains available outside targets."""
    cases = e2.load_case_definitions()
    rows, pre, post = _rows(cases)
    candidates = [
        case
        for case in cases
        if case["residual_class"] is None and case["case_id"] not in e2.TARGET_CASES.values()
    ]
    selected: list[dict[str, object]] = []
    for case in candidates:
        if all(case["family"] != other["family"] for other in selected):
            selected.append(case)
        if len(selected) == 2:
            break
    assert len(selected) == 2
    for case in selected:
        _set_safe_rejection(rows, str(case["case_id"]))
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


def test_family_floor_rejects_two_of_four() -> None:
    """A family below 3/4 rejects even when the global floor is sufficient."""
    cases = e2.load_case_definitions()
    rows, pre, post = _rows(cases)
    family_cases = []
    for family in e2.FAMILIES:
        candidates = [
            case
            for case in cases
            if case["family"] == family and case["case_id"] not in e2.TARGET_CASES.values()
        ]
        if len(candidates) >= 2:
            family_cases = candidates
            break
    assert len(family_cases) >= 2
    for case in family_cases[:2]:
        _set_safe_rejection(rows, str(case["case_id"]))
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


@pytest.mark.parametrize("residual_class", ["LICHEN_CLASS", "MARINER_CLASS"])
def test_residual_floor_requires_both_cases(residual_class: str) -> None:
    """Both historical residual classes remain mandatory 2/2 gates."""
    cases = e2.load_case_definitions()
    rows, pre, post = _rows(cases)
    case = next(case for case in cases if case["residual_class"] == residual_class)
    _set_safe_rejection(rows, str(case["case_id"]))
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


def test_unstable_case_rejects_population() -> None:
    """A changed final signature across attempts is not stable evidence."""
    cases = e2.load_case_definitions()
    rows, pre, post = _rows(cases)
    second = _rows_for_case(rows, str(cases[0]["case_id"]))[1]
    _set_wrong_escape([second], str(cases[0]["case_id"]))
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


def _set_schema_recovery_trace(
    rows: list[dict[str, object]],
    case_id: str,
    *,
    terminal: bool = False,
) -> None:
    """Attach an R2B schema-recovery trace to both attempts of one case."""
    for row in _rows_for_case(rows, case_id):
        planner = row["planner"]
        correction_outcome = "provider_failure" if terminal else "structured_success"
        planner["call_trace"] = [
            {
                "call_kind": "INITIAL",
                "outcome": "provider_failure",
                "provider_category": "invalid_response",
                "response_reason": "schema_validation",
            },
            {
                "call_kind": "SCHEMA_CORRECTION",
                "outcome": correction_outcome,
                "provider_category": "invalid_response" if terminal else None,
                "response_reason": "schema_validation" if terminal else None,
            },
        ]
        planner["provider_calls"] = 2
        planner["schema_correction_used"] = True
        if terminal:
            planner.update(
                {
                    "final_planner_success": False,
                    "final_error_type": "ProviderRequestError",
                    "final_error_code": "invalid_response",
                    "provider_infrastructure_failure": False,
                    "raw_work_unit_facts": None,
                    "raw_contract_ok": False,
                    "raw_classification": "PLANNER_FAILURE",
                    "final_work_unit_facts": None,
                    "final_classification": "PLANNER_FAILURE",
                    "final_contract_ok": False,
                    "final_plan_available": False,
                    "terminal_stage": "planner",
                    "terminal_failure_code": "invalid_response",
                }
            )
            row["final_system"].update(
                {
                    "final_work_unit_facts": None,
                    "final_classification": "PLANNER_FAILURE",
                    "final_contract_ok": False,
                    "final_plan_available": False,
                    "terminal_stage": "planner",
                    "terminal_failure_code": "invalid_response",
                }
            )


def test_xenon_schema_recovery_metrics_and_terminal_guard() -> None:
    """Xenon recovery is measured, while terminal schema failure rejects E2."""
    cases = e2.load_case_definitions()
    rows, pre, post = _rows(cases)
    _set_schema_recovery_trace(rows, e2.TARGET_CASES["XENON"])
    summary = e2.summarize_population(
        rows,
        cases,
        authorized_checkpoint=CHECKPOINT,
        pre_fingerprint=pre,
        post_fingerprint=post,
    )
    assert summary["xenon_metrics"]["schema_correction_call_count"] == 2
    assert summary["xenon_metrics"]["final_pass_attempt_count"] == 2
    assert summary["decision"] == "SYSTEM_REEVALUATION_ACCEPTED"

    rows, pre, post = _rows(cases)
    _set_schema_recovery_trace(rows, e2.TARGET_CASES["XENON"], terminal=True)
    summary = e2.summarize_population(
        rows,
        cases,
        authorized_checkpoint=CHECKPOINT,
        pre_fingerprint=pre,
        post_fingerprint=post,
    )
    assert summary["decision"] == "SYSTEM_REEVALUATION_REJECTED"
    assert summary["xenon_metrics"]["terminal_schema_validation_count"] == 2

    rows, pre, post = _rows(cases)
    _set_schema_recovery_trace(rows, e2.TARGET_CASES["XENON"], terminal=True)
    success_row = _rows_for_case(rows, e2.TARGET_CASES["XENON"])[1]
    success_row["planner"]["call_trace"][1].update(
        {
            "outcome": "structured_success",
            "provider_category": None,
            "response_reason": None,
        }
    )
    facts = _facts(next(case for case in cases if case["case_id"] == e2.TARGET_CASES["XENON"]))
    classification = p5.classify_facts(facts)
    success_row["planner"].update(
        {
            "final_planner_success": True,
            "final_error_type": None,
            "final_error_code": None,
            "provider_infrastructure_failure": False,
            "raw_work_unit_facts": facts,
            "raw_classification": classification,
            "raw_contract_ok": True,
            "final_work_unit_facts": facts,
            "final_classification": classification,
            "final_contract_ok": True,
            "final_plan_available": True,
            "terminal_stage": None,
            "terminal_failure_code": None,
        }
    )
    success_row["final_system"].update(
        {
            "final_work_unit_facts": facts,
            "final_classification": classification,
            "final_contract_ok": True,
            "final_plan_available": True,
            "terminal_stage": None,
            "terminal_failure_code": None,
        }
    )
    summary = e2.summarize_population(
        rows,
        cases,
        authorized_checkpoint=CHECKPOINT,
        pre_fingerprint=pre,
        post_fingerprint=post,
    )
    assert summary["xenon_metrics"]["initial_schema_validation_count"] == 2
    assert summary["xenon_metrics"]["schema_correction_call_count"] == 2
    assert summary["xenon_metrics"]["schema_correction_structured_success_count"] == 1
    assert summary["xenon_metrics"]["terminal_schema_validation_count"] == 1
    assert summary["xenon_metrics"]["final_pass_attempt_count"] == 1


@pytest.mark.parametrize("target", ["FIG", "LINDEN"])
def test_r1_target_report_shapes_are_provider_free(target: str) -> None:
    """Fig and Linden report-boundary repairs preserve their scalar sections."""
    case = next(
        case for case in e2.load_case_definitions() if case["case_id"] == e2.TARGET_CASES[target]
    )
    section = tuple(case["expected_sections"][0])
    plan = SemanticPlan(
        summary="target report-shape test",
        report_task=ReportTask(goal="unrequested report", capability_ids=("report.standard",)),
        section_tasks=(SectionTask(goal="target section", capability_ids=section),),
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


@pytest.mark.parametrize(
    "field",
    [
        "base",
        "evaluation_contract",
        "corpus",
        "prompt",
        "schema",
        "source",
        "policy",
        "production",
    ],
)
def test_provenance_tampering_is_inconclusive(field: str) -> None:
    """Each decision-bearing E2 provenance field fails closed independently."""
    cases = e2.load_case_definitions()
    rows, pre, post = _rows(cases)
    field_map = {
        "base": ("design_baseline_sha", "0" * 40),
        "evaluation_contract": ("evaluation_contract_version", "other.v0"),
        "corpus": ("corpus_sha256", "0" * 64),
        "prompt": ("P_prompt_sha256", "0" * 64),
        "schema": ("response_schema_sha256", "0" * 64),
        "source": ("source_summary_sha256", "0" * 64),
        "policy": ("policy_versions", {"drifted": "v0"}),
        "production": ("production_source_hashes", {"drifted": "0" * 64}),
    }
    key, value = field_map[field]
    rows[0][key] = value
    assert (
        e2.population_integrity(
            rows,
            cases,
            expected_checkpoint=CHECKPOINT,
            pre_fingerprint=pre,
        )[0]
        is False
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


def test_call_sequence_and_case_tampering_are_inconclusive() -> None:
    """Call count, sequence, attempt, case, and worker mutations fail closed."""
    cases = e2.load_case_definitions()
    for mutation in ("sequence", "count", "attempt", "case", "worker"):
        rows, pre, _ = _rows(cases)
        if mutation == "sequence":
            rows[0]["planner"]["call_trace"] = [
                {"call_kind": "INITIAL", "outcome": "structured_success"},
                {"call_kind": "SCHEMA_CORRECTION", "outcome": "structured_success"},
            ]
            rows[0]["planner"]["provider_calls"] = 2
        elif mutation == "count":
            rows[0]["planner"]["provider_calls"] = 0
        elif mutation == "attempt":
            rows[0]["attempt_index"] = 8
        elif mutation == "case":
            rows[0]["case_id"] = "unknown-case"
        else:
            rows[0]["program_calls"] = 1
        assert (
            e2.population_integrity(
                rows,
                cases,
                expected_checkpoint=CHECKPOINT,
                pre_fingerprint=pre,
            )[0]
            is False
        )


@pytest.mark.parametrize(
    "path_name",
    ["evidence_path", "endpoint_fingerprint_pre", "endpoint_fingerprint_post", "summary_path"],
)
def test_live_collision_guard_runs_before_endpoint_or_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    path_name: str,
) -> None:
    """Any non-empty live output blocks before endpoint/provider construction."""
    paths = {
        "evidence_path": tmp_path / "evidence.jsonl",
        "endpoint_fingerprint_pre": tmp_path / "pre.json",
        "endpoint_fingerprint_post": tmp_path / "post.json",
        "summary_path": tmp_path / "summary.json",
    }
    paths[path_name].write_text("stale", encoding="utf-8")
    args = Namespace(
        evidence_path=str(paths["evidence_path"]),
        endpoint_fingerprint_pre=str(paths["endpoint_fingerprint_pre"]),
        endpoint_fingerprint_post=str(paths["endpoint_fingerprint_post"]),
        summary_path=str(paths["summary_path"]),
        base_url="http://endpoint.example/v1",
        api_key_env="MISSING",
        api_key_file=None,
    )
    monkeypatch.setattr(
        e2.fingerprint,
        "capture_endpoint_fingerprint_v2",
        lambda **_: pytest.fail("endpoint called"),
    )
    monkeypatch.setattr(
        e2,
        "_provider_configuration",
        lambda _: pytest.fail("provider constructed"),
    )
    with pytest.raises(RuntimeError, match="non-empty"):
        asyncio.run(e2._run_live(args, CHECKPOINT))


def test_invalid_pre_identity_stops_before_provider_construction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An unexpected PRE endpoint identity cannot reach provider construction."""
    paths = {
        "evidence_path": tmp_path / "evidence.jsonl",
        "endpoint_fingerprint_pre": tmp_path / "pre.json",
        "endpoint_fingerprint_post": tmp_path / "post.json",
        "summary_path": tmp_path / "summary.json",
    }
    args = Namespace(
        evidence_path=str(paths["evidence_path"]),
        endpoint_fingerprint_pre=str(paths["endpoint_fingerprint_pre"]),
        endpoint_fingerprint_post=str(paths["endpoint_fingerprint_post"]),
        summary_path=str(paths["summary_path"]),
        base_url="http://192.168.2.141:8888/v1",
        api_key_env="MISSING",
        api_key_file=None,
    )
    invalid_pre = fingerprint.build_endpoint_fingerprint_v2(
        endpoint=args.base_url,
        model_api_label=e2.FROZEN_MODEL,
        models_payload={"data": [{"id": e2.FROZEN_MODEL}]},
    )
    monkeypatch.setattr(e2, "verify_reviewed_checkout", lambda _: None)
    monkeypatch.setattr(e2, "verify_frozen_contract", lambda: {})
    monkeypatch.setattr(
        e2.fingerprint,
        "capture_endpoint_fingerprint_v2",
        lambda **_: invalid_pre,
    )
    monkeypatch.setattr(e2, "_api_key", lambda _: "test-key")
    monkeypatch.setattr(
        e2,
        "_provider_configuration",
        lambda _: pytest.fail("provider constructed"),
    )
    with pytest.raises(RuntimeError, match="PRE endpoint fingerprint"):
        asyncio.run(e2._run_live(args, CHECKPOINT))


@pytest.mark.parametrize(
    "argv",
    [
        ["--base-url", "http://endpoint.example/v1"],
        ["--live-authorized"],
        ["--live-authorized", "--base-url", "http://endpoint.example/v1"],
        ["--authorized-checkpoint", CHECKPOINT],
    ],
)
def test_cli_requires_complete_live_authorization(argv: list[str]) -> None:
    """Incomplete live combinations stop before any execution path."""
    with pytest.raises(SystemExit):
        e2.main(argv)


def test_partial_population_is_inconclusive() -> None:
    """A 47-row future population cannot be resumed or interpreted."""
    cases = e2.load_case_definitions()
    rows, pre, post = _rows(cases)
    rows.pop()
    summary = e2.summarize_population(
        rows,
        cases,
        authorized_checkpoint=CHECKPOINT,
        pre_fingerprint=pre,
        post_fingerprint=post,
    )
    assert summary["decision"] == "INCONCLUSIVE_SYSTEM_REEVALUATION"
    assert "wrong_row_count" in summary["population"]["integrity_reasons"]
    assert summary["population_integrity"] is False
    assert "wrong_row_count" in summary["population_integrity_reasons"]


def test_finalize_is_network_free_and_records_exact_file_hashes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Finalization reads local artifacts only and hashes their exact bytes."""
    cases = e2.load_case_definitions()
    rows, pre, post = _rows(cases)
    evidence = tmp_path / "evidence.jsonl"
    pre_path = tmp_path / "pre.json"
    post_path = tmp_path / "post.json"
    evidence.write_text("\n".join(e2.canonical_json(row) for row in rows) + "\n", encoding="utf-8")
    pre_path.write_text(e2.canonical_json(pre) + "\n", encoding="utf-8")
    post_path.write_text(e2.canonical_json(post) + "\n", encoding="utf-8")
    monkeypatch.setattr(e2, "verify_reviewed_checkout", lambda _: None)
    monkeypatch.setattr(e2, "verify_frozen_contract", lambda: {})
    monkeypatch.setattr(e2, "_provider_configuration", lambda _: pytest.fail("provider called"))
    monkeypatch.setattr(
        e2.fingerprint,
        "capture_endpoint_fingerprint_v2",
        lambda **_: pytest.fail("endpoint called"),
    )
    summary = e2.finalize(
        evidence_path=evidence,
        pre_path=pre_path,
        post_path=post_path,
        authorized_checkpoint=CHECKPOINT,
    )
    assert summary["decision"] == "SYSTEM_REEVALUATION_ACCEPTED"
    assert summary["raw_evidence_sha256"] == e2.artifact_sha256(evidence)
    assert summary["pre_fingerprint_file_sha256"] == e2.artifact_sha256(pre_path)
    assert summary["post_fingerprint_file_sha256"] == e2.artifact_sha256(post_path)


def test_response_diagnostics_artifact_is_protected(monkeypatch: pytest.MonkeyPatch) -> None:
    """R2A structured-response diagnostics are part of E2 production provenance."""
    real_baseline = e2._baseline_blob

    def drift(path: str) -> bytes:
        if path == "src/wellplot/agent/providers/response_diagnostics.py":
            return b"drifted"
        return real_baseline(path)

    monkeypatch.setattr(e2, "_baseline_blob", drift)
    with pytest.raises(RuntimeError, match="response_diagnostics.py"):
        e2.verify_frozen_contract()
