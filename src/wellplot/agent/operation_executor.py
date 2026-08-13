###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Transactional execution of hierarchy-scoped typed service operations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..authoring_reconciler import AuthoringOperationPhase
from ..authoring_service import (
    AuthoringService,
    AuthoringTarget,
    CreateRequest,
    MoveRequest,
    RemoveRequest,
    UpdateRequest,
)
from ..model.authoring import AuthoringDocumentSpec
from .compilation import (
    AuthoringCompilationScope,
    AuthoringRequestWorkUnit,
    operation_request_object_kind,
    operation_submission_operations,
    validate_operation_submission,
)


class TypedOperationExecutionStatus(StrEnum):
    """Result status for one typed operation."""

    COMPLETED = "completed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class TypedVerificationEvidence(BaseModel):
    """Canonical evidence captured for one operation postcondition."""

    model_config = ConfigDict(extra="forbid")

    target: AuthoringTarget | None = None
    requested: dict[str, Any] = Field(default_factory=dict)
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    persisted_index: int | None = None


class TypedOperationOutcome(BaseModel):
    """Read-after-write outcome for one typed service request."""

    model_config = ConfigDict(extra="forbid")

    branch: AuthoringCompilationScope
    operation_id: str
    work_unit_id: str
    request_item_id: str | None = None
    clause_text: str | None = None
    natural_parent: str | None = None
    action: str
    object_kind: str
    status: TypedOperationExecutionStatus
    postcondition_verified: bool = False
    message: str = ""
    error: str | None = None
    defaults_provenance: dict[str, str] = Field(default_factory=dict)
    verification: TypedVerificationEvidence = Field(default_factory=TypedVerificationEvidence)


class TypedPhaseCheckpoint(BaseModel):
    """Canonical snapshot captured after one verified operation phase."""

    model_config = ConfigDict(extra="forbid")

    phase: AuthoringOperationPhase
    status: TypedOperationExecutionStatus
    operation_ids: tuple[str, ...] = ()
    applied_count: int = 0
    document: AuthoringDocumentSpec


