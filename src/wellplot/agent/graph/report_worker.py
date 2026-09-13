###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Report-wide compiler node."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import nullcontext
from dataclasses import dataclass
from functools import partial
from typing import Any

from ...authoring_service import AuthoringService
from ...capabilities import CapabilityRegistry
from ...capabilities.builtins import ReportArtifact
from ...model.authoring import AuthoringDocumentSpec
from ...model.intent import AuthoringDocumentIntent
from ..execution_trace import current_agent_trace
from .context_projection import report_document_context, report_source_context
from .executor import execute_document_intent
from .models import CompilationMode, CompiledArtifact, ReconstructionPlan
from .prompt_context import compact_prompt_json
from .provider_adapter import StructuredModelProtocol
from .report_requirements import ReportRequirementPlanner
from .report_tasks import (
    ReportTask,
    materialize_report_remark_ids,
    merge_report_parts,
    report_tasks,
)
from .worker_contracts import report_contract


@dataclass(slots=True)
class ReportCompiler:
    """Compile report-wide desired state into one capability artifact."""

    model: StructuredModelProtocol
    registry: CapabilityRegistry
    requirements_planner: ReportRequirementPlanner | None = None

    async def compile(
        self,
        *,
        request: str,
        plan: ReconstructionPlan,
        current_document: dict[str, object],
        source_manifest: dict[str, object],
        mode: CompilationMode = "reconstruct",
    ) -> CompiledArtifact:
        """Compile only report-wide requirements from one semantic plan."""
        spec = self.registry.get(plan.report_capability_id)
        if spec.category != "report":
            raise ValueError(f"{plan.report_capability_id!r} is not a report capability.")
        report_values = plan.report_values
        if self.requirements_planner is not None:
            report_values = await self.requirements_planner.resolve(
                request=request,
                current_document=current_document,
                source_manifest=source_manifest,
                prior_values=plan.report_values,
                mode=mode,
            )
        report_values = materialize_report_remark_ids(report_values, current_document)
        revision_instruction = (
            " In revision mode, omit unchanged report-wide values so their current state is "
            "preserved."
            if mode == "revise"
            else ""
        )
        context = {
            "original_request": request,
            "report_goal": plan.report_goal,
            "report_values": report_values,
            "postconditions": plan.postconditions,
            "mode": mode,
            "current_document": report_document_context(current_document),
            "source_manifest": report_source_context(source_manifest),
            # The required function schema is sent separately; do not duplicate it here.
            "capability": spec.planning_descriptor(),
        }
        trace = current_agent_trace()
        stage = trace.stage("report", target_id="report") if trace is not None else nullcontext()
        with stage:
            response_model = spec.artifact_model
            if response_model is ReportArtifact:
                response_model = report_contract(
                    current_document, reconstruct=mode == "reconstruct"
                )
            tasks = [ReportTask("report", report_values, response_model)]
            if spec.artifact_model is ReportArtifact and mode == "reconstruct":
                tasks = report_tasks(response_model, report_values)
            accepted: dict[str, Any] = {}
            for task in tasks:
                task_context = dict(context)
                task_context["report_values"] = task.values
                task_context["task_id"] = task.target_id
                response_validator = None
                if spec.artifact_model is ReportArtifact:
                    response_validator = partial(
                        _validate_report_part,
                        accepted=accepted,
                        current_document=current_document,
                        report_values=task.values,
                    )
                task_stage = (
                    trace.stage("report_task", target_id=task.target_id)
                    if trace is not None and len(tasks) > 1
                    else nullcontext()
                )
                with task_stage:
                    artifact = await self.model.generate(
                        instructions=(
                            "Complete only the fields permitted by this task's schema. Other tasks "
                            "own the other report fields. Include every value in report_values. "
                            "A null plan value is unspecified: omit that setting. Never use "
                            "the literal string 'null' as a placeholder. "
                            "You are the report compiler. Compile report/header/page/depth/"
                            "output/remarks/tail requirements. Do not author section tracks, "
                            "bindings, fills, or annotations. Return desired state. "
                            "Omit unrequested fields to preserve scaffold values and defaults. "
                            "Use only listed header slot IDs; labels and aliases describe "
                            "their meaning. Never invent slots. "
                            "Submit sparse updates, not a copy of current_document. "
                            "Absent settings preserve automatic sizing. Do not substitute "
                            "empty strings, zeroes, or tiny numbers for them. Only set geometry "
                            "or typography when requested. Populate each requested header "
                            "value and remark body. Header general_fields and detail_fields "
                            "entries have this shape: "
                            '{"slot_id": "<listed ID>", "value": {"value": "<value>"}}. '
                            "Header detail context is an inventory, not a replacement layout. Keep "
                            "header.detail omitted unless replacing the layout is requested. A new "
                            "remark needs its requested text or lines, not just a title. "
                            + revision_instruction
                        ),
                        user_message=(
                            "Compile the report-wide portion of the reconstruction.\n\nContext:\n"
                            + compact_prompt_json(task_context)
                        ),
                        response_model=task.response_model,
                        tool_name="submit_report_artifact",
                        tool_description="Submit typed report-wide desired state.",
                        max_rounds=3,
                        response_validator=response_validator,
                    )
                    if trace is not None:
                        trace.record(
                            "structured_output",
                            status="accepted",
                            payload=artifact.model_dump(mode="json", exclude_unset=True),
                        )
                accepted = merge_report_parts(
                    accepted, artifact.model_dump(mode="json", exclude_unset=True)
                )
            if spec.artifact_model is ReportArtifact and len(tasks) > 1:
                _validate_report(
                    ReportArtifact.model_validate(accepted), current_document, report_values
                )
        return CompiledArtifact(
            worker_id="report",
            capability_id=spec.capability_id,
            target_id="report",
            payload=accepted,
        )


