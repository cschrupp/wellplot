"""Deterministic CM-57P8 prompt-factor localization tests."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import BaseModel
from scripts import cm57p8_prompt_factor_localization as p8

from wellplot.agent.code_mode.planner import SectionTask, SemanticPlan
from wellplot.agent.providers.base import (
    ProviderMetrics,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)


@dataclass
class Backend:
    """Return one fixed plan and record forwarded provider requests."""

    plan: SemanticPlan = field(
        default_factory=lambda: SemanticPlan(
            summary="test",
            section_tasks=(SectionTask(goal="test section", capability_ids=("section.log_plot",)),),
        )
    )
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
        raise AssertionError(f"Unexpected worker request: {request!r}")


def _synthetic_rows(
    reference_values: dict[str, bool],
    *,
    schema_values: dict[str, list[bool]] | None = None,
) -> list[dict[str, object]]:
    """Build bounded rows for localization decision tests."""
    rows = []
    for attempt in range(2):
        arms = {}
        for arm in p8.ARMS:
            plan_available = True
            if schema_values and arm in schema_values:
                plan_available = schema_values[arm][attempt]
            arms[arm] = {
                "final_plan_available": plan_available,
                "final_classification": "PLANNER_CONTRACT_OK"
                if plan_available
                else "PLANNER_SCHEMA_FAILURE",
                "reference": {
                    "expected_reference_required": False,
                    "final_plan_available": plan_available,
                    "actual_reference_present": reference_values.get(arm, False)
                    if plan_available
                    else None,
                    "unexpected_reference": reference_values.get(arm, False)
                    if plan_available
                    else None,
                    "missing_required_reference": False if plan_available else None,
                },
            }
        rows.append(
            {"case_id": p8.PROTECTED_REFERENCE_TARGET, "attempt_index": attempt, "arms": arms}
        )
    return rows


def _schema_rows(
    patterns: dict[str, tuple[bool, bool, bool]],
) -> list[dict[str, object]]:
    """Build two stable attempts for the schema localization targets."""
    rows = []
    for case_id in sorted(p8.SCHEMA_TARGETS):
        pattern = patterns[case_id]
        for attempt in range(2):
            available = {
                "P": False,
                "R": pattern[0],
                "C": pattern[1],
                "RC": pattern[2],
            }
            arms = {
                arm: {
                    "final_plan_available": available[arm],
                    "final_classification": "PLANNER_CONTRACT_OK"
                    if available[arm]
                    else "PLANNER_SCHEMA_FAILURE",
                    "reference": {
                        "expected_reference_required": True,
                        "final_plan_available": available[arm],
                        "actual_reference_present": None,
                        "unexpected_reference": None,
                        "missing_required_reference": None,
                    },
                }
                for arm in p8.ARMS
            }
            rows.append({"case_id": case_id, "attempt_index": attempt, "arms": arms})
    return rows


def _decision_row(*, infrastructure_failure: bool = False, program_calls: int = 0) -> dict:
    """Build one minimal row for top-level decision tests."""
    return {
        "arms": {
            arm: {
                "provider_infrastructure_failure": infrastructure_failure,
                "program_call_count": program_calls,
            }
            for arm in p8.ARMS
        }
    }


def _patch_decision_inputs(
    monkeypatch: pytest.MonkeyPatch,
    *,
    reference_classification: str,
    schema_classification: str,
    reference_reproduced: bool = True,
    schema_reproduced: bool = True,
    population_complete: bool = True,
    population_reasons: list[str] | None = None,
) -> None:
    """Patch only deterministic decision inputs for top-level label tests."""
    monkeypatch.setattr(
        p8,
        "population_integrity",
        lambda *args, **kwargs: (population_complete, population_reasons or []),
    )
    monkeypatch.setattr(
        p8,
        "historical_anchor_reproduction",
        lambda *args, **kwargs: {
            "all": {"checked": 0, "mismatches": [], "reproduced": True},
            "reference": {"checked": 0, "mismatches": [], "reproduced": reference_reproduced},
            "schema": {"checked": 0, "mismatches": [], "reproduced": schema_reproduced},
        },
    )
    monkeypatch.setattr(
        p8,
        "_reference_localization",
        lambda *args, **kwargs: {"classification": reference_classification},
    )
    monkeypatch.setattr(
        p8,
        "_schema_localization",
        lambda *args, **kwargs: {"classification": schema_classification},
    )


def test_manifest_resolves_exactly_twelve_p7_cases_without_request_text() -> None:
    """The manifest selects exposed P7 cases and does not duplicate prose."""
    payload = json.loads(p8.MANIFEST_PATH.read_text(encoding="utf-8"))
    assert len(payload["cases"]) == 12
    assert all("request" not in case for case in payload["cases"])
    cases = p8.load_manifest()
    assert len(cases) == 12
    assert {case["case_id"] for case in cases} == {item["case_id"] for item in payload["cases"]}


def test_manifest_and_frozen_contract_hashes_pass() -> None:
    """P7 corpus, raw evidence, prompts, schema, and production bytes are frozen."""
    contract = p8.verify_frozen_contract()
    assert contract["manifest_version"] == p8.MANIFEST_VERSION
    assert contract["p7_raw_sha256"] == p8.EXPECTED_P7_RAW_SHA256
    assert contract["production_schema_sha256"] == p8.EXPECTED_SCHEMA_SHA256
    assert contract["historical_anchor_derivation"] == "FROZEN_FROM_VERIFIED_P7_RAW"


def test_p7_raw_derivation_rejects_wrong_sha(tmp_path: Path) -> None:
    """Anchor derivation fails closed if the supplied P7 raw bytes drift."""
    raw = tmp_path / "p7.jsonl"
    raw.write_text("{}\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="exact verified P7 raw evidence SHA"):
        p8.derive_historical_anchors(raw)


def test_factor_prompts_change_only_the_frozen_system_suffix() -> None:
    """P/R/C/RC use the exact four frozen prompt compositions."""
    assert p8.composed_prompt("P") == p8._PLANNER_SYSTEM_PROMPT
    assert p8.composed_prompt("R") == (
        p8._PLANNER_SYSTEM_PROMPT + "\n" + p8.REPORT_BOUNDARY_INSTRUCTION
    )
    assert p8.composed_prompt("C") == (
        p8._PLANNER_SYSTEM_PROMPT + "\n" + p8.SECTION_COMPOSITION_INSTRUCTION
    )
    assert p8.composed_prompt("RC") == p8.p4.composed_prompt("RC")
    assert p8.PROMPT_SHA256 == {
        "P": p8.EXPECTED_BASE_PROMPT_SHA256,
        "R": p8.EXPECTED_R_PROMPT_SHA256,
        "C": p8.EXPECTED_C_PROMPT_SHA256,
        "RC": p8.EXPECTED_RC_PROMPT_SHA256,
    }


@pytest.mark.parametrize("arm", p8.ARMS)
def test_prompt_backend_preserves_non_system_request_fields(arm: p8.Arm) -> None:
    """Prompt substitution does not alter request payload or response model."""
    delegate = Backend()
    wrapper = p8.PromptFactorBackend(delegate=delegate, arm=arm)
    original = StructuredGenerationRequest(
        system_prompt=p8._PLANNER_SYSTEM_PROMPT,
        user_prompt="bounded request",
        timeout_seconds=5.0,
        temperature=0.0,
        max_output_tokens=100,
    )
    asyncio.run(wrapper.generate_structured(original, response_model=SemanticPlan))
    forwarded = delegate.requests[0]
    assert forwarded.user_prompt == original.user_prompt
    assert forwarded.timeout_seconds == original.timeout_seconds
    assert forwarded.temperature == original.temperature
    assert forwarded.max_output_tokens == original.max_output_tokens
    assert forwarded.system_prompt == p8.composed_prompt(arm)
    assert delegate.response_models == [SemanticPlan]


def test_p8_does_not_use_nonempty_report_or_invariant_schema() -> None:
    """Every factor uses the production SemanticPlan response model."""
    assert p8._schema_sha256() == p8.EXPECTED_SCHEMA_SHA256
    assert "NonEmptyReportSemanticPlan" not in p8.canonical_json(p8._frozen_provenance())
    assert "InvariantSemanticPlanner" not in p8.canonical_json(p8._frozen_provenance())


def test_reference_projection_is_unavailable_without_a_plan() -> None:
    """Terminal planner outcomes cannot manufacture semantic reference facts."""
    case = {"expected_sections": [["section.log_plot", "track.reference"]]}
    projection = p8._reference_projection(None, case)
    assert projection["expected_reference_required"] is True
    assert projection["final_plan_available"] is False
    assert projection["unexpected_reference"] is None
    assert projection["missing_required_reference"] is None


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ((False, True, True), "REFERENCE_SECTION_COMPOSITION_SUFFICIENT"),
        ((True, False, True), "REFERENCE_REPORT_BOUNDARY_SUFFICIENT"),
        ((False, False, True), "REFERENCE_RC_INTERACTION_REQUIRED"),
        ((True, True, True), "REFERENCE_MULTIPLE_FACTORS_SUFFICIENT"),
    ],
)
def test_reference_localization_classifies_all_stable_patterns(
    pattern: tuple[bool, bool, bool], expected: str
) -> None:
    """The protected target supports all four frozen reference labels."""
    rows = _synthetic_rows({"P": False, "R": pattern[0], "C": pattern[1], "RC": pattern[2]})
    result = p8._reference_localization(
        rows,
        (),
        {"reference": {"reproduced": True}},
    )
    assert result["classification"] == expected
    assert result["stable"] is True


def test_reference_localization_rejects_unstable_factor() -> None:
    """Attempt disagreement is not interpreted as a stable reference effect."""
    rows = _synthetic_rows({"P": False, "R": False, "C": True, "RC": True})
    rows[1]["arms"]["C"]["reference"]["unexpected_reference"] = False
    result = p8._reference_localization(
        rows,
        (),
        {"reference": {"reproduced": True}},
    )
    assert result["classification"] == "REFERENCE_FACTOR_UNSTABLE"


def test_reference_localization_is_inconclusive_when_its_anchors_drift() -> None:
    """Reference localization is gated only by its own historical anchors."""
    rows = _synthetic_rows({"P": False, "R": False, "C": True, "RC": True})
    result = p8._reference_localization(
        rows,
        (),
        {"reference": {"reproduced": False}},
    )
    assert result["classification"] == "INCONCLUSIVE_REFERENCE_LOCALIZATION"


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ((False, True, True), "SCHEMA_SECTION_COMPOSITION_SUFFICIENT"),
        ((True, False, True), "SCHEMA_REPORT_BOUNDARY_SUFFICIENT"),
        ((False, False, True), "SCHEMA_RC_INTERACTION_REQUIRED"),
        ((True, True, True), "SCHEMA_MULTIPLE_FACTORS_SUFFICIENT"),
    ],
)
def test_schema_localization_classifies_all_stable_patterns(
    pattern: tuple[bool, bool, bool], expected: str
) -> None:
    """The schema targets support all four frozen factor labels."""
    patterns = dict.fromkeys(p8.SCHEMA_TARGETS, pattern)
    result = p8._schema_localization(
        _schema_rows(patterns),
        {"schema": {"reproduced": True}},
    )
    assert result["classification"] == expected
    assert result["stable"] is True


def test_schema_localization_accepts_case_dependent_stabilization() -> None:
    """Different stable patterns are valid case-dependent evidence."""
    case_ids = sorted(p8.SCHEMA_TARGETS)
    patterns = {
        case_ids[0]: (False, True, True),
        case_ids[1]: (True, False, True),
    }
    result = p8._schema_localization(
        _schema_rows(patterns),
        {"schema": {"reproduced": True}},
    )
    assert result["classification"] == "SCHEMA_STABILIZATION_CASE_DEPENDENT"
    assert result["stable"] is True


def test_schema_localization_rejects_unstable_factor() -> None:
    """Attempt disagreement is not interpreted as stable schema evidence."""
    patterns = dict.fromkeys(p8.SCHEMA_TARGETS, (False, True, True))
    rows = _schema_rows(patterns)
    rows[1]["arms"]["C"]["final_plan_available"] = False
    result = p8._schema_localization(rows, {"schema": {"reproduced": True}})
    assert result["classification"] == "SCHEMA_FACTOR_UNSTABLE"
    assert result["stable"] is False


def test_schema_localization_is_inconclusive_when_its_anchors_drift() -> None:
    """Schema localization is gated only by its own historical anchors."""
    patterns = dict.fromkeys(p8.SCHEMA_TARGETS, (False, True, True))
    result = p8._schema_localization(
        _schema_rows(patterns),
        {"schema": {"reproduced": False}},
    )
    assert result["classification"] == "INCONCLUSIVE_SCHEMA_LOCALIZATION"


def test_positive_reference_controls_mark_missing_required_tracks() -> None:
    """Required reference selection is reported separately from over-selection."""
    row = {
        "case_id": "p7-depth-conductivity-06",
        "attempt_index": 0,
        "arms": {arm: {"reference": {"missing_required_reference": arm == "C"}} for arm in p8.ARMS},
    }
    controls = p8.positive_reference_controls([row])
    assert (
        controls["p7-depth-conductivity-06"]["C"]["reference_positive_control_regression"] is True
    )
    assert (
        controls["p7-depth-conductivity-06"]["P"]["reference_positive_control_regression"] is False
    )


def test_decision_accepts_case_dependent_schema_localization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Case-dependent schema evidence remains interpretable and complete."""
    _patch_decision_inputs(
        monkeypatch,
        reference_classification="REFERENCE_MULTIPLE_FACTORS_SUFFICIENT",
        schema_classification="SCHEMA_STABILIZATION_CASE_DEPENDENT",
    )
    result = p8.decision([_decision_row()], ())
    assert result["decision"] == "PROMPT_FACTOR_LOCALIZATION_COMPLETE"