class TypedSubmissionExecutionResult(BaseModel):
    """Atomic result for one or more hierarchy-scoped submissions."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    stopped: bool
    document: AuthoringDocumentSpec
    outcomes: tuple[TypedOperationOutcome, ...] = ()
    phase_summaries: tuple[TypedPhaseCheckpoint, ...] = ()
    applied_operation_ids: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


_SCOPE_ORDER: tuple[AuthoringCompilationScope, ...] = (
    "report",
    "structure",
    "scalar",
    "raster",
    "annotation",
)


def _request_target(request: BaseModel, returned: BaseModel | None = None) -> AuthoringTarget:
    """Build a canonical read-back target from one service request/result."""
    kind = operation_request_object_kind(request)
    if isinstance(request, RemoveRequest):
        return request.target
    if isinstance(request, MoveRequest):
        return AuthoringTarget(
            object_kind=request.object_kind,
            object_id=request.object_id,
            section_id=request.section_id,
        )
    if kind == "report":
        return AuthoringTarget(object_kind="report", object_id="report")
    if kind in {"page", "depth", "output", "header", "tail"}:
        return AuthoringTarget(object_kind=kind, object_id=kind)
    if kind == "header_slot":
        return AuthoringTarget(object_kind=kind, object_id=request.slot_id)
    if kind == "service_title":
        return AuthoringTarget(object_kind=kind, object_id=request.slot_id)
    if kind == "section":
        object_id = request.section_id if hasattr(request, "section_id") else request.section.id
        return AuthoringTarget(object_kind=kind, object_id=object_id)
    if kind == "track":
        return AuthoringTarget(
            object_kind=kind,
            object_id=request.track_id if hasattr(request, "track_id") else request.track.id,
            section_id=request.section_id,
        )
    if kind in {"curve_binding", "raster_binding"}:
        binding = getattr(request, "binding", None)
        object_id = request.binding_id if binding is None else binding.binding_id
        return AuthoringTarget(
            object_kind=kind,
            object_id=object_id,
            section_id=request.section_id,
            track_id=request.track_id,
        )
    if kind == "annotation":
        annotation = getattr(request, "annotation", None)
        object_id = request.annotation_id if annotation is None else annotation.annotation_id
        return AuthoringTarget(
            object_kind=kind,
            object_id=object_id,
            section_id=request.section_id,
            track_id=request.track_id,
        )
    if kind == "fill":
        fill = getattr(request, "fill", None)
        object_id = request.fill_id if fill is None else fill.fill_id
        if object_id is None and returned is not None:
            object_id = getattr(returned, "fill_id", None)
        if object_id is None:
            raise ValueError("Fill operation requires a stable fill_id for read-back.")
        return AuthoringTarget(
            object_kind=kind,
            object_id=object_id,
            section_id=request.section_id,
            track_id=request.track_id,
        )
    if kind == "remark":
        remark = getattr(request, "remark", None)
        object_id = getattr(request, "remark_id", None)
        if object_id is None and remark is not None:
            object_id = getattr(remark, "remark_id", None)
        if object_id is not None:
            return AuthoringTarget(object_kind=kind, object_id=object_id)
        if returned is None or getattr(returned, "remark_id", None) is None:
            raise ValueError("Remark create operation did not return a stable remark_id.")
        return AuthoringTarget(object_kind=kind, object_id=returned.remark_id)
    raise ValueError(f"Unsupported typed request kind {kind!r}.")


def _create_payload(request: BaseModel) -> BaseModel | None:
    """Return the complete object carried by a create request."""
    for field_name in ("section", "track", "binding", "annotation", "fill", "remark"):
        value = getattr(request, field_name, None)
        if isinstance(value, BaseModel):
            return value
    return None


def _same(left: object, right: object) -> bool:
    """Compare canonical models without exposing mutable instances."""
    if isinstance(left, BaseModel):
        left = left.model_dump(mode="python", exclude_none=False)
    if isinstance(right, BaseModel):
        right = right.model_dump(mode="python", exclude_none=False)
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        return dict(left) == dict(right)
    return left == right


def _same_create_payload(actual: BaseModel, expected: BaseModel, object_kind: str) -> bool:
    """Compare a create payload without treating later child writes as conflicts."""
    actual_data = actual.model_dump(mode="python", exclude_none=False)
    expected_data = expected.model_dump(mode="python", exclude_none=False)
    if object_kind == "section":
        actual_data.pop("tracks", None)
        expected_data.pop("tracks", None)
    elif object_kind == "track":
        for data in (actual_data, expected_data):
            data.pop("bindings", None)
            data.pop("annotations", None)
            data.pop("fills", None)
    return actual_data == expected_data


def _json_value(value: object) -> object:
    """Convert canonical values into stable JSON-compatible evidence."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", exclude_none=False)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _requested_evidence(request: BaseModel) -> dict[str, Any]:
    """Serialize the typed request that supplied an operation's expectation."""
    payload = request.model_dump(mode="json", exclude_unset=True)
    return dict(_json_value(payload))


def _target_snapshot(
    service: AuthoringService,
    target: AuthoringTarget | None,
) -> dict[str, Any] | None:
    """Read one target and its canonical collection index, if it exists."""
    if target is None:
        return None
    try:
        value = service.get(target)
    except (KeyError, ValueError, TypeError):
        return None
    references = service.list(
        target.object_kind,
        section_id=target.section_id,
        track_id=target.track_id,
    )
    reference = next((item for item in references if item.object_id == target.object_id), None)
    return {
        "value": _json_value(value),
        "index": None if reference is None else reference.index,
    }


