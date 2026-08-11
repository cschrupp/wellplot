"""Tests for typed request compilation and bounded intent correction."""

from __future__ import annotations

from functools import partial
from pathlib import Path
from types import SimpleNamespace

import anyio

from wellplot.agent import AuthoringSession
from wellplot.agent.compilation import (
    AuthoringIntentCoverage,
    AuthoringIntentSubmission,
    build_request_manifest,
    validate_intent_coverage,
)
from wellplot.authoring_context import AuthoringContextSnapshot
from wellplot.model.intent import AuthoringDocumentIntent


def test_request_manifest_assigns_stable_items_to_bulleted_requests() -> None:
    """Keep request coverage identifiers stable for one prompt shape."""
    manifest = build_request_manifest(
        """
        Build the supported report.

        Data Sources:
        - main: main.dlis
        - repeat: repeat.dlis

        - Add a VDL array track.
        - Use the explicit blue dashed curve style.
        """
    )

    assert [item.item_id for item in manifest.items] == [
        "request-001",
        "request-002",
        "request-003",
        "request-004",
        "request-005",
        "request-006",
    ]
    assert manifest.items[1].text == "Data Sources:"
    assert manifest.items[2].text == "main: main.dlis"
    assert manifest.items[5].text == "Use the explicit blue dashed curve style."


def test_intent_coverage_reports_missing_and_invalid_items() -> None:
    """Reject a provider submission that cannot account for the full request."""
    manifest = build_request_manifest("- Set the title.\n- Add the CBL track.")
    coverage = [
        AuthoringIntentCoverage(
            request_item_id="request-001",
            status="mapped",
            intent_paths=["title"],
        ),
        AuthoringIntentCoverage(
            request_item_id="request-999",
            status="mapped",
            intent_paths=["sections[main].tracks[cbl]"],
        ),
    ]

    errors = validate_intent_coverage(manifest, coverage)

    assert any("unknown request item" in error for error in errors)
    assert any("Missing coverage" in error for error in errors)


class _CorrectionBackend:
    """Provider double that needs one deterministic coverage correction."""

    provider = "fake"
    model = "fake-model"
    credential_source = "test"

    def __init__(self) -> None:
        self.attempts = 0
        self.initial_user_message = ""

    async def run_authoring(self, **kwargs: object) -> object:
        """Submit an invalid first coverage report and a valid correction."""
        self.initial_user_message = str(kwargs["initial_user_message"])
        tool_caller = kwargs["tool_caller"]
        assert callable(tool_caller)
        self.attempts += 1
        first = await tool_caller(
            "submit_authoring_intent",
            {
                "intent": {"title": "Revised"},
                "coverage": [],
            },
        )
        assert first["is_error"] is True
        self.attempts += 1
        second = await tool_caller(
            "submit_authoring_intent",
            {
                "intent": {"title": "Revised"},
                "coverage": [
                    {
                        "request_item_id": "request-001",
                        "status": "mapped",
                        "intent_paths": ["title"],
                    }
                ],
            },
        )
        assert second["accepted"] is True
        return SimpleNamespace(final_text="Compiled typed intent.", tool_trace=())


class _NoToolBackend:
    """Provider double that returns prose without submitting the typed tool."""

    provider = "fake"
    model = "fake-model"
    credential_source = "test"

    async def run_authoring(self, **_: object) -> object:
        """Return a normal prose response with no tool call."""
        return SimpleNamespace(
            final_text=(
                "I can describe the requested changes, but I will not call a tool. "
                "Token sk-testtoken123456 was not used."
            ),
            tool_trace=(),
            report_facts={
                "provider_response": {
                    "adapter": "fixture",
                    "finish_reasons": ["stop"],
                }
            },
        )


class _InvalidSubmissionBackend:
    """Provider double that submits malformed typed arguments."""

    provider = "fake"
    model = "fake-model"
    credential_source = "test"

    async def run_authoring(self, **kwargs: object) -> object:
        """Submit one invalid intent and stop."""
        tool_caller = kwargs["tool_caller"]
        assert callable(tool_caller)
        response = await tool_caller(
            "submit_authoring_intent",
            {"intent": {"unexpected": True}, "coverage": []},
        )
        assert response["is_error"] is True
        return SimpleNamespace(final_text="The typed submission was rejected.", tool_trace=())


