"""Provider-free tests for the SI-V2.2 qualification harness."""

# Test functions intentionally use pytest's fixture-driven signatures.
# ruff: noqa: ANN001,ANN002,ANN003,ANN201,ANN202,D103

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import BaseModel
from scripts import si_v2_2_model_qualification as qualification

from wellplot.agent.code_mode.semantic_ir_v2 import (
    CurveSemanticIntent,
    FillSemanticIntent,
    SectionSemanticIntentV2,
    SemanticIRV2,
)
from wellplot.agent.providers.base import (
    ModelBackendProtocol,
    ProviderFailureCategory,
    ProviderMetrics,
    ProviderRequestError,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from wellplot.agent.providers.response_diagnostics import (
    ProviderResponseFailureReason,
    StructuredResponseProviderError,
)


class _FakeBackend(ModelBackendProtocol):
    """Return queued values or errors without any network capability."""

    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[StructuredGenerationRequest] = []

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return StructuredGenerationResult(
            value=response_model.model_validate(outcome),
            metrics=ProviderMetrics(input_tokens=1, output_tokens=1, total_tokens=2),
        )

    async def generate_program(self, request: object) -> object:
        raise AssertionError("SI-V2.2 must not call program generation.")


class _CorpusBackend(ModelBackendProtocol):
    """Return the matching frozen gold intent for mocked lifecycle tests."""

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.gold = qualification._load_gold()

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        self.events.append("provider")
        request_payload = json.loads(request.user_prompt)
        case_id = next(
            case["case_id"]
            for case in qualification._load_requests()
            if case["request"] == request_payload["request"]
        )
        value = self.gold[str(case_id)]
        return StructuredGenerationResult(
            value=response_model.model_validate(value.model_dump(mode="json")),
            metrics=ProviderMetrics(input_tokens=1, output_tokens=1, total_tokens=2),
        )

    async def generate_program(self, request: object) -> object:
        raise AssertionError("SI-V2.2 must not call program generation.")


def _case_and_gold(case_id: str = "cm59-single-fig-05") -> tuple[dict[str, object], object]:
    case = next(case for case in qualification._load_requests() if case["case_id"] == case_id)
    gold = qualification._load_gold()[case_id]
    return case, gold


def test_prelive_report_validates_gold_without_provider_or_endpoint(monkeypatch):
    monkeypatch.setattr(
        qualification,
        "_provider_configuration",
        lambda args: pytest.fail("provider construction during prelive"),
    )
    monkeypatch.setattr(
        qualification.fingerprint,
        "capture_endpoint_fingerprint_v2",
        lambda **kwargs: pytest.fail("endpoint access during prelive"),
    )

    report = qualification.prelive_report()

    assert report["status"] == "PRELIVE_READY"
    assert report["cases"] == 24
    assert report["gold"]["exact_signature_matches"] == 24
    assert report["provider_calls"] == 0
    assert report["endpoint_calls"] == 0


def test_provider_prompt_contains_no_case_or_capability_topology():
    case, _ = _case_and_gold()
    payload = qualification._semantic_prompt_payload(str(case["request"]))

    assert case["case_id"] not in payload
    assert not any(
        term in qualification.SEMANTIC_SYSTEM_PROMPT
        for term in qualification.FORBIDDEN_PROMPT_TERMS
    )
    assert "expected_sections" not in payload
    assert "expected_report_capabilities" not in payload


def test_semantic_projection_omits_local_ids_and_preserves_fill_relationship():
    fill_intent = SemanticIRV2(
        summary="synthetic fill",
        sections=(
            SectionSemanticIntentV2(
                kind="log_plot",
                goal="show a filled curve",
                features=(
                    CurveSemanticIntent(kind="curve", semantic_id="first"),
                    FillSemanticIntent(
                        kind="fill",
                        semantic_id="fill",
                        target_semantic_id="first",
                    ),
                ),
            ),
        ),
    )

    projection = qualification.semantic_projection(fill_intent)

    serialized = qualification.canonical_json(projection)
    assert "semantic_id" not in serialized
    assert "target_semantic_id" not in serialized
    assert any(
        feature.get("kind") == "fill"
        for section in projection["sections"]
        for feature in section["features"]
    )


def test_structural_retry_is_single_and_does_not_become_semantic_retry():
    case, gold = _case_and_gold()
    backend = _FakeBackend(
        [
            StructuredResponseProviderError(
                "invalid",
                response_reason=ProviderResponseFailureReason.SCHEMA_VALIDATION,
            ),
            gold.model_dump(mode="json"),
        ]
    )

    result = asyncio.run(qualification.run_execution(case=case, gold_intent=gold, provider=backend))

    assert len(backend.requests) == 2
    assert result["provider_call_count"] == 2
    assert result["structural_retry_used"] is True
    assert result["structural_status"] == "STRUCTURAL_PASS"
    assert result["semantic_status"] == "SEMANTIC_PASS"
    assert all("Correction" not in request.system_prompt for request in backend.requests[:1])


def test_non_invalid_provider_failure_is_terminal_without_retry():
    case, gold = _case_and_gold()
    backend = _FakeBackend([ProviderRequestError(ProviderFailureCategory.TIMEOUT, "timeout")])

    result = asyncio.run(qualification.run_execution(case=case, gold_intent=gold, provider=backend))

    assert len(backend.requests) == 1
    assert result["structural_status"] == "STRUCTURAL_FAIL"
    assert result["infrastructure_status"] == "timeout"


def test_semantic_failure_is_not_upgraded_by_safety_rescue(monkeypatch):
    case, gold = _case_and_gold()
    section = gold.sections[0]
    feature = section.features[0].model_copy(update={"reference": True})
    wrong = gold.model_copy(
        update={"sections": (section.model_copy(update={"features": (feature,)}),)}
    )
    backend = _FakeBackend([wrong.model_dump(mode="json")])
    gold_plan = qualification._build_gold_plan(case)

    class _FakeSafetyResult:
        changed = True
        safe_plan = gold_plan
        actions: tuple[object, ...] = ()

        def evidence(self) -> SimpleNamespace:
            return SimpleNamespace(model_dump=lambda mode: {"changed": True, "actions": []})

    monkeypatch.setattr(qualification, "compile_semantic_ir_v2", lambda *args, **kwargs: gold_plan)
    monkeypatch.setattr(
        qualification, "enforce_capability_safety", lambda **kwargs: _FakeSafetyResult()
    )
    monkeypatch.setattr(
        qualification, "enforce_report_boundary_safety", lambda **kwargs: _FakeSafetyResult()
    )
    monkeypatch.setattr(
        qualification, "enforce_section_leaf_safety", lambda **kwargs: _FakeSafetyResult()
    )

    result = asyncio.run(qualification.run_execution(case=case, gold_intent=gold, provider=backend))

    assert result["semantic_status"] == "SEMANTIC_FAIL"
    assert result["final_system_status"] == "SAFETY_RESCUE"


def test_compiler_and_safety_are_not_called_after_structural_failure(monkeypatch):
    case, gold = _case_and_gold()
    backend = _FakeBackend(
        [
            StructuredResponseProviderError(
                "invalid",
                response_reason=ProviderResponseFailureReason.INVALID_JSON,
            ),
            StructuredResponseProviderError(
                "invalid",
                response_reason=ProviderResponseFailureReason.INVALID_JSON,
            ),
        ]
    )
    compiler_calls = 0
    safety_calls = 0

    def fail_compiler(*args, **kwargs):
        nonlocal compiler_calls
        compiler_calls += 1
        raise AssertionError("compiler called after structural failure")

    def fail_safety(**kwargs):
        nonlocal safety_calls
        safety_calls += 1
        raise AssertionError("CM-58 called after structural failure")

    monkeypatch.setattr(qualification, "compile_semantic_ir_v2", fail_compiler)
    monkeypatch.setattr(qualification, "enforce_capability_safety", fail_safety)

    result = asyncio.run(qualification.run_execution(case=case, gold_intent=gold, provider=backend))

    assert result["structural_status"] == "STRUCTURAL_FAIL"
    assert compiler_calls == 0
    assert safety_calls == 0


def test_decision_hierarchy_distinguishes_provider_semantic_compiler_and_safety():
    base = {
        "integrity_reasons": [],
        "endpoint_drift": [],
        "infrastructure_failures": 0,
        "terminal_structural_failures": 0,
        "compiler_invariant_failures": 0,
        "unstable_cases": 0,
        "stable_semantic_passes": 24,
        "family_stable_passes": dict.fromkeys(qualification.FAMILIES, 4),
        "named_anchor_passes": dict.fromkeys(qualification.NAMED_ANCHORS, 2),
        "safety_regressions": 0,
        "wrong_final_escapes": 0,
        "semantic_pass_compile_failures": 0,
        "semantic_pass_signature_mismatches": 0,
    }

    assert qualification._decision({**base, "terminal_structural_failures": 1}) == (
        "SI_V2_PROVIDER_BOUNDARY_REJECTED"
    )
    assert qualification._decision({**base, "compiler_invariant_failures": 1}) == (
        "SI_V2_COMPILER_REJECTED"
    )
    assert (
        qualification._decision(
            {**base, "semantic_pass_signature_mismatches": 1, "safety_regressions": 1}
        )
        == "SI_V2_COMPILER_REJECTED"
    )
    assert (
        qualification._decision(
            {**base, "semantic_pass_compile_failures": 1, "stable_semantic_passes": 21}
        )
        == "SI_V2_COMPILER_REJECTED"
    )
    assert qualification._decision({**base, "safety_regressions": 1}) == ("SI_V2_SAFETY_REJECTED")
    assert qualification._decision({**base, "stable_semantic_passes": 21}) == (
        "SI_V2_MODEL_SEMANTIC_REJECTED"
    )
    assert qualification._decision(base) == "SI_V2_MODEL_QUALIFIED"


def test_secret_is_not_in_prompt_or_provider_free_projection():
    secret = "sentinel-secret-not-for-evidence"
    payload = qualification._semantic_prompt_payload("Plot the requested curve.")
    assert secret not in payload
    assert secret not in qualification.canonical_json(qualification._provenance())


def test_population_requires_exact_two_attempts_and_worker_zero():
    cases = qualification._load_requests()
    pre = {
        "fingerprint_version": "endpoint-model-v2",
        "endpoint": "http://example.test/v1",
        "model_api_label": qualification.FROZEN_MODEL,
        "available_model_ids": [qualification.FROZEN_MODEL],
        "normalized_identity_sha256": "x",
        "raw_model_catalog_sha256": "y",
        "provenance_scope": "ENDPOINT_MODEL_NORMALIZED",
    }
    rows = []
    expected = qualification._provenance()
    for case in cases:
        for attempt in range(qualification.ATTEMPTS):
            rows.append(
                {
                    **expected,
                    "authorized_checkpoint": qualification.BASELINE_SHA,
                    "endpoint_pre_fingerprint_sha256": qualification.sha256_text(
                        qualification.canonical_json(pre)
                    ),
                    "case_id": case["case_id"],
                    "attempt": attempt,
                    "worker_program_calls": 1,
                    "provider": {"provider_call_count": 1},
                }
            )

    reasons = qualification._population_reasons(
        rows[:-1], cases, pre, pre, qualification.BASELINE_SHA
    )

    assert "row_count" in reasons
    assert "worker_program_calls" in reasons


def test_population_rejects_endpoint_identity_drift_from_frozen_identity():
    cases = qualification._load_requests()
    endpoint = {"normalized_identity_sha256": "0" * 64}
    reasons = qualification._population_reasons(
        [], cases, endpoint, endpoint, qualification.BASELINE_SHA
    )

    assert "pre_expected_endpoint_identity" in reasons
    assert "post_expected_endpoint_identity" in reasons


def test_provider_call_count_uses_readable_evidence_rows():
    rows = [
        {"provider": {"provider_call_count": 2}},
        {"provider": {"provider_call_count": 1}},
        {"provider": {"provider_call_count": "not-a-count"}},
        {"provider": None},
    ]

    assert qualification._provider_call_count(rows) == 3


def test_integrity_summary_records_raw_evidence_hash_and_provider_calls(monkeypatch, tmp_path):
    evidence = tmp_path / "evidence.jsonl"
    pre_path = tmp_path / "pre.json"
    post_path = tmp_path / "post.json"
    evidence.write_text('{"provider":{"provider_call_count":2}}\n', encoding="utf-8")
    pre_path.write_text("{}", encoding="utf-8")
    post_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(qualification, "_verify_live_checkout", lambda checkpoint: None)

    summary = qualification.finalize(
        evidence_path=evidence,
        pre_path=pre_path,
        post_path=post_path,
        authorized_checkpoint="a" * 40,
    )

    assert summary["provider_calls"] == 2
    assert summary["raw_evidence_sha256"] == qualification.artifact_sha256(evidence)


def _live_args(tmp_path):
    return SimpleNamespace(
        base_url="http://example.test/v1",
        api_key_env="TEST_KEY",
        api_key_file=None,
        evidence_path=str(tmp_path / "evidence.jsonl"),
        endpoint_fingerprint_pre=str(tmp_path / "pre.json"),
        endpoint_fingerprint_post=str(tmp_path / "post.json"),
        summary_path=str(tmp_path / "summary.json"),
    )


def test_live_rejects_invalid_pre_before_provider_construction(monkeypatch, tmp_path):
    provider_setups: list[str] = []
    endpoint_payload = {
        "normalized_identity_sha256": qualification.EXPECTED_ENDPOINT_IDENTITY_SHA256
    }

    monkeypatch.setattr(qualification, "_verify_live_checkout", lambda checkpoint: None)
    monkeypatch.setattr(qualification, "_api_key", lambda args: "sentinel")
    monkeypatch.setattr(
        qualification.fingerprint,
        "capture_endpoint_fingerprint_v2",
        lambda **kwargs: endpoint_payload,
    )
    monkeypatch.setattr(
        qualification.fingerprint,
        "validate_endpoint_fingerprint_v2",
        lambda value: (False, ["test_invalid"]),
    )
    monkeypatch.setattr(
        qualification,
        "_provider_configuration",
        lambda args: provider_setups.append("constructed"),
    )

    with pytest.raises(RuntimeError, match="PRE endpoint fingerprint is invalid"):
        asyncio.run(qualification._run_live(_live_args(tmp_path), "a" * 40))

    assert provider_setups == []
    assert Path(tmp_path / "pre.json").exists()
    assert not Path(tmp_path / "post.json").exists()
    assert not Path(tmp_path / "evidence.jsonl").exists()


def test_live_rejects_wrong_pre_identity_before_provider_construction(monkeypatch, tmp_path):
    provider_setups: list[str] = []
    endpoint_payload = {"normalized_identity_sha256": "0" * 64}

    monkeypatch.setattr(qualification, "_verify_live_checkout", lambda checkpoint: None)
    monkeypatch.setattr(qualification, "_api_key", lambda args: "sentinel")
    monkeypatch.setattr(
        qualification.fingerprint,
        "capture_endpoint_fingerprint_v2",
        lambda **kwargs: endpoint_payload,
    )
    monkeypatch.setattr(
        qualification.fingerprint,
        "validate_endpoint_fingerprint_v2",
        lambda value: (True, []),
    )
    monkeypatch.setattr(
        qualification,
        "_provider_configuration",
        lambda args: provider_setups.append("constructed"),
    )

    with pytest.raises(RuntimeError, match="PRE endpoint identity"):
        asyncio.run(qualification._run_live(_live_args(tmp_path), "a" * 40))

    assert provider_setups == []
    assert Path(tmp_path / "pre.json").exists()
    assert not Path(tmp_path / "post.json").exists()
    assert not Path(tmp_path / "evidence.jsonl").exists()


def test_mocked_live_sequence_is_pre_then_48_rows_then_post(monkeypatch, tmp_path):
    events: list[str] = []
    backend = _CorpusBackend(events)
    endpoint_payload = {
        "fingerprint_version": "endpoint-model-v2",
        "endpoint": "http://example.test/v1",
        "model_api_label": qualification.FROZEN_MODEL,
        "available_model_ids": [qualification.FROZEN_MODEL],
        "normalized_identity_sha256": qualification.EXPECTED_ENDPOINT_IDENTITY_SHA256,
        "raw_model_catalog_sha256": "catalog",
        "provenance_scope": "ENDPOINT_MODEL_NORMALIZED",
    }
    endpoint_calls = 0

    def fake_fingerprint(**kwargs: object) -> dict[str, object]:
        nonlocal endpoint_calls
        endpoint_calls += 1
        events.append("pre" if endpoint_calls == 1 else "post")
        return dict(endpoint_payload)

    monkeypatch.setattr(qualification, "_verify_live_checkout", lambda checkpoint: None)
    monkeypatch.setattr(qualification, "_api_key", lambda args: "sentinel")
    monkeypatch.setattr(
        qualification.fingerprint,
        "capture_endpoint_fingerprint_v2",
        fake_fingerprint,
    )
    monkeypatch.setattr(
        qualification.fingerprint,
        "validate_endpoint_fingerprint_v2",
        lambda value: (True, []),
    )
    monkeypatch.setattr(
        qualification,
        "_provider_configuration",
        lambda args: events.append("provider_setup") or backend,
    )

    args = _live_args(tmp_path)
    asyncio.run(qualification._run_live(args, "a" * 40))

    assert len(events) == 51
    assert events[0:2] == ["pre", "provider_setup"]
    assert events[2:-1] == ["provider"] * 48
    assert events[-1] == "post"
    assert len(Path(args.evidence_path).read_text(encoding="utf-8").splitlines()) == 48