@pytest.mark.parametrize(
    ("reference_reproduced", "schema_reproduced", "expected"),
    [
        (False, True, "PROMPT_FACTOR_LOCALIZATION_PARTIAL"),
        (True, False, "PROMPT_FACTOR_LOCALIZATION_PARTIAL"),
    ],
)
def test_decision_allows_one_localized_axis_when_the_other_anchor_drifts(
    monkeypatch: pytest.MonkeyPatch,
    reference_reproduced: bool,
    schema_reproduced: bool,
    expected: str,
) -> None:
    """One valid mechanism axis is sufficient for a partial result."""
    reference_classification = (
        "REFERENCE_MULTIPLE_FACTORS_SUFFICIENT"
        if reference_reproduced
        else "INCONCLUSIVE_REFERENCE_LOCALIZATION"
    )
    schema_classification = (
        "SCHEMA_MULTIPLE_FACTORS_SUFFICIENT"
        if schema_reproduced
        else "INCONCLUSIVE_SCHEMA_LOCALIZATION"
    )
    _patch_decision_inputs(
        monkeypatch,
        reference_classification=reference_classification,
        schema_classification=schema_classification,
        reference_reproduced=reference_reproduced,
        schema_reproduced=schema_reproduced,
    )
    result = p8.decision([_decision_row()], ())
    assert result["decision"] == expected


