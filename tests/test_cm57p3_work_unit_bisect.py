"""Deterministic CM-57P3 planner work-unit micro-bisect tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest
from pydantic import BaseModel
from scripts import cm57p3_work_unit_bisect as p3

from wellplot.agent.code_mode.planner import (
    ReportTask,
    SectionTask,
    SemanticPlan,
    SemanticPlanner,
)
from wellplot.agent.providers.base import (
    ProviderMetrics,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from wellplot.capabilities import create_builtin_registry


@dataclass
class Backend:
    """Return one fixed plan and record the exact provider requests."""

    plan: SemanticPlan
    requests: list[StructuredGenerationRequest] = field(default_factory=list)
    response_models: list[type[BaseModel]] = field(default_factory=list)

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        """Return the fixed plan after recording the request."""
        self.requests.append(request)
        self.response_models.append(response_model)
        return StructuredGenerationResult(
            value=response_model.model_validate(self.plan),
            metrics=ProviderMetrics(),
        )

    async def generate_program(self, request: object) -> object:
        """Reject accidental program generation."""
        raise AssertionError(f"Unexpected program request: {request!r}")


def _case() -> dict[str, object]:
    return p3.p2.load_case_definitions()[0]


def _valid_plan() -> SemanticPlan:
    case = _case()
    return SemanticPlan(
        summary="one section",
        section_tasks=(
            SectionTask(
                goal="create one section",
                capability_ids=tuple(case["expected_capabilities"]),
            ),
        ),
    )


def _run_planner(backend: object) -> None:
    """Run one planner request against the supplied backend."""
    planner = SemanticPlanner(backend=backend, registry=create_builtin_registry())  # type: ignore[arg-type]
    asyncio.run(
        planner.plan(
            request="Create one section.",
            mode="reconstruct",
            timeout_seconds=5.0,
            temperature=0.0,
            max_output_tokens=100,
        )
    )


def _request(
    arm: p3.Arm,
    *,
    wrapped: bool = True,
) -> tuple[Backend, p3.PromptArmBackend | None]:
    delegate = Backend(_valid_plan())
    wrapper = (
        p3.PromptArmBackend(delegate=delegate, arm=arm, forwarded_requests=[]) if wrapped else None
    )
    _run_planner(wrapper if wrapper is not None else delegate)
    return delegate, wrapper


def test_prompt_composition_is_deterministic_and_factorial() -> None:
    """Prompt arms contain only their authorized factor instructions."""
    assert p3.composed_prompt("P") == p3._PLANNER_SYSTEM_PROMPT
    assert p3.composed_prompt("W").startswith(p3._PLANNER_SYSTEM_PROMPT)
    assert p3.WORK_UNIT_INSTRUCTION in p3.composed_prompt("W")
    assert p3.REPORT_BOUNDARY_INSTRUCTION not in p3.composed_prompt("W")
    assert p3.WORK_UNIT_INSTRUCTION in p3.composed_prompt("WR")
    assert p3.REPORT_BOUNDARY_INSTRUCTION in p3.composed_prompt("WR")
    assert p3.composed_prompt("WR").count(p3.WORK_UNIT_INSTRUCTION) == 1
    assert p3.composed_prompt("WR").count(p3.REPORT_BOUNDARY_INSTRUCTION) == 1
    assert len(set(p3.PROMPT_SHA256.values())) == 4


@pytest.mark.parametrize("arm", p3.ARMS)
def test_prompt_arm_changes_only_system_prompt(arm: p3.Arm) -> None:
    """Every arm preserves all non-system provider request fields."""
    delegate, wrapper = _request(arm)
    assert wrapper is not None
    assert len(delegate.requests) == len(wrapper.forwarded_requests) == 1
    forwarded = wrapper.forwarded_requests[0]
    assert forwarded.user_prompt == delegate.requests[0].user_prompt
    assert forwarded.timeout_seconds == delegate.requests[0].timeout_seconds
    assert forwarded.temperature == delegate.requests[0].temperature
    assert forwarded.max_output_tokens == delegate.requests[0].max_output_tokens
    expected = p3._PLANNER_SYSTEM_PROMPT if arm == "P" else p3.composed_prompt(arm)
    assert forwarded.system_prompt == expected


def test_prompt_wrapper_rejects_production_prompt_drift_before_delegate() -> None:
    """Prompt drift fails before the wrapped provider is called."""
    delegate = Backend(_valid_plan())
    wrapper = p3.PromptArmBackend(delegate=delegate, arm="W", forwarded_requests=[])
    request = StructuredGenerationRequest(
        system_prompt="drifted",
        user_prompt="request",
        timeout_seconds=1.0,
    )
    with pytest.raises(RuntimeError, match="unexpected production planner prompt"):
        asyncio.run(wrapper.generate_structured(request, response_model=SemanticPlan))
    assert delegate.requests == []


def test_p_arm_is_production_equivalent() -> None:
    """The P wrapper emits the same request as direct production planning."""
    direct, _ = _request("P", wrapped=False)
    wrapped, wrapper = _request("P")
    assert wrapper is not None
    assert direct.requests == wrapped.requests == wrapper.forwarded_requests
    assert direct.response_models == wrapped.response_models == [SemanticPlan]
    assert wrapper.forwarded_requests[0] is wrapped.requests[0]


def test_wrapper_returns_provider_result_without_modification() -> None:
    """The wrapper does not alter the provider's structured result."""
    delegate = Backend(_valid_plan())
    wrapper = p3.PromptArmBackend(delegate=delegate, arm="WR", forwarded_requests=[])
    result = asyncio.run(
        wrapper.generate_structured(
            StructuredGenerationRequest(
                system_prompt=p3._PLANNER_SYSTEM_PROMPT,
                user_prompt="request",
                timeout_seconds=1.0,
            ),
            response_model=SemanticPlan,
        )
    )
    assert result.value == _valid_plan()


