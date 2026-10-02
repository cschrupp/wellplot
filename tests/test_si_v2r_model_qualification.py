"""Focused provider-free tests for the SI-V2R-LQ0 qualification harness."""

from __future__ import annotations

import asyncio
import json
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
        "named_anchor_attempt_passes": dict.fromkeys(lq.NAMED_ANCHORS, 2),
        "safety_regressions": 0,
        "wrong_final_escapes": 0,
        "reference_metadata_conflicts": 0,
    }

    assert lq._decision(summary) == "SI_V2R_LIVE_INCONCLUSIVE_INFRASTRUCTURE"


def test_required_report_context_must_remain_report_owned() -> None:
    """Report requirements cannot be satisfied by a section or annotation."""
    gold = next(
        intent
        for intent in lq._load_gold().values()
        if intent.report_work is not None and intent.sections
    )
    report = gold.report_work
    assert report is not None
    generated = gold.model_copy(
        update={
            "report_work": report.model_copy(update={"requirements": ()}),
            "sections": (
                gold.sections[0].model_copy(
                    update={
                        "features": (
                            gold.sections[0]
                            .features[0]
                            .model_copy(update={"requirements": report.requirements}),
                            *gold.sections[0].features[1:],
                        )
                    }
                ),
            ),
        }
    )

    preserved, misses = lq._required_context_preservation(generated, gold)

    assert preserved is False
    assert "report_work.requirements[0]" in misses


def test_required_context_allows_harmless_surrounding_prose() -> None:
    """Owned context may be expanded without requiring exact generated wording."""
    gold = next(intent for intent in lq._load_gold().values() if intent.report_work is not None)
    report = gold.report_work
    assert report is not None and report.requirements
    generated = gold.model_copy(
        update={
            "report_work": report.model_copy(
                update={
                    "requirements": (
                        f"Please include the {report.requirements[0]} item in the report.",
                    )
                }
            )
        }
    )

    assert lq._required_context_preservation(generated, gold) == (True, [])


def test_required_feature_context_cannot_move_to_section_or_disappear() -> None:
    """Feature-owned requirements must remain on the corresponding feature."""
    gold = next(
        intent
        for intent in lq._load_gold().values()
        if any(feature.requirements for section in intent.sections for feature in section.features)
    )
    section = gold.sections[0]
    feature_index = next(
        index for index, feature in enumerate(section.features) if feature.requirements
    )
    feature = section.features[feature_index]
    generated_features = list(section.features)
    generated_features[feature_index] = feature.model_copy(update={"requirements": ()})
    generated = gold.model_copy(
        update={
            "sections": (
                section.model_copy(
                    update={
                        "requirements": feature.requirements,
                        "features": tuple(generated_features),
                    }
                ),
                *gold.sections[1:],
            )
        }
    )

    preserved, misses = lq._required_context_preservation(generated, gold)

    assert preserved is False
    assert any("features" in miss and "requirements[0]" in miss for miss in misses)


def test_duplicate_capabilities_are_not_type_equivalent() -> None:
    """Type equivalence must not erase duplicate capability selections."""
    plan = SemanticPlan(
        summary="duplicate",
        section_tasks=(
            SectionTask(
                goal="section",
                capability_ids=("section.log_plot", "section.log_plot"),
            ),
        ),
    )
    expected = {"report": [], "sections": [["section.log_plot"]]}

    assert lq._type_signature(plan) is None
    assert lq._capability_type_equivalent(plan, expected) is False


def _decision_summary(**updates: object) -> dict[str, object]:
    """Build a semantically qualified summary for decision-rule tests."""
    summary: dict[str, object] = {
        "integrity_reasons": [],
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
        "named_anchor_attempt_passes": dict.fromkeys(lq.NAMED_ANCHORS, 2),
        "safety_regressions": 0,
        "wrong_final_escapes": 0,
        "reference_metadata_conflicts": 0,
    }
    summary.update(updates)
    return summary


def test_perfect_summary_qualifies_and_one_anchor_attempt_rejects() -> None:
    """Named anchors are gated by two passing attempts, not one stable case."""
    assert lq._decision(_decision_summary()) == "SI_V2R_MODEL_QUALIFIED"

    failed_anchor = dict.fromkeys(lq.NAMED_ANCHORS, 2)
    failed_anchor["fig"] = 1
    assert (
        lq._decision(_decision_summary(named_anchor_attempt_passes=failed_anchor))
        == "SI_V2R_MODEL_SEMANTIC_REJECTED"
    )