def _outcome_context(
    operation: object,
    scope: AuthoringCompilationScope,
    work_units: Mapping[str, AuthoringRequestWorkUnit],
    *,
    status: TypedOperationExecutionStatus,
    defaults_provenance: Mapping[str, str] | None = None,
    target: AuthoringTarget | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    postcondition_verified: bool = False,
    message: str = "",
    error: str | None = None,
) -> TypedOperationOutcome:
    """Build one outcome with clause and hierarchy context attached."""
    typed_operation = operation
    work_unit = work_units.get(typed_operation.work_unit_id)
    persisted_index = None if after is None else after.get("index")
    return TypedOperationOutcome(
        branch=scope,
        operation_id=typed_operation.operation_id,
        work_unit_id=typed_operation.work_unit_id,
        request_item_id=None if work_unit is None else work_unit.request_item_id,
        clause_text=None if work_unit is None else work_unit.clause_text,
        natural_parent=None if work_unit is None else work_unit.natural_parent,
        action=typed_operation.action,
        object_kind=operation_request_object_kind(typed_operation.request),
        status=status,
        postcondition_verified=postcondition_verified,
        message=message,
        error=error,
        defaults_provenance=dict(defaults_provenance or {}),
        verification=TypedVerificationEvidence(
            target=target,
            requested=_requested_evidence(typed_operation.request),
            before=before,
            after=after,
            persisted_index=persisted_index,
        ),
    )


def _request_object_kind_from_envelope(operation: object) -> str:
    """Read object kind from a generated operation envelope."""
    return operation_request_object_kind(operation.request)


def _ordered_operations(
    submissions: Iterable[BaseModel],
    work_units: Mapping[str, AuthoringRequestWorkUnit],
) -> tuple[tuple[str, object], ...]:
    """Topologically order operations with stable branch and submission order."""
    candidates: list[tuple[str, object]] = []
    for scope in _SCOPE_ORDER:
        for submission in submissions:
            if getattr(submission, "branch", None) != scope:
                continue
            candidates.extend(
                (scope, operation) for operation in operation_submission_operations(submission)
            )
    by_id = {operation.operation_id: (scope, operation) for scope, operation in candidates}
    if len(by_id) != len(candidates):
        raise ValueError("Operation ids must be unique across all branch submissions.")
    phase_order = {phase: index for index, phase in enumerate(AuthoringOperationPhase)}
    scope_order = {scope: index for index, scope in enumerate(_SCOPE_ORDER)}
    candidate_order = {id(operation): index for index, (_, operation) in enumerate(candidates)}

    def priority(candidate: tuple[str, object]) -> tuple[int, int, int]:
        scope, operation = candidate
        work_unit = work_units.get(operation.work_unit_id)
        phase = None if work_unit is None else work_unit.phase
        return (
            99 if phase is None else phase_order[phase],
            scope_order[scope],
            candidate_order[id(operation)],
        )

    ordered: list[tuple[str, object]] = []
    remaining = list(candidates)
    while remaining:
        progress = False
        for candidate in sorted(remaining, key=priority):
            _, operation = candidate
            if all(
                dependency in {item[1].operation_id for item in ordered}
                for dependency in operation.depends_on
            ):
                ordered.append(candidate)
                remaining.remove(candidate)
                progress = True
        if not progress:
            unresolved = [item[1].operation_id for item in remaining]
            raise ValueError(f"Operation dependency cycle or missing dependency: {unresolved!r}.")
    return tuple(ordered)


def _apply_request(service: AuthoringService, request: BaseModel) -> BaseModel | None:
    """Apply one already-validated typed service request."""
    if isinstance(request, RemoveRequest):
        service.remove(request)
        return None
    if isinstance(request, MoveRequest):
        return service.move(request)
    if isinstance(request, CreateRequest.__args__):
        return service.create(request)
    if isinstance(request, UpdateRequest.__args__):
        return service.update(request)
    raise TypeError(f"Unsupported typed request {type(request).__name__}.")


def _target_exists(service: AuthoringService, target: AuthoringTarget) -> bool:
    """Return whether a canonical target currently exists."""
    try:
        service.get(target)
    except (KeyError, ValueError, TypeError):
        return False
    return True


