"""Provider-free CM-59A-R2C-A schema-shape diagnostics tests."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ConfigDict, Field, create_model
from scripts import cm57p9_runtime_fingerprint as fingerprint
from scripts import cm59a_r2c_a_schema_validation_shape_diagnostic as r2c

from wellplot.agent.code_mode.planner import SemanticPlan
from wellplot.agent.providers import openai_compat_v2
from wellplot.agent.providers.base import ProviderFailureCategory, StructuredGenerationRequest
from wellplot.agent.providers.openai_compat_v2 import OpenAICompatibleBackendV2
from wellplot.agent.providers.response_diagnostics import (
    ProviderResponseFailureReason,
    StructuredResponseProviderError,
)


class _Plan(BaseModel):
    """Small strict response model for adapter-level shape tests."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)


class _FakeCompletions:
    """Minimal async completion resource with one configured response."""

    def __init__(self, content: object) -> None:
        self.content = content
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> object:
        """Record one request and return it as an SDK-like object."""
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(role="assistant", content=self.content, tool_calls=[]),
                    finish_reason="stop",
                )
            ],
            usage=None,
        )


class _FakeClient:
    """Injected client exposing the fake completion resource."""

    def __init__(self, completions: _FakeCompletions) -> None:
        self.chat = SimpleNamespace(completions=completions)


def _request() -> StructuredGenerationRequest:
    """Build one valid structured provider request."""
    return StructuredGenerationRequest(
        system_prompt="Return one response.",
        user_prompt="Return the requested object.",
        timeout_seconds=5,
    )


def _backend(content: object) -> OpenAICompatibleBackendV2:
    """Build an adapter around one fake response."""
    response_content = json.dumps(content) if isinstance(content, (dict, list)) else content
    return OpenAICompatibleBackendV2(
        model="local-test",
        client=_FakeClient(_FakeCompletions(response_content)),
        structured_output="json_schema",
    )


def _run(content: object, model: type[BaseModel] = _Plan) -> StructuredResponseProviderError:
    """Return the bounded adapter error for one response payload."""
    with pytest.raises(StructuredResponseProviderError) as caught:
        asyncio.run(_backend(content).generate_structured(_request(), response_model=model))
    return caught.value


def test_missing_field_shape_retains_only_declared_location() -> None:
    """A missing declared field is represented without provider payload data."""
    error = _run({})

    assert error.response_reason is ProviderResponseFailureReason.SCHEMA_VALIDATION
    assert error.validation_shape is not None
    assert error.validation_shape.to_json() == {
        "issue_count": 1,
        "issues": [{"error_type": "missing", "location": ["title"]}],
        "truncated": False,
    }
    assert error.diagnostic_metadata() == {"response_reason": "schema_validation"}


def test_extra_field_and_input_value_are_redacted() -> None:
    """Unknown model fields and invalid values never enter shape evidence."""
    error = _run(
        {
            "title": {"secret": "SECRET_PROVIDER_VALUE_91AC"},
            "TOP_SECRET_MODEL_FIELD_7F91": "ignored",
        }
    )
    serialized = json.dumps(error.validation_shape.to_json(), sort_keys=True)

    assert error.validation_shape is not None
    assert "<unknown_field>" in serialized
    assert "TOP_SECRET_MODEL_FIELD_7F91" not in serialized
    assert "SECRET_PROVIDER_VALUE_91AC" not in serialized
    assert "input" not in serialized
    assert "msg" not in serialized


def test_list_index_is_normalized_and_root_location_is_supported() -> None:
    """Indices become stars and model-level locations become $root."""
    item = create_model("Item", title=(str, ...))
    batch = create_model("Batch", items=(list[item], ...))
    error = _run({"items": [{}]}, batch)
    locations = [issue["location"] for issue in error.validation_shape.to_json()["issues"]]

    assert locations == [["items", "*", "title"]]

    root_error = _run({"summary": "only"}, SemanticPlan)
    assert root_error.validation_shape is not None
    assert root_error.validation_shape.to_json()["issues"] == [
        {"error_type": "value_error", "location": ["$root"]}
    ]


