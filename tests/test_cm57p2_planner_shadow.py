"""Deterministic CM-57P2 planner-shadow tests."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError
from scripts import cm57p2_planner_shadow as p2

from wellplot.agent.code_mode.planner import SectionTask, SemanticPlan
from wellplot.agent.providers.base import (
    ProviderFailureCategory,
    ProviderMetrics,
    ProviderRequestError,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)


class QueueBackend:
    """Return queued planner values or raise queued provider failures."""

    def __init__(self, responses: list[object]) -> None:
        """Store a finite sequence of provider outcomes."""
        self.responses = list(responses)

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[Any],
    ) -> StructuredGenerationResult[Any]:
        """Return the next queued outcome."""
        del request, response_model
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return StructuredGenerationResult(
            value=response,
            metrics=ProviderMetrics(total_tokens=1, latency_ms=1.0),
        )

    async def generate_program(self, request: object) -> object:
        """Reject accidental downstream worker execution."""
        raise AssertionError(f"Unexpected downstream call: {request!r}")


def _cases() -> tuple[dict[str, object], ...]:
    return p2.load_case_definitions()


def _valid_plan(case: dict[str, object]) -> SemanticPlan:
    return SemanticPlan(
        summary="one section",
        section_tasks=(
            SectionTask(
                goal="create the requested section",
                capability_ids=tuple(case["expected_capabilities"]),
            ),
        ),
    )


def _invalid_duplicate_plan(case: dict[str, object]) -> SemanticPlan:
    """Build a structurally valid plan with a duplicate capability type."""
    capabilities = tuple(case["expected_capabilities"])
    return SemanticPlan(
        summary="duplicate capability",
        section_tasks=(
            SectionTask(
                goal="create the requested section",
                capability_ids=capabilities + (capabilities[-1],),
            ),
        ),
    )


def _run(case: dict[str, object], backend: QueueBackend, attempt: int = 0) -> dict[str, object]:
    registry = p2.create_builtin_registry()
    return asyncio.run(
        p2.run_planner_attempt(
            case,
            delegate=backend,
            registry=registry,
            attempt_index=attempt,
            historical_status="PLANNER_FAILURE",
        )
    )


def test_prelive_report_is_provider_free_and_guarded() -> None:
    """The default report performs only deterministic guards."""
    report = p2.prelive_report()

    assert report["status"] == "PRELIVE_READY"
    assert report["provider_calls"] == 0
    assert report["live_inference"] == "NOT_STARTED"
    assert report["future_population"] == {"cases": 16, "rows": 32}
    assert report["source_summary_matrix_sha256"] == p2.EXPECTED_SOURCE_MATRIX_SHA256


def test_frozen_corpus_and_source_summary_are_path_free() -> None:
    """The reused production source summary contains no host identities."""
    cases = _cases()
    matrix, digest = p2._source_matrix(cases)

    assert digest == p2.EXPECTED_SOURCE_MATRIX_SHA256
    serialized = p2.canonical_json(matrix)
    assert "/" not in serialized
    assert "candidate_id" not in serialized
    assert "source_path" not in serialized


def test_valid_production_planner_result_is_classified_without_downstream_work() -> None:
    """A valid plan stops before any program worker call."""
    case = _cases()[0]
    row = _run(case, QueueBackend([_valid_plan(case)]))

    assert row["planner_call_count"] == 1
    assert row["program_call_count"] == 0
    assert row["final_classification"] == "PLANNER_CONTRACT_OK"
    assert row["initial_classification"] == "INITIAL_CONTRACT_OK"
    assert row["historical_recovered"] is True
    assert all("request" not in call for call in row["call_trace"])


def test_plan_projection_contains_shape_only_and_no_semantic_prose() -> None:
    """Bounded plan projections exclude request and source prose."""
    plan = SemanticPlan(
        summary="/secret/summary",
        section_tasks=(
            SectionTask(
                goal="/secret/request",
                capability_ids=("section.log_plot",),
                source_hints=("/secret/source.dlis",),
            ),
        ),
    )

    projection = p2._plan_projection(plan)
    serialized = p2.canonical_json(projection)

    assert projection["section_count"] == 1
    assert "secret" not in serialized
    assert "goal" not in serialized
    assert "source.dlis" not in serialized


def test_semantic_correction_is_recorded_and_final_plan_is_classified() -> None:
    """The production planner's one semantic correction remains visible."""
    case = _cases()[0]
    row = _run(case, QueueBackend([_invalid_duplicate_plan(case), _valid_plan(case)]))

    assert row["planner_call_count"] == 2
    assert row["initial_classification"] == "INITIAL_CAPABILITY_DUPLICATION"
    assert row["final_classification"] == "PLANNER_CONTRACT_OK"
    assert row["call_trace"][1]["call_kind"] == "SEMANTIC_CORRECTION"


def test_invalid_structured_response_retry_is_distinct_from_correction() -> None:
    """An invalid structured response is recorded as a bounded retry."""
    case = _cases()[0]
    error = ProviderRequestError(
        ProviderFailureCategory.INVALID_RESPONSE,
        "invalid structured response",
    )
    row = _run(case, QueueBackend([error, _valid_plan(case)]))

    assert row["planner_call_count"] == 2
    assert row["final_classification"] == "PLANNER_CONTRACT_OK"
    assert row["call_trace"][0]["outcome"] == "provider_failure"
    assert row["call_trace"][1]["call_kind"] == "INVALID_RESPONSE_RETRY"
    assert row["provider_failure_categories"] == ["invalid_response"]