def test_partial_infrastructure_population_is_finalizable_without_network(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A flushed infrastructure terminal makes a prefix population inconclusive."""
    monkeypatch.setattr(lq, "_verify_live_checkout", lambda checkpoint: None)
    monkeypatch.setattr(
        lq.fingerprint,
        "capture_endpoint_fingerprint_v2",
        lambda **kwargs: pytest.fail("finalization must not capture an endpoint fingerprint"),
    )
    monkeypatch.setattr(
        lq,
        "_provider_configuration",
        lambda args: pytest.fail("finalization must not construct a provider"),
    )
    monkeypatch.setattr(
        lq.fingerprint,
        "validate_endpoint_fingerprint_v2",
        lambda value: (True, []),
    )
    monkeypatch.setattr(lq.fingerprint, "compare_endpoint_fingerprints_v2", lambda a, b: [])
    checkpoint = "a" * 40
    pre = {"normalized_identity_sha256": lq.EXPECTED_ENDPOINT_IDENTITY_SHA256}
    post = dict(pre)
    row = {
        **lq._provenance(),
        "authorized_checkpoint": checkpoint,
        "endpoint_pre_fingerprint_sha256": lq.sha256_text(lq.canonical_json(pre)),
        "case_id": "cm59-report-cascade-01",
        "family": "REPORT_ONLY",
        "attempt": 0,
        "provider": {
            "provider_call_count": 1,
            "infrastructure_status": "transport",
            "structural_status": "STRUCTURAL_FAIL",
        },
        "worker_program_calls": 0,
    }
    evidence = tmp_path / "evidence.jsonl"
    pre_path = tmp_path / "pre.json"
    post_path = tmp_path / "post.json"
    evidence.write_text(json.dumps(row) + "\n", encoding="utf-8")
    pre_path.write_text(json.dumps(pre) + "\n", encoding="utf-8")
    post_path.write_text(json.dumps(post) + "\n", encoding="utf-8")

    summary = lq.finalize(
        evidence_path=evidence,
        pre_path=pre_path,
        post_path=post_path,
        authorized_checkpoint=checkpoint,
    )

    assert summary["rows_completed"] == 1
    assert summary["infrastructure_failures"] == 1
    assert summary["decision"] == "SI_V2R_LIVE_INCONCLUSIVE_INFRASTRUCTURE"


def test_live_collision_rejected_before_pre_capture(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A reused evidence file fails before any endpoint access."""
    args = _live_args(tmp_path)
    Path(args.evidence_path).write_text("existing\n", encoding="utf-8")
    monkeypatch.setattr(lq, "_verify_live_checkout", lambda checkpoint: None)
    monkeypatch.setattr(
        lq.fingerprint,
        "capture_endpoint_fingerprint_v2",
        lambda **kwargs: pytest.fail("endpoint accessed after artifact collision"),
    )

    with pytest.raises(RuntimeError, match="non-empty"):
        asyncio.run(lq._run_live(args, "a" * 40))


def test_wrong_pre_identity_rejected_before_provider_construction(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A wrong PRE endpoint identity cannot reach provider construction."""
    args = _live_args(tmp_path)
    monkeypatch.setattr(lq, "_verify_live_checkout", lambda checkpoint: None)
    monkeypatch.setattr(
        lq,
        "_load_requests",
        lambda: ({"case_id": "case-a", "family": "REPORT_ONLY", "request": "a"},),
    )
    monkeypatch.setattr(lq, "_load_gold", lambda: {"case-a": object()})
    monkeypatch.setattr(lq, "_api_key", lambda args: "secret")
    monkeypatch.setattr(
        lq.fingerprint,
        "capture_endpoint_fingerprint_v2",
        lambda **kwargs: {"normalized_identity_sha256": "wrong"},
    )
    monkeypatch.setattr(
        lq.fingerprint,
        "validate_endpoint_fingerprint_v2",
        lambda value: (True, []),
    )
    monkeypatch.setattr(
        lq,
        "_provider_configuration",
        lambda args: pytest.fail("provider constructed for wrong PRE identity"),
    )

    with pytest.raises(RuntimeError, match="does not match"):
        asyncio.run(lq._run_live(args, "a" * 40))


def _live_args(tmp_path: Path) -> SimpleNamespace:
    """Build isolated live arguments for lifecycle tests."""
    return SimpleNamespace(
        evidence_path=str(tmp_path / "evidence.jsonl"),
        endpoint_fingerprint_pre=str(tmp_path / "pre.json"),
        endpoint_fingerprint_post=str(tmp_path / "post.json"),
        summary_path=str(tmp_path / "summary.json"),
        base_url="http://endpoint/v1",
        api_key_env="TEST_KEY",
        api_key_file=None,
    )


def test_live_lifecycle_captures_post_after_success_and_infra_stop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The live lifecycle flushes rows and captures POST after an infra terminal."""
    events: list[str] = []
    cases = (
        {"case_id": "case-a", "family": "REPORT_ONLY", "request": "a"},
        {"case_id": "case-b", "family": "REPORT_ONLY", "request": "b"},
    )
    gold = {case["case_id"]: object() for case in cases}
    monkeypatch.setattr(lq, "_verify_live_checkout", lambda checkpoint: None)
    monkeypatch.setattr(lq, "_load_requests", lambda: cases)
    monkeypatch.setattr(lq, "_load_gold", lambda: gold)
    monkeypatch.setattr(lq, "_validate_expected_endpoint_fingerprint", lambda value, label: None)
    monkeypatch.setattr(lq, "_api_key", lambda args: "secret")

    def capture(
        *, endpoint: str, model_api_label: str, api_key: str, timeout_seconds: float
    ) -> dict[str, str]:
        events.append("pre" if "pre" not in events else "post")
        return {"normalized_identity_sha256": lq.EXPECTED_ENDPOINT_IDENTITY_SHA256}

    monkeypatch.setattr(lq.fingerprint, "capture_endpoint_fingerprint_v2", capture)
    monkeypatch.setattr(lq, "_provider_configuration", lambda args: events.append("provider"))
    call_count = 0

    async def fake_run_execution(
        *, case: object, gold_intent: object, provider: object
    ) -> dict[str, object]:
        nonlocal call_count
        call_count += 1
        events.append(f"execution-{call_count}")
        return {
            "provider_call_count": 1,
            "infrastructure_status": "transport" if call_count == 2 else None,
        }

    monkeypatch.setattr(lq, "run_execution", fake_run_execution)
    args = _live_args(tmp_path)

    asyncio.run(lq._run_live(args, "a" * 40))

    assert call_count == 2
    assert events == ["pre", "provider", "execution-1", "execution-2", "post"]
    assert len(lq._load_jsonl(Path(args.evidence_path))) == 2


def test_live_lifecycle_captures_post_when_execution_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Unexpected execution errors still trigger POST fingerprint capture."""
    events: list[str] = []
    monkeypatch.setattr(lq, "_verify_live_checkout", lambda checkpoint: None)
    monkeypatch.setattr(
        lq,
        "_load_requests",
        lambda: ({"case_id": "case-a", "family": "REPORT_ONLY", "request": "a"},),
    )
    monkeypatch.setattr(lq, "_load_gold", lambda: {"case-a": object()})
    monkeypatch.setattr(lq, "_validate_expected_endpoint_fingerprint", lambda value, label: None)
    monkeypatch.setattr(lq, "_api_key", lambda args: "secret")

    def capture(
        *, endpoint: str, model_api_label: str, api_key: str, timeout_seconds: float
    ) -> dict[str, str]:
        events.append("fingerprint")
        return {"normalized_identity_sha256": lq.EXPECTED_ENDPOINT_IDENTITY_SHA256}

    monkeypatch.setattr(lq.fingerprint, "capture_endpoint_fingerprint_v2", capture)
    monkeypatch.setattr(lq, "_provider_configuration", lambda args: object())

    async def fail_run_execution(
        *, case: object, gold_intent: object, provider: object
    ) -> dict[str, object]:
        raise RuntimeError("unexpected execution failure")

    monkeypatch.setattr(lq, "run_execution", fail_run_execution)

    with pytest.raises(RuntimeError, match="unexpected"):
        asyncio.run(lq._run_live(_live_args(tmp_path), "a" * 40))

    assert events == ["fingerprint", "fingerprint"]


def test_provider_payload_contains_no_case_gold_or_secret() -> None:
    """The provider payload is request-only and does not carry grader data."""
    secret = "sentinel-secret-not-for-provider"
    payload = lq._semantic_prompt_payload(f"Plot this; {secret}")
    value = json.loads(payload)

    assert set(value) == {"request", "mode", "current_document_summary"}
    assert value["current_document_summary"] == {}
    assert "expected_report_capabilities" not in payload
    assert "expected_sections" not in payload
    assert "case_id" not in payload
    assert "family" not in payload
    assert value["request"].endswith(secret)
    assert payload.count(secret) == 1


def _load_case(case_id: str) -> dict[str, object]:
    """Load one frozen request case for provider-free unit tests."""
    return next(case for case in lq._load_requests() if case["case_id"] == case_id)