def test_validation_shape_is_bounded_and_sorted() -> None:
    """More than sixteen issues are truncated after deterministic sorting."""
    fields = {f"field_{index:02d}": (str, ...) for index in range(17)}
    model = create_model("ManyFields", **fields)
    error = _run({}, model)

    assert error.validation_shape is not None
    assert error.validation_shape.issue_count == 17
    assert len(error.validation_shape.issues) == 16
    assert error.validation_shape.truncated is True
    assert list(error.validation_shape.issues) == sorted(
        error.validation_shape.issues,
        key=lambda issue: (issue.error_type, issue.location),
    )


def test_diagnostic_extraction_failure_preserves_schema_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Telemetry failure cannot change the outward provider classification."""

    def fail_shape(*_args: object) -> None:
        """Force the observational extractor to fail."""
        raise RuntimeError("diagnostic-only failure")

    monkeypatch.setattr(openai_compat_v2, "schema_validation_shape", fail_shape)
    error = _run({})

    assert error.category is ProviderFailureCategory.INVALID_RESPONSE
    assert error.response_reason is ProviderResponseFailureReason.SCHEMA_VALIDATION
    assert error.validation_shape is None


@pytest.mark.parametrize("content", ["{bad", {"title": "ok"}])
def test_invalid_json_and_valid_structured_output_have_no_shape(content: object) -> None:
    """Shape telemetry is limited to Pydantic schema-validation failures."""
    if isinstance(content, dict):
        result = asyncio.run(
            _backend(content).generate_structured(_request(), response_model=_Plan)
        )
        assert result.value.title == "ok"
        return
    error = _run(content)
    assert error.response_reason is ProviderResponseFailureReason.INVALID_JSON
    assert error.validation_shape is None


def _endpoint_pair() -> tuple[dict[str, object], dict[str, object]]:
    """Build equal valid endpoint fixtures without network access."""
    payload = {"data": [{"id": r2c.FROZEN_MODEL, "created": 1}]}
    pre = fingerprint.build_endpoint_fingerprint_v2(
        endpoint="http://192.168.2.140:8888/v1",
        model_api_label=r2c.FROZEN_MODEL,
        models_payload=payload,
    )
    return pre, dict(pre)


def _shape(seed: str) -> dict[str, object]:
    """Build one bounded serialized shape for synthetic decision tests."""
    return {
        "issue_count": 1,
        "issues": [{"error_type": "missing", "location": [seed]}],
        "truncated": False,
    }


def _population(
    *,
    kestrel_shapes: tuple[dict[str, object], ...] | None = None,
    xenon_shapes: tuple[dict[str, object], ...] | None = None,
    all_success: bool = False,
    infrastructure: bool = False,
    truncated: bool = False,
    terminal: str | None = None,
) -> tuple[list[dict[str, object]], dict[str, object], dict[str, object]]:
    """Build a complete provider-free four-row diagnostic population."""
    pre, post = _endpoint_pair()
    pre_hash = r2c.sha256_text(r2c.canonical_json(pre))
    cases = {str(case["case_id"]): case for case in r2c.load_target_cases()}
    rows: list[dict[str, object]] = []
    for case_id in r2c.TARGET_CASES:
        shapes = (kestrel_shapes if case_id == r2c.TARGET_CASES[0] else xenon_shapes) or (
            _shape("summary"),
            _shape("summary"),
        )
        for attempt_index in range(2):
            if all_success:
                trace = [
                    {
                        "call_index": 0,
                        "call_kind": "INITIAL",
                        "outcome": "structured_success",
                        "provider_category": None,
                        "response_reason": None,
                        "validation_shape": None,
                    }
                ]
            elif terminal == "invalid_json":
                trace = [
                    {
                        "call_index": 0,
                        "call_kind": "INITIAL",
                        "outcome": "provider_failure",
                        "provider_category": "invalid_response",
                        "response_reason": "invalid_json",
                        "validation_shape": None,
                    },
                    {
                        "call_index": 1,
                        "call_kind": "INVALID_RESPONSE_RETRY",
                        "outcome": "provider_failure",
                        "provider_category": "invalid_response",
                        "response_reason": "invalid_json",
                        "validation_shape": None,
                    },
                ]
            elif terminal == "provider_rejected":
                trace = [
                    {
                        "call_index": 0,
                        "call_kind": "INITIAL",
                        "outcome": "provider_failure",
                        "provider_category": "provider_rejected",
                        "response_reason": None,
                        "validation_shape": None,
                    }
                ]
            elif terminal == "semantic_failure":
                trace = [
                    {
                        "call_index": 0,
                        "call_kind": "INITIAL",
                        "outcome": "structured_success",
                        "provider_category": None,
                        "response_reason": None,
                        "validation_shape": None,
                    },
                    {
                        "call_index": 1,
                        "call_kind": "SEMANTIC_CORRECTION",
                        "outcome": "structured_success",
                        "provider_category": None,
                        "response_reason": None,
                        "validation_shape": None,
                    },
                ]
            elif infrastructure:
                trace = [
                    {
                        "call_index": 0,
                        "call_kind": "INITIAL",
                        "outcome": "provider_failure",
                        "provider_category": "transport",
                        "response_reason": None,
                        "validation_shape": None,
                    }
                ]
            else:
                current_shape = shapes[attempt_index]
                if truncated:
                    current_shape = {
                        "issue_count": r2c.MAX_SCHEMA_VALIDATION_ISSUES + 1,
                        "issues": [
                            {"error_type": "missing", "location": ["summary"]}
                            for _ in range(r2c.MAX_SCHEMA_VALIDATION_ISSUES)
                        ],
                        "truncated": True,
                    }
                trace = [
                    {
                        "call_index": 0,
                        "call_kind": "INITIAL",
                        "outcome": "provider_failure",
                        "provider_category": "invalid_response",
                        "response_reason": "schema_validation",
                        "validation_shape": current_shape,
                    },
                    {
                        "call_index": 1,
                        "call_kind": "SCHEMA_CORRECTION",
                        "outcome": "provider_failure",
                        "provider_category": "invalid_response",
                        "response_reason": "schema_validation",
                        "validation_shape": current_shape,
                    },
                ]
            planner = {
                "provider_calls": len(trace),
                "program_calls": 0,
                "call_trace": trace,
                "provider_infrastructure_failure": infrastructure,
                "final_plan_available": all_success,
                "final_error_type": (
                    None
                    if all_success
                    else "ProviderRequestError"
                    if terminal in {"invalid_json", "provider_rejected"}
                    else "PlannerSemanticFailure"
                    if terminal == "semantic_failure"
                    else "ProviderRequestError"
                ),
                "final_plan_projection": None,
            }
            rows.append(
                {
                    **r2c.frozen_provenance(),
                    "authorized_harness_checkpoint": "a" * 40,
                    "endpoint_pre_fingerprint_sha256": pre_hash,
                    "case_id": case_id,
                    "attempt_index": attempt_index,
                    "request_sha256": r2c.sha256_text(str(cases[case_id]["request"])),
                    "planner": planner,
                    "program_calls": 0,
                }
            )
    return rows, pre, post


def _decision(
    population: tuple[list[dict[str, object]], dict[str, object], dict[str, object]],
) -> str:
    """Evaluate one synthetic population with the frozen checkpoint."""
    rows, pre, post = population
    return r2c.decision(
        rows,
        expected_checkpoint="a" * 40,
        pre_fingerprint=pre,
        post_fingerprint=post,
    )


def test_shared_and_distinct_signature_decisions() -> None:
    """Stable equal and unequal target signatures are distinguished."""
    shared = _population(
        kestrel_shapes=(_shape("summary"), _shape("summary")),
        xenon_shapes=(_shape("summary"), _shape("summary")),
    )
    distinct = _population(
        kestrel_shapes=(_shape("summary"), _shape("summary")),
        xenon_shapes=(_shape("goal"), _shape("goal")),
    )

    assert _decision(shared) == "STABLE_SHARED_VALIDATION_SIGNATURE"
    assert _decision(distinct) == "STABLE_DISTINCT_VALIDATION_SIGNATURES"


def test_variable_signature_decision() -> None:
    """One target varying between attempts is not treated as stable."""
    population = _population(kestrel_shapes=(_shape("summary"), _shape("goal")))

    assert _decision(population) == "VARIABLE_VALIDATION_SIGNATURE"


def test_failures_not_reproduced_decision() -> None:
    """Four successful planner executions are reported as not reproduced."""
    assert _decision(_population(all_success=True)) == "FAILURES_NOT_REPRODUCED"


@pytest.mark.parametrize("terminal", ["invalid_json", "provider_rejected", "semantic_failure"])
def test_non_schema_terminal_outcomes_are_not_success(
    terminal: str,
) -> None:
    """Non-schema terminal outcomes are mixed evidence, not success."""
    assert _decision(_population(terminal=terminal)) == "MIXED_DIAGNOSTIC_OUTCOME"


def test_mixed_success_and_non_schema_terminal_is_not_success() -> None:
    """A successful execution cannot hide a non-schema terminal outcome."""
    rows, pre, post = _population(all_success=True)
    terminal_rows, _, _ = _population(terminal="invalid_json")
    for row, terminal_row in zip(rows[:2], terminal_rows[:2], strict=True):
        row["planner"] = terminal_row["planner"]
    assert (
        r2c.decision(
            rows,
            expected_checkpoint="a" * 40,
            pre_fingerprint=pre,
            post_fingerprint=post,
        )
        == "MIXED_DIAGNOSTIC_OUTCOME"
    )


def _trace_reasons(trace: list[dict[str, object]]) -> list[str]:
    """Validate one synthetic trace without rebuilding a full population."""
    return r2c._call_trace_reasons(
        {
            "provider_calls": len(trace),
            "call_trace": trace,
        }
    )


def test_schema_validation_requires_schema_correction() -> None:
    """A schema failure without its correction call is invalid evidence."""
    trace = _population()[0][0]["planner"]["call_trace"][:1]
    assert "schema_correction_missing" in _trace_reasons(trace)


def test_schema_correction_requires_schema_validation_trigger() -> None:
    """Non-schema initial failures cannot be labeled schema corrections."""
    trace = _population(terminal="invalid_json")[0][0]["planner"]["call_trace"]
    trace[1]["call_kind"] = "SCHEMA_CORRECTION"
    assert "schema_correction_trigger_invalid" in _trace_reasons(trace)


def test_invalid_response_retry_requires_non_schema_invalid_response() -> None:
    """Generic invalid-response retry cannot follow schema validation or transport."""
    schema_trace = _population()[0][0]["planner"]["call_trace"]
    schema_trace[1]["call_kind"] = "INVALID_RESPONSE_RETRY"
    reasons = _trace_reasons(schema_trace)
    assert "schema_used_generic_retry" in reasons

    transport_trace = _population(infrastructure=True)[0][0]["planner"]["call_trace"]
    transport_trace.append(
        {
            "call_index": 1,
            "call_kind": "INVALID_RESPONSE_RETRY",
            "outcome": "provider_failure",
            "provider_category": "invalid_response",
            "response_reason": "invalid_json",
            "validation_shape": None,
        }
    )
    assert "invalid_response_retry_trigger_invalid" in _trace_reasons(transport_trace)


def test_semantic_correction_requires_initial_structured_success() -> None:
    """Semantic correction is legal only after an initial structured result."""
    trace = _population()[0][0]["planner"]["call_trace"]
    trace[1]["call_kind"] = "SEMANTIC_CORRECTION"
    assert "semantic_correction_trigger_invalid" in _trace_reasons(trace)


def test_call_indexes_are_contiguous() -> None:
    """Evidence call indexes must match their bounded trace positions."""
    trace = _population()[0][0]["planner"]["call_trace"]
    trace[1]["call_index"] = 3
    assert "call_index_invalid" in _trace_reasons(trace)


def test_mixed_outcome_decision() -> None:
    """One stable schema failure and one stable success are mixed evidence."""
    rows, pre, post = _population()
    for row in rows:
        if row["case_id"] == r2c.TARGET_CASES[1]:
            row["planner"] = {
                "provider_calls": 1,
                "program_calls": 0,
                "call_trace": [
                    {
                        "call_index": 0,
                        "call_kind": "INITIAL",
                        "outcome": "structured_success",
                        "provider_category": None,
                        "response_reason": None,
                        "validation_shape": None,
                    }
                ],
                "provider_infrastructure_failure": False,
                "final_plan_available": True,
                "final_plan_projection": None,
            }
    assert (
        r2c.decision(
            rows,
            expected_checkpoint="a" * 40,
            pre_fingerprint=pre,
            post_fingerprint=post,
        )
        == "MIXED_DIAGNOSTIC_OUTCOME"
    )


def test_instrumentation_gap_and_truncation_decisions() -> None:
    """Missing or truncated shapes dominate structural comparison."""
    rows, pre, post = _population()
    rows[0]["planner"]["call_trace"][0]["validation_shape"] = None
    assert (
        r2c.decision(
            rows,
            expected_checkpoint="a" * 40,
            pre_fingerprint=pre,
            post_fingerprint=post,
        )
        == "DIAGNOSTIC_INSTRUMENTATION_GAP"
    )
    assert _decision(_population(truncated=True)) == "DIAGNOSTIC_INSTRUMENTATION_GAP"


def test_infrastructure_and_endpoint_integrity_are_inconclusive() -> None:
    """Operational failures prevent a diagnostic decision."""
    assert _decision(_population(infrastructure=True)) == "INCONCLUSIVE_DIAGNOSTIC"
    rows, pre, post = _population()
    post = dict(post)
    post["normalized_identity_sha256"] = "f" * 64
    assert (
        r2c.decision(
            rows,
            expected_checkpoint="a" * 40,
            pre_fingerprint=pre,
            post_fingerprint=post,
        )
        == "INCONCLUSIVE_DIAGNOSTIC"
    )


def test_shape_integrity_matches_producer_vocabulary_and_bounds() -> None:
    """Tampered shape fields, types, locations, and counts fail closed."""
    rows, pre, _ = _population()
    shape = rows[0]["planner"]["call_trace"][0]["validation_shape"]
    shape["SECRET"] = "do-not-retain"
    valid, reasons = r2c.population_integrity(
        rows,
        expected_checkpoint="a" * 40,
        pre_fingerprint=pre,
    )
    assert not valid
    assert "validation_shape_fields_invalid" in reasons

    for invalid_type in ("SECRET_ERROR_TYPE", "Missing Field", "<model_generated_error>"):
        rows, pre, _ = _population()
        rows[0]["planner"]["call_trace"][0]["validation_shape"]["issues"][0]["error_type"] = (
            invalid_type
        )
        valid, reasons = r2c.population_integrity(
            rows,
            expected_checkpoint="a" * 40,
            pre_fingerprint=pre,
        )
        assert not valid
        assert "validation_issue_type_invalid" in reasons

    rows, pre, _ = _population()
    rows[0]["planner"]["call_trace"][0]["validation_shape"]["issues"][0]["location"] = [
        "TOP_SECRET_MODEL_FIELD_7F91"
    ]
    valid, reasons = r2c.population_integrity(
        rows,
        expected_checkpoint="a" * 40,
        pre_fingerprint=pre,
    )
    assert not valid
    assert "validation_location_invalid" in reasons

    for shape in (
        {
            "issue_count": 2,
            "issues": [{"error_type": "missing", "location": ["summary"]}],
            "truncated": False,
        },
        {
            "issue_count": 2,
            "issues": [{"error_type": "missing", "location": ["summary"]}],
            "truncated": True,
        },
        {
            "issue_count": r2c.MAX_SCHEMA_VALIDATION_ISSUES,
            "issues": [
                {"error_type": "missing", "location": ["summary"]}
                for _ in range(r2c.MAX_SCHEMA_VALIDATION_ISSUES)
            ],
            "truncated": True,
        },
    ):
        rows, pre, _ = _population()
        rows[0]["planner"]["call_trace"][0]["validation_shape"] = shape
        valid, reasons = r2c.population_integrity(
            rows,
            expected_checkpoint="a" * 40,
            pre_fingerprint=pre,
        )
        assert not valid
        assert "validation_shape_count_invalid" in reasons


def test_truncated_location_requires_final_max_depth_sentinel() -> None:
    """Location truncation is valid only in the producer's exact representation."""
    rows, pre, _ = _population()
    rows[0]["planner"]["call_trace"][0]["validation_shape"]["issues"][0]["location"] = [
        "summary",
        "<truncated>",
    ]
    valid, reasons = r2c.population_integrity(
        rows,
        expected_checkpoint="a" * 40,
        pre_fingerprint=pre,
    )
    assert not valid
    assert "validation_location_truncation_invalid" in reasons

    rows, pre, _ = _population()
    rows[0]["planner"]["call_trace"][0]["validation_shape"]["issues"][0]["location"] = [
        "summary"
    ] * (r2c.MAX_SCHEMA_VALIDATION_LOCATION_DEPTH - 1) + ["<truncated>"]
    valid, reasons = r2c.population_integrity(
        rows,
        expected_checkpoint="a" * 40,
        pre_fingerprint=pre,
    )
    assert valid
    assert "validation_location_truncation_invalid" not in reasons


