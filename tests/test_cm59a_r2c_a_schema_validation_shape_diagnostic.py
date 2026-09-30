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
) -> tuple[list[dict[str, object]], dict[str, object], dict[str, object]]:
    """Build a complete provider-free four-row diagnostic population."""
    pre, post = _endpoint_pair()
    pre_hash = r2c.sha256_text(r2c.canonical_json(pre))
    cases = {str(case["case_id"]): case for case in r2c.load_target_cases()}
    rows: list[dict[str, object]] = []
    for case_id in r2c.TARGET_CASES:
        shapes = (kestrel_shapes if case_id == r2c.TARGET_CASES[0] else xenon_shapes) or (
            _shape("title"),
            _shape("title"),
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
                    current_shape = {**current_shape, "truncated": True}
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
        kestrel_shapes=(_shape("title"), _shape("title")),
        xenon_shapes=(_shape("title"), _shape("title")),
    )
    distinct = _population(
        kestrel_shapes=(_shape("title"), _shape("title")),
        xenon_shapes=(_shape("summary"), _shape("summary")),
    )

    assert _decision(shared) == "STABLE_SHARED_VALIDATION_SIGNATURE"
    assert _decision(distinct) == "STABLE_DISTINCT_VALIDATION_SIGNATURES"


def test_variable_signature_decision() -> None:
    """One target varying between attempts is not treated as stable."""
    population = _population(kestrel_shapes=(_shape("title"), _shape("summary")))

    assert _decision(population) == "VARIABLE_VALIDATION_SIGNATURE"


def test_failures_not_reproduced_decision() -> None:
    """Four successful planner executions are reported as not reproduced."""
    assert _decision(_population(all_success=True)) == "FAILURES_NOT_REPRODUCED"


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


def test_evidence_serialization_contains_no_raw_provider_values() -> None:
    """Bounded evidence cannot retain model content or exception prose."""
    population = _population()
    serialized = json.dumps(population[0], sort_keys=True)

    assert "SECRET_PROVIDER_VALUE_91AC" not in serialized
    assert "TOP_SECRET_MODEL_FIELD_7F91" not in serialized
    assert "safe_message" not in serialized
    assert "exception" not in serialized