def _validate_report_part(
    artifact: ReportArtifact,
    *,
    accepted: dict[str, Any],
    current_document: dict[str, object],
    report_values: Mapping[str, Any],
) -> None:
    """Validate the current task against all accepted in-memory report work."""
    combined = merge_report_parts(accepted, artifact.model_dump(mode="json", exclude_unset=True))
    _validate_report(ReportArtifact.model_validate(combined), current_document, report_values)


def _validate_report(
    artifact: ReportArtifact,
    current_document: dict[str, object],
    report_values: Mapping[str, Any],
) -> None:
    """Reject reports that omit planned values or cannot apply canonically."""
    coverage_errors = _report_coverage_errors(
        artifact.model_dump(mode="json", exclude_unset=True),
        report_values,
    )
    if coverage_errors:
        raise ValueError("Report omitted planned values:\n" + "\n".join(coverage_errors))
    document = AuthoringDocumentSpec.model_validate(current_document).model_copy(deep=True)
    intent = AuthoringDocumentIntent.model_validate(
        artifact.intent.model_dump(mode="json", exclude_unset=True)
    )
    result = execute_document_intent(AuthoringService(document), intent)
    if not result.success:
        raise ValueError(
            "Report cannot be applied to the current scaffold:\n" + "\n".join(result.errors)
        )


def _report_coverage_errors(
    artifact: Mapping[str, Any], report_values: Mapping[str, Any]
) -> list[str]:
    """Require the report artifact to carry explicit stable-slot plan values."""
    planned_header = _mapping(report_values.get("header"))
    artifact_header = _mapping(_mapping(artifact.get("intent")).get("header"))
    errors = _planned_header_scalar_errors(planned_header, artifact_header)
    for collection in ("general_fields", "detail_fields", "service_titles"):
        errors.extend(
            _planned_slot_value_errors(
                collection,
                _mapping_sequence(planned_header.get(collection)),
                _mapping_sequence(artifact_header.get(collection)),
            )
        )
    errors.extend(
        _planned_remark_errors(
            _mapping_sequence(report_values.get("remarks")),
            _mapping_sequence(_mapping(artifact.get("intent")).get("remarks")),
        )
    )
    return errors


def _planned_header_scalar_errors(
    planned: Mapping[str, Any], artifact: Mapping[str, Any]
) -> list[str]:
    """Check explicitly planned direct header settings."""
    errors = []
    for name in ("enabled", "provider_name", "title", "subtitle", "tail_enabled"):
        expected = planned.get(name)
        if expected is None:
            continue
        actual = artifact.get(name)
        if _comparable_value(actual) != _comparable_value(expected):
            errors.append(f"Header field {name!r} must be {expected!r}.")
    return errors


def _planned_slot_value_errors(
    collection: str,
    planned: Sequence[Mapping[str, Any]],
    artifact: Sequence[Mapping[str, Any]],
) -> list[str]:
    """Check values whose stable slots were resolved by the planner."""
    artifact_by_slot = {
        slot_id: item for item in artifact if isinstance((slot_id := item.get("slot_id")), str)
    }
    errors = []
    for item in planned:
        slot_id = item.get("slot_id")
        expected = item.get("value")
        if not isinstance(slot_id, str) or expected is None:
            continue
        actual_item = artifact_by_slot.get(slot_id)
        actual = _mapping(actual_item.get("value")).get("value") if actual_item else None
        if _comparable_value(actual) != _comparable_value(expected):
            errors.append(f"{collection} slot {slot_id!r} must carry {expected!r}.")
    return errors


def _planned_remark_errors(
    planned: Sequence[Mapping[str, Any]], artifact: Sequence[Mapping[str, Any]]
) -> list[str]:
    """Require every explicitly planned remark body or title."""
    errors = []
    for expected in planned:
        title = expected.get("title")
        if not isinstance(title, str) or not title:
            continue
        actual = next((item for item in artifact if item.get("title") == title), None)
        if actual is None:
            errors.append(f"Remark {title!r} is missing.")
            continue
        for name in ("text", "lines"):
            if (
                name in expected
                and expected[name] is not None
                and actual.get(name) != expected[name]
            ):
                errors.append(f"Remark {title!r} must carry planned {name}.")
    return errors


def _comparable_value(value: object) -> object:
    """Compare report display values after their canonical text normalization."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    return value


def _mapping(value: object) -> Mapping[str, Any]:
    """Return a safe mapping view for untrusted planner and artifact payloads."""
    return value if isinstance(value, Mapping) else {}


def _mapping_sequence(value: object) -> list[Mapping[str, Any]]:
    """Return mapping items while discarding malformed planner payload entries."""
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [item for item in value if isinstance(item, Mapping)]