def test_correction_path_uses_same_factor_prompt() -> None:
    """Semantic correction requests use the same factor prompt as initial calls."""
    case = _case()
    duplicate = SemanticPlan(
        summary="duplicate",
        section_tasks=(
            SectionTask(
                goal="duplicate",
                capability_ids=tuple(case["expected_capabilities"]) * 2,
            ),
        ),
    )
    delegate = _SequenceBackend(plan=_valid_plan(), responses=[duplicate, _valid_plan()])
    wrapper = p3.PromptArmBackend(delegate=delegate, arm="R", forwarded_requests=[])
    planner = SemanticPlanner(backend=wrapper, registry=create_builtin_registry())
    asyncio.run(
        planner.plan(request="Create one section.", mode="reconstruct", timeout_seconds=1.0)
    )
    assert len(wrapper.forwarded_requests) == 2
    assert all(
        request.system_prompt == p3.composed_prompt("R") for request in wrapper.forwarded_requests
    )


def test_direct_and_p_wrapped_correction_requests_are_equivalent() -> None:
    """Direct production and P-wrapped correction paths emit equal requests."""
    case = _case()
    duplicate = SemanticPlan(
        summary="duplicate",
        section_tasks=(
            SectionTask(
                goal="duplicate",
                capability_ids=tuple(case["expected_capabilities"]) * 2,
            ),
        ),
    )
    direct = _SequenceBackend(plan=_valid_plan(), responses=[duplicate, _valid_plan()])
    wrapped_delegate = _SequenceBackend(plan=_valid_plan(), responses=[duplicate, _valid_plan()])
    wrapper = p3.PromptArmBackend(
        delegate=wrapped_delegate,
        arm="P",
        forwarded_requests=[],
    )
    planner_direct = SemanticPlanner(backend=direct, registry=create_builtin_registry())
    planner_wrapped = SemanticPlanner(backend=wrapper, registry=create_builtin_registry())
    for planner in (planner_direct, planner_wrapped):
        asyncio.run(
            planner.plan(request="Create one section.", mode="reconstruct", timeout_seconds=1.0)
        )
    assert direct.requests == wrapped_delegate.requests == wrapper.forwarded_requests
    assert (
        direct.response_models == wrapped_delegate.response_models == [SemanticPlan, SemanticPlan]
    )


@dataclass
class _SequenceBackend(Backend):
    responses: list[SemanticPlan] = field(default_factory=list)

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        """Return the next configured plan."""
        self.requests.append(request)
        self.response_models.append(response_model)
        return StructuredGenerationResult(
            value=response_model.model_validate(self.responses.pop(0)),
            metrics=ProviderMetrics(),
        )


def test_classification_distinguishes_fragmentation_and_report_pollution() -> None:
    """Work-unit fragmentation and report pollution remain separate facts."""
    case = _case()
    expected = list(case["expected_capabilities"])
    registry = create_builtin_registry()
    fragmented = SemanticPlan(
        summary="split",
        section_tasks=tuple(
            SectionTask(goal="part", capability_ids=(capability,)) for capability in expected
        ),
    )
    facts = p3._facts(fragmented, expected, registry)
    assert facts["work_unit_fragmentation"] is True
    assert facts["fragmentation_with_gap"] is False
    polluted = SemanticPlan(
        summary="report",
        report_task=ReportTask(goal="placeholder"),
        section_tasks=(SectionTask(goal="section", capability_ids=tuple(expected)),),
    )
    polluted_facts = p3._facts(polluted, expected, registry)
    assert polluted_facts["report_task_present"] is True
    assert polluted_facts["empty_report_task"] is True
    assert p3.final_contract_ok(polluted_facts) is False


