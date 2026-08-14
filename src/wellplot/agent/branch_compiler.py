###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Compile natural-language work units into typed branch operations.

This module deliberately stops before persistence.  It is the provider-facing
compiler that turns one parent-scoped group into a validated submission for
``execute_typed_submissions``.  The authoritative route switch is deferred to
the later agent migration slice.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from pydantic import BaseModel

from .compilation import (
    AuthoringCompilationScope,
    AuthoringRequestWorkUnit,
    branch_operation_submission_model,
    compilation_scope_for_object_family,
    validate_operation_submission,
)
from .core import (
    AuthoringToolCall,
    FunctionToolDefinition,
    ProviderRunResult,
)


@dataclass(frozen=True)
class BranchOperationGroup:
    """One canonical branch and natural parent compiled in one provider call."""

    scope: AuthoringCompilationScope
    parent_scope: str | None
    work_units: tuple[AuthoringRequestWorkUnit, ...]
    context: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class DirectBranchCompilationResult:
    """Validated branch submissions ready for the typed transaction executor."""

    success: bool
    submissions: tuple[BaseModel, ...] = ()
    groups: tuple[BranchOperationGroup, ...] = ()
    tool_trace: tuple[AuthoringToolCall, ...] = ()
    correction_errors: tuple[dict[str, object], ...] = ()
    blocked_reasons: tuple[str, ...] = ()
    provider_facts: dict[str, object] = field(default_factory=dict)


_SCOPE_ORDER: tuple[AuthoringCompilationScope, ...] = (
    "report",
    "structure",
    "scalar",
    "raster",
    "annotation",
)
_OBJECT_FAMILY_ORDER = {
    "report": 0,
    "header": 1,
    "service_title": 1,
    "page": 1,
    "output": 1,
    "depth": 1,
    "remarks": 1,
    "tail": 1,
    "section": 2,
    "track": 3,
    "curve_binding": 4,
    "raster_binding": 4,
    "fill": 5,
    "annotation": 5,
}


def _group_parent(unit: AuthoringRequestWorkUnit) -> str | None:
    """Return the stable natural parent key used for one provider group."""
    parent = unit.natural_parent
    return parent.strip() if isinstance(parent, str) and parent.strip() else None


def build_branch_operation_groups(
    work_units: Iterable[AuthoringRequestWorkUnit],
    *,
    context: Mapping[str, object] | None = None,
) -> tuple[BranchOperationGroup, ...]:
    """Group actionable work units by canonical scope and natural parent.

    Provider output never chooses the hierarchy branch.  The object-family
    catalog supplies the scope, and the original request supplies the natural
    parent used to keep unrelated edits out of one provider call.
    """
    grouped: dict[tuple[AuthoringCompilationScope, str | None], list[AuthoringRequestWorkUnit]] = (
        defaultdict(list)
    )
    for unit in work_units:
        if unit.status in {"unsupported", "inconsistent"}:
            continue
        scope = compilation_scope_for_object_family(unit.object_family)
        if scope is None:
            continue
        grouped[(scope, _group_parent(unit))].append(unit)

    shared_context = dict(context or {})
    parent_snapshots = shared_context.get("parent_snapshots")
    groups: list[BranchOperationGroup] = []
    for (scope, parent_scope), items in grouped.items():
        ordered_items = tuple(
            sorted(
                items,
                key=lambda item: (
                    _OBJECT_FAMILY_ORDER.get(item.object_family, 99),
                    item.request_item_id,
                ),
            )
        )
        group_context = dict(shared_context)
        if isinstance(parent_snapshots, Mapping):
            group_context["selected_parent"] = parent_snapshots.get(parent_scope)
        group_context["parent_scope"] = parent_scope
        groups.append(
            BranchOperationGroup(
                scope=scope,
                parent_scope=parent_scope,
                work_units=ordered_items,
                context=group_context,
            )
        )

    scope_order = {scope: index for index, scope in enumerate(_SCOPE_ORDER)}
    return tuple(
        sorted(
            groups,
            key=lambda group: (
                scope_order[group.scope],
                min(_OBJECT_FAMILY_ORDER.get(unit.object_family, 99) for unit in group.work_units),
                "" if group.parent_scope is None else group.parent_scope,
            ),
        )
    )