def test_summary_omits_shapes_when_population_integrity_fails() -> None:
    """Malformed evidence cannot be copied into a fail-closed summary."""
    rows, pre, post = _population()
    rows[0]["planner"]["call_trace"][0]["validation_shape"]["SECRET"] = "TOP_SECRET_MODEL_VALUE"
    summary = r2c.summarize_population(
        rows,
        authorized_checkpoint="a" * 40,
        pre_fingerprint=pre,
        post_fingerprint=post,
    )
    serialized = json.dumps(summary, sort_keys=True)
    assert summary["population_integrity"] is False
    assert summary["Kestrel_initial_validation_shapes"] == []
    assert "TOP_SECRET_MODEL_VALUE" not in serialized


def test_historical_helper_drift_is_rejected_before_live_activity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The imported historical helper is protected by the frozen contract."""
    real_baseline = r2c._baseline_blob

    def drift(path: str) -> bytes:
        if path == "scripts/cm59a_system_reevaluation.py":
            return b"historical-helper-drift"
        return real_baseline(path)

    monkeypatch.setattr(r2c, "_baseline_blob", drift)
    with pytest.raises(RuntimeError, match="scripts/cm59a_system_reevaluation"):
        r2c.verify_frozen_contract()


def test_summary_shape_projection_does_not_alias_evidence() -> None:
    """Projected shape summaries remain independent of raw evidence objects."""
    shape = _shape("summary")
    projected = r2c._safe_shape_projection(shape)

    assert projected == shape
    assert projected is not shape
    assert projected["issues"] is not shape["issues"]
    assert projected["issues"][0] is not shape["issues"][0]
    assert projected["issues"][0]["location"] is not shape["issues"][0]["location"]

    shape["issues"][0]["location"][0] = "goal"
    shape["issues"].append({"error_type": "missing", "location": ["summary"]})

    assert projected == {
        "issue_count": 1,
        "issues": [{"error_type": "missing", "location": ["summary"]}],
        "truncated": False,
    }


def test_artifact_collision_guard_is_fail_closed(tmp_path: Path) -> None:
    """A populated future output path is rejected without deletion."""
    path = tmp_path / "evidence.jsonl"
    path.write_text("existing", encoding="utf-8")

    with pytest.raises(RuntimeError, match="non-empty"):
        r2c._ensure_empty(path)

    assert path.read_text(encoding="utf-8") == "existing"


def test_pre_live_report_is_provider_free() -> None:
    """The default audit reports zero live activity."""
    report = r2c.prelive_report()

    assert report["status"] == "PRELIVE_READY"
    assert report["provider_calls"] == 0
    assert report["endpoint_calls"] == 0
    assert report["worker_program_calls"] == 0


def _live_args(tmp_path: Path) -> SimpleNamespace:
    """Build live arguments with isolated temporary artifact paths."""
    return SimpleNamespace(
        base_url="http://192.168.2.140:8888/v1",
        evidence_path=str(tmp_path / "evidence.jsonl"),
        endpoint_fingerprint_pre=str(tmp_path / "pre.json"),
        endpoint_fingerprint_post=str(tmp_path / "post.json"),
        summary_path=str(tmp_path / "summary.json"),
        api_key_env="TEST_API_KEY",
        api_key_file="unused.key",
    )


def _successful_live_result() -> dict[str, object]:
    """Build one bounded provider-free planner result for orchestration tests."""
    return {
        "provider_calls": 1,
        "program_calls": 0,
        "call_trace": [
            {
                "call_index": 0,
                "call_kind": "INITIAL",
                "outcome": "structured_success",
                "provider_category": None,
                "response_reason": None,
                "validation_shape": None,
            }
        ],
        "initial_plan_available": True,
        "final_plan_available": True,
        "final_plan_projection": None,
        "final_error_type": None,
        "final_error_code": None,
        "provider_infrastructure_failure": False,
    }


def test_live_wiring_passes_credentials_to_pre_and_post_in_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The mocked live path wires credentials without contacting a provider."""
    args = _live_args(tmp_path)
    sentinel = "SECRET_R2CA_KEY_91AC"
    pre, post = _endpoint_pair()
    captures: list[dict[str, object]] = []
    events: list[str] = []
    planner_cases: list[str] = []

    monkeypatch.setattr(r2c, "verify_reviewed_checkout", lambda _checkpoint: None)
    monkeypatch.setattr(r2c, "verify_frozen_contract", lambda: {})
    monkeypatch.setattr(r2c, "_api_key", lambda _args: sentinel)

    def fake_capture(
        *,
        endpoint: str,
        model_api_label: str,
        api_key: str,
        timeout_seconds: float,
    ) -> dict[str, object]:
        assert endpoint == args.base_url
        assert model_api_label == r2c.FROZEN_MODEL
        assert api_key == sentinel
        assert timeout_seconds == 20.0
        captures.append(
            {
                "endpoint": endpoint,
                "model_api_label": model_api_label,
                "api_key": api_key,
                "timeout_seconds": timeout_seconds,
            }
        )
        events.append("PRE" if len(captures) == 1 else "POST")
        return pre if len(captures) == 1 else post

    async def fake_run_execution(
        case: dict[str, object],
        *,
        delegate: object,
        registry: object,
    ) -> dict[str, object]:
        del delegate, registry
        planner_cases.append(str(case["case_id"]))
        events.append(f"planner:{case['case_id']}")
        return _successful_live_result()

    def fake_provider(_args: object) -> object:
        events.append("provider")
        return object()

    monkeypatch.setattr(r2c.fingerprint, "capture_endpoint_fingerprint_v2", fake_capture)
    monkeypatch.setattr(r2c, "_provider_configuration", fake_provider)
    monkeypatch.setattr(r2c, "run_execution", fake_run_execution)

    asyncio.run(r2c._run_live(args, "a" * 40))

    assert len(captures) == 2
    assert events[0] == "PRE"
    assert events[1] == "provider"
    assert events[2:] == [
        "planner:cm59-report-kestrel-04",
        "planner:cm59-report-kestrel-04",
        "planner:cm59-mixed-xenon-21",
        "planner:cm59-mixed-xenon-21",
        "POST",
    ]
    assert planner_cases == [
        "cm59-report-kestrel-04",
        "cm59-report-kestrel-04",
        "cm59-mixed-xenon-21",
        "cm59-mixed-xenon-21",
    ]
    evidence = Path(args.evidence_path).read_text(encoding="utf-8")
    assert len(evidence.splitlines()) == 4
    assert sentinel not in evidence
    assert sentinel not in Path(args.endpoint_fingerprint_pre).read_text(encoding="utf-8")
    assert sentinel not in Path(args.endpoint_fingerprint_post).read_text(encoding="utf-8")
    assert not Path(args.summary_path).exists()