def _population() -> list[dict[str, object]]:
    cases = p3.p2.load_case_definitions()
    rows = []
    for case in cases:
        for attempt in range(p3.ATTEMPTS):
            rows.append(
                {
                    "case_id": case["case_id"],
                    "attempt_index": attempt,
                    "authorized_checkpoint": p3.BASELINE_SHA,
                    "arms": {
                        arm: {
                            "final_contract_ok": True,
                            "provider_infrastructure_failure": False,
                            "work_unit_fragmentation": False,
                            "report_task_present": False,
                            "final_facts": {
                                "wrong_capability_selection": False,
                                "work_unit_fragmentation": False,
                                "report_task_present": False,
                            },
                        }
                        for arm in p3.ARMS
                    },
                }
            )
    return rows


def test_population_integrity_requires_all_four_arms() -> None:
    """A shared row without one arm is not a valid future population."""
    rows = _population()
    del rows[0]["arms"]["WR"]
    complete, reasons = p3.population_integrity(rows, p3.p2.load_case_definitions())
    assert complete is False
    assert "arm_set_mismatch" in reasons


def test_factor_tables_report_all_transition_buckets() -> None:
    """Pair tables account for every shared row."""
    rows = _population()
    rows[0]["arms"]["P"]["final_facts"]["work_unit_fragmentation"] = True
    rows[0]["arms"]["W"]["final_facts"]["work_unit_fragmentation"] = True
    rows[1]["arms"]["P"]["final_facts"]["work_unit_fragmentation"] = True
    rows[2]["arms"]["W"]["final_facts"]["work_unit_fragmentation"] = True
    table = p3.factor_tables(rows)
    assert sum(table["P_to_W"]["neutral"]["final_contract_ok"].values()) == len(rows)
    assert sum(table["P_to_R"]["neutral"]["final_contract_ok"].values()) == len(rows)
    assert sum(table["W_to_WR"]["neutral"]["final_contract_ok"].values()) == len(rows)
    assert sum(table["R_to_WR"]["neutral"]["final_contract_ok"].values()) == len(rows)
    assert set(table["P_to_W"]["fragmentation"]) == {
        "FRAGMENTED_TO_FRAGMENTED",
        "FRAGMENTED_TO_CORRECT",
        "CORRECT_TO_CORRECT",
        "CORRECT_TO_FRAGMENTED",
        "UNAVAILABLE",
    }
    assert table["P_to_W"]["fragmentation"] == {
        "FRAGMENTED_TO_FRAGMENTED": 1,
        "FRAGMENTED_TO_CORRECT": 1,
        "CORRECT_TO_CORRECT": len(rows) - 3,
        "CORRECT_TO_FRAGMENTED": 1,
        "UNAVAILABLE": 0,
    }


def test_terminal_semantic_facts_are_unavailable_in_pair_tables() -> None:
    """Terminal semantic and schema failures are not semantic false values."""
    rows = _population()
    rows[0]["arms"]["P"]["final_facts"] = None
    rows[0]["arms"]["P"]["final_contract_ok"] = False
    rows[0]["arms"]["P"]["final_classification"] = "PLANNER_SEMANTIC_FAILURE"
    table = p3.factor_tables(rows)["P_to_W"]
    assert table["fragmentation"]["UNAVAILABLE"] == 1
    assert table["report_task"]["UNAVAILABLE"] == 1
    assert table["fragmentation"]["CORRECT_TO_CORRECT"] == len(rows) - 1
    assert table["report_task"]["ABSENT_TO_ABSENT"] == len(rows) - 1
    assert table["full_contract"]["RIGHT_ONLY_PASS"] == 1

    rows = _population()
    rows[0]["arms"]["P"]["final_facts"] = None
    rows[0]["arms"]["W"]["final_facts"] = None
    rows[0]["arms"]["P"]["final_contract_ok"] = False
    rows[0]["arms"]["W"]["final_contract_ok"] = False
    rows[0]["arms"]["P"]["final_classification"] = "PLANNER_SCHEMA_FAILURE"
    rows[0]["arms"]["W"]["final_classification"] = "PLANNER_SCHEMA_FAILURE"
    table = p3.factor_tables(rows)["P_to_W"]
    assert table["fragmentation"]["UNAVAILABLE"] == 1
    assert table["report_task"]["UNAVAILABLE"] == 1
    assert table["fragmentation"]["CORRECT_TO_CORRECT"] == len(rows) - 1


