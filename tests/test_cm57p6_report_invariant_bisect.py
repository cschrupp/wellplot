"""Provider-free CM-57P6 non-empty report invariant tests."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

import pytest
from pydantic import BaseModel, ValidationError
from scripts import cm57p6_report_invariant_bisect as p6

from wellplot.agent.code_mode.planner import (
    PlannerSemanticError,
    PlannerSemanticFailure,
    SectionTask,
    SemanticPlan,
    SemanticPlanner,
)
from wellplot.agent.providers.base import (
    ProviderFailureCategory,
    ProviderMetrics,
    ProviderRequestError,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from wellplot.capabilities import create_builtin_registry


@dataclass
class QueueBackend:
    """Return queued provider outcomes and record request models."""

    responses: list[object]
    requests: list[StructuredGenerationRequest] = field(default_factory=list)
    response_models: list[type[BaseModel]] = field(default_factory=list)

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        """Return the next queued response or raise its configured error."""
        self.requests.append(request)
        self.response_models.append(response_model)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        response_value = response.model_dump() if isinstance(response, BaseModel) else response
        return StructuredGenerationResult(
            value=response_model.model_validate(response_value),
            metrics=ProviderMetrics(total_tokens=1, latency_ms=1.0),
        )

    async def generate_program(self, request: object) -> object:
        """Reject accidental worker execution."""
        raise AssertionError(f"CM-57P6 must not call program generation: {request!r}")


def _empty_report_plan() -> SemanticPlan:
    """Build the historical invalid report work unit."""
    return p6._empty_report_plan()


def _valid_report_plan() -> SemanticPlan:
    """Build a valid report work unit."""
    return p6._valid_report_plan()


def _valid_section_plan() -> SemanticPlan:
    """Build a valid section-only plan."""
    return p6._valid_section_plan()


def _duplicate_section_plan() -> SemanticPlan:
    """Build a plan rejected by the existing duplicate-capability rule."""
    return SemanticPlan(
        summary="duplicate section capability",
        section_tasks=(
            SectionTask(
                goal="one section",
                capability_ids=("section.log_plot", "section.log_plot"),
            ),
        ),
    )


def test_manifest_is_exactly_the_frozen_diagnostic_population() -> None:
    """The manifest reuses only the authorized P5 cases and role split."""
    entries = p6.load_manifest()

    assert len(entries) == 12
    assert [entry["case_id"] for entry in entries[:3]] == list(p6.TARGET_CASES)
    assert [entry["role"] for entry in entries].count(p6.ROLE_TARGET) == 3
    assert [entry["role"] for entry in entries].count(p6.ROLE_REPORT_CONTROL) == 5
    assert [entry["role"] for entry in entries].count(p6.ROLE_SECTION_SENTINEL) == 4
    assert p6.artifact_sha256(p6.MANIFEST_PATH) == p6.EXPECTED_MANIFEST_SHA256

    statuses = {entry["case_id"]: entry["historical_rc_status"] for entry in entries}
    for case_id in p6.TARGET_CASES:
        assert statuses[case_id] == {
            "final_classification": "REPORT_CAPABILITY_MISMATCH",
            "report_task_present": True,
            "report_capability_ids": [],
            "attempts": 2,
        }
    for case_id in p6.REPORT_CONTROL_CASES:
        assert statuses[case_id]["final_classification"] == "PLANNER_CONTRACT_OK"
        assert statuses[case_id]["report_capability_ids"] == ["report.standard"]


def test_production_and_experimental_schema_hashes_are_frozen_and_isolated() -> None:
    """Only report capability non-emptiness changes at the response boundary."""
    assert p6.schema_diff_isolated()
    assert p6.schema_sha256(SemanticPlan) == p6.EXPECTED_PRODUCTION_SCHEMA_SHA256
    assert p6.schema_sha256(p6.NonEmptyReportSemanticPlan) == p6.EXPECTED_NONEMPTY_SCHEMA_SHA256

    SemanticPlan.model_validate({"summary": "empty", "report_task": {"goal": "report"}})
    with pytest.raises(ValidationError):
        p6.NonEmptyReportSemanticPlan.model_validate(
            {"summary": "empty", "report_task": {"goal": "report", "capability_ids": []}}
        )
    assert p6.NonEmptyReportSemanticPlan.model_validate(_valid_section_plan().model_dump())
    assert p6.NonEmptyReportSemanticPlan.model_validate(
        {
            "summary": "report",
            "report_task": {"goal": "report", "capability_ids": ["report.standard"]},
        }
    )


def test_invariant_validator_rejects_only_empty_present_report_tasks() -> None:
    """The experiment adds no host inference or unrelated semantic rule."""
    registry = create_builtin_registry()

    assert p6.validate_semantic_plan_nonempty_report(_valid_section_plan(), registry)
    assert p6.validate_semantic_plan_nonempty_report(_valid_report_plan(), registry)
    with pytest.raises(PlannerSemanticError) as error_info:
        p6.validate_semantic_plan_nonempty_report(_empty_report_plan(), registry)
    assert error_info.value.code == "empty_report_capabilities"


def test_rcv_correction_is_bounded_and_uses_the_exact_diagnostic() -> None:
    """RCV corrects one empty report plan with exactly one extra call."""
    backend = QueueBackend([_empty_report_plan(), _valid_report_plan()])
    planner = p6.InvariantSemanticPlanner(
        backend=backend,
        registry=create_builtin_registry(),
    )

    result = asyncio.run(
        planner.plan(
            request="Prepare a report.",
            mode="reconstruct",
            source_summary=p6.p5.FIXED_SOURCE_SUMMARY,
            timeout_seconds=1.0,
            temperature=0.0,
            max_output_tokens=100,
        )
    )

    assert result == _valid_report_plan()
    assert len(backend.requests) == 2
    assert backend.response_models == [SemanticPlan, SemanticPlan]
    assert backend.requests[0].system_prompt == p6._PLANNER_SYSTEM_PROMPT
    assert "empty_report_capabilities" in backend.requests[1].user_prompt


def test_rcv_second_empty_report_is_a_bounded_typed_failure() -> None:
    """A second semantic violation terminates without a third provider call."""
    backend = QueueBackend([_empty_report_plan(), _empty_report_plan()])
    planner = p6.InvariantSemanticPlanner(
        backend=backend,
        registry=create_builtin_registry(),
    )

    with pytest.raises(PlannerSemanticFailure) as error_info:
        asyncio.run(
            planner.plan(
                request="Prepare a report.",
                mode="reconstruct",
                timeout_seconds=1.0,
                temperature=0.0,
                max_output_tokens=100,
            )
        )
    assert error_info.value.code == "empty_report_capabilities"
    assert len(backend.requests) == 2


def test_rcv_matches_production_requests_when_invariant_is_inactive() -> None:
    """RCV preserves production request construction and correction flow."""
    registry = create_builtin_registry()
    control_backend = QueueBackend([_duplicate_section_plan(), _valid_section_plan()])
    candidate_backend = QueueBackend([_duplicate_section_plan(), _valid_section_plan()])

    control_wrapper = p6.PromptBackend(control_backend, [], [])
    candidate_wrapper = p6.PromptBackend(candidate_backend, [], [])
    asyncio.run(
        SemanticPlanner(backend=control_wrapper, registry=registry).plan(
            request="same",
            mode="reconstruct",
            timeout_seconds=1.0,
            temperature=0.0,
            max_output_tokens=100,
        )
    )
    asyncio.run(
        p6.InvariantSemanticPlanner(backend=candidate_wrapper, registry=registry).plan(
            request="same",
            mode="reconstruct",
            timeout_seconds=1.0,
            temperature=0.0,
            max_output_tokens=100,
        )
    )

    assert control_backend.requests == candidate_backend.requests
    assert control_backend.response_models == candidate_backend.response_models


def test_rcs_uses_experimental_schema_and_converts_without_mutation() -> None:
    """RCS changes only the requested provider response model."""
    plan = _valid_report_plan()
    original = plan.model_dump()
    backend = QueueBackend([plan])
    wrapper = p6.SchemaPromptBackend(backend, [], [])

    result = asyncio.run(
        SemanticPlanner(backend=wrapper, registry=create_builtin_registry()).plan(
            request="same",
            mode="reconstruct",
            timeout_seconds=1.0,
        )
    )

    assert result == plan
    assert plan.model_dump() == original
    assert backend.response_models == [p6.NonEmptyReportSemanticPlan]


def test_rcs_invalid_response_uses_only_production_retry() -> None:
    """RCS preserves the normal one invalid-response retry budget."""
    backend = QueueBackend(
        [
            ProviderRequestError(
                ProviderFailureCategory.INVALID_RESPONSE,
                "safe invalid response",
            ),
            _valid_report_plan(),
        ]
    )
    wrapper = p6.SchemaPromptBackend(backend, [], [])

    result = asyncio.run(
        SemanticPlanner(backend=wrapper, registry=create_builtin_registry()).plan(
            request="same",
            mode="reconstruct",
            timeout_seconds=1.0,
        )
    )

    assert result == _valid_report_plan()
    assert len(backend.requests) == 2
    assert backend.response_models == [
        p6.NonEmptyReportSemanticPlan,
        p6.NonEmptyReportSemanticPlan,
    ]


def test_recording_backend_counts_provider_schema_rejections() -> None:
    """Provider-mapped invalid responses remain visible as schema failures."""
    calls: list[dict[str, object]] = []
    recorder = p6.RecordingBackend(
        delegate=QueueBackend(
            [ProviderRequestError(ProviderFailureCategory.INVALID_RESPONSE, "safe invalid")]
        ),
        response_schema_sha256=p6.EXPECTED_NONEMPTY_SCHEMA_SHA256,
        calls=calls,
        plans=[],
    )

    with pytest.raises(ProviderRequestError):
        asyncio.run(
            recorder.generate_structured(
                StructuredGenerationRequest(
                    system_prompt="system",
                    user_prompt="request",
                    timeout_seconds=1.0,
                ),
                response_model=p6.NonEmptyReportSemanticPlan,
            )
        )

    assert calls == [
        {
            "call_kind": "INITIAL",
            "response_schema_sha256": p6.EXPECTED_NONEMPTY_SCHEMA_SHA256,
            "outcome": "provider_failure",
            "provider_category": ProviderFailureCategory.INVALID_RESPONSE.value,
        }
    ]


def test_frozen_provenance_and_manifest_are_bounded_and_path_free() -> None:
    """Pre-live evidence metadata contains no filesystem or provider prose."""
    serialized = p6.canonical_json(
        {"manifest": p6.load_manifest(), "provenance": p6.frozen_provenance()}
    )

    assert "/home/" not in serialized
    assert "/tmp/" not in serialized
    assert "api_key" not in serialized
    assert "provider_response" not in serialized


def _facts(*, report_ids: list[str], contract_ok: bool) -> dict[str, object]:
    """Build bounded final facts for decision-rule tests."""
    return {
        "report_task_present": bool(report_ids),
        "report_capability_ids": report_ids,
        "report_presence_correct": True,
        "report_capabilities_exact": True,
        "section_count_correct": True,
        "section_multiset_exact": True,
        "duplicate_capability_type": False,
        "parent_closure_valid": True,
        "unresolved_correct": True,
        "contract_ok": contract_ok,
    }


def _arm(*, contract_ok: bool, recovered: bool, infrastructure: bool = False) -> dict[str, object]:
    """Build one bounded synthetic arm result."""
    report_ids = ["report.standard"] if recovered else []
    return {
        "final_planner_success": True,
        "final_contract_ok": contract_ok,
        "final_work_unit_facts": _facts(report_ids=report_ids, contract_ok=contract_ok),
        "provider_infrastructure_failure": infrastructure,
    }


def _decision_rows(
    *,
    rcv_recoveries: int = 0,
    rcs_recoveries: int = 0,
    rcv_regression: bool = False,
    rcs_regression: bool = False,
) -> list[dict[str, object]]:
    """Build a compact synthetic population for frozen decision labels."""
    rows: list[dict[str, object]] = []
    target_index = 0
    for entry in p6.load_manifest():
        role = str(entry["role"])
        attempts = 2
        for _ in range(attempts):
            is_target = role == p6.ROLE_TARGET
            rcv_recovered = is_target and target_index < rcv_recoveries
            rcs_recovered = is_target and target_index < rcs_recoveries
            if is_target:
                target_index += 1
            rc_ok = not is_target
            rows.append(
                {
                    "case_id": entry["case_id"],
                    "role": role,
                    "attempt_index": len(rows) % 2,
                    "arms": {
                        "RC": _arm(contract_ok=rc_ok, recovered=False),
                        "RCV": _arm(
                            contract_ok=rcv_recovered or not is_target,
                            recovered=rcv_recovered,
                            infrastructure=False,
                        ),
                        "RCS": _arm(
                            contract_ok=rcs_recovered or not is_target,
                            recovered=rcs_recovered,
                            infrastructure=False,
                        ),
                    },
                }
            )
    if rcv_regression:
        for row in rows:
            if row["role"] == p6.ROLE_REPORT_CONTROL:
                row["arms"]["RCV"]["final_contract_ok"] = False  # type: ignore[index]
                break
    if rcs_regression:
        for row in rows:
            if row["role"] == p6.ROLE_REPORT_CONTROL:
                row["arms"]["RCS"]["final_contract_ok"] = False  # type: ignore[index]
                break
    return rows


def _complete_population(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Add the frozen evidence envelope to synthetic decision rows."""
    checkpoint = "a" * 40
    manifest = {entry["case_id"]: entry for entry in p6.load_manifest()}
    cases = p6._case_by_id()
    provenance = p6.frozen_provenance()
    for row in rows:
        case_id = row["case_id"]
        entry = manifest[case_id]
        status = entry["historical_rc_status"]
        row.update(
            provenance,
            authorized_checkpoint=checkpoint,
            request_sha256=p6.sha256_text(str(cases[case_id]["request"])),
            historical_rc_status=status,
        )
        rc_arm = row["arms"]["RC"]  # type: ignore[index]
        rc_arm.update(
            prompt_sha256=p6.EXPECTED_RC_PROMPT_SHA256,
            response_schema_sha256=p6.EXPECTED_PRODUCTION_SCHEMA_SHA256,
            semantic_correction_used=False,
            final_classification=status["final_classification"],
        )
        rc_facts = rc_arm["final_work_unit_facts"]
        rc_facts.update(
            report_task_present=status["report_task_present"],
            report_capability_ids=status["report_capability_ids"],
        )
        for arm in ("RCV", "RCS"):
            candidate = row["arms"][arm]  # type: ignore[index]
            candidate.update(
                prompt_sha256=p6.EXPECTED_RC_PROMPT_SHA256,
                response_schema_sha256=(
                    p6.EXPECTED_NONEMPTY_SCHEMA_SHA256
                    if arm == "RCS"
                    else p6.EXPECTED_PRODUCTION_SCHEMA_SHA256
                ),
            )
    return rows


