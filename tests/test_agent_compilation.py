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