@pytest.mark.parametrize(
    ("row", "population_complete", "expected"),
    [
        (
            _decision_row(),
            False,
            "INCONCLUSIVE_PROMPT_FACTOR_LOCALIZATION",
        ),
        (
            _decision_row(infrastructure_failure=True),
            True,
            "INCONCLUSIVE_PROMPT_FACTOR_LOCALIZATION",
        ),
        (
            _decision_row(program_calls=1),
            True,
            "INCONCLUSIVE_PROMPT_FACTOR_LOCALIZATION",
        ),
    ],
)
def test_decision_fails_closed_for_population_infrastructure_or_worker_corruption(
    monkeypatch: pytest.MonkeyPatch,
    row: dict[str, object],
    population_complete: bool,
    expected: str,
) -> None:
    """Global integrity failures cannot yield a localization decision."""
    _patch_decision_inputs(
        monkeypatch,
        reference_classification="REFERENCE_MULTIPLE_FACTORS_SUFFICIENT",
        schema_classification="SCHEMA_MULTIPLE_FACTORS_SUFFICIENT",
        population_complete=population_complete,
        population_reasons=["synthetic_corruption"] if not population_complete else [],
    )
    result = p8.decision([row], ())
    assert result["decision"] == expected


def test_population_integrity_rejects_worker_program_calls() -> None:
    """The P8 population cannot contain worker/program execution."""
    case = p8.load_manifest()[0]
    row = {
        "case_id": case["case_id"],
        "attempt_index": 0,
        "arms": {
            arm: {
                "program_call_count": 1,
                "prompt_sha256": p8.PROMPT_SHA256[arm],
                "response_schema_sha256": p8.EXPECTED_SCHEMA_SHA256,
            }
            for arm in p8.ARMS
        },
    }
    complete, reasons = p8.population_integrity([row], (case,))
    assert complete is False
    assert "worker_program_call" in reasons


