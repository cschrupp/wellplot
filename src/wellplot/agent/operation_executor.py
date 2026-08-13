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

from pydantic import BaseModel, ConfigDict

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


class TypedOperationOutcome(BaseModel):
    """Read-after-write outcome for one typed service request."""

    model_config = ConfigDict(extra="forbid")

    operation_id: str
    work_unit_id: str
    action: str
    object_kind: str
    status: TypedOperationExecutionStatus
    postcondition_verified: bool = False
    message: str = ""
    error: str | None = None


class TypedSubmissionExecutionResult(BaseModel):
    """Atomic result for one or more hierarchy-scoped submissions."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    stopped: bool
    document: AuthoringDocumentSpec
    outcomes: tuple[TypedOperationOutcome, ...] = ()
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


def _request_object_kind_from_envelope(operation: object) -> str:
    """Read object kind from a generated operation envelope."""
    return operation_request_object_kind(operation.request)


def _ordered_operations(
    submissions: Iterable[BaseModel],
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
    ordered: list[tuple[str, object]] = []
    remaining = list(candidates)
    while remaining:
        progress = False
        for candidate in list(remaining):
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
) -> TypedSubmissionExecutionResult:
    """Execute typed branch submissions atomically with canonical read-back."""
    submission_list = tuple(submissions)
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
                work_units,
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
        ordered = _ordered_operations(submission_list)
    except ValueError as exc:
        return TypedSubmissionExecutionResult(
            success=False,
            stopped=True,
            document=service.document,
            errors=(str(exc),),
        )

    for scope, operation in ordered:
        missing = [
            dependency for dependency in operation.depends_on if dependency not in applied_ids
        ]
        object_kind = _request_object_kind_from_envelope(operation)
        if missing:
            message = f"Missing completed dependencies: {', '.join(missing)}."
            outcomes.append(
                TypedOperationOutcome(
                    operation_id=operation.operation_id,
                    work_unit_id=operation.work_unit_id,
                    action=operation.action,
                    object_kind=object_kind,
                    status=TypedOperationExecutionStatus.BLOCKED,
                    error=message,
                )
            )
            return TypedSubmissionExecutionResult(
                success=False,
                stopped=True,
                document=service.document,
                outcomes=tuple(outcomes),
                applied_operation_ids=tuple(applied_ids),
                errors=(f"{operation.operation_id}: {message}",),
            )
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
            if (
                operation.action == "create"
                and target is not None
                and _target_exists(working_service, target)
            ):
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
                outcomes.append(
                    TypedOperationOutcome(
                        operation_id=operation.operation_id,
                        work_unit_id=operation.work_unit_id,
                        action=operation.action,
                        object_kind=object_kind,
                        status=TypedOperationExecutionStatus.SKIPPED,
                        postcondition_verified=True,
                        message="Target already exists; operation is idempotently satisfied.",
                    )
                )
                applied_ids.append(operation.operation_id)
                continue
            returned = _apply_request(working_service, request)
            if operation.action == "remove":
                verified = target is not None and not _target_exists(working_service, target)
            elif operation.action == "move":
                if target is None:
                    verified = False
                else:
                    references = working_service.list(
                        target.object_kind,
                        section_id=target.section_id,
                    )
                    reference = next(
                        (item for item in references if item.object_id == target.object_id),
                        None,
                    )
                    verified = reference is not None and reference.index == request.new_index
            else:
                read_target = _request_target(request, returned)
                actual = working_service.get(read_target)
                verified = returned is not None and _same(actual, returned)
            if not verified:
                raise RuntimeError("Canonical read-after-write verification failed.")
        except Exception as exc:  # noqa: BLE001 - deterministic boundary report
            message = str(exc) or exc.__class__.__name__
            outcomes.append(
                TypedOperationOutcome(
                    operation_id=operation.operation_id,
                    work_unit_id=operation.work_unit_id,
                    action=operation.action,
                    object_kind=object_kind,
                    status=TypedOperationExecutionStatus.BLOCKED,
                    error=message,
                )
            )
            return TypedSubmissionExecutionResult(
                success=False,
                stopped=True,
                document=service.document,
                outcomes=tuple(outcomes),
                applied_operation_ids=tuple(applied_ids),
                errors=(f"{operation.operation_id}: {message}",),
            )
        outcomes.append(
            TypedOperationOutcome(
                operation_id=operation.operation_id,
                work_unit_id=operation.work_unit_id,
                action=operation.action,
                object_kind=object_kind,
                status=TypedOperationExecutionStatus.COMPLETED,
                postcondition_verified=True,
                message=f"Applied and verified in {scope} branch.",
            )
        )
        applied_ids.append(operation.operation_id)

    service.replace_document(working_service.document)
    return TypedSubmissionExecutionResult(
        success=True,
        stopped=False,
        document=service.document,
        outcomes=tuple(outcomes),
        applied_operation_ids=tuple(applied_ids),
    )


__all__ = [
    "TypedOperationExecutionStatus",
    "TypedOperationOutcome",
    "TypedSubmissionExecutionResult",
    "execute_typed_submissions",
]
