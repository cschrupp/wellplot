"""Provider-free CM-59A-R2A-L1 Xenon diagnostic tests."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from scripts import cm59a_r2a_l1_xenon_diagnostic as l1

from wellplot.agent.code_mode.planner import ReportTask, SectionTask, SemanticPlan
from wellplot.agent.providers.base import (
    ProviderMetrics,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from wellplot.agent.providers.response_diagnostics import (
    ProviderResponseFailureReason,
    StructuredResponseProviderError,
)


def _valid_plan() -> SemanticPlan:
    """Build the frozen Xenon gold as a provider-free SemanticPlan."""
    return SemanticPlan(
        summary="bounded synthetic plan",
        report_task=ReportTask(goal="report note", capability_ids=("report.standard",)),
        section_tasks=(
            SectionTask(
                goal="acoustic image",
                capability_ids=("section.log_plot", "track.array", "binding.raster"),
            ),
        ),
    )


def _invalid(reason: ProviderResponseFailureReason) -> StructuredResponseProviderError:
    """Build one bounded structured-response failure."""
    return StructuredResponseProviderError(
        "secret provider detail should not enter evidence",
        response_reason=reason,
    )


@dataclass
class _SequenceBackend:
    """Return one configured planner result or failure per call."""

    responses: list[object]
    calls: int = 0

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[SemanticPlan],
    ) -> StructuredGenerationResult[SemanticPlan]:
        """Record calls while preserving the production response boundary."""
        del request
        self.calls += 1
        value = self.responses.pop(0)
        if isinstance(value, BaseException):
            raise value
        return StructuredGenerationResult(
            value=response_model.model_validate(value),
            metrics=ProviderMetrics(),
        )

    async def generate_program(self, request: object) -> object:
        """Reject accidental program generation."""
        raise AssertionError(f"unexpected program request: {request!r}")


def _attempt(
    classification: str,
    *,
    reason: str | None = None,
    signature: str | None = None,
) -> dict[str, object]:
    """Build a minimal bounded attempt projection for classifier tests."""
    return {
        "attempt_classification": classification,
        "final_response_reason": reason,
        "terminal_signature": signature or reason or classification,
    }


def _fingerprint(*, created: int = 1) -> dict[str, object]:
    """Build a valid endpoint fingerprint without network access."""
    return l1.fingerprint.build_endpoint_fingerprint_v2(
        endpoint="http://example.test/v1",
        model_api_label=l1.FROZEN_MODEL,
        models_payload={"data": [{"id": l1.FROZEN_MODEL, "created": created}]},
    )


def test_prelive_report_is_provider_and_endpoint_free() -> None:
    """The default audit validates the future contract without live activity."""
    report = l1.prelive_report()

    assert report["status"] == "PRELIVE_READY"
    assert report["target_case"] == l1.TARGET_CASE_ID
    assert report["future_planner_executions"] == 2
    assert report["future_inference_calls_min"] == 2
    assert report["future_inference_calls_max"] == 4
    assert report["provider_calls"] == 0
    assert report["endpoint_calls"] == 0
    assert report["production_delta"] == 0
    assert report["raw_provider_retention"] == 0


def test_frozen_case_and_reason_taxonomy_are_exact() -> None:
    """The target and all nine R2A reasons are checked against frozen values."""
    case = l1._load_target_case()

    assert case["case_id"] == l1.TARGET_CASE_ID
    assert l1.TARGET_REQUEST_SHA256 == (
        "c0f175abcb01eb875126d2bd3a2a8a6cd2efcf2207494419ce27edc82d8802c5"
    )
    assert set(l1.REASONS) == {
        "unusable_choice",
        "missing_message",
        "non_assistant_message",
        "incomplete_output",
        "unexpected_finish_reason",
        "tool_call",
        "missing_content",
        "invalid_json",
        "schema_validation",
    }
    assert len(l1.REASONS) == 9


@pytest.mark.parametrize(
    ("responses", "expected_calls", "expected_classification"),
    [
        ([_valid_plan()], 1, "PLANNER_SUCCESS"),
        (
            [_invalid(ProviderResponseFailureReason.INVALID_JSON), _valid_plan()],
            2,
            "PLANNER_SUCCESS",
        ),
        (
            [
                _invalid(ProviderResponseFailureReason.INVALID_JSON),
                _invalid(ProviderResponseFailureReason.SCHEMA_VALIDATION),
            ],
            2,
            "TERMINAL_INVALID_RESPONSE",
        ),
    ],
)
def test_production_planner_call_budget_is_bounded(
    responses: list[object], expected_calls: int, expected_classification: str
) -> None:
    """Success and invalid-response recovery never exceed two calls."""
    backend = _SequenceBackend(responses=responses)
    result = asyncio.run(
        l1.run_attempt(
            l1._load_target_case(),
            delegate=backend,
            registry=l1.create_builtin_registry(),
            attempt_index=0,
        )
    )

    assert backend.calls == expected_calls
    assert result["planner_call_count"] == expected_calls
    assert result["attempt_classification"] == expected_classification


def test_terminal_reason_uses_second_invalid_response() -> None:
    """The terminal retry reason is recorded while the first remains in trace."""
    backend = _SequenceBackend(
        responses=[
            _invalid(ProviderResponseFailureReason.INVALID_JSON),
            _invalid(ProviderResponseFailureReason.SCHEMA_VALIDATION),
        ]
    )
    result = asyncio.run(
        l1.run_attempt(
            l1._load_target_case(),
            delegate=backend,
            registry=l1.create_builtin_registry(),
            attempt_index=0,
        )
    )

    assert result["final_response_reason"] == "schema_validation"
    assert [call["response_reason"] for call in result["call_trace"]] == [
        "invalid_json",
        "schema_validation",
    ]


@pytest.mark.parametrize(
    ("attempts", "expected"),
    [
        (
            [_attempt("TERMINAL_INVALID_RESPONSE", reason="invalid_json")] * 2,
            "STABLE_INVALID_RESPONSE_REASON",
        ),
        (
            [
                _attempt("TERMINAL_INVALID_RESPONSE", reason="invalid_json"),
                _attempt("TERMINAL_INVALID_RESPONSE", reason="schema_validation"),
            ],
            "VARIABLE_INVALID_RESPONSE_REASON",
        ),
        ([_attempt("PLANNER_SUCCESS")] * 2, "HISTORICAL_FAILURE_NOT_REPRODUCED"),
        (
            [
                _attempt("PLANNER_SUCCESS"),
                _attempt("TERMINAL_INVALID_RESPONSE", reason="invalid_json"),
            ],
            "MIXED_DIAGNOSTIC_OUTCOME",
        ),
        (
            [_attempt("OTHER_PLANNER_TERMINAL", signature="semantic_error")] * 2,
            "OTHER_STABLE_PLANNER_TERMINAL",
        ),
        (
            [_attempt("DIAGNOSTIC_GAP"), _attempt("PLANNER_SUCCESS")],
            "DIAGNOSTIC_INSTRUMENTATION_GAP",
        ),
        (
            [_attempt("INFRA_FAILURE"), _attempt("PLANNER_SUCCESS")],
            "INCONCLUSIVE_DIAGNOSTIC",
        ),
    ],
)
def test_case_decisions_are_bounded(attempts: list[dict[str, object]], expected: str) -> None:
    """Each authorized case-level decision is deterministic and threshold-free."""
    assert l1.classify_attempts(attempts) == expected


def test_wrong_semantic_plan_is_success_not_invalid_response() -> None:
    """A structured but semantically wrong plan remains a planner success."""
    assert l1.classify_attempts([_attempt("PLANNER_SUCCESS")] * 2) == (
        "HISTORICAL_FAILURE_NOT_REPRODUCED"
    )


def test_endpoint_identity_uses_normalized_v2_projection() -> None:
    """Raw catalog variation is descriptive when normalized identity is stable."""
    pre = _fingerprint(created=1)
    post = _fingerprint(created=2)

    equal, reasons = l1._endpoint_status(pre, post)

    assert equal
    assert reasons == []


def test_endpoint_identity_change_is_inconclusive() -> None:
    """A changed normalized endpoint/model identity cannot characterize Xenon."""
    pre = _fingerprint()
    post = l1.fingerprint.build_endpoint_fingerprint_v2(
        endpoint="http://other.test/v1",
        model_api_label=l1.FROZEN_MODEL,
        models_payload={"data": [{"id": l1.FROZEN_MODEL}]},
    )

    equal, reasons = l1._endpoint_status(pre, post)

    assert not equal
    assert "endpoint_endpoint" in reasons


def test_population_integrity_rejects_partial_and_worker_calls() -> None:
    """Incomplete attempts and program calls fail closed before classification."""
    pre = _fingerprint()
    row = {
        **l1.frozen_provenance(),
        "authorized_harness_checkpoint": "a" * 40,
        "pre_endpoint_fingerprint_sha256": l1.sha256_text(l1.canonical_json(pre)),
        "case_id": l1.TARGET_CASE_ID,
        "request_sha256": l1.TARGET_REQUEST_SHA256,
        "attempt_index": 0,
        "attempt": {
            "planner_call_count": 3,
            "program_calls": 1,
            "call_trace": [],
        },
    }

    valid, reasons = l1.population_integrity(
        [row], expected_checkpoint="a" * 40, pre_fingerprint=pre
    )

    assert not valid
    assert {"wrong_row_count", "provider_call_count", "program_calls"}.issubset(reasons)


def test_no_raw_provider_text_enters_attempt_or_summary() -> None:
    """Provider messages and invalid payload details never enter evidence."""
    secret = "SECRET_INVALID_JSON_PAYLOAD"
    backend = _SequenceBackend(
        responses=[
            StructuredResponseProviderError(
                secret,
                response_reason=ProviderResponseFailureReason.INVALID_JSON,
            ),
            StructuredResponseProviderError(
                secret,
                response_reason=ProviderResponseFailureReason.INVALID_JSON,
            ),
        ]
    )
    result = asyncio.run(
        l1.run_attempt(
            l1._load_target_case(),
            delegate=backend,
            registry=l1.create_builtin_registry(),
            attempt_index=0,
        )
    )

    assert secret not in json.dumps(result)


def test_artifact_paths_are_not_overwritten_by_empty_check() -> None:
    """The collision guard permits only absent or zero-length paths."""
    path = Path("/tmp/cm59a-r2a-l1-test-collision.jsonl")
    path.write_text("", encoding="utf-8")
    try:
        l1._ensure_empty(path)
        path.write_text("evidence", encoding="utf-8")
        with pytest.raises(RuntimeError, match="non-empty"):
            l1._ensure_empty(path)
    finally:
        path.unlink(missing_ok=True)
