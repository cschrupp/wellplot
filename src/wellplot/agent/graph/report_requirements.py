###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Focused extraction of report-wide requirements from a user request."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from ..execution_trace import current_agent_trace
from .context_projection import report_document_context, report_source_context
from .models import CompilationMode
from .planner import report_values_contract
from .prompt_context import compact_prompt_json
from .provider_adapter import StructuredModelProtocol


@dataclass(frozen=True, slots=True)
class ReportValuesReconciliation:
    """Merged report values and explicit focused-planner replacements."""

    values: dict[str, Any]
    focused_overrides: tuple[str, ...]


@dataclass(slots=True)
class ReportRequirementPlanner:
    """Extract typed report values independently from section planning.

    The reconstruction planner remains responsible for the complete semantic
    topology. This focused stage audits its report values against the original
    request using only the report form inventory, so a large section plan cannot
    crowd out header or remarks requirements.
    """

    model: StructuredModelProtocol

    async def resolve(
        self,
        *,
        request: str,
        current_document: dict[str, object],
        source_manifest: dict[str, object],
        prior_values: Mapping[str, Any],
        mode: CompilationMode,
    ) -> dict[str, Any]:
        """Return report values reconciled with the primary planner's output."""
        response_model = report_values_contract(current_document)
        context = {
            "original_request": request,
            "mode": mode,
            "prior_report_values": dict(prior_values),
            "current_document": report_document_context(current_document),
            "source_manifest": report_source_context(source_manifest),
        }
        revision_instruction = (
            " In revision mode, include only explicit report-wide changes and preserve all "
            "other current report values."
            if mode == "revise"
            else ""
        )
        trace = current_agent_trace()
        stage = (
            trace.stage("report_requirements", target_id="report")
            if trace is not None
            else nullcontext()
        )
        with stage:
            requirements = await self.model.generate(
                instructions=(
                    "You are Wellplot's focused report-requirements planner. Extract every "
                    "explicit report-wide requirement from the original request: heading "
                    "metadata, service titles, remarks, tail, page, depth, and output. Do "
                    "not plan sections, tracks, bindings, fills, or annotations. Audit "
                    "prior_report_values rather than assuming it is complete. Use only the "
                    "stable header slot IDs exposed by current_document. Match requested "
                    "fields using each slot's key, label, and aliases. Preserve requested "
                    "display text exactly, including units and fixed decimals. Include each "
                    "requested remark with a non-empty title and body. Omit report settings "
                    "not explicitly requested; never use empty strings, zeroes, or literal "
                    "'null' placeholders." + revision_instruction
                ),
                user_message=(
                    "Return only the typed report requirements for this request. The response "
                    "schema is supplied as the required function schema.\n\nContext:\n"
                    + compact_prompt_json(context)
                ),
                response_model=response_model,
                tool_name="submit_report_requirements",
                tool_description="Submit typed report requirements for later bounded compilation.",
                max_rounds=3,
            )
            resolved = requirements.model_dump(mode="json", exclude_unset=True, exclude_none=True)
            if trace is not None:
                trace.record("structured_output", status="accepted", payload=resolved)
            reconciliation = merge_report_values(prior_values, resolved)
            if trace is not None and reconciliation.focused_overrides:
                trace.record(
                    "report_requirements_reconciled",
                    status="focused_values_preferred",
                    details={"replaced_targets": reconciliation.focused_overrides},
                )
        return reconciliation.values


def merge_report_values(
    prior_values: Mapping[str, Any], resolved_values: Mapping[str, Any]
) -> ReportValuesReconciliation:
    """Merge report plans, giving declared focused values deterministic precedence.

    The topology planner supplies preliminary report values as context for the
    focused report planner. The focused planner owns report-wide extraction, so
    a value it explicitly supplies replaces the preliminary value for the same
    stable target. Each replacement is returned to the caller for traceability.
    """
    result = deepcopy(dict(prior_values))
    focused_overrides: list[str] = []
    for name, resolved in resolved_values.items():
        if name == "header":
            result[name] = _merge_header_values(
                result.get(name),
                resolved,
                focused_overrides=focused_overrides,
            )
        elif name == "remarks":
            result[name] = _merge_remarks(
                result.get(name),
                resolved,
                focused_overrides=focused_overrides,
            )
        elif name not in result or result[name] is None:
            result[name] = deepcopy(resolved)
        elif result[name] != resolved:
            result[name] = deepcopy(resolved)
            focused_overrides.append(f"report.{name}")
    return ReportValuesReconciliation(
        values=result,
        focused_overrides=tuple(focused_overrides),
    )