def test_report_control_rc_baseline_mismatch_is_inconclusive() -> None:
    """A contemporaneous RC failure on a passing control invalidates P6."""
    rows = _complete_population(_decision_rows(rcv_recoveries=6, rcs_recoveries=6))
    control = next(row for row in rows if row["role"] == p6.ROLE_REPORT_CONTROL)
    control["arms"]["RC"].update(  # type: ignore[index]
        final_classification="REPORT_CAPABILITY_MISMATCH",
        final_contract_ok=False,
    )
    control["arms"]["RC"]["final_work_unit_facts"].update(  # type: ignore[index]
        report_task_present=True,
        report_capability_ids=[],
    )

    complete, reasons = p6.population_integrity(
        rows,
        expected_checkpoint="a" * 40,
    )

    assert not complete
    assert "rc_baseline_not_reproduced" in reasons
    assert p6.decision(rows, expected_checkpoint="a" * 40) == (
        "INCONCLUSIVE_REPORT_INVARIANT_BISECT"
    )


def test_joint_rc_and_candidate_control_failure_cannot_validate() -> None:
    """RC and candidate loss of a passing control is not a zero-regression pass."""
    rows = _complete_population(_decision_rows(rcv_recoveries=6, rcs_recoveries=6))
    control = next(row for row in rows if row["role"] == p6.ROLE_REPORT_CONTROL)
    control["arms"]["RC"]["final_contract_ok"] = False  # type: ignore[index]
    control["arms"]["RCV"]["final_contract_ok"] = False  # type: ignore[index]
    control["arms"]["RCS"]["final_contract_ok"] = False  # type: ignore[index]

    complete, reasons = p6.population_integrity(
        rows,
        expected_checkpoint="a" * 40,
    )

    assert not complete
    assert "rc_baseline_not_reproduced" in reasons
    assert p6.decision(rows, expected_checkpoint="a" * 40) == (
        "INCONCLUSIVE_REPORT_INVARIANT_BISECT"
    )


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"rcv_recoveries": 6, "rcs_recoveries": 6}, "REPORT_INVARIANT_BOTH_VALIDATED"),
        ({"rcv_recoveries": 0, "rcs_recoveries": 6}, "REPORT_INVARIANT_SCHEMA_VALIDATED"),
        ({"rcv_recoveries": 6, "rcs_recoveries": 0}, "REPORT_INVARIANT_VALIDATOR_VALIDATED"),
        ({"rcv_recoveries": 2, "rcs_recoveries": 0}, "REPORT_INVARIANT_PARTIAL_RECOVERY"),
        ({}, "REPORT_INVARIANT_NO_RECOVERY"),
        ({"rcv_regression": True}, "REPORT_INVARIANT_REGRESSION"),
    ],
)
def test_frozen_decision_labels(kwargs: dict[str, object], expected: str) -> None:
    """Each non-inconclusive P6 decision label has a deterministic trigger."""
    rows = _decision_rows(**kwargs)
    original_integrity = p6.population_integrity
    p6.population_integrity = lambda rows, expected_checkpoint=None: (True, [])
    try:
        assert p6.decision(rows) == expected
    finally:
        p6.population_integrity = original_integrity


