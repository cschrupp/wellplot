"""Bounded report construction tasks with disjoint output contracts."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, ClassVar, Literal, get_args

from pydantic import BaseModel, Field, create_model

HEADER_BATCH_SIZE = 8
HEADER_COLLECTIONS = ("general_fields", "detail_fields", "service_titles")


@dataclass(frozen=True)
class ReportTask:
    """One independently validated portion of a report artifact."""

    target_id: str
    values: dict[str, Any]
    response_model: type[BaseModel]


def report_tasks(base: type[BaseModel], values: dict[str, Any]) -> list[ReportTask]:
    """Partition planned collections while retaining one report-settings task."""
    intent = base.model_fields["intent"].annotation
    header = intent.model_fields["header"].annotation
    settings = deepcopy(values)
    planned_header = settings.get("header", {})
    tasks = []
    for collection in HEADER_COLLECTIONS:
        entries = planned_header.pop(collection, [])
        for offset in range(0, len(entries), HEADER_BATCH_SIZE):
            batch = entries[offset : offset + HEADER_BATCH_SIZE]
            item_base = get_args(header.model_fields[collection].annotation)[0]
            allowed_slots = set(get_args(item_base.model_fields["slot_id"].annotation))
            requested_slots = [entry["slot_id"] for entry in batch]
            unknown = set(requested_slots) - allowed_slots
            if unknown:
                raise ValueError(f"Planned {collection} contains unknown slots: {sorted(unknown)}.")
            if len(requested_slots) != len(set(requested_slots)):
                raise ValueError(f"Planned {collection} contains duplicate slots.")
            item = create_model(
                "ReportTaskSlot",
                __base__=item_base,
                slot_id=(Literal[tuple(requested_slots)], ...),
            )
            task_header = _only_fields(header, {collection})
            task_header = create_model(
                "ReportTaskHeader",
                __base__=task_header,
                **{collection: (list[item], Field(min_length=len(batch), max_length=len(batch)))},
            )
            task_intent = create_model(
                "ReportTaskIntent",
                __base__=_only_fields(intent, {"header"}),
                header=(task_header, ...),
            )
            tasks.append(
                ReportTask(
                    f"report.{collection}.{offset // HEADER_BATCH_SIZE + 1}",
                    {"header": {collection: batch}},
                    create_model("ReportTaskArtifact", __base__=base, intent=(task_intent, ...)),
                )
            )
    remarks = settings.pop("remarks", [])
    for index, remark in enumerate(remarks):
        item_base = get_args(intent.model_fields["remarks"].annotation)[0]
        fields = {}
        if remark.get("remark_id"):
            fields["remark_id"] = (Literal[remark["remark_id"]], ...)
        item = create_model("ReportTaskRemark", __base__=item_base, **fields)
        task_intent = create_model(
            "ReportTaskIntent",
            __base__=_only_fields(intent, {"remarks"}),
            remarks=(list[item], Field(min_length=1, max_length=1)),
        )
        tasks.append(
            ReportTask(
                f"report.remark.{index + 1}",
                {"remarks": [remark]},
                create_model("ReportTaskArtifact", __base__=base, intent=(task_intent, ...)),
            )
        )
    if not tasks:
        return [ReportTask("report", values, base)]
    settings_header = _only_fields(header, set(header.model_fields) - set(HEADER_COLLECTIONS))
    settings_intent = create_model(
        "ReportSettingsIntent",
        __base__=_only_fields(intent, set(intent.model_fields) - {"remarks"}),
        header=(settings_header, None),
    )
    # Establish report geometry/layout before validating individual slot edits.
    tasks.insert(
        0,
        ReportTask(
            "report.settings",
            settings,
            create_model("ReportSettingsArtifact", __base__=base, intent=(settings_intent, ...)),
        ),
    )
    return tasks


def merge_report_parts(accepted: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Combine disjoint task fields without mutating already accepted output."""
    result = deepcopy(accepted)
    for name, value in candidate.items():
        if name not in result:
            result[name] = deepcopy(value)
        elif isinstance(value, dict) and isinstance(result[name], dict):
            result[name] = merge_report_parts(result[name], value)
        elif isinstance(value, list) and isinstance(result[name], list):
            result[name].extend(deepcopy(value))
        else:
            raise ValueError(f"Report tasks overlap at field {name!r}.")
    return result


def _only_fields(base: type[BaseModel], allowed: set[str]) -> type[BaseModel]:
    """Remove other task fields from both validation and advertised schema."""
    excluded = {name: (ClassVar[None], None) for name in base.model_fields if name not in allowed}
    return create_model(f"Task{base.__name__}", __base__=base, **excluded)
