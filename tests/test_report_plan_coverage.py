"""Report workers must cover the planner's explicit stable-slot values."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from wellplot.agent.core import FunctionToolDefinition, ProviderRunResult
from wellplot.agent.execution_trace import AgentRunTrace, bind_agent_trace
from wellplot.agent.graph.models import CompiledArtifact, ReconstructionPlan
from wellplot.agent.graph.provider_adapter import ExistingProviderStructuredAdapter
from wellplot.agent.graph.report_tasks import (
    HEADER_BATCH_SIZE,
    materialize_report_remark_ids,
    report_tasks,
)
from wellplot.agent.graph.report_worker import ReportCompiler
from wellplot.agent.graph.worker_contracts import report_contract
from wellplot.capabilities import create_builtin_registry
from wellplot.model.authoring import AuthoringDocumentSpec


class _Backend:
    def __init__(self, submissions: list[dict[str, Any]]) -> None:
        self.submissions = submissions
        self.replies: list[dict[str, Any]] = []
        self.calls = 0

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
        self.calls += 1
        while self.submissions:
            submission = self.submissions.pop(0)
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
    settings = {"intent": {"header": {"enabled": True}}}
    incomplete = {"intent": {"header": {"general_fields": []}}}
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
    company = {
        "intent": {"header": {"general_fields": corrected["intent"]["header"]["general_fields"]}}
    }
    titles = {
        "intent": {"header": {"service_titles": corrected["intent"]["header"]["service_titles"]}}
    }
    backend = _Backend([settings, incomplete, company, titles])
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
    assert backend.replies[0] == {"accepted": True}
    assert backend.replies[1]["is_error"] is True
    assert "general_fields" in backend.replies[1]["error"]
    assert backend.replies[2:] == [{"accepted": True}, {"accepted": True}]
    assert result.payload == corrected
    assert document == before


def test_report_batches_preserve_all_values_and_reject_other_task_fields() -> None:
    """A long header is assembled completely without rewriting accepted groups."""
    document = _document()
    entries = [{"slot_id": f"general.field_{index}", "value": str(index)} for index in range(27)]
    document["header"]["general_fields"] = [
        {"slot_id": entry["slot_id"], "key": f"field_{index}", "label": f"Field {index}"}
        for index, entry in enumerate(entries)
    ]
    document = AuthoringDocumentSpec.model_validate(document).model_dump(mode="json")
    before = deepcopy(document)
    plan = _plan().model_copy(update={"report_values": {"header": {"general_fields": entries}}})
    tasks = report_tasks(report_contract(document, reconstruct=True), plan.report_values)
    assert len(tasks) == 5
    submissions = [{"intent": {}}]
    for task in tasks[1:]:
        batch = task.values["header"]["general_fields"]
        assert len(batch) <= HEADER_BATCH_SIZE
        submission = {
            "intent": {
                "header": {
                    "general_fields": [
                        {"slot_id": item["slot_id"], "value": {"value": item["value"]}}
                        for item in batch
                    ]
                }
            }
        }
        forbidden = deepcopy(submission)
        forbidden["intent"]["header"]["title"] = "null"
        with pytest.raises(ValueError):
            task.response_model.model_validate(forbidden)
        submissions.append(submission)
    backend = _Backend(submissions)
    result = asyncio.run(
        ReportCompiler(
            ExistingProviderStructuredAdapter(backend), create_builtin_registry()
        ).compile(
            request="Set all 27 header fields.",
            plan=plan,
            current_document=document,
            source_manifest={},
        )
    )
    actual = result.payload["intent"]["header"]["general_fields"]
    assert [(item["slot_id"], item["value"]["value"]) for item in actual] == [
        (item["slot_id"], item["value"]) for item in entries
    ]
    assert backend.calls == 5
    assert document == before


def test_failed_report_task_leaves_document_unchanged() -> None:
    """Accepted settings do not persist when the following header task fails."""
    document = _document()
    before = deepcopy(document)
    backend = _Backend([{"intent": {"header": {"enabled": True}}}])
    with pytest.raises(Exception, match="required|accepted|submit_report_artifact"):
        asyncio.run(
            ReportCompiler(
                ExistingProviderStructuredAdapter(backend), create_builtin_registry()
            ).compile(
                request="Set report fields.",
                plan=_plan(),
                current_document=document,
                source_manifest={},
            )
        )
    assert document == before
    assert backend.calls == 2


def test_report_tasks_do_not_expand_allowed_header_slots() -> None:
    """Planner suggestions cannot introduce IDs absent from the advertised inventory."""
    with pytest.raises(ValueError, match="unknown slots"):
        report_tasks(
            report_contract(_document(), reconstruct=True),
            {"header": {"general_fields": [{"slot_id": "invented", "value": "x"}]}},
        )


def test_report_remarks_are_individual_ordered_and_traced(tmp_path: Path) -> None:
    """Each remark keeps its body and ordered position in the combined report."""
    document = _document()
    remarks = [
        {"remark_id": f"remark-{index}", "title": f"Notice {index}", "lines": [f"Body {index}"]}
        for index in range(3)
    ]
    plan = _plan().model_copy(update={"report_values": {"remarks": remarks}})
    backend = _Backend([{"intent": {}}] + [{"intent": {"remarks": [remark]}} for remark in remarks])
    trace = AgentRunTrace.create(logfile_path=tmp_path / "draft.log.yaml", mode="reconstruct")

    async def compile_report() -> CompiledArtifact:
        with bind_agent_trace(trace):
            return await ReportCompiler(
                ExistingProviderStructuredAdapter(backend), create_builtin_registry()
            ).compile(
                request="Add all notices in order.",
                plan=plan,
                current_document=document,
                source_manifest={},
            )

    result = asyncio.run(compile_report())
    assert result.payload["intent"]["remarks"] == remarks
    events = [json.loads(line) for line in trace.path.read_text().splitlines()]
    targets = [
        event["target_id"]
        for event in events
        if event["event"] == "stage_finished" and event["stage"] == "report_task"
    ]
    assert targets == ["report.settings", "report.remark.1", "report.remark.2", "report.remark.3"]


def test_report_remark_tasks_pin_materialized_stable_ids() -> None:
    """Independent remark tasks cannot overwrite a prior remark target."""
    document = _document()
    document["remarks"] = [
        {
            "remark_id": "remark-1",
            "title": "Public Data and IP Notice",
            "text": "Keep the reproduction boundary explicit.",
        }
    ]
    values = materialize_report_remark_ids(
        {
            "remarks": [
                {"title": "Supported Reconstruction Scope", "text": "Keep the scope bounded."},
                {"title": "Data Sources", "text": "Use staged DLIS files."},
                {
                    "title": "Public Data and IP Notice",
                    "text": "Keep the reproduction boundary explicit.",
                },
            ]
        },
        document,
    )

    assert [remark["remark_id"] for remark in values["remarks"]] == [
        "remark-2",
        "remark-3",
        "remark-1",
    ]
    tasks = report_tasks(report_contract(document, reconstruct=True), values)
    with pytest.raises(ValueError, match="remark-2"):
        tasks[2].response_model.model_validate(
            {
                "intent": {
                    "remarks": [
                        {
                            "remark_id": "remark-2",
                            "title": "Data Sources",
                            "text": "Use staged DLIS files.",
                        }
                    ]
                }
            }
        )