class _CoverageFailureBackend:
    """Provider double that submits typed data without complete coverage."""

    provider = "fake"
    model = "fake-model"
    credential_source = "test"

    async def run_authoring(self, **kwargs: object) -> object:
        """Submit an intent that omits one request item from coverage."""
        tool_caller = kwargs["tool_caller"]
        assert callable(tool_caller)
        response = await tool_caller(
            "submit_authoring_intent",
            {
                "intent": {"title": "Revised"},
                "coverage": [
                    {
                        "request_item_id": "request-001",
                        "status": "mapped",
                        "intent_paths": ["title"],
                    }
                ],
            },
        )
        assert response["is_error"] is True
        return SimpleNamespace(final_text="Coverage was incomplete.", tool_trace=())


class _RoundBudgetBackend:
    """Provider double that exhausts extraction rounds before submission."""

    provider = "fake"
    model = "fake-model"
    credential_source = "test"

    async def run_authoring(self, **_: object) -> object:
        """Raise the adapter's conventional round-budget error."""
        raise RuntimeError("The OpenAI-compatible authoring loop exceeded 3 rounds.")


def test_desired_state_extraction_allows_one_coverage_correction() -> None:
    """Accept a corrected submission without exposing mutation tools."""
    backend = _CorrectionBackend()
    session = AuthoringSession(backend=backend, runtime=SimpleNamespace(server_root=Path(".")))
    context = AuthoringContextSnapshot(draft_logfile="draft.log.yaml")

    result, intent = anyio.run(
        partial(
            session._extract_desired_state,
            request_text="Set the report title to Revised.",
            draft_logfile="draft.log.yaml",
            existing=SimpleNamespace(model_dump=lambda **_: {}),
            context_snapshot=context,
            max_rounds=12,
        )
    )

    assert backend.attempts == 2
    assert intent is not None
    assert intent.title == "Revised"
    assert result.report_facts["request_coverage"][0]["intent_paths"] == ["title"]
    assert "request_manifest" in backend.initial_user_message
    assert "AuthoringIntentSubmission schema" in backend.initial_user_message


def _extract_with_backend(backend: object, request_text: str = "Set the report title.") -> object:
    """Run extraction against a small provider double."""
    session = AuthoringSession(backend=backend, runtime=SimpleNamespace(server_root=Path(".")))
    context = AuthoringContextSnapshot(draft_logfile="draft.log.yaml")
    return anyio.run(
        partial(
            session._extract_desired_state,
            request_text=request_text,
            draft_logfile="draft.log.yaml",
            existing=SimpleNamespace(model_dump=lambda **_: {}),
            context_snapshot=context,
            max_rounds=3,
        )
    )


def test_extraction_reports_no_tool_call_and_sanitized_provider_text() -> None:
    """Identify a prose-only provider response before any MCP mutation."""
    result, intent = _extract_with_backend(_NoToolBackend())

    assert intent is None
    assert result.report_facts["provider_response"] == {
        "adapter": "fixture",
        "finish_reasons": ["stop"],
    }
    assert result.report_facts["extraction"] == {
        "status": "no_tool_call",
        "submission_attempts": 0,
        "tool_calls_emitted": False,
        "validation_failures": [],
        "coverage_failures": [],
        "provider_text": (
            "I can describe the requested changes, but I will not call a tool. "
            "Token [REDACTED] was not used."
        ),
    }


def test_extraction_reports_schema_validation_failure() -> None:
    """Identify malformed typed arguments separately from a missing tool call."""
    result, intent = _extract_with_backend(_InvalidSubmissionBackend())

    assert intent is None
    assert result.report_facts["extraction"]["status"] == "schema_validation_failed"
    assert result.report_facts["extraction"]["submission_attempts"] == 1
    assert result.report_facts["extraction"]["validation_failures"]


def test_extraction_reports_coverage_failure() -> None:
    """Identify incomplete request accounting after typed validation succeeds."""
    result, intent = _extract_with_backend(
        _CoverageFailureBackend(),
        request_text="- Set the report title.\n- Add a remarks block.",
    )

    assert intent is None
    assert result.report_facts["extraction"]["status"] == "coverage_failed"
    assert result.report_facts["extraction"]["coverage_failures"]


def test_extraction_reports_round_budget_failure() -> None:
    """Convert extraction round exhaustion into structured provider diagnostics."""
    result, intent = _extract_with_backend(_RoundBudgetBackend())

    assert intent is None
    assert result.report_facts["extraction"]["status"] == "round_budget_exhausted"
    assert result.report_facts["provider_error"]


def test_intent_submission_keeps_typed_intent_and_coverage_together() -> None:
    """Keep the provider contract independently validatable."""
    submission = AuthoringIntentSubmission(
        intent=AuthoringDocumentIntent(title="Revised"),
        coverage=[
            {
                "request_item_id": "request-001",
                "status": "mapped",
                "intent_paths": ["title"],
            }
        ],
    )

    assert submission.intent.title == "Revised"
    assert submission.coverage[0].status == "mapped"