def test_live_rejects_nonempty_output_before_provider_construction(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A pre-existing evidence file aborts before checkout/provider work."""
    output = tmp_path / "evidence.jsonl"
    output.write_text("existing\n", encoding="utf-8")
    monkeypatch.setattr(p8, "OUTPUT_PATH", output)
    monkeypatch.setattr(
        p8,
        "_provider_configuration",
        lambda args: pytest.fail("provider constructed before output guard"),
    )
    args = SimpleNamespace(base_url="http://example.invalid", api_key_file=None, api_key_env="KEY")
    with pytest.raises(RuntimeError, match="non-empty evidence path"):
        asyncio.run(p8._run_live(args, p8.BASELINE_SHA))


def test_live_rejects_checkout_drift_before_provider_construction(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Reviewed-checkout failure aborts before provider construction."""
    monkeypatch.setattr(p8, "OUTPUT_PATH", tmp_path / "evidence.jsonl")
    monkeypatch.setattr(
        p8,
        "verify_reviewed_checkout",
        lambda checkpoint: (_ for _ in ()).throw(RuntimeError("synthetic checkout drift")),
    )
    monkeypatch.setattr(
        p8,
        "_provider_configuration",
        lambda args: pytest.fail("provider constructed before checkout guard"),
    )
    args = SimpleNamespace(base_url="http://example.invalid", api_key_file=None, api_key_env="KEY")
    with pytest.raises(RuntimeError, match="synthetic checkout drift"):
        asyncio.run(p8._run_live(args, p8.BASELINE_SHA))


def test_terminal_schema_failure_is_not_infrastructure_failure() -> None:
    """Invalid structured output remains a studied schema outcome."""
    assert (
        p8._provider_classification(
            type("Error", (), {"category": p8.ProviderFailureCategory.INVALID_RESPONSE})()
        )
        == "PLANNER_SCHEMA_FAILURE"
    )


def test_population_and_decision_fail_closed_on_empty_or_wrong_checkpoint() -> None:
    """Incomplete populations cannot yield a localization decision."""
    cases = p8.load_manifest()
    complete, reasons = p8.population_integrity([], cases, expected_checkpoint=p8.BASELINE_SHA)
    assert complete is False
    assert "wrong_row_count" in reasons
    result = p8.decision([], cases, expected_checkpoint=p8.BASELINE_SHA)
    assert result["decision"] == "INCONCLUSIVE_PROMPT_FACTOR_LOCALIZATION"


def test_prelive_report_constructs_no_provider() -> None:
    """The default CLI contract is provider-free and bounded."""
    report = p8.prelive_report()
    assert report["provider_calls"] == 0
    assert report["worker_program_calls"] == 0
    assert report["live_inference"] == "NOT_STARTED"
    assert report["shared_rows"] == 24
