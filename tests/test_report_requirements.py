"""Focused report-requirements planning regressions."""

from __future__ import annotations

import asyncio
import json

from pydantic import BaseModel

from wellplot.agent.graph.models import ReconstructionPlan
from wellplot.agent.graph.report_requirements import (
    ReportRequirementPlanner,
    merge_report_values,
)
from wellplot.agent.graph.report_worker import ReportCompiler
from wellplot.capabilities import create_builtin_registry
from wellplot.model.authoring import AuthoringDocumentSpec


def _document() -> dict[str, object]:
    """Return a small cased-hole-style report scaffold."""
    return AuthoringDocumentSpec.model_validate(
        {
            "name": "report-requirements",
            "header": {
                "general_fields": [
                    {"slot_id": "general.company", "key": "company", "label": "Company"},
                    {
                        "slot_id": "general.country",
                        "key": "country",
                        "label": "Country",
                        "aliases": ["State", "State / Country"],
                    },
                ],
            },
            "sections": [
                {
                    "id": "main",
                    "title": "Main",
                    "tracks": [
                        {"id": "depth", "title": "Depth", "kind": "reference", "width_mm": 10},
                    ],
                }
            ],
        }
    ).model_dump(mode="json")


def _plan() -> ReconstructionPlan:
    """Return the partial report plan observed in a broad reconstruction plan."""
    return ReconstructionPlan.model_validate(
        {
            "summary": "Reconstruct the cased-hole packet.",
            "report_values": {
                "header": {
                    "general_fields": [
                        {"slot_id": "general.company", "value": "University of Utah"},
                    ]
                }
            },
            "sections": [
                {
                    "section_id": "main",
                    "capability_id": "section.log_plot",
                    "goal": "Keep main.",
                }
            ],
        }
    )


class _ReportRequirementsModel:
    """Return focused requirements followed by bounded report artifacts."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.requirements_context: dict[str, object] | None = None
        self.report_calls = 0

    async def generate(
        self,
        *,
        instructions: str,
        user_message: str,
        response_model: type[BaseModel],
        tool_name: str,
        tool_description: str,
        max_rounds: int = 3,
        response_validator: object | None = None,
    ) -> BaseModel:
        """Return a schema-validated deterministic response for each graph stage."""
        del instructions, tool_description, max_rounds
        self.calls.append(tool_name)
        if tool_name == "submit_report_requirements":
            self.requirements_context = json.loads(user_message.split("Context:\n", maxsplit=1)[1])
            payload: dict[str, object] = {
                "header": {
                    "general_fields": [
                        {"slot_id": "general.country", "value": "Utah"},
                    ]
                }
            }
        elif tool_name == "submit_report_artifact":
            self.report_calls += 1
            payload = (
                {"intent": {}}
                if self.report_calls == 1
                else {
                    "intent": {
                        "header": {
                            "general_fields": [
                                {
                                    "slot_id": "general.company",
                                    "value": {"value": "University of Utah"},
                                },
                                {
                                    "slot_id": "general.country",
                                    "value": {"value": "Utah"},
                                },
                            ]
                        }
                    }
                }
            )
        else:
            raise AssertionError(f"Unexpected tool {tool_name!r}.")
        result = response_model.model_validate(payload)
        if response_validator is not None:
            response_validator(result)  # type: ignore[operator]
        return result


def test_focused_report_requirements_complete_a_partial_primary_plan() -> None:
    """A report-only stage supplies values omitted by topology planning."""
    model = _ReportRequirementsModel()
    document = _document()
    plan = _plan()

    result = asyncio.run(
        ReportCompiler(
            model=model,
            registry=create_builtin_registry(),
            requirements_planner=ReportRequirementPlanner(model=model),
        ).compile(
            request="Set company to University of Utah and State to Utah.",
            plan=plan,
            current_document=document,
            source_manifest={},
        )
    )

    assert model.calls == [
        "submit_report_requirements",
        "submit_report_artifact",
        "submit_report_artifact",
    ]
    assert model.requirements_context is not None
    general_fields = model.requirements_context["current_document"]["header"]["general_fields"]
    assert general_fields[1]["aliases"] == ["State", "State / Country"]
    values = result.payload["intent"]["header"]["general_fields"]
    assert [(value["slot_id"], value["value"]["value"]) for value in values] == [
        ("general.company", "University of Utah"),
        ("general.country", "Utah"),
    ]


def test_focused_report_requirements_replace_conflicting_display_slots() -> None:
    """Focused report extraction owns a stable slot when planners disagree."""
    reconciliation = merge_report_values(
        {
            "header": {
                "detail_fields": [
                    {
                        "slot_id": "detail.row_19.column_1.cell_1",
                        "value": "177.2 degF",
                    }
                ]
            }
        },
        {
            "header": {
                "detail_fields": [
                    {
                        "slot_id": "detail.row_19.column_1.cell_1",
                        "value": "177.2",
                    }
                ]
            }
        },
    )

    assert reconciliation.values["header"]["detail_fields"] == [
        {
            "slot_id": "detail.row_19.column_1.cell_1",
            "value": "177.2",
        }
    ]
    assert reconciliation.focused_overrides == (
        "header.detail_fields.detail.row_19.column_1.cell_1",
    )