def test_terminal_semantic_failure_is_bounded() -> None:
    """A second semantic failure becomes a typed terminal planner failure."""
    case = _cases()[0]
    invalid = _invalid_duplicate_plan(case)
    row = _run(case, QueueBackend([invalid, invalid]))

    assert row["planner_call_count"] == 2
    assert row["final_classification"] == "PLANNER_SEMANTIC_FAILURE"
    assert row["semantic_failure_code"] == "duplicate_capability"
    assert row["final_planner_success"] is False


def test_provider_infrastructure_failure_is_not_a_planner_contract_failure() -> None:
    """Provider transport failure remains separate from planner semantics."""
    case = _cases()[0]
    error = ProviderRequestError(ProviderFailureCategory.TIMEOUT, "provider unavailable")
    row = _run(case, QueueBackend([error]))

    assert row["planner_call_count"] == 1
    assert row["final_classification"] == "PROVIDER_INFRA_FAILURE"
    assert row["provider_infrastructure_failure"] is True


def test_backend_validation_error_is_classified_as_schema_failure() -> None:
    """A typed backend validation error is bounded as schema evidence."""
    case = _cases()[0]
    error = ValidationError.from_exception_data(
        "SemanticPlan",
        [{"type": "missing", "loc": ("summary",), "input": {}}],
    )
    row = _run(case, QueueBackend([error]))

    assert row["planner_call_count"] == 1
    assert row["final_classification"] == "PLANNER_SCHEMA_FAILURE"
    assert row["provider_infrastructure_failure"] is False


def test_unexpected_backend_exception_propagates() -> None:
    """Unexpected backend programming errors are not hidden by the harness."""
    case = _cases()[0]

    with pytest.raises(RuntimeError, match="implementation defect"):
        _run(case, QueueBackend([RuntimeError("implementation defect")]))


def test_wrong_selection_and_duplicates_remain_visible_without_repair() -> None:
    """Final comparisons expose wrong selections without host-side repair."""
    case = _cases()[0]
    capabilities = list(case["expected_capabilities"])
    capabilities[-1] = "track.reference"
    plan = SemanticPlan(
        summary="wrong selection",
        section_tasks=(SectionTask(goal="wrong", capability_ids=tuple(capabilities)),),
    )
    row = _run(case, QueueBackend([plan]))

    assert row["final_classification"] == "WRONG_CAPABILITY_SELECTION"
    assert row["final_facts"]["missing_capabilities"] == ["binding.curve"]


def test_initial_duplicate_is_recorded_without_normalization() -> None:
    """Initial duplicate capability types remain visible before correction."""
    case = _cases()[0]
    row = _run(case, QueueBackend([_invalid_duplicate_plan(case), _valid_plan(case)]))

    assert row["initial_classification"] == "INITIAL_CAPABILITY_DUPLICATION"
    assert row["initial_facts"]["duplicate_capabilities"] == ["binding.curve"]


def test_population_decision_precedence_and_thresholds() -> None:
    """Population decisions preserve infrastructure and regression precedence."""
    cases = _cases()
    base = [
        {
            "case_id": case["case_id"],
            "attempt_index": attempt,
            "final_classification": "PLANNER_CONTRACT_OK",
            "provider_infrastructure_failure": False,
            "historical_success_regression": False,
        }
        for case in cases
        for attempt in range(p2.ATTEMPTS)
    ]

    assert p2.planner_decision(base, cases) == "PLANNER_CONTRACT_VALIDATED"
    base[0]["final_classification"] = "WRONG_CAPABILITY_SELECTION"
    assert p2.planner_decision(base, cases) == "PLANNER_CONTRACT_REGRESSION"
    base[0]["final_classification"] = "PLANNER_CONTRACT_OK"
    base[0]["provider_infrastructure_failure"] = True
    assert p2.planner_decision(base, cases) == "INCONCLUSIVE_PLANNER_EVALUATION"


def test_population_integrity_rejects_duplicates_and_missing_rows() -> None:
    """Population integrity rejects duplicate case-attempt identities."""
    cases = _cases()
    rows = [
        {"case_id": case["case_id"], "attempt_index": attempt}
        for case in cases
        for attempt in range(p2.ATTEMPTS)
    ]
    rows[-1] = dict(rows[-2])

    complete, reasons = p2.population_integrity(rows, cases)

    assert complete is False
    assert "duplicate_case_attempt" in reasons


def test_nonempty_future_evidence_path_is_rejected_before_provider_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pre-existing evidence file is rejected before provider construction."""
    evidence = tmp_path / "evidence.jsonl"
    evidence.write_text("existing\n", encoding="utf-8")
    monkeypatch.setattr(p2, "OUTPUT_PATH", evidence)
    monkeypatch.setattr(p2, "verify_reviewed_checkout", lambda checkpoint: None)
    monkeypatch.setattr(
        p2,
        "_provider_configuration",
        lambda args: pytest.fail("provider must not be constructed"),
    )

    with pytest.raises(RuntimeError, match="non-empty evidence path"):
        asyncio.run(
            p2._run_live(
                argparse_namespace(),
                "a" * 40,
            )
        )


def argparse_namespace() -> SimpleNamespace:
    """Return the minimal future-live argument object for the evidence guard test."""
    return SimpleNamespace(
        base_url="http://example.test",
        api_key_env="KEY",
        api_key_file=None,
    )