def test_pre_failure_stops_before_provider_or_planner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed PRE fingerprint cannot construct a provider or run a planner."""
    args = _live_args(tmp_path)
    counts = {"capture": 0, "provider": 0, "planner": 0}
    monkeypatch.setattr(r2c, "verify_reviewed_checkout", lambda _checkpoint: None)
    monkeypatch.setattr(r2c, "verify_frozen_contract", lambda: {})
    monkeypatch.setattr(r2c, "_api_key", lambda _args: "secret")

    def fail_capture(**_kwargs: object) -> dict[str, object]:
        counts["capture"] += 1
        raise RuntimeError("preflight failed")

    def unexpected_provider(_args: object) -> object:
        counts["provider"] += 1
        raise AssertionError("provider construction must not occur")

    async def unexpected_planner(*_args: object, **_kwargs: object) -> dict[str, object]:
        counts["planner"] += 1
        raise AssertionError("planner execution must not occur")

    monkeypatch.setattr(r2c.fingerprint, "capture_endpoint_fingerprint_v2", fail_capture)
    monkeypatch.setattr(r2c, "_provider_configuration", unexpected_provider)
    monkeypatch.setattr(r2c, "run_execution", unexpected_planner)

    with pytest.raises(RuntimeError, match="preflight failed"):
        asyncio.run(r2c._run_live(args, "a" * 40))

    assert counts == {"capture": 1, "provider": 0, "planner": 0}
    assert not Path(args.evidence_path).exists()


def test_credential_failure_stops_before_endpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing credentials fail before the PRE endpoint helper is invoked."""
    args = _live_args(tmp_path)
    captures = 0
    monkeypatch.setattr(r2c, "verify_reviewed_checkout", lambda _checkpoint: None)
    monkeypatch.setattr(r2c, "verify_frozen_contract", lambda: {})

    def fail_key(_args: object) -> str:
        raise RuntimeError("credential missing")

    def unexpected_capture(**_kwargs: object) -> dict[str, object]:
        nonlocal captures
        captures += 1
        raise AssertionError("endpoint capture must not occur")

    monkeypatch.setattr(r2c, "_api_key", fail_key)
    monkeypatch.setattr(r2c.fingerprint, "capture_endpoint_fingerprint_v2", unexpected_capture)

    with pytest.raises(RuntimeError, match="credential missing"):
        asyncio.run(r2c._run_live(args, "a" * 40))

    assert captures == 0