def _merge_header_values(
    prior: object,
    resolved: object,
    *,
    focused_overrides: list[str],
) -> dict[str, Any]:
    """Merge header scalar settings and stable-slot collections by identity."""
    prior_mapping = _mapping(prior)
    resolved_mapping = _mapping(resolved)
    result = deepcopy(prior_mapping)
    for name, value in resolved_mapping.items():
        if name in {"general_fields", "detail_fields", "service_titles"}:
            result[name] = _merge_slot_values(
                result.get(name),
                value,
                collection=name,
                focused_overrides=focused_overrides,
            )
        elif name not in result or result[name] is None:
            result[name] = deepcopy(value)
        elif result[name] != value:
            result[name] = deepcopy(value)
            focused_overrides.append(f"header.{name}")
    return result


def _merge_slot_values(
    prior: object,
    resolved: object,
    *,
    collection: str,
    focused_overrides: list[str],
) -> list[dict[str, Any]]:
    """Merge stable-slot values while preserving primary-plan ordering."""
    result = [dict(value) for value in _mapping_sequence(prior)]
    index_by_slot = {
        slot_id: index
        for index, value in enumerate(result)
        if isinstance((slot_id := value.get("slot_id")), str) and slot_id
    }
    for value in _mapping_sequence(resolved):
        slot_id = value.get("slot_id")
        if not isinstance(slot_id, str) or not slot_id:
            raise ValueError(f"Focused {collection} plan requires a non-empty slot_id.")
        index = index_by_slot.get(slot_id)
        if index is None:
            copied = dict(value)
            result.append(copied)
            index_by_slot[slot_id] = len(result) - 1
        elif result[index] != value:
            merged = dict(result[index])
            merged.update(value)
            result[index] = merged
            focused_overrides.append(f"header.{collection}.{slot_id}")
    return result


def _merge_remarks(
    prior: object,
    resolved: object,
    *,
    focused_overrides: list[str],
) -> list[dict[str, Any]]:
    """Merge remarks by stable ID, falling back to their requested title."""
    result = [dict(value) for value in _mapping_sequence(prior)]
    index_by_identity = {_remark_identity(value): index for index, value in enumerate(result)}
    for value in _mapping_sequence(resolved):
        identity = _remark_identity(value)
        index = index_by_identity.get(identity)
        if index is None:
            copied = dict(value)
            result.append(copied)
            index_by_identity[identity] = len(result) - 1
        elif result[index] != value:
            merged = dict(result[index])
            merged.update(value)
            result[index] = merged
            focused_overrides.append(f"remark.{identity}")
    return result


def _remark_identity(value: Mapping[str, Any]) -> str:
    """Return the stable identity used to reconcile one planned remark."""
    remark_id = value.get("remark_id")
    if isinstance(remark_id, str) and remark_id:
        return f"id:{remark_id}"
    title = value.get("title")
    if isinstance(title, str) and title:
        return f"title:{title}"
    raise ValueError("Focused report remarks require a non-empty title or remark_id.")


def _mapping(value: object) -> dict[str, Any]:
    """Return a defensive dictionary for one optional plan mapping."""
    return dict(value) if isinstance(value, Mapping) else {}


def _mapping_sequence(value: object) -> list[Mapping[str, Any]]:
    """Return mapping entries from one optional plan collection."""
    if not isinstance(value, Sequence) or isinstance(value, (bytes, str)):
        return []
    return [item for item in value if isinstance(item, Mapping)]
