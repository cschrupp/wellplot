"""Deterministic CM-57P8 prompt-factor localization tests."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path

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


def test_reference_localization_classifies_section_factor_pattern() -> None:
    """The protected target uses the frozen A-D reference labels."""
    rows = _synthetic_rows({"P": False, "R": False, "C": True, "RC": True})
    result = p8._reference_localization(rows, (), {"reproduced": True})
    assert result["classification"] == "REFERENCE_SECTION_COMPOSITION_SUFFICIENT"


def test_schema_localization_classifies_section_factor_pattern() -> None:
    """The two schema targets classify structured availability independently."""
    rows = []
    for case_id in sorted(p8.SCHEMA_TARGETS):
        for attempt in range(2):
            arms = {
                arm: {
                    "final_plan_available": arm in {"C", "RC"},
                    "final_classification": "PLANNER_CONTRACT_OK"
                    if arm in {"C", "RC"}
                    else "PLANNER_SCHEMA_FAILURE",
                    "reference": {
                        "expected_reference_required": True,
                        "final_plan_available": arm in {"C", "RC"},
                        "actual_reference_present": None,
                        "unexpected_reference": None,
                        "missing_required_reference": None,
                    },
                }
                for arm in p8.ARMS
            }
            rows.append({"case_id": case_id, "attempt_index": attempt, "arms": arms})
    result = p8._schema_localization(rows, {"reproduced": True})
    assert result["classification"] == "SCHEMA_SECTION_COMPOSITION_SUFFICIENT"


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
