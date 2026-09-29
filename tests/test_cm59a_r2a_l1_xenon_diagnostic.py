"""Provider-free CM-59A-R2A-L1 Xenon diagnostic tests."""

from __future__ import annotations

import asyncio
import copy
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import NoReturn

import pytest
from scripts import cm59a_r2a_l1_xenon_diagnostic as l1

from wellplot.agent.code_mode.planner import ReportTask, SectionTask, SemanticPlan
from wellplot.agent.providers.base import (
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


def _valid_evidence_attempt() -> dict[str, object]:
    """Build one complete successful attempt projection."""
    return {
        "attempt_index": 0,
        "planner_call_count": 1,
        "invalid_response_retry_used": False,
        "semantic_correction_used": False,
        "final_plan_available": True,
        "final_provider_category": None,
        "final_response_reason": None,
        "provider_infrastructure_failure": False,
        "raw_plan_projection": {"section_capability_signatures": []},
        "raw_work_unit_facts": {},
        "raw_contract_ok": False,
        "attempt_classification": "PLANNER_SUCCESS",
        "terminal_signature": None,
        "call_trace": [
            {
                "call_kind": "INITIAL",
                "outcome": "structured_success",
                "provider_category": None,
                "response_reason": None,
                "metrics": {},
            }
        ],
        "program_calls": 0,
    }


def _valid_rows(
    *,
    checkpoint: str = "a" * 40,
    pre: dict[str, object] | None = None,
) -> list[dict[str, object]]:
    """Build two complete synthetic rows for provider-free finalization tests."""
    pre = pre or _fingerprint()
    pre_sha = l1.sha256_text(l1.canonical_json(pre))
    rows: list[dict[str, object]] = []
    for attempt_index in range(l1.ATTEMPTS):
        attempt = _valid_evidence_attempt()
        attempt["attempt_index"] = attempt_index
        rows.append(
            {
                **l1.frozen_provenance(),
                "authorized_harness_checkpoint": checkpoint,
                "pre_endpoint_fingerprint_sha256": pre_sha,
                "case_id": l1.TARGET_CASE_ID,
                "request_sha256": l1.TARGET_REQUEST_SHA256,
                "attempt_index": attempt_index,
                "attempt": attempt,
            }
        )
    return rows


def _live_args(tmp_path: Path) -> SimpleNamespace:
    """Build guarded live arguments with isolated temporary artifacts."""
    return SimpleNamespace(
        base_url="http://example.test/v1",
        api_key_env="L1_UNUSED_KEY",
        api_key_file=None,
        evidence_path=str(tmp_path / "evidence.jsonl"),
        endpoint_fingerprint_pre=str(tmp_path / "pre.json"),
        endpoint_fingerprint_post=str(tmp_path / "post.json"),
        summary_path=str(tmp_path / "summary.json"),
    )


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


def test_transport_failure_is_one_call_infrastructure_failure() -> None:
    """Transport failures do not enter the invalid-response retry path."""
    backend = _SequenceBackend(
        responses=[ProviderRequestError(ProviderFailureCategory.TRANSPORT, "secret transport")]
    )
    result = asyncio.run(
        l1.run_attempt(
            l1._load_target_case(),
            delegate=backend,
            registry=l1.create_builtin_registry(),
            attempt_index=0,
        )
    )

    assert backend.calls == 1
    assert result["attempt_classification"] == "INFRA_FAILURE"
    assert result["provider_infrastructure_failure"] is True
    assert result["invalid_response_retry_used"] is False


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


@pytest.mark.parametrize(
    ("name", "mutate", "reason"),
    [
        (
            "duplicate attempt",
            lambda rows: rows.__setitem__(1, copy.deepcopy(rows[0])),
            "duplicate_attempt",
        ),
        (
            "out of range attempt",
            lambda rows: rows[0].__setitem__("attempt_index", 2),
            "attempt_index_mismatch",
        ),
        ("wrong case", lambda rows: rows[0].__setitem__("case_id", "other"), "case_id_mismatch"),
        (
            "wrong request",
            lambda rows: rows[0].__setitem__("request_sha256", "0" * 64),
            "request_hash_mismatch",
        ),
        (
            "wrong prompt",
            lambda rows: rows[0].__setitem__("prompt_sha256", "0" * 64),
            "prompt_sha256_mismatch",
        ),
        (
            "wrong schema",
            lambda rows: rows[0].__setitem__("response_schema_sha256", "0" * 64),
            "response_schema_sha256_mismatch",
        ),
        (
            "wrong source summary",
            lambda rows: rows[0].__setitem__("source_summary_sha256", "0" * 64),
            "source_summary_sha256_mismatch",
        ),
        (
            "wrong anchor",
            lambda rows: rows[0].__setitem__("production_anchor_sha", "0" * 40),
            "production_anchor_sha_mismatch",
        ),
        (
            "wrong checkpoint",
            lambda rows: rows[0].__setitem__("authorized_harness_checkpoint", "0" * 40),
            "checkpoint_mismatch",
        ),
        (
            "wrong PRE binding",
            lambda rows: rows[0].__setitem__("pre_endpoint_fingerprint_sha256", "0" * 64),
            "pre_fingerprint_mismatch",
        ),
        (
            "too many calls",
            lambda rows: rows[0]["attempt"].__setitem__(
                "call_trace", rows[0]["attempt"]["call_trace"] * 3
            ),
            "provider_call_count",
        ),
        (
            "program call",
            lambda rows: rows[0]["attempt"].__setitem__("program_calls", 1),
            "program_calls",
        ),
        (
            "invalid call kind",
            lambda rows: rows[0]["attempt"]["call_trace"][0].__setitem__("call_kind", "OTHER"),
            "call_kind_invalid",
        ),
        (
            "invalid call outcome",
            lambda rows: rows[0]["attempt"]["call_trace"][0].__setitem__("outcome", "other"),
            "call_outcome_invalid",
        ),
        (
            "missing invalid reason",
            lambda rows: rows[0]["attempt"]["call_trace"][0].update(
                {"outcome": "structured_output_failure", "provider_category": "invalid_response"}
            ),
            "invalid_response_reason_missing",
        ),
        (
            "unknown reason",
            lambda rows: rows[0]["attempt"]["call_trace"][0].update(
                {
                    "outcome": "structured_output_failure",
                    "provider_category": "invalid_response",
                    "response_reason": "unknown",
                }
            ),
            "response_reason_invalid",
        ),
    ],
)
def test_population_integrity_tamper_matrix(
    name: str, mutate: Callable[[list[dict[str, object]]], None], reason: str
) -> None:
    """Every decision-bearing population mutation fails with a bounded reason."""
    del name
    pre = _fingerprint()
    rows = _valid_rows(pre=pre)
    mutate(rows)

    valid, reasons = l1.population_integrity(
        rows, expected_checkpoint="a" * 40, pre_fingerprint=pre
    )

    assert not valid
    assert reason in reasons


def test_partial_population_finalization_is_inconclusive() -> None:
    """The finalizer, not only the integrity helper, rejects one-row evidence."""
    pre = _fingerprint()
    post = _fingerprint(created=2)
    summary = l1.summarize_population(
        _valid_rows(pre=pre)[:1],
        pre_fingerprint=pre,
        post_fingerprint=post,
        expected_checkpoint="a" * 40,
        evidence_bytes=b"partial",
    )

    assert summary["decision"] == "INCONCLUSIVE_DIAGNOSTIC"
    assert summary["population_integrity"] is False
    assert "wrong_row_count" in summary["population_integrity_reasons"]


def test_diagnostic_gap_is_not_stable_invalid_response() -> None:
    """A final invalid response without a reason becomes an instrumentation gap."""
    pre = _fingerprint()
    rows = _valid_rows(pre=pre)
    for row in rows:
        row["attempt"].update(
            {
                "attempt_classification": "TERMINAL_INVALID_RESPONSE",
                "final_provider_category": "invalid_response",
                "final_response_reason": None,
            }
        )
        row["attempt"]["call_trace"][0].update(
            {
                "outcome": "structured_output_failure",
                "provider_category": "invalid_response",
                "response_reason": "invalid_json",
            }
        )
    summary = l1.summarize_population(
        rows,
        pre_fingerprint=pre,
        post_fingerprint=_fingerprint(created=2),
        expected_checkpoint="a" * 40,
        evidence_bytes=b"gap",
    )

    assert summary["decision"] == "DIAGNOSTIC_INSTRUMENTATION_GAP"


def test_finalization_is_provider_and_endpoint_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Finalization reads preserved artifacts without constructing live objects."""
    pre = _fingerprint()
    post = _fingerprint(created=2)
    rows = _valid_rows(checkpoint=l1.current_checkout_sha(), pre=pre)
    evidence = tmp_path / "evidence.jsonl"
    pre_path = tmp_path / "pre.json"
    post_path = tmp_path / "post.json"
    evidence.write_text("\n".join(l1.canonical_json(row) for row in rows) + "\n", encoding="utf-8")
    pre_path.write_text(l1.canonical_json(pre), encoding="utf-8")
    post_path.write_text(l1.canonical_json(post), encoding="utf-8")
    monkeypatch.setattr(
        l1.fingerprint,
        "capture_endpoint_fingerprint_v2",
        lambda **kwargs: pytest.fail("endpoint capture during finalization"),
    )
    monkeypatch.setattr(
        l1,
        "_provider_configuration",
        lambda args: pytest.fail("provider construction during finalization"),
    )
    monkeypatch.setattr(l1, "_verify_reviewed_checkout", lambda checkpoint: None)

    summary = l1.finalize(
        evidence_path=evidence,
        pre_path=pre_path,
        post_path=post_path,
        authorized_checkpoint=l1.current_checkout_sha(),
    )

    assert summary["decision"] == "HISTORICAL_FAILURE_NOT_REPRODUCED"
    assert summary["provider_call_count"] == 2


def test_final_summary_does_not_retain_provider_error_text() -> None:
    """Final summary serialization contains only bounded reason data."""
    secret = "SECRET_PROVIDER_PAYLOAD"
    pre = _fingerprint()
    backend = _SequenceBackend(
        [
            _invalid(ProviderResponseFailureReason.INVALID_JSON),
            _invalid(ProviderResponseFailureReason.INVALID_JSON),
        ]
    )
    attempt = asyncio.run(
        l1.run_attempt(
            l1._load_target_case(),
            delegate=backend,
            registry=l1.create_builtin_registry(),
            attempt_index=0,
        )
    )
    assert secret not in json.dumps(attempt)
    rows = _valid_rows(pre=pre)
    rows[0]["attempt"] = attempt
    summary = l1.summarize_population(
        rows,
        pre_fingerprint=pre,
        post_fingerprint=_fingerprint(created=2),
        expected_checkpoint="a" * 40,
        evidence_bytes=json.dumps(rows).encode(),
    )

    assert secret not in json.dumps(summary)


@pytest.mark.parametrize(
    "path_name",
    ["evidence_path", "endpoint_fingerprint_pre", "endpoint_fingerprint_post", "summary_path"],
)
def test_live_collision_guard_runs_before_endpoint_or_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, path_name: str
) -> None:
    """Every populated live artifact path aborts before any live activity."""
    args = _live_args(tmp_path)
    Path(getattr(args, path_name)).write_text("existing", encoding="utf-8")
    endpoint_calls = 0
    provider_calls = 0

    def endpoint_failure(**kwargs: object) -> NoReturn:
        nonlocal endpoint_calls
        endpoint_calls += 1
        raise AssertionError("endpoint capture should not run")

    def provider_failure(namespace: object) -> NoReturn:
        nonlocal provider_calls
        provider_calls += 1
        raise AssertionError("provider construction should not run")

    monkeypatch.setattr(l1.fingerprint, "capture_endpoint_fingerprint_v2", endpoint_failure)
    monkeypatch.setattr(l1, "_provider_configuration", provider_failure)
    monkeypatch.setattr(l1, "_verify_reviewed_checkout", lambda checkpoint: None)
    with pytest.raises(RuntimeError, match="non-empty"):
        asyncio.run(l1._run_live(args, l1.current_checkout_sha()))

    assert endpoint_calls == 0
    assert provider_calls == 0


@pytest.mark.parametrize("checkpoint", ["a" * 39, "a" * 40])
def test_live_requires_exact_full_checkpoint_before_activity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, checkpoint: str
) -> None:
    """Wrong or abbreviated checkpoints fail before endpoint/provider access."""
    args = _live_args(tmp_path)
    monkeypatch.setattr(
        l1.fingerprint,
        "capture_endpoint_fingerprint_v2",
        lambda **kwargs: pytest.fail("endpoint capture after checkpoint rejection"),
    )
    monkeypatch.setattr(
        l1,
        "_provider_configuration",
        lambda namespace: pytest.fail("provider construction after checkpoint rejection"),
    )

    with pytest.raises(RuntimeError, match="checkpoint"):
        asyncio.run(l1._run_live(args, checkpoint))


@pytest.mark.parametrize(
    "argv",
    [
        ["--base-url", "http://example.test/v1"],
        ["--authorized-checkpoint", "a" * 40],
        ["--live-authorized", "--authorized-checkpoint", "a" * 40],
        ["--live-authorized", "--base-url", "http://example.test/v1"],
    ],
)
def test_cli_authorization_guards_stop_before_live_activity(argv: list[str]) -> None:
    """Incomplete live CLI authorization cannot reach endpoint construction."""
    with pytest.raises(SystemExit):
        l1.main(argv)


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
