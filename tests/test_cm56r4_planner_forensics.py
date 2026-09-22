"""Deterministic tests for CM-56R4 planner/provider forensics."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ConfigDict
from scripts.cm56r4_planner_forensics import (
    ForensicCapture,
    _ForensicClient,
    capture_forensic_response,
    classify_reverse_call,
    classify_source_plan,
    derived_call_roles,
)

from wellplot.agent.code_mode.planner import SectionTask, SemanticPlan


def _response(content: object, *, finish_reason: str | None = "stop", **message: object) -> object:
    """Build a minimal SDK-shaped completion for forensic tests."""
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason=finish_reason,
                message=SimpleNamespace(role="assistant", content=content, **message),
            )
        ]
    )


def _plan_payload() -> dict[str, object]:
    """Return one valid planner payload."""
    return {
        "summary": "Create a section.",
        "section_tasks": [
            {
                "goal": "Create the selected section.",
                "capability_ids": ["section.log_plot"],
                "source_hints": ["secondary"],
            }
        ],
    }


def test_proxy_delegates_exact_arguments_and_returns_response_identity() -> None:
    """The proxy forwards exact request arguments and preserves response identity."""

    class Completions:
        def __init__(self) -> None:
            self.arguments: dict[str, object] | None = None
            self.response = _response(json.dumps(_plan_payload()))

        async def create(self, **kwargs: object) -> object:
            self.arguments = kwargs
            return self.response

    completions = Completions()
    client = _ForensicClient(
        SimpleNamespace(chat=SimpleNamespace(completions=completions)),
        ForensicCapture(),
    )
    request = {"model": "test", "messages": [], "temperature": 0.0}
    result = asyncio.run(completions_proxy_call(client, request))
    assert result is completions.response
    assert completions.arguments == request


async def completions_proxy_call(client: _ForensicClient, request: dict[str, object]) -> object:
    """Call the proxy in an async test without adding a runtime dependency."""
    return await client.chat.completions.create(**request)


def test_valid_structured_json_is_recognized_without_raw_content() -> None:
    """A valid response is independently parsed and semantically validated."""
    call = capture_forensic_response(_response(json.dumps(_plan_payload())))
    evidence = call.public(derived_call_role="initial")
    assert call.json_parse_valid is True
    assert call.pydantic_valid is True
    assert call.semantic_plan_valid is True
    assert evidence["content_sha256"]
    assert json.dumps(_plan_payload()) not in json.dumps(evidence)


def test_invalid_json_records_safe_metadata_only() -> None:
    """Malformed JSON records only parse metadata and a content hash."""
    call = capture_forensic_response(_response("not-json"))
    evidence = call.public(derived_call_role="initial")
    assert classify_reverse_call([call]) == "REVERSE_JSON_PARSE_FAILURE"
    assert evidence["json_error_type"] == "JSONDecodeError"
    assert evidence["content_chars"] == 8
    assert "not-json" not in json.dumps(evidence)


def test_schema_error_has_safe_location_and_type_only() -> None:
    """Schema errors expose location/type without provider values."""
    payload = _plan_payload()
    payload["section_tasks"][0]["reverse"] = True  # type: ignore[index]
    call = capture_forensic_response(_response(json.dumps(payload)))
    evidence = call.public(derived_call_role="initial")
    assert classify_reverse_call([call]) == "REVERSE_SCHEMA_VALIDATION_FAILURE"
    assert evidence["pydantic_error_locations"] == [
        {"loc": ["section_tasks", "0", "reverse"], "type": "extra_forbidden"}
    ]
    assert "True" not in json.dumps(evidence)


def test_semantic_capability_failure_is_separate_from_schema_failure() -> None:
    """A schema-valid unknown capability is classified semantically."""
    payload = _plan_payload()
    payload["section_tasks"][0]["capability_ids"] = ["unknown.capability"]  # type: ignore[index]
    call = capture_forensic_response(_response(json.dumps(payload)))
    assert call.pydantic_valid is True
    assert call.semantic_plan_valid is False
    assert call.semantic_error_code == "unknown_capability"
    assert classify_reverse_call([call]) == "REVERSE_SEMANTIC_CAPABILITY_FAILURE"


@pytest.mark.parametrize(
    ("message", "finish_reason", "expected"),
    [
        ({"refusal": "no"}, "stop", "REVERSE_PROVIDER_SHAPE_FAILURE"),
        ({"tool_calls": [{"id": "tool"}]}, "stop", "REVERSE_PROVIDER_SHAPE_FAILURE"),
        ({}, "length", "REVERSE_INCOMPLETE_RESPONSE"),
        ({}, "stop", "REVERSE_INCOMPLETE_RESPONSE"),
    ],
)
def test_shape_and_incomplete_responses_are_classified(
    message: dict[str, object], finish_reason: str, expected: str
) -> None:
    """Refusals, tools, and incomplete content have distinct safe categories."""
    content = None if message else ""
    call = capture_forensic_response(_response(content, finish_reason=finish_reason, **message))
    assert classify_reverse_call([call]) == expected


def test_source_plan_classifications_cover_single_and_duplicate_shapes() -> None:
    """Source classifications distinguish exact, missing, and duplicate shapes."""

    def plan(*hints: tuple[str, ...]) -> SemanticPlan:
        return SemanticPlan(
            summary="summary",
            section_tasks=tuple(
                SectionTask(goal="goal", capability_ids=("section.log_plot",), source_hints=hint)
                for hint in hints
            ),
        )

    assert classify_source_plan(plan(("secondary",))) == "SOURCE_EXACT_SECONDARY"
    assert classify_source_plan(plan(())) == "SOURCE_MISSING_HINT"
    assert classify_source_plan(plan(("primary",))) == "SOURCE_WRONG_PRIMARY"
    assert classify_source_plan(plan(("other",))) == "SOURCE_INVALID_HINT"
    assert classify_source_plan(plan((), ())) == "SOURCE_DUPLICATE_TASKS_NO_HINT"
    assert (
        classify_source_plan(plan(("primary",), ("secondary",)))
        == "SOURCE_DUPLICATE_TASKS_MIXED_HINTS"
    )
    assert (
        classify_source_plan(plan(("secondary",), ("secondary",)))
        == "SOURCE_DUPLICATE_TASKS_SAME_HINT"
    )


def test_call_roles_distinguish_semantic_correction_and_invalid_retry() -> None:
    """Call sequence labels preserve the bounded planner correction distinction."""
    first = ForensicCapture().capture_response(_response(json.dumps({"bad": True})))
    second = ForensicCapture().capture_response(_response(json.dumps(_plan_payload())))
    first.semantic_error_code = "unknown_capability"
    assert derived_call_roles([first, second]) == ("initial", "semantic_correction")
    first.semantic_error_code = None
    assert derived_call_roles([first, second]) == ("initial", "invalid_response_retry")


def test_content_hash_is_deterministic_and_serialized_evidence_has_no_raw_content() -> None:
    """The content hash is stable while raw provider text is not serialized."""
    content = json.dumps(_plan_payload(), sort_keys=True)
    first = capture_forensic_response(_response(content)).public(derived_call_role="initial")
    second = capture_forensic_response(_response(content)).public(derived_call_role="initial")
    assert first["content_sha256"] == second["content_sha256"]
    assert content not in json.dumps(first)


def test_forensic_schema_error_does_not_retain_provider_values() -> None:
    """Sanitized schema evidence excludes arbitrary provider payload values."""

    class StrictModel(BaseModel):
        model_config = ConfigDict(extra="forbid")
        value: int

    call = capture_forensic_response(
        _response(json.dumps({"value": 3, "secret": "provider payload"})),
        response_model=StrictModel,
    )
    evidence = call.public(derived_call_role="initial")
    assert call.pydantic_valid is False
    assert "provider payload" not in json.dumps(evidence)