def execute_typed_submissions(
    service: AuthoringService,
    submissions: Iterable[BaseModel],
    work_units: Iterable[AuthoringRequestWorkUnit],
    *,
    defaults_provenance_by_operation: Mapping[str, Mapping[str, str]] | None = None,
) -> TypedSubmissionExecutionResult:
    """Execute typed branch submissions atomically with canonical read-back."""
    submission_list = tuple(submissions)
    work_unit_list = tuple(work_units)
    work_unit_by_id = {unit.unit_id: unit for unit in work_unit_list}
    all_operations = tuple(
        operation
        for submission in submission_list
        for operation in operation_submission_operations(submission)
    )
    all_operation_ids = {operation.operation_id for operation in all_operations}
    validation_errors: list[str] = []
    for submission in submission_list:
        scope = getattr(submission, "branch", None)
        if scope not in _SCOPE_ORDER:
            validation_errors.append(f"Unsupported submission branch {scope!r}.")
            continue
        validation_errors.extend(
            validate_operation_submission(
                scope,
                submission,
                work_unit_list,
                external_operation_ids=all_operation_ids,
            )
        )
    if validation_errors:
        return TypedSubmissionExecutionResult(
            success=False,
            stopped=True,
            document=service.document,
            errors=tuple(validation_errors),
        )

    working_service = AuthoringService(service.document)
    outcomes: list[TypedOperationOutcome] = []
    applied_ids: list[str] = []
    try:
        ordered = _ordered_operations(submission_list, work_unit_by_id)
    except ValueError as exc:
        return TypedSubmissionExecutionResult(
            success=False,
            stopped=True,
            document=service.document,
            errors=(str(exc),),
        )

    phase_summaries: list[TypedPhaseCheckpoint] = []
    current_phase: AuthoringOperationPhase | None = None
    current_phase_operation_ids: list[str] = []
    current_phase_applied = 0

    def checkpoint(phase: AuthoringOperationPhase, status: TypedOperationExecutionStatus) -> None:
        """Record the current transactional snapshot for one operation phase."""
        phase_summaries.append(
            TypedPhaseCheckpoint(
                phase=phase,
                status=status,
                operation_ids=tuple(current_phase_operation_ids),
                applied_count=current_phase_applied,
                document=AuthoringDocumentSpec.model_validate(
                    working_service.document.model_dump(mode="python")
                ),
            )
        )

    for scope, operation in ordered:
        work_unit = work_unit_by_id.get(operation.work_unit_id)
        operation_phase = None if work_unit is None else work_unit.phase
        if operation_phase is not None and operation_phase != current_phase:
            if current_phase is not None:
                checkpoint(current_phase, TypedOperationExecutionStatus.COMPLETED)
            current_phase = operation_phase
            current_phase_operation_ids = []
            current_phase_applied = 0
        if operation_phase is not None:
            current_phase_operation_ids.append(operation.operation_id)
        missing = [
            dependency for dependency in operation.depends_on if dependency not in applied_ids
        ]
        if missing:
            message = f"Missing completed dependencies: {', '.join(missing)}."
            outcomes.append(
                _outcome_context(
                    operation,
                    scope,
                    work_unit_by_id,
                    status=TypedOperationExecutionStatus.BLOCKED,
                    defaults_provenance=(defaults_provenance_by_operation or {}).get(
                        operation.operation_id
                    ),
                    error=message,
                )
            )
            if operation_phase is not None:
                checkpoint(operation_phase, TypedOperationExecutionStatus.BLOCKED)
            return TypedSubmissionExecutionResult(
                success=False,
                stopped=True,
                document=service.document,
                outcomes=tuple(outcomes),
                phase_summaries=tuple(phase_summaries),
                applied_operation_ids=tuple(applied_ids),
                errors=(f"{operation.operation_id}: {message}",),
            )
        target: AuthoringTarget | None = None
        before: dict[str, Any] | None = None
        after: dict[str, Any] | None = None
        object_kind = _request_object_kind_from_envelope(operation)
        try:
            request = operation.request
            if operation.action == "create" and object_kind in {"remark", "fill"}:
                payload = _create_payload(request)
                identity_field = "remark_id" if object_kind == "remark" else "fill_id"
                if payload is None or getattr(payload, identity_field, None) is None:
                    raise ValueError(
                        f"Create operation {operation.operation_id!r} requires a stable "
                        f"{object_kind} identity ({identity_field})."
                    )
            target = _request_target(request)
            before = _target_snapshot(working_service, target)
            if operation.action == "create" and target is not None and before is not None:
                actual = working_service.get(target)
                expected = _create_payload(request)
                if (
                    expected is None
                    or not isinstance(actual, BaseModel)
                    or not _same_create_payload(actual, expected, object_kind)
                ):
                    raise ValueError(
                        f"Create operation {operation.operation_id!r} conflicts with "
                        f"existing {object_kind} {target.object_id!r}."
                    )
                after = before
                outcomes.append(
                    _outcome_context(
                        operation,
                        scope,
                        work_unit_by_id,
                        status=TypedOperationExecutionStatus.SKIPPED,
                        defaults_provenance=(defaults_provenance_by_operation or {}).get(
                            operation.operation_id
                        ),
                        target=target,
                        before=before,
                        after=after,
                        postcondition_verified=True,
                        message="Target already exists; operation is idempotently satisfied.",
                    )
                )
                applied_ids.append(operation.operation_id)
                if operation_phase is not None:
                    current_phase_applied += 1
                continue
            returned = _apply_request(working_service, request)
            if operation.action == "remove":
                verified = target is not None and not _target_exists(working_service, target)
                after = None
            elif operation.action == "move":
                after = _target_snapshot(working_service, target)
                verified = after is not None and after["index"] == request.new_index
            else:
                read_target = _request_target(request, returned)
                actual = working_service.get(read_target)
                after = _target_snapshot(working_service, read_target)
                verified = returned is not None and _same(actual, returned)
            if not verified:
                raise RuntimeError("Canonical read-after-write verification failed.")
        except Exception as exc:  # noqa: BLE001 - deterministic boundary report
            message = str(exc) or exc.__class__.__name__
            if target is not None:
                after = _target_snapshot(working_service, target)
            outcomes.append(
                _outcome_context(
                    operation,
                    scope,
                    work_unit_by_id,
                    status=TypedOperationExecutionStatus.BLOCKED,
                    defaults_provenance=(defaults_provenance_by_operation or {}).get(
                        operation.operation_id
                    ),
                    target=target,
                    before=before,
                    after=after,
                    error=message,
                )
            )
            if operation_phase is not None:
                checkpoint(operation_phase, TypedOperationExecutionStatus.BLOCKED)
            return TypedSubmissionExecutionResult(
                success=False,
                stopped=True,
                document=service.document,
                outcomes=tuple(outcomes),
                phase_summaries=tuple(phase_summaries),
                applied_operation_ids=tuple(applied_ids),
                errors=(f"{operation.operation_id}: {message}",),
            )
        outcomes.append(
            _outcome_context(
                operation,
                scope,
                work_unit_by_id,
                status=TypedOperationExecutionStatus.COMPLETED,
                defaults_provenance=(defaults_provenance_by_operation or {}).get(
                    operation.operation_id
                ),
                target=target,
                before=before,
                after=after,
                postcondition_verified=True,
                message=f"Applied and verified in {scope} branch.",
            )
        )
        applied_ids.append(operation.operation_id)
        if operation_phase is not None:
            current_phase_applied += 1

    if current_phase is not None:
        checkpoint(current_phase, TypedOperationExecutionStatus.COMPLETED)

    service.replace_document(working_service.document)
    return TypedSubmissionExecutionResult(
        success=True,
        stopped=False,
        document=service.document,
        outcomes=tuple(outcomes),
        phase_summaries=tuple(phase_summaries),
        applied_operation_ids=tuple(applied_ids),
    )


__all__ = [
    "TypedOperationExecutionStatus",
    "TypedOperationOutcome",
    "TypedPhaseCheckpoint",
    "TypedSubmissionExecutionResult",
    "TypedVerificationEvidence",
    "execute_typed_submissions",
]