def _normalize_provider_result(result: object) -> ProviderRunResult:
    """Normalize provider adapters and lightweight recorded test doubles."""
    return ProviderRunResult(
        final_text=str(getattr(result, "final_text", "")),
        tool_trace=tuple(getattr(result, "tool_trace", ()) or ()),
        report_facts=dict(getattr(result, "report_facts", {}) or {}),
    )


def _provider_failure_facts(exc: BaseException) -> dict[str, object]:
    """Keep adapter-provided trace and facts when one branch call fails."""
    facts = dict(getattr(exc, "report_facts", {}) or {})
    facts["provider_error"] = str(exc) or type(exc).__name__
    return facts


def _group_message(
    group: BranchOperationGroup,
    *,
    available_operation_ids: Iterable[str],
    resolved_parent_objects: Iterable[Mapping[str, object]],
) -> str:
    """Build the compact provider context for one branch/parent call."""
    payload = {
        "branch": group.scope,
        "parent_scope": group.parent_scope,
        "request_items": [unit.model_dump(mode="json") for unit in group.work_units],
        "selected_parent": group.context.get("selected_parent"),
        "source_channels": group.context.get("source_channels", {}),
        "applicable_defaults": group.context.get("applicable_defaults", {}),
        "canonical_operations": group.context.get("canonical_operations", {}),
        "available_operation_ids": sorted(set(available_operation_ids)),
        "resolved_parent_objects": list(resolved_parent_objects),
    }
    return (
        "Submit typed operations for this branch and natural parent only. Do not emit a "
        "full-document intent, YAML paths, or operations for another parent. Preserve "
        "explicit values exactly. Use one operation-coverage entry per work unit. Parent "
        "operations must precede child operations; use available operation ids for "
        "cross-group dependencies. The typed operation schema is supplied as the tool "
        "schema.\n\nContext:\n" + json.dumps(payload, indent=2, default=str)
    )


def _operation_object_context(operation: object) -> dict[str, object] | None:
    """Extract one stable object identity for descendant context."""
    request = getattr(operation, "request", None)
    if request is None:
        return None
    object_kind = str(getattr(request, "kind", getattr(request, "object_kind", "")))
    if not object_kind:
        return None
    payload_field = {
        "section": "section",
        "track": "track",
        "curve_binding": "binding",
        "raster_binding": "binding",
        "annotation": "annotation",
        "fill": "fill",
        "remark": "remark",
    }.get(object_kind, object_kind)
    payload = getattr(request, payload_field, None)
    object_id = getattr(payload, "id", None)
    if object_id is None:
        object_id = getattr(payload, "binding_id", None)
    if object_id is None:
        object_id = getattr(payload, "annotation_id", None)
    if object_id is None:
        object_id = getattr(payload, "fill_id", None)
    if object_id is None:
        object_id = getattr(payload, "remark_id", None)
    if object_id is None:
        object_id = getattr(request, "object_id", None)
    if object_id is None:
        return None
    result: dict[str, object] = {
        "operation_id": operation.operation_id,
        "object_kind": object_kind,
        "object_id": str(object_id),
    }
    for field_name in ("section_id", "track_id"):
        value = getattr(request, field_name, None)
        if value is not None:
            result[field_name] = value
    return result


