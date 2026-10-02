"""Focused provider-free tests for the SI-V2R-LQ0 qualification harness."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts import si_v2r_model_qualification as lq

from wellplot.agent.code_mode.planner import SectionTask, SemanticPlan
from wellplot.agent.code_mode.semantic_ir_v2r import SemanticIRV2R
from wellplot.agent.providers.response_diagnostics import (
    ProviderResponseFailureReason,
    StructuredResponseProviderError,
)


def _intent(*, reference: dict[str, object] | None = None) -> SemanticIRV2R:
    """Build a small V2R intent for projection tests."""
    return SemanticIRV2R.model_validate(
        {
            "summary": "synthetic semantic request",
            "sections": [
                {
                    "kind": "log_plot",
                    "goal": "show a curve",
                    "features": [
                        {"kind": "curve", "semantic_id": "curve-local"},
                        {
                            "kind": "fill",
                            "semantic_id": "fill-local",
                            "target_semantic_id": "curve-local",
                        },
                    ],
                    "reference_intent": reference,
                }
            ],
        }
    )


def test_prelive_validates_all_gold_without_live_activity(monkeypatch: pytest.MonkeyPatch) -> None:
    """The pre-live report validates the full gold corpus and never constructs a provider."""
    monkeypatch.setattr(
        lq,
        "_provider_configuration",
        lambda args: pytest.fail("provider construction during pre-live"),
    )

    report = lq.prelive_report()

    assert report["status"] == "PRELIVE_READY"
    assert report["gold"]["case_count"] == 24
    assert report["gold"]["compiled"] == 24
    assert report["gold"]["reference_preservation"] == 24
    assert report["provider_calls"] == 0
    assert report["endpoint_calls"] == 0
    assert report["worker_program_calls"] == 0


def test_projection_distinguishes_companion_and_reference_track() -> None:
    """The hard V2R projection keeps the two reference meanings distinct."""
    companion = lq.semantic_projection(_intent(reference={"kind": "companion_depth_lane"}))
    targeted = lq.semantic_projection(
        _intent(reference={"kind": "reference_track", "target_semantic_id": "curve-local"})
    )

    assert companion != targeted
    assert companion["sections"][0]["reference_intent"] == {"kind": "companion_depth_lane"}
    assert targeted["sections"][0]["reference_intent"] == {
        "kind": "reference_track",
        "target_feature_position": 0,
    }


def test_projection_removes_arbitrary_semantic_id_spelling() -> None:
    """Equivalent feature identity handles do not change the semantic projection."""
    first = lq.semantic_projection(_intent())
    renamed = lq.semantic_projection(
        SemanticIRV2R.model_validate(
            {
                "summary": "different prose",
                "sections": [
                    {
                        "kind": "log_plot",
                        "goal": "different prose",
                        "features": [
                            {"kind": "curve", "semantic_id": "x"},
                            {"kind": "fill", "semantic_id": "y", "target_semantic_id": "x"},
                        ],
                    }
                ],
            }
        )
    )

    assert first == renamed


def test_report_work_is_not_section_annotation() -> None:
    """Report ownership is graded independently from section feature kinds."""
    report = SemanticIRV2R.model_validate(
        {"summary": "report", "report_work": {"goal": "write a note"}}
    )
    annotation = SemanticIRV2R.model_validate(
        {
            "summary": "section",
            "sections": [
                {
                    "kind": "log_plot",
                    "goal": "mark the interval",
                    "features": [{"kind": "annotation", "semantic_id": "marker"}],
                }
            ],
        }
    )

    assert lq.semantic_projection(report) != lq.semantic_projection(annotation)
    assert lq.semantic_projection(report)["report_work_present"] is True
    assert lq.semantic_projection(annotation)["report_work_present"] is False


def test_capability_order_only_difference_is_not_type_mismatch() -> None:
    """Capability ordering remains diagnostic rather than semantic equivalence."""
    first = SemanticPlan(
        summary="one",
        section_tasks=(
            SectionTask(goal="section", capability_ids=("section.log_plot", "track.normal")),
        ),
    )
    second = SemanticPlan(
        summary="one",
        section_tasks=(
            SectionTask(goal="section", capability_ids=("track.normal", "section.log_plot")),
        ),
    )

    assert lq._plan_signature(first) != lq._plan_signature(second)
    assert lq._type_signature(first) == lq._type_signature(second)


def test_reference_metadata_conflict_is_detected() -> None:
    """A final plan that drops a preserved reference lane is a conflict."""
    intent = _intent(reference={"kind": "companion_depth_lane"})
    compiled = lq.compile_semantic_ir_v2r(
        intent,
        registry=lq.create_builtin_registry(),
        lowering_registry=lq.create_builtin_semantic_lowering_registry(),
    )
    broken = compiled.semantic_plan.model_copy(
        update={
            "section_tasks": (
                compiled.semantic_plan.section_tasks[0].model_copy(
                    update={"capability_ids": ("section.log_plot", "track.normal", "binding.curve")}
                ),
            )
        }
    )

    assert lq._reference_metadata_consistent(compiled, broken) is False


def test_structural_retry_is_single_and_format_only() -> None:
    """A structured failure allows exactly one generic retry and no semantic retry."""
    gold = next(iter(lq._load_gold().values()))

    class FakeProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def generate_structured(self, request: object, response_model: object) -> object:
            self.calls += 1
            if self.calls == 1:
                raise StructuredResponseProviderError(
                    "invalid structured response",
                    response_reason=ProviderResponseFailureReason.INVALID_JSON,
                )
            return SimpleNamespace(value=gold)

    case = _load_case("cm59-report-cascade-01")
    provider = FakeProvider()
    result = asyncio.run(lq.run_execution(case=case, gold_intent=gold, provider=provider))

    assert provider.calls == 2
    assert result["structural_retry_used"] is True
    assert result["provider_call_count"] == 2
    assert result["structural_status"] == "STRUCTURAL_PASS"


def test_pre_live_contract_does_not_expose_gold_or_case_data() -> None:
    """The provider prompt contains semantic instructions, not benchmark answers."""
    prompt = lq.V2R_SYSTEM_PROMPT + lq.STRUCTURAL_RETRY_PROMPT
    cases = lq._load_requests()

    assert all(str(case["case_id"]) not in prompt for case in cases)
    assert all(
        capability not in prompt
        for case in cases
        for capability in case["expected_report_capabilities"]
    )
    assert all(term not in prompt for term in lq.FORBIDDEN_PROMPT_TERMS)


def test_artifact_collision_guard_rejects_nonempty_path(tmp_path: Path) -> None:
    """Evidence paths cannot be truncated or reused."""
    path = tmp_path / "evidence.jsonl"
    path.write_text("existing\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="non-empty"):
        lq._ensure_empty(path)


def test_wrong_endpoint_identity_fails_closed() -> None:
    """The frozen endpoint identity is required before provider construction."""
    with pytest.raises(RuntimeError, match="invalid|does not match"):
        lq._validate_expected_endpoint_fingerprint(
            {"normalized_identity_sha256": "wrong"}, label="PRE"
        )


def test_decision_precedence_keeps_infrastructure_first() -> None:
    """Integrity failure cannot be reclassified as a model result."""
    summary = {
        "integrity_reasons": ["row_count"],
        "endpoint_drift": [],
        "infrastructure_failures": 0,
        "terminal_structural_failures": 0,
        "compiler_invariant_failures": 0,
        "compiler_reference_preservation_failures": 0,
        "semantic_pass_compiler_failures": 0,
        "semantic_pass_type_mismatches": 0,
        "unstable_cases": 0,
        "stable_semantic_passes": 24,
        "family_stable_passes": dict.fromkeys(lq.FAMILIES, 4),
        "reference_family_stable_passes": 4,
        "named_anchor_passes": dict.fromkeys(lq.NAMED_ANCHORS, 2),
        "safety_regressions": 0,
        "wrong_final_escapes": 0,
        "reference_metadata_conflicts": 0,
    }

    assert lq._decision(summary) == "SI_V2R_LIVE_INCONCLUSIVE_INFRASTRUCTURE"


def _load_case(case_id: str) -> dict[str, object]:
    """Load one frozen request case for provider-free unit tests."""
    return next(case for case in lq._load_requests() if case["case_id"] == case_id)