def test_semantic_pair_tables_conserve_population_rows() -> None:
    """Every semantic transition table accounts for all shared rows."""
    rows = _population()
    for pair in p3.factor_tables(rows).values():
        for metric in ("fragmentation", "report_task"):
            assert sum(pair[metric].values()) == len(rows)


def test_decision_precedence_covers_recovery_and_regression() -> None:
    """Regression precedence dominates an otherwise complete population."""
    cases = p3.p2.load_case_definitions()
    rows = _population()
    assert p3.decision(rows, cases, expected_checkpoint=p3.BASELINE_SHA) == (
        "PROMPT_CONTRACT_FULL_RECOVERY"
    )
    rows[0]["arms"]["WR"]["final_contract_ok"] = False
    assert p3.decision(rows, cases, expected_checkpoint=p3.BASELINE_SHA) == (
        "PROMPT_CONTRACT_REGRESSION"
    )


def test_terminal_failures_are_decision_safe() -> None:
    """Semantic and schema terminal outcomes never crash aggregation."""
    cases = p3.p2.load_case_definitions()
    rows = _population()
    rows[0]["arms"]["WR"].update(
        {
            "final_contract_ok": False,
            "final_facts": None,
            "final_classification": "PLANNER_SEMANTIC_FAILURE",
            "final_planner_success": False,
        }
    )
    assert p3.decision(rows, cases, expected_checkpoint=p3.BASELINE_SHA) == (
        "PROMPT_CONTRACT_REGRESSION"
    )

    rows = _population()
    rows[0]["arms"]["P"].update(
        {
            "final_contract_ok": False,
            "final_facts": None,
            "final_classification": "PLANNER_SEMANTIC_FAILURE",
            "final_planner_success": False,
        }
    )
    assert p3.decision(rows, cases, expected_checkpoint=p3.BASELINE_SHA) == (
        "PROMPT_CONTRACT_FULL_RECOVERY"
    )

    rows = _population()
    for arm in ("P", "WR"):
        rows[0]["arms"][arm].update(
            {
                "final_contract_ok": False,
                "final_facts": None,
                "final_classification": "PLANNER_SCHEMA_FAILURE",
                "final_planner_success": False,
            }
        )
    assert p3.decision(rows, cases, expected_checkpoint=p3.BASELINE_SHA) == (
        "PROMPT_CONTRACT_NO_RECOVERY"
    )

    rows = _population()
    rows[0]["arms"]["WR"]["provider_infrastructure_failure"] = True
    assert p3.decision(rows, cases, expected_checkpoint=p3.BASELINE_SHA) == (
        "INCONCLUSIVE_PLANNER_MICRO_BISECT"
    )


def test_repeatability_marks_partial_cases_unavailable() -> None:
    """Incomplete per-case attempts do not cause an index error."""
    result = p3.repeatability(_population()[:1])
    assert result["unavailable_cases"]["P"] == [_case()["case_id"]]


def test_summary_exposes_initial_final_and_terminal_arm_metrics() -> None:
    """Aggregates retain both semantic phases and terminal outcomes."""
    summary = p3.summarize_population(
        _population(),
        p3.p2.load_case_definitions(),
        authorized_checkpoint=p3.BASELINE_SHA,
    )
    metrics = summary["arm_metrics"]["WR"]
    expected_keys = {
        "initial_contract_passes",
        "initial_work_unit_fragmentation",
        "initial_empty_report_task",
        "initial_union_exact_expected",
        "final_contract_passes",
        "final_fragmentation_with_gap",
        "final_nonempty_report_task",
        "final_duplicates",
        "final_parent_closure_failures",
        "final_unresolved_requirements",
        "planner_semantic_failures",
        "planner_schema_failures",
        "provider_infrastructure_failures",
        "semantic_correction_failures",
        "rows_without_semantic_correction",
    }
    assert expected_keys <= set(metrics)


def test_prelive_report_makes_no_provider_calls() -> None:
    """The provider-free report describes the gated future matrix."""
    report = p3.prelive_report()
    assert report["status"] == "PRELIVE_READY"
    assert report["provider_calls"] == 0
    assert report["worker_calls"] == 0
    assert report["future_population"]["shared_rows"] == 32
    assert report["future_population"]["planner_executions"] == 128