def test_live_collision_guard_precedes_credential_and_endpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A populated artifact path rejects the run before any external activity."""
    args = _live_args(tmp_path)
    Path(args.evidence_path).write_text("existing", encoding="utf-8")
    activity = {"key": 0, "capture": 0}
    monkeypatch.setattr(r2c, "verify_reviewed_checkout", lambda _checkpoint: None)
    monkeypatch.setattr(r2c, "verify_frozen_contract", lambda: {})

    def unexpected_key(_args: object) -> str:
        activity["key"] += 1
        raise AssertionError("credential resolution must not occur")

    def unexpected_capture(**_kwargs: object) -> dict[str, object]:
        activity["capture"] += 1
        raise AssertionError("endpoint capture must not occur")

    monkeypatch.setattr(r2c, "_api_key", unexpected_key)
    monkeypatch.setattr(r2c.fingerprint, "capture_endpoint_fingerprint_v2", unexpected_capture)

    with pytest.raises(RuntimeError, match="non-empty"):
        asyncio.run(r2c._run_live(args, "a" * 40))

    assert activity == {"key": 0, "capture": 0}
    assert Path(args.evidence_path).read_text(encoding="utf-8") == "existing"


def test_evidence_serialization_contains_no_raw_provider_values() -> None:
    """Bounded evidence cannot retain model content or exception prose."""
    population = _population()
    serialized = json.dumps(population[0], sort_keys=True)

    assert "SECRET_PROVIDER_VALUE_91AC" not in serialized
    assert "TOP_SECRET_MODEL_FIELD_7F91" not in serialized
    assert "safe_message" not in serialized
    assert "exception" not in serialized