async def compile_direct_branch_operations(
    backend: object,
    groups: Iterable[BranchOperationGroup],
    *,
    max_rounds: int = 6,
) -> DirectBranchCompilationResult:
    """Compile each branch group with one bounded provider correction.

    The function does not mutate a document.  Accepted submissions are already
    validated against the canonical branch contract and can be passed directly
    to :func:`wellplot.agent.operation_executor.execute_typed_submissions`.
    """
    group_list = tuple(groups)
    submissions: list[BaseModel] = []
    tool_trace: list[AuthoringToolCall] = []
    correction_errors: list[dict[str, object]] = []
    blocked_reasons: list[str] = []
    provider_facts: dict[str, object] = {"groups": []}
    available_operation_ids: set[str] = set()
    resolved_parent_objects: list[dict[str, object]] = []

    for group in group_list:
        model = branch_operation_submission_model(group.scope)
        tool_name = f"submit_{group.scope}_operations"
        attempts = 0
        accepted: BaseModel | None = None
        group_errors: list[str] = []

        async def submit_operations(
            name: str,
            arguments: dict[str, object],
            *,
            expected_name: str = tool_name,
            submission_model: type[BaseModel] = model,
            current_group: BranchOperationGroup = group,
            errors_for_group: list[str] = group_errors,
        ) -> dict[str, object]:
            """Validate one initial or corrected branch submission."""
            nonlocal accepted, attempts
            if name != expected_name:
                return {
                    "is_error": True,
                    "error": f"Only {expected_name} is available in this branch stage.",
                }
            attempts += 1
            if attempts > 2:
                return {
                    "is_error": True,
                    "error": (
                        "Only one initial submission and one correction submission are "
                        "allowed."
                    ),
                }
            try:
                candidate = submission_model.model_validate(arguments)
            except Exception as exc:  # Pydantic returns provider-actionable details.
                message = f"{type(exc).__name__}: {exc}"
                errors_for_group.append(message)
                return {
                    "is_error": True,
                    "error": f"Invalid {submission_model.__name__}: {exc}",
                }
            errors = validate_operation_submission(
                current_group.scope,
                candidate,
                current_group.work_units,
                external_operation_ids=available_operation_ids,
            )
            if errors:
                errors_for_group.extend(errors)
                return {
                    "is_error": True,
                    "error": "Branch operation submission is invalid:\n- " + "\n- ".join(errors),
                }
            accepted = candidate
            return {
                "accepted": True,
                "message": f"{current_group.scope.title()} branch operations validated.",
            }

        tool = FunctionToolDefinition(
            name=tool_name,
            description=(
                f"Submit typed operations for the {group.scope} branch and one natural parent."
            ),
            parameters=model.model_json_schema(),
        )
        try:
            raw_result = await backend.run_authoring(
                instructions=(
                    "You are a direct branch-operation compiler for wellplot. Emit only "
                    f"the typed {group.scope} operation submission requested by the tool. "
                    "Do not invent scientific-family branches or mutate through MCP."
                ),
                initial_user_message=_group_message(
                    group,
                    available_operation_ids=available_operation_ids,
                    resolved_parent_objects=resolved_parent_objects,
                ),
                tool_definitions=[tool],
                tool_caller=submit_operations,
                max_rounds=max_rounds,
                required_tool_name=tool_name,
            )
            normalized = _normalize_provider_result(raw_result)
            tool_trace.extend(normalized.tool_trace)
            provider_facts["groups"].append(
                {
                    "scope": group.scope,
                    "parent_scope": group.parent_scope,
                    "attempts": attempts,
                    **normalized.report_facts,
                }
            )
        except Exception as exc:  # Provider failures must block without mutation.
            failure_trace = tuple(getattr(exc, "tool_trace", ()) or ())
            tool_trace.extend(failure_trace)
            blocked_reasons.append(
                f"{group.scope} branch for parent {group.parent_scope!r} failed: "
                f"{str(exc) or type(exc).__name__}"
            )
            provider_facts["groups"].append(
                {
                    "scope": group.scope,
                    "parent_scope": group.parent_scope,
                    "attempts": attempts,
                    **_provider_failure_facts(exc),
                }
            )
            break

        if accepted is None:
            if group_errors:
                if attempts > 1:
                    correction_errors.append(
                        {
                            "scope": group.scope,
                            "parent_scope": group.parent_scope,
                            "errors": list(group_errors),
                        }
                    )
                blocked_reasons.append(
                    f"{group.scope} branch for parent {group.parent_scope!r} did not "
                    "produce a valid typed operation submission."
                )
            else:
                blocked_reasons.append(
                    f"{group.scope} branch for parent {group.parent_scope!r} was not submitted."
                )
            break

        if attempts > 1 and group_errors:
            correction_errors.append(
                {
                    "scope": group.scope,
                    "parent_scope": group.parent_scope,
                    "errors": list(group_errors),
                }
            )
        submissions.append(accepted)
        available_operation_ids.update(
            operation.operation_id for operation in getattr(accepted, "operations", ())
        )
        for operation in getattr(accepted, "operations", ()):
            identity = _operation_object_context(operation)
            if identity is not None:
                resolved_parent_objects.append(identity)

    success = not blocked_reasons and len(submissions) == len(group_list)
    return DirectBranchCompilationResult(
        success=success,
        submissions=tuple(submissions),
        groups=group_list,
        tool_trace=tuple(tool_trace),
        correction_errors=tuple(correction_errors),
        blocked_reasons=tuple(blocked_reasons),
        provider_facts=provider_facts,
    )


__all__ = [
    "BranchOperationGroup",
    "DirectBranchCompilationResult",
    "build_branch_operation_groups",
    "compile_direct_branch_operations",
]