def test_infrastructure_or_population_failure_is_inconclusive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inconclusive precedence dominates otherwise viable synthetic arms."""
    rows = _decision_rows(rcv_recoveries=6, rcs_recoveries=6)
    monkeypatch.setattr(
        p6, "population_integrity", lambda rows, expected_checkpoint=None: (False, ["drift"])
    )
    assert p6.decision(rows) == "INCONCLUSIVE_REPORT_INVARIANT_BISECT"

    rows = _decision_rows(rcv_recoveries=6, rcs_recoveries=6)
    rows[0]["arms"]["RCV"]["provider_infrastructure_failure"] = True  # type: ignore[index]
    monkeypatch.setattr(
        p6, "population_integrity", lambda rows, expected_checkpoint=None: (True, [])
    )
    assert p6.decision(rows) == "INCONCLUSIVE_REPORT_INVARIANT_BISECT"


def test_transition_tables_preserve_unavailable_terminal_outcomes() -> None:
    """Missing final facts are counted as unavailable, not semantic failures."""
    rows = _decision_rows()
    rows[0]["arms"]["RCS"]["final_work_unit_facts"] = None  # type: ignore[index]

    table = p6._transition_table(rows, "RC", "RCS", "report_capabilities_exact")

    assert table["UNAVAILABLE"] == 1
    assert sum(table.values()) == len(rows)


def test_prelive_report_runs_provider_free_and_is_json_serializable() -> None:
    """The default P6 entry point performs no provider construction."""
    report = p6.prelive_report()

    assert report["status"] == "PRELIVE_READY"
    assert report["provider_calls"] == 0
    assert report["live_inference"] == "NOT_STARTED"
    assert json.dumps(report, sort_keys=True)
