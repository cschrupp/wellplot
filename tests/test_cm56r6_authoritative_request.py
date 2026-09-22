"""Deterministic CM-56R6 authoritative-request and forensic tests."""

from __future__ import annotations

import json

import pytest
from scripts.cm56_typed_section_shadow import (
    _document,
    build_fixture_enricher,
    build_source_candidates,
    load_case_definitions,
)
from scripts.cm56r4_planner_forensics import ForensicCall
from scripts.cm56r6_authoritative_request import (
    AUTHORITATIVE_FIELD,
    AUTHORITATIVE_REQUEST_SYSTEM_PROMPT,
    build_authoritative_worker_input,
    classify_repeated_channel_calls,
    only_authoritative_field_differs,
)

from wellplot.agent.code_mode.planner import SectionTask, SemanticPlan
from wellplot.agent.code_mode.typed_section_worker import (
    TYPED_SECTION_SYSTEM_PROMPT,
    build_typed_section_input,
    serialize_typed_section_input,
)
from wellplot.capabilities import create_builtin_registry


def _case(case_id: str) -> dict[str, object]:
    """Load one frozen CM-56 case."""
    return next(case for case in load_case_definitions() if case["case_id"] == case_id)


def _context(case: dict[str, object], task: SectionTask) -> object:
    """Resolve one fixture context through the existing test enricher."""
    return (
        build_fixture_enricher(case)
        .enrich(
            plan=SemanticPlan(summary=task.goal, section_tasks=(task,)),
            document=_document(),
            source_candidates=build_source_candidates(case),
        )
        .sections[0]
    )


def _draft_input(case_id: str = "scalar_linear") -> str:
    """Build one production typed payload without provider calls."""
    case = _case(case_id)
    task = SectionTask(
        goal=str(case["request"]),
        capability_ids=("section.log_plot", "track.normal", "binding.curve"),
        source_hints=("scalar-source",),
        requirements=("linear scale from 0 to 150",),
    )
    context = _context(case, task)
    return serialize_typed_section_input(
        build_typed_section_input(
            task,
            section_context=context,
            registry=create_builtin_registry(),
        )
    )


def test_authoritative_variant_is_exactly_production_input_plus_one_field() -> None:
    """C changes only the explicit authoritative request field."""
    production = _draft_input()
    authoritative = build_authoritative_worker_input(production, "Create Gamma Ray.")
    assert only_authoritative_field_differs(production, authoritative)
    assert json.loads(authoritative)[AUTHORITATIVE_FIELD] == "Create Gamma Ray."


def test_authoritative_request_redacts_posix_and_windows_paths() -> None:
    """The provider-visible authoritative request is path-safe."""
    production = _draft_input()
    request = r"Use /secret/well/input.dlis and C:\\secret\\well\\input.dlis."
    authoritative = build_authoritative_worker_input(production, request)
    serialized = json.dumps(json.loads(authoritative), sort_keys=True)
    assert "/secret/well/input.dlis" not in serialized
    assert r"C:\\secret\\well\\input.dlis" not in serialized
    assert "[redacted-path]" in serialized


def test_authoritative_prompt_defines_request_task_context_ownership() -> None:
    """The diagnostic prompt makes the causal ownership hypothesis explicit."""
    assert TYPED_SECTION_SYSTEM_PROMPT in AUTHORITATIVE_REQUEST_SYSTEM_PROMPT
    assert "authoritative_original_request" in AUTHORITATIVE_REQUEST_SYSTEM_PROMPT
    assert "routing and scope" in AUTHORITATIVE_REQUEST_SYSTEM_PROMPT
    assert "available inputs" in AUTHORITATIVE_REQUEST_SYSTEM_PROMPT
    assert "Do not invent semantics" in AUTHORITATIVE_REQUEST_SYSTEM_PROMPT


def test_authoritative_payload_does_not_use_expected_output_or_provider_fields() -> None:
    """The C payload remains a request-preservation diagnostic, not hidden gold."""
    payload = json.loads(build_authoritative_worker_input(_draft_input(), "Create a section."))
    assert set(payload) == {
        "authoritative_original_request",
        "capabilities",
        "section_task",
        "sources",
    }
    serialized = json.dumps(payload, sort_keys=True)
    assert "expected_sections" not in serialized
    assert "merged_intent" not in serialized
    assert "provider_response" not in serialized
    assert "canonical_path" not in serialized


def test_authoritative_payload_is_deterministic() -> None:
    """Identical production input and request produce identical C payloads."""
    production = _draft_input("reverse_scale")
    first = build_authoritative_worker_input(production, "Preserve the reversed scale.")
    second = build_authoritative_worker_input(production, "Preserve the reversed scale.")
    assert first == second


@pytest.mark.parametrize(
    ("call", "expected"),
    [
        (
            ForensicCall(provider_call_index=1, provider_exception_type="TimeoutError"),
            "PROVIDER_EXCEPTION",
        ),
        (
            ForensicCall(provider_call_index=1, has_refusal=True),
            "PROVIDER_SHAPE_FAILURE",
        ),
        (
            ForensicCall(provider_call_index=1, content_is_string=True, content_chars=0),
            "INCOMPLETE_RESPONSE",
        ),
        (
            ForensicCall(
                provider_call_index=1,
                content_is_string=True,
                content_chars=10,
                json_parse_valid=False,
            ),
            "JSON_PARSE_FAILURE",
        ),
        (
            ForensicCall(
                provider_call_index=1,
                content_is_string=True,
                content_chars=10,
                json_parse_valid=True,
                pydantic_valid=False,
            ),
            "SCHEMA_VALIDATION_FAILURE",
        ),
        (
            ForensicCall(
                provider_call_index=1,
                content_is_string=True,
                content_chars=10,
                json_parse_valid=True,
                pydantic_valid=True,
                semantic_plan_valid=False,
            ),
            "SEMANTIC_PLAN_FAILURE",
        ),
        (
            ForensicCall(
                provider_call_index=1,
                content_is_string=True,
                content_chars=10,
                json_parse_valid=True,
                pydantic_valid=True,
                semantic_plan_valid=True,
            ),
            "PLAN_SUCCESS",
        ),
    ],
)
def test_repeated_channel_forensic_classification(call: ForensicCall, expected: str) -> None:
    """The terminal response class is retained without provider content."""
    assert classify_repeated_channel_calls([call]) == expected


def test_repeated_channel_empty_capture_is_explicit() -> None:
    """A request with no captured response is not mislabeled as invalid JSON."""
    assert classify_repeated_channel_calls([]) == "NO_PROVIDER_RESPONSE"


def test_repeated_channel_schema_evidence_does_not_retain_provider_values() -> None:
    """Forensic classification uses metadata, not raw response text."""
    call = ForensicCall(
        provider_call_index=1,
        content_is_string=True,
        content_chars=32,
        json_parse_valid=True,
        pydantic_valid=False,
        pydantic_error_locations=({"loc": ["section_tasks", "0"], "type": "extra_forbidden"},),
    )
    evidence = call.public(derived_call_role="initial")
    assert "provider secret" not in json.dumps(evidence)
    assert classify_repeated_channel_calls([call]) == "SCHEMA_VALIDATION_FAILURE"
