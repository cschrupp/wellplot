"""Deterministic CM-57P4 planner prompt interaction tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest
from pydantic import BaseModel
from scripts import cm57p3_work_unit_bisect as p3
from scripts import cm57p4_prompt_interaction_bisect as p4

from wellplot.agent.code_mode.planner import SectionTask, SemanticPlan, SemanticPlanner
from wellplot.agent.providers.base import (
    ProviderMetrics,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from wellplot.capabilities import create_builtin_registry


@dataclass
class Backend:
    """Return one fixed plan and record provider requests."""

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
        """Reject accidental worker execution."""
        raise AssertionError(f"Unexpected program request: {request!r}")


@dataclass
class SequenceBackend(Backend):
    """Return configured plans in sequence for correction-path tests."""

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


def _case() -> dict[str, object]:
    return p4.p2.load_case_definitions()[0]


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
    """Run one production planner invocation against a supplied backend."""
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


def _request(arm: p4.Arm) -> tuple[Backend, p4.PromptArmBackend]:
    delegate = Backend(_valid_plan())
    wrapper = p4.PromptArmBackend(delegate=delegate, arm=arm, forwarded_requests=[])
    _run_planner(wrapper)
    return delegate, wrapper


def test_prompt_composition_preserves_controls_and_hashes() -> None:
    """R and WR remain P3 controls; RW and RC are isolated interventions."""
    assert p4.composed_prompt("R") == p3.composed_prompt("R")
    assert p4.composed_prompt("WR") == p3.composed_prompt("WR")
    assert p4.composed_prompt("RW") == (
        p4._PLANNER_SYSTEM_PROMPT
        + "\n"
        + p4.REPORT_BOUNDARY_INSTRUCTION
        + "\n"
        + p4.WORK_UNIT_INSTRUCTION
    )
    assert p4.composed_prompt("RC") == (
        p4._PLANNER_SYSTEM_PROMPT
        + "\n"
        + p4.REPORT_BOUNDARY_INSTRUCTION
        + "\n"
        + p4.SECTION_COMPOSITION_INSTRUCTION
    )
    assert p4.PROMPT_SHA256["R"] == (
        "fe8db9c9cba4cf7bf13d79c3e838eaa53e19770fbf6dd764cdcf93020008c563"
    )
    assert p4.PROMPT_SHA256["WR"] == (
        "5a0e49f077e45587e19470f962b09528a4a485a0d05725eb285cef676de1035f"
    )
    assert p4.PROMPT_SHA256["RW"] == (
        "d9043041fdc651d613c67a2a77a825be1d52b1940a2f82d0ff73e03d914116ca"
    )
    assert p4.PROMPT_SHA256["RC"] == (
        "e1710cb516a96c47ec1d0593752e83aacc1bb4502c3026b2b6a9a676c90e4d34"
    )


@pytest.mark.parametrize("arm", p4.ARMS)
def test_prompt_wrapper_changes_only_system_prompt(arm: p4.Arm) -> None:
    """All P4 arms preserve the complete non-system provider request."""
    delegate, wrapper = _request(arm)
    forwarded = wrapper.forwarded_requests[0]
    original = delegate.requests[0]
    assert forwarded.user_prompt == original.user_prompt
    assert forwarded.timeout_seconds == original.timeout_seconds
    assert forwarded.temperature == original.temperature
    assert forwarded.max_output_tokens == original.max_output_tokens
    assert forwarded.system_prompt == p4.composed_prompt(arm)


def test_prompt_wrapper_rejects_base_prompt_drift_before_delegate() -> None:
    """Prompt drift fails closed before the delegate is called."""
    delegate = Backend(_valid_plan())
    wrapper = p4.PromptArmBackend(delegate=delegate, arm="RC", forwarded_requests=[])
    request = StructuredGenerationRequest(
        system_prompt="drifted",
        user_prompt="request",
        timeout_seconds=1.0,
    )
    with pytest.raises(RuntimeError, match="unexpected production planner prompt"):
        asyncio.run(wrapper.generate_structured(request, response_model=SemanticPlan))
    assert delegate.requests == []


def test_correction_path_uses_the_same_arm_prompt() -> None:
    """Initial and semantic-correction requests use identical arm composition."""
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
    delegate = SequenceBackend(plan=_valid_plan(), responses=[duplicate, _valid_plan()])
    wrapper = p4.PromptArmBackend(delegate=delegate, arm="RW", forwarded_requests=[])
    planner = SemanticPlanner(backend=wrapper, registry=create_builtin_registry())
    asyncio.run(
        planner.plan(request="Create one section.", mode="reconstruct", timeout_seconds=1.0)
    )
    assert len(wrapper.forwarded_requests) == 2
    assert all(
        request.system_prompt == p4.composed_prompt("RW") for request in wrapper.forwarded_requests
    )


def test_wrapper_returns_provider_result_without_modification() -> None:
    """The prompt wrapper does not transform provider output."""
    delegate = Backend(_valid_plan())
    wrapper = p4.PromptArmBackend(delegate=delegate, arm="RC", forwarded_requests=[])
    result = asyncio.run(
        wrapper.generate_structured(
            StructuredGenerationRequest(
                system_prompt=p4._PLANNER_SYSTEM_PROMPT,
                user_prompt="request",
                timeout_seconds=1.0,
            ),
            response_model=SemanticPlan,
        )
    )
    assert result.value == _valid_plan()


def test_mixed_residual_facts_match_frozen_diagnostic() -> None:
    """The historical WR split and omission are classified independently."""
    expected = [
        "section.log_plot",
        "track.normal",
        "binding.curve",
        "track.array",
        "binding.raster",
    ]
    registry = create_builtin_registry()
    fragmented = SemanticPlan(
        summary="split",
        section_tasks=(
            SectionTask(goal="normal", capability_ids=("track.normal",)),
            SectionTask(goal="array", capability_ids=("track.array",)),
        ),
    )
    fragmented_facts = p4._facts(fragmented, expected, registry)
    assert fragmented_facts["section_count_ok"] is False
    assert fragmented_facts["fragmentation_with_gap"] is True
    assert fragmented_facts["union_missing_capabilities"] == [
        "binding.curve",
        "binding.raster",
        "section.log_plot",
    ]
    corrected = SemanticPlan(
        summary="corrected",
        section_tasks=(
            SectionTask(
                goal="section",
                capability_ids=("section.log_plot", "track.normal", "track.array"),
            ),
        ),
    )
    corrected_facts = p4._facts(corrected, expected, registry)
    assert corrected_facts["single_task_closure_omission"] is True
    assert corrected_facts["union_missing_capabilities"] == [
        "binding.curve",
        "binding.raster",
    ]


def _population() -> list[dict[str, object]]:
    cases = p4.p2.load_case_definitions()
    return [
        {
            "case_id": case["case_id"],
            "attempt_index": attempt,
            "authorized_checkpoint": p4.BASELINE_SHA,
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
                for arm in p4.ARMS
            },
        }
        for case in cases
        for attempt in range(p4.ATTEMPTS)
    ]


def test_factor_tables_cover_all_six_pairs_and_conserve_rows() -> None:
    """Every required full and semantic pair table accounts for 32 rows."""
    tables = p4.factor_tables(_population())
    assert set(tables) == {"R_to_WR", "WR_to_RW", "R_to_RW", "R_to_RC", "RW_to_RC", "WR_to_RC"}
    for pair in tables.values():
        assert sum(pair["full_contract"].values()) == 32
        for metric in ("fragmentation", "report_task"):
            assert sum(pair[metric].values()) == 32


def test_terminal_rows_are_unavailable_for_semantic_pairs() -> None:
    """Terminal failures cannot masquerade as semantic false facts."""
    rows = _population()
    rows[0]["arms"]["R"]["final_contract_ok"] = False
    rows[0]["arms"]["R"]["final_facts"] = None
    rows[0]["arms"]["R"]["final_classification"] = "PLANNER_SCHEMA_FAILURE"
    table = p4.factor_tables(rows)["R_to_WR"]
    assert table["fragmentation"]["UNAVAILABLE"] == 1
    assert table["report_task"]["UNAVAILABLE"] == 1
    assert table["full_contract"]["RIGHT_ONLY_PASS"] == 1


def test_population_integrity_requires_all_p4_arms() -> None:
    """A row missing an arm is not a valid live population."""
    rows = _population()
    del rows[0]["arms"]["RC"]
    complete, reasons = p4.population_integrity(rows, p4.p2.load_case_definitions())
    assert complete is False
    assert "arm_set_mismatch" in reasons


def test_decision_precedence_is_candidate_specific() -> None:
    """One poor candidate does not invalidate an independent successful candidate."""
    cases = p4.p2.load_case_definitions()
    rows = _population()
    for row in rows[:2]:
        row["arms"]["WR"]["final_contract_ok"] = False
    for row in rows[:3]:
        row["arms"]["RW"]["final_contract_ok"] = False
    rows[3]["arms"]["RC"]["final_contract_ok"] = False
    assert p4.decision(rows, cases, expected_checkpoint=p4.BASELINE_SHA) == (
        "PROMPT_INTERACTION_PARTIAL_RECOVERY"
    )
    for row in rows:
        row["arms"]["RW"]["final_contract_ok"] = False
        row["arms"]["RC"]["final_contract_ok"] = False
    assert p4.decision(rows, cases, expected_checkpoint=p4.BASELINE_SHA) == (
        "PROMPT_INTERACTION_REGRESSION"
    )


def test_decision_labels_no_recovery_and_inconclusive() -> None:
    """No recovery and provider infrastructure outcomes remain distinct."""
    cases = p4.p2.load_case_definitions()
    rows = _population()
    for row in rows[:2]:
        row["arms"]["WR"]["final_contract_ok"] = False
        row["arms"]["RW"]["final_contract_ok"] = False
        row["arms"]["RC"]["final_contract_ok"] = False
    assert p4.decision(rows, cases, expected_checkpoint=p4.BASELINE_SHA) == (
        "PROMPT_INTERACTION_NO_RECOVERY"
    )
    rows[0]["arms"]["RC"]["provider_infrastructure_failure"] = True
    assert p4.decision(rows, cases, expected_checkpoint=p4.BASELINE_SHA) == (
        "INCONCLUSIVE_PROMPT_INTERACTION_BISECT"
    )


def test_prelive_report_is_provider_free_and_frozen() -> None:
    """The default CLI path verifies the future matrix without provider calls."""
    report = p4.prelive_report()
    assert report["status"] == "PRELIVE_READY"
    assert report["provider_calls"] == 0
    assert report["worker_calls"] == 0
    assert report["arms"] == ["R", "WR", "RW", "RC"]
    assert report["future_population"] == {
        "cases": 16,
        "shared_rows": 32,
        "planner_executions": 128,
        "provider_calls_min": 128,
        "provider_calls_max": 256,
    }
