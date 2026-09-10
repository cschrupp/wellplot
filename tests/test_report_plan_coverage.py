"""Report workers must cover the planner's explicit stable-slot values."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import Any

from wellplot.agent.core import FunctionToolDefinition, ProviderRunResult
from wellplot.agent.graph.models import ReconstructionPlan
from wellplot.agent.graph.provider_adapter import ExistingProviderStructuredAdapter
from wellplot.agent.graph.report_worker import ReportCompiler
from wellplot.agent.graph.worker_contracts import report_contract
from wellplot.capabilities import create_builtin_registry
from wellplot.model.authoring import AuthoringDocumentSpec


class _Backend:
    def __init__(self, submissions: list[dict[str, Any]]) -> None:
        self.submissions = submissions
        self.replies: list[dict[str, Any]] = []

    async def run_authoring(
        self,
        *,
        instructions: str,
        initial_user_message: str,
        tool_definitions: list[FunctionToolDefinition],
        tool_caller: Callable[[str, dict[str, object]], Awaitable[dict[str, object]]],
        max_rounds: int,
        required_tool_name: str | None = None,
        stream_response: bool = True,
    ) -> ProviderRunResult:
        assert max_rounds == 3
        assert required_tool_name == "submit_report_artifact"
        for submission in self.submissions:
            reply = await tool_caller("submit_report_artifact", submission)
            self.replies.append(reply)
            if reply == {"accepted": True}:
                break
        return ProviderRunResult(final_text="Submitted", tool_trace=())


def _document() -> dict[str, object]:
    return AuthoringDocumentSpec.model_validate(
        {
            "name": "test",
            "header": {
                "general_fields": [
                    {"slot_id": "general.company", "key": "company", "label": "Company"},
                ],
                "service_titles": [{"slot_id": "service_title.1"}],
            },
            "sections": [
                {
                    "id": "main",
                    "title": "Main",
                    "tracks": [
                        {"id": "depth", "title": "Depth", "kind": "reference", "width_mm": 10},
                    ],
                },
            ],
        }
    ).model_dump(mode="json")


def _plan() -> ReconstructionPlan:
    return ReconstructionPlan.model_validate(
        {
            "summary": "Set report fields.",
            "report_values": {
                "header": {
                    "enabled": True,
                    "general_fields": [
                        {"slot_id": "general.company", "value": "University of Utah"},
                    ],
                    "service_titles": [
                        {"slot_id": "service_title.1", "value": "Cement Bond Log"},
                    ],
                },
            },
            "sections": [
                {
                    "section_id": "main",
                    "capability_id": "section.log_plot",
                    "goal": "Keep main section.",
                }
            ],
        }
    )


def test_report_contract_hides_opaque_extensions_in_construction() -> None:
    """Providers cannot echo compatibility data removed from their context."""
    model = report_contract(_document(), reconstruct=True)
    invalid = {"intent": {"header": {"extensions": {}}}}
    try:
        model.model_validate(invalid)
    except ValueError:
        pass
    else:
        raise AssertionError("Construction report contract accepted opaque extensions.")


def test_report_worker_corrects_omitted_planned_header_values() -> None:
    """The report stage rejects a sparse but incomplete CBL header submission."""
    document = _document()
    before = deepcopy(document)
    incomplete = {"intent": {"header": {"enabled": True}}}
    corrected = {
        "intent": {
            "header": {
                "enabled": True,
                "general_fields": [
                    {"slot_id": "general.company", "value": {"value": "University of Utah"}},
                ],
                "service_titles": [
                    {"slot_id": "service_title.1", "value": {"value": "Cement Bond Log"}},
                ],
            },
        },
    }
    backend = _Backend([incomplete, corrected])
    result = asyncio.run(
        ReportCompiler(
            ExistingProviderStructuredAdapter(backend), create_builtin_registry()
        ).compile(
            request="Set report fields.",
            plan=_plan(),
            current_document=document,
            source_manifest={},
        )
    )
    assert backend.replies[0]["is_error"] is True
    assert "general_fields slot 'general.company'" in backend.replies[0]["error"]
    assert "service_titles slot 'service_title.1'" in backend.replies[0]["error"]
    assert backend.replies[1] == {"accepted": True}
    assert result.payload == corrected
    assert document == before
