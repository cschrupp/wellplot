###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
###############################################################################

"""Deterministic execution and verification of authoring operation plans."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from .authoring_reconciler import (
    AuthoringOperation,
    AuthoringOperationAction,
    AuthoringOperationObjectKind,
    AuthoringOperationPhase,
    AuthoringReconciliationPlan,
)
from .authoring_service import (
    AuthoringService,
    AuthoringTarget,
    CreateAnnotationRequest,
    CreateCurveBindingRequest,
    CreateFillRequest,
    CreateRasterBindingRequest,
    CreateRemarkRequest,
    CreateSectionRequest,
    CreateTrackRequest,
    CurveBindingPatch,
    DepthPatch,
    MoveRequest,
    PagePatch,
    RasterBindingPatch,
    RemarkPatch,
    RemoveRequest,
    ReportPatch,
    SectionPatch,
    TrackPatch,
    UpdateAnnotationRequest,
    UpdateCurveBindingRequest,
    UpdateDepthRequest,
    UpdateFillRequest,
    UpdateHeaderRequest,
    UpdateOutputRequest,
    UpdatePageRequest,
    UpdateRasterBindingRequest,
    UpdateRemarkRequest,
    UpdateReportRequest,
    UpdateSectionRequest,
    UpdateTailRequest,
    UpdateTrackRequest,
)
from .model.authoring import (
    AnnotationSpec,
    AuthoringDepthSpec,
    AuthoringDocumentSpec,
    AuthoringHeaderSpec,
    AuthoringOutputSpec,
    AuthoringPageSpec,
    AuthoringRemarkSpec,
    AuthoringSectionSpec,
    AuthoringStyle,
    AuthoringTailSpec,
    CurveBindingSpec,
    CurveFillSpec,
    RasterBindingSpec,
    TrackSpec,
)


class _ExecutorModel(BaseModel):
    """Strict base model for deterministic execution results."""

    model_config = ConfigDict(extra="forbid")


class AuthoringExecutionStatus(StrEnum):
    """Status values for operations and phase checkpoints."""

    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    SKIPPED = "skipped"


class AuthoringOperationOutcome(_ExecutorModel):
    """Read-after-write result for one operation."""

    operation_id: str
    phase: AuthoringOperationPhase
    action: AuthoringOperationAction
    object_kind: AuthoringOperationObjectKind
    object_id: str
    status: AuthoringExecutionStatus
    postcondition_verified: bool = False
    message: str = ""
    error: str | None = None


class AuthoringPhaseCheckpoint(_ExecutorModel):
    """Persisted canonical snapshot and optional preview after one phase."""

    phase: AuthoringOperationPhase
    status: AuthoringExecutionStatus
    operation_ids: tuple[str, ...] = ()
    applied_count: int = 0
    document: AuthoringDocumentSpec
    preview_png: bytes | None = Field(default=None, repr=False)
    preview_error: str | None = None


class AuthoringExecutionResult(_ExecutorModel):
    """Complete execution report for one deterministic operation plan."""

    success: bool
    stopped: bool
    document: AuthoringDocumentSpec
    outcomes: tuple[AuthoringOperationOutcome, ...] = ()
    phase_summaries: tuple[AuthoringPhaseCheckpoint, ...] = ()
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


PreviewCallback = Callable[[AuthoringDocumentSpec, AuthoringOperationPhase], bytes | None]


@dataclass(frozen=True)
class _ExpectedState:
    """Internal postcondition representation."""

    kind: str
    value: object


_MISSING = object()


def _plain(value: object) -> object:
    """Convert canonical models and tuples to comparable structures."""
    if isinstance(value, BaseModel):
        return {
            key: _plain(item)
            for key, item in value.model_dump(mode="python", exclude_none=False).items()
        }
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    return value


def _mapping(value: object) -> Mapping[str, Any]:
    """Return a mapping view for one canonical value."""
    plain = _plain(value)
    return plain if isinstance(plain, Mapping) else {}


def _same(left: object, right: object) -> bool:
    """Compare canonical values without enum/tuple representation differences."""
    return _plain(left) == _plain(right)


def _items(value: object) -> Sequence[object]:
    """Return a safe sequence for an optional canonical collection."""
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value
    return ()


def _merge(current: object, patch: object) -> object:
    """Recursively merge a partial mapping into a canonical mapping."""
    if not isinstance(patch, Mapping):
        return deepcopy(patch)
    result = deepcopy(dict(_mapping(current)))
    for key, value in patch.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _clear_marker(value: object) -> bool:
    """Return whether a value is the G4 explicit clear marker."""
    return isinstance(value, Mapping) and value.get("operation") == "clear"


def _resolve_clears(value: object, defaults: object = _MISSING) -> object:
    """Translate clear markers into canonical reset values before validation."""
    if _clear_marker(value):
        if defaults is not _MISSING:
            return deepcopy(defaults)
        return None
    if isinstance(value, Mapping):
        default_mapping = defaults if isinstance(defaults, Mapping) else {}
        return {
            key: _resolve_clears(item, default_mapping.get(key, _MISSING))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_resolve_clears(item) for item in value]
    return deepcopy(value)


def _omit_undefined(value: object) -> object:
    """Drop omitted partial-intent fields before validating a created object."""
    if isinstance(value, Mapping):
        return {key: _omit_undefined(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_omit_undefined(item) for item in value]
    return deepcopy(value)


def _find_by_id(items: object, field_name: str, object_id: str) -> object:
    """Find a stable object identity in a canonical collection."""
    for item in _items(items):
        mapping = _mapping(item)
        if mapping.get(field_name) == object_id or (
            field_name in {"section_id", "track_id"} and mapping.get("id") == object_id
        ):
            return item
    return _MISSING


def _find_header_slot(document: AuthoringDocumentSpec, slot_id: str) -> object:
    """Find one general, service-title, or detail header slot."""
    header = document.header
    if header is None:
        return _MISSING
    for collection_name in ("general_fields", "service_titles"):
        found = _find_by_id(getattr(header, collection_name), "slot_id", slot_id)
        if found is not _MISSING:
            return found
    if header.detail is None:
        return _MISSING
    for row in header.detail.rows:
        found = _find_by_id(row.values, "slot_id", slot_id)
        if found is not _MISSING:
            return found
        for column in row.columns:
            found = _find_by_id(column.cells, "slot_id", slot_id)
            if found is not _MISSING:
                return found
    return _MISSING


def _target_exists(service: AuthoringService, operation: AuthoringOperation) -> bool:
    """Check a target precondition without mutating the service."""
    kind = operation.object_kind
    if kind in {
        AuthoringOperationObjectKind.REPORT,
        AuthoringOperationObjectKind.PAGE,
        AuthoringOperationObjectKind.DEPTH,
        AuthoringOperationObjectKind.OUTPUT,
        AuthoringOperationObjectKind.TAIL,
        AuthoringOperationObjectKind.HEADER,
    }:
        return True
    if kind == AuthoringOperationObjectKind.HEADER_SLOT:
        return _find_header_slot(service.document, operation.object_id) is not _MISSING
    try:
        service.get(
            AuthoringTarget(
                object_kind=kind.value,
                object_id=operation.object_id,
                section_id=operation.section_id,
                track_id=operation.track_id,
            )
        )
    except (KeyError, ValueError, TypeError):
        return False
    return True


def _target_value(service: AuthoringService, operation: AuthoringOperation) -> object:
    """Read one persisted target after an operation."""
    kind = operation.object_kind
    if kind == AuthoringOperationObjectKind.HEADER_SLOT:
        value = _find_header_slot(service.document, operation.object_id)
        if value is _MISSING:
            raise KeyError(f"Unknown header slot {operation.object_id!r}.")
        return deepcopy(value)
    return service.get(
        AuthoringTarget(
            object_kind=kind.value,
            object_id=operation.object_id,
            section_id=operation.section_id,
            track_id=operation.track_id,
        )
    )


def _subset(actual: object, expected: object) -> bool:
    """Check that a persisted canonical value contains an expected payload."""
    if isinstance(expected, Mapping):
        actual_mapping = _mapping(actual)
        return all(
            key in actual_mapping and _subset(actual_mapping[key], value)
            for key, value in expected.items()
        )
    if isinstance(expected, list):
        actual_items = _items(actual)
        return len(actual_items) == len(expected) and all(
            _subset(actual_item, expected_item)
            for actual_item, expected_item in zip(actual_items, expected, strict=True)
        )
    return _same(actual, expected)


def _validate_plan(plan: AuthoringReconciliationPlan) -> list[str]:
    """Validate operation IDs, dependency references, and dependency order."""
    errors: list[str] = []
    positions: dict[str, int] = {}
    for index, operation in enumerate(plan.operations):
        if operation.operation_id in positions:
            errors.append(f"Duplicate operation id {operation.operation_id!r}.")
        positions[operation.operation_id] = index
    for index, operation in enumerate(plan.operations):
        for dependency in operation.depends_on:
            if dependency not in positions:
                errors.append(
                    f"Operation {operation.operation_id!r} depends on unknown operation "
                    f"{dependency!r}."
                )
            elif positions[dependency] >= index:
                errors.append(
                    f"Operation {operation.operation_id!r} depends on a later operation "
                    f"{dependency!r}."
                )
    return errors


class AuthoringExecutor:
    """Execute and verify a G4 plan against one deterministic service."""

    def __init__(self, service: AuthoringService) -> None:
        """Bind the executor to one service-owned canonical document."""
        self.service = service

    def execute(
        self,
        plan: AuthoringReconciliationPlan,
        *,
        preview_callback: PreviewCallback | None = None,
    ) -> AuthoringExecutionResult:
        """Apply operations until the first failed precondition or postcondition."""
        document = self.service.document
        if not plan.ready:
            errors = tuple(f"{issue.code}: {issue.message}" for issue in plan.issues)
            return AuthoringExecutionResult(
                success=False,
                stopped=True,
                document=document,
                errors=errors,
            )
        plan_errors = _validate_plan(plan)
        if plan_errors:
            return AuthoringExecutionResult(
                success=False,
                stopped=True,
                document=document,
                errors=tuple(plan_errors),
            )

        outcomes: list[AuthoringOperationOutcome] = []
        checkpoints: list[AuthoringPhaseCheckpoint] = []
        errors: list[str] = []
        warnings: list[str] = []
        applied_ids: set[str] = set()
        operation_index = 0
        for phase in AuthoringOperationPhase:
            phase_operations = [item for item in plan.operations if item.phase == phase]
            if not phase_operations:
                continue
            phase_status = AuthoringExecutionStatus.COMPLETED
            phase_applied = 0
            for operation in phase_operations:
                operation_index += 1
                missing_dependencies = [
                    dependency
                    for dependency in operation.depends_on
                    if dependency not in applied_ids
                ]
                if missing_dependencies:
                    message = f"Missing completed dependencies: {', '.join(missing_dependencies)}."
                    outcomes.append(self._failed_outcome(operation, message))
                    errors.append(f"{operation.operation_id}: {message}")
                    phase_status = AuthoringExecutionStatus.BLOCKED
                    break
                expected_exists = operation.action != AuthoringOperationAction.CREATE
                if _target_exists(self.service, operation) != expected_exists:
                    expected = "exist" if expected_exists else "not exist"
                    message = f"Precondition failed: target was expected to {expected}."
                    outcomes.append(self._failed_outcome(operation, message))
                    errors.append(f"{operation.operation_id}: {message}")
                    phase_status = AuthoringExecutionStatus.BLOCKED
                    break
                try:
                    expected = self._apply(operation)
                    if not self._verify(operation, expected):
                        raise RuntimeError("Read-after-write postcondition did not match.")
                except Exception as exc:  # noqa: BLE001 - report deterministic boundary errors
                    message = str(exc) or exc.__class__.__name__
                    outcomes.append(self._failed_outcome(operation, message))
                    errors.append(f"{operation.operation_id}: {message}")
                    phase_status = AuthoringExecutionStatus.BLOCKED
                    break
                outcomes.append(
                    AuthoringOperationOutcome(
                        operation_id=operation.operation_id,
                        phase=operation.phase,
                        action=operation.action,
                        object_kind=operation.object_kind,
                        object_id=operation.object_id,
                        status=AuthoringExecutionStatus.COMPLETED,
                        postcondition_verified=True,
                        message="Applied and verified.",
                    )
                )
                applied_ids.add(operation.operation_id)
                phase_applied += 1
            if phase_status == AuthoringExecutionStatus.COMPLETED and phase_applied > 0:
                preview_png, preview_error = self._capture_preview(phase, preview_callback)
            else:
                preview_png, preview_error = None, None
            if preview_error:
                warnings.append(f"{phase.value}: {preview_error}")
            checkpoints.append(
                AuthoringPhaseCheckpoint(
                    phase=phase,
                    status=phase_status,
                    operation_ids=tuple(item.operation_id for item in phase_operations),
                    applied_count=phase_applied,
                    document=self.service.document,
                    preview_png=preview_png,
                    preview_error=preview_error,
                )
            )
            if phase_status == AuthoringExecutionStatus.BLOCKED:
                break
        return AuthoringExecutionResult(
            success=not errors,
            stopped=bool(errors),
            document=self.service.document,
            outcomes=tuple(outcomes),
            phase_summaries=tuple(checkpoints),
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

    def _capture_preview(
        self,
        phase: AuthoringOperationPhase,
        callback: PreviewCallback | None,
    ) -> tuple[bytes | None, str | None]:
        """Capture one optional preview from the persisted service snapshot."""
        if callback is None:
            return None, None
        try:
            preview = callback(self.service.document, phase)
        except Exception as exc:  # noqa: BLE001 - preview is an optional boundary
            return None, f"Preview callback failed: {exc}"
        if preview is not None and not isinstance(preview, bytes):
            return None, "Preview callback must return bytes or None."
        return preview, None

    @staticmethod
    def _failed_outcome(operation: AuthoringOperation, message: str) -> AuthoringOperationOutcome:
        """Build one failed operation result without claiming a write occurred."""
        return AuthoringOperationOutcome(
            operation_id=operation.operation_id,
            phase=operation.phase,
            action=operation.action,
            object_kind=operation.object_kind,
            object_id=operation.object_id,
            status=AuthoringExecutionStatus.BLOCKED,
            postcondition_verified=False,
            message="Execution stopped.",
            error=message,
        )

    def _apply(self, operation: AuthoringOperation) -> _ExpectedState:
        """Translate one plan operation to a typed service request."""
        if operation.action == AuthoringOperationAction.CREATE:
            return self._create(operation)
        if operation.action == AuthoringOperationAction.UPDATE:
            return self._update(operation)
        if operation.action == AuthoringOperationAction.REMOVE:
            self.service.remove(
                RemoveRequest(
                    target=AuthoringTarget(
                        object_kind=operation.object_kind.value,
                        object_id=operation.object_id,
                        section_id=operation.section_id,
                        track_id=operation.track_id,
                    )
                )
            )
            return _ExpectedState("removed", None)
        if operation.action == AuthoringOperationAction.MOVE:
            new_index = operation.payload.get("new_index")
            self.service.move(
                MoveRequest(
                    object_kind=operation.object_kind.value,
                    object_id=operation.object_id,
                    section_id=operation.section_id,
                    new_index=new_index,
                )
            )
            return _ExpectedState("moved", new_index)
        raise TypeError(f"Unsupported action {operation.action!r}.")

    def _create(self, operation: AuthoringOperation) -> _ExpectedState:
        """Create and validate one canonical object through the service."""
        raw = operation.payload.get("object")
        if not isinstance(raw, Mapping):
            raise ValueError("Create operation requires an object mapping.")
        value_mapping = _omit_undefined(_resolve_clears(raw))
        if not isinstance(value_mapping, Mapping):
            raise ValueError("Create operation did not resolve to an object mapping.")
        if operation.object_kind == AuthoringOperationObjectKind.SECTION:
            value = AuthoringSectionSpec.model_validate(value_mapping)
            self.service.create(CreateSectionRequest(section=value))
        elif operation.object_kind == AuthoringOperationObjectKind.TRACK:
            value = TypeAdapter(TrackSpec).validate_python(value_mapping)
            self.service.create(
                CreateTrackRequest(
                    section_id=self._required_scope(operation, "section"),
                    track=value,
                )
            )
        elif operation.object_kind == AuthoringOperationObjectKind.CURVE_BINDING:
            value = CurveBindingSpec.model_validate(value_mapping)
            self.service.create(
                CreateCurveBindingRequest(
                    section_id=self._required_scope(operation, "section"),
                    track_id=self._required_scope(operation, "track"),
                    binding=value,
                )
            )
        elif operation.object_kind == AuthoringOperationObjectKind.RASTER_BINDING:
            value = RasterBindingSpec.model_validate(value_mapping)
            self.service.create(
                CreateRasterBindingRequest(
                    section_id=self._required_scope(operation, "section"),
                    track_id=self._required_scope(operation, "track"),
                    binding=value,
                )
            )
        elif operation.object_kind == AuthoringOperationObjectKind.ANNOTATION:
            value = TypeAdapter(AnnotationSpec).validate_python(value_mapping)
            self.service.create(
                CreateAnnotationRequest(
                    section_id=self._required_scope(operation, "section"),
                    track_id=self._required_scope(operation, "track"),
                    annotation=value,
                )
            )
        elif operation.object_kind == AuthoringOperationObjectKind.FILL:
            value = CurveFillSpec.model_validate(value_mapping)
            self.service.create(
                CreateFillRequest(
                    section_id=self._required_scope(operation, "section"),
                    track_id=self._required_scope(operation, "track"),
                    fill=value,
                )
            )
        elif operation.object_kind == AuthoringOperationObjectKind.REMARK:
            value = AuthoringRemarkSpec.model_validate(value_mapping)
            self.service.create(CreateRemarkRequest(remark=value))
        else:
            raise ValueError(f"Create is unsupported for {operation.object_kind.value!r}.")
        return _ExpectedState("subset", value_mapping)

    def _update(self, operation: AuthoringOperation) -> _ExpectedState:
        """Update one canonical object, merging replacements where required."""
        payload = operation.payload
        kind = operation.object_kind
        if "clear" in payload:
            return self._clear_singleton(operation)
        patch = payload.get("patch")
        if kind == AuthoringOperationObjectKind.REPORT:
            value = _resolve_clears(patch or {}, {"title": None, "subtitle": None})
            self.service.update(UpdateReportRequest(patch=ReportPatch.model_validate(value)))
            return _ExpectedState("subset", value)
        if kind == AuthoringOperationObjectKind.PAGE:
            value = _resolve_clears(patch or {}, AuthoringPageSpec().model_dump(mode="python"))
            self.service.update(UpdatePageRequest(patch=PagePatch.model_validate(value)))
            return _ExpectedState("subset", value)
        if kind == AuthoringOperationObjectKind.DEPTH:
            value = _resolve_clears(patch or {}, AuthoringDepthSpec().model_dump(mode="python"))
            self.service.update(UpdateDepthRequest(patch=DepthPatch.model_validate(value)))
            return _ExpectedState("subset", value)
        if kind == AuthoringOperationObjectKind.OUTPUT:
            current = self.service.document.output.model_dump(mode="python")
            value = _merge(
                current,
                _resolve_clears(patch or {}, AuthoringOutputSpec().model_dump(mode="python")),
            )
            output = AuthoringOutputSpec.model_validate(value)
            self.service.update(UpdateOutputRequest(output=output))
            return _ExpectedState("replacement", output)
        if kind == AuthoringOperationObjectKind.TAIL:
            current = self.service.document.tail.model_dump(mode="python")
            value = _merge(
                current,
                _resolve_clears(patch or {}, AuthoringTailSpec().model_dump(mode="python")),
            )
            tail = AuthoringTailSpec.model_validate(value)
            self.service.update(UpdateTailRequest(tail=tail))
            return _ExpectedState("replacement", tail)
        if kind == AuthoringOperationObjectKind.HEADER:
            return self._update_header(operation, patch)
        if kind == AuthoringOperationObjectKind.HEADER_SLOT:
            return self._update_header_slot(operation, patch)
        if kind == AuthoringOperationObjectKind.SECTION:
            value = _resolve_clears(
                patch or {},
                {
                    "subtitle": None,
                    "depth_range": None,
                    "data_source": None,
                    "extensions": {},
                },
            )
            self.service.update(
                UpdateSectionRequest(
                    section_id=operation.object_id,
                    patch=SectionPatch.model_validate(value),
                )
            )
            return _ExpectedState("subset", value)
        if kind == AuthoringOperationObjectKind.TRACK:
            value = _resolve_clears(
                patch or {},
                {
                    "x_scale": None,
                    "reference": None,
                    "grid": None,
                    "track_header": None,
                    "extensions": {},
                },
            )
            self.service.update(
                UpdateTrackRequest(
                    section_id=self._required_scope(operation, "section"),
                    track_id=operation.object_id,
                    patch=TrackPatch.model_validate(value),
                )
            )
            return _ExpectedState("subset", value)
        if kind == AuthoringOperationObjectKind.CURVE_BINDING:
            value = _resolve_clears(
                patch or {},
                {"style": dict.fromkeys(AuthoringStyle.model_fields, None)},
            )
            self.service.update(
                UpdateCurveBindingRequest(
                    section_id=self._required_scope(operation, "section"),
                    track_id=self._required_scope(operation, "track"),
                    binding_id=operation.object_id,
                    patch=CurveBindingPatch.model_validate(value),
                )
            )
            return _ExpectedState("subset", value)
        if kind == AuthoringOperationObjectKind.RASTER_BINDING:
            value = _resolve_clears(
                patch or {},
                {"style": dict.fromkeys(AuthoringStyle.model_fields, None)},
            )
            self.service.update(
                UpdateRasterBindingRequest(
                    section_id=self._required_scope(operation, "section"),
                    track_id=self._required_scope(operation, "track"),
                    binding_id=operation.object_id,
                    patch=RasterBindingPatch.model_validate(value),
                )
            )
            return _ExpectedState("subset", value)
        if kind == AuthoringOperationObjectKind.ANNOTATION:
            raw = payload.get("object")
            value = TypeAdapter(AnnotationSpec).validate_python(_resolve_clears(raw))
            self.service.update(
                UpdateAnnotationRequest(
                    section_id=self._required_scope(operation, "section"),
                    track_id=self._required_scope(operation, "track"),
                    annotation_id=operation.object_id,
                    annotation=value,
                )
            )
            return _ExpectedState("replacement", value)
        if kind == AuthoringOperationObjectKind.FILL:
            current = self.service.get(
                AuthoringTarget(
                    object_kind="fill",
                    object_id=operation.object_id,
                    section_id=self._required_scope(operation, "section"),
                    track_id=self._required_scope(operation, "track"),
                )
            )
            value = _merge(current, _resolve_clears(patch or {}))
            fill = CurveFillSpec.model_validate(value)
            self.service.update(
                UpdateFillRequest(
                    section_id=self._required_scope(operation, "section"),
                    track_id=self._required_scope(operation, "track"),
                    fill_id=operation.object_id,
                    fill=fill,
                )
            )
            return _ExpectedState("replacement", fill)
        if kind == AuthoringOperationObjectKind.REMARK:
            value = _resolve_clears(patch or {})
            self.service.update(
                UpdateRemarkRequest(
                    remark_id=operation.object_id,
                    patch=RemarkPatch.model_validate(value),
                )
            )
            return _ExpectedState("subset", value)
        raise ValueError(f"Update is unsupported for {kind.value!r}.")

    def _clear_singleton(self, operation: AuthoringOperation) -> _ExpectedState:
        """Reset one document-level settings object to its canonical defaults."""
        kind = operation.object_kind
        if kind == AuthoringOperationObjectKind.OUTPUT:
            value = AuthoringOutputSpec()
            self.service.update(UpdateOutputRequest(output=value))
            return _ExpectedState("replacement", value)
        if kind == AuthoringOperationObjectKind.PAGE:
            value = AuthoringPageSpec()
            self.service.update(
                UpdatePageRequest(patch=PagePatch.model_validate(value.model_dump()))
            )
            return _ExpectedState("replacement", value)
        if kind == AuthoringOperationObjectKind.DEPTH:
            value = AuthoringDepthSpec()
            self.service.update(
                UpdateDepthRequest(patch=DepthPatch.model_validate(value.model_dump()))
            )
            return _ExpectedState("replacement", value)
        if kind == AuthoringOperationObjectKind.HEADER:
            value = AuthoringHeaderSpec()
            self.service.update(UpdateHeaderRequest(header=value))
            return _ExpectedState("replacement", value)
        if kind == AuthoringOperationObjectKind.TAIL:
            value = AuthoringTailSpec()
            self.service.update(UpdateTailRequest(tail=value))
            return _ExpectedState("replacement", value)
        raise ValueError(f"Cannot clear {kind.value!r} through the executor.")

    def _update_header(
        self,
        operation: AuthoringOperation,
        patch: object,
    ) -> _ExpectedState:
        """Merge a partial header update and persist a validated replacement."""
        current = self.service.document.header
        base = current or AuthoringHeaderSpec()
        value = _merge(base, _resolve_clears(patch or {}))
        header = AuthoringHeaderSpec.model_validate(value)
        self.service.update(UpdateHeaderRequest(header=header))
        return _ExpectedState("replacement", header)

    def _update_header_slot(
        self,
        operation: AuthoringOperation,
        patch: object,
    ) -> _ExpectedState:
        """Merge one stable header slot through a validated header replacement."""
        document = self.service.document
        header = document.header
        if header is None:
            raise KeyError("Cannot update a header slot when no header exists.")
        slot = _find_header_slot(document, operation.object_id)
        if slot is _MISSING:
            raise KeyError(f"Unknown header slot {operation.object_id!r}.")
        updated_slot = _merge(slot, _resolve_clears(patch or {}))
        replacement_header = deepcopy(header)
        self._replace_header_slot(replacement_header, operation.object_id, updated_slot)
        self.service.update(UpdateHeaderRequest(header=replacement_header))
        return _ExpectedState("subset", _resolve_clears(patch or {}))

    @staticmethod
    def _replace_header_slot(header: AuthoringHeaderSpec, slot_id: str, value: object) -> None:
        """Replace one slot in a copied canonical header."""
        for collection_name in ("general_fields", "service_titles"):
            collection = getattr(header, collection_name)
            for index, item in enumerate(collection):
                if item.slot_id == slot_id:
                    collection[index] = type(item).model_validate(value)
                    return
        if header.detail is None:
            raise KeyError(f"Unknown header slot {slot_id!r}.")
        for row in header.detail.rows:
            for collection in (row.values,):
                for index, item in enumerate(collection):
                    if item.slot_id == slot_id:
                        collection[index] = type(item).model_validate(value)
                        return
            for column in row.columns:
                for index, item in enumerate(column.cells):
                    if item.slot_id == slot_id:
                        column.cells[index] = type(item).model_validate(value)
                        return
        raise KeyError(f"Unknown header slot {slot_id!r}.")

    @staticmethod
    def _required_scope(operation: AuthoringOperation, name: str) -> str:
        """Return a required parent scope or raise a precise execution error."""
        value = operation.section_id if name == "section" else operation.track_id
        if not value:
            raise ValueError(f"Operation {operation.operation_id!r} requires {name}_id.")
        return value

    def _verify(self, operation: AuthoringOperation, expected: _ExpectedState) -> bool:
        """Read the persisted target and verify the exact operation postcondition."""
        if expected.kind == "removed":
            return not _target_exists(self.service, operation)
        if expected.kind == "moved":
            refs = self.service.list(operation.object_kind.value, section_id=operation.section_id)
            ref = next((item for item in refs if item.object_id == operation.object_id), None)
            return ref is not None and ref.index == expected.value
        actual = _target_value(self.service, operation)
        if expected.kind == "replacement":
            return _same(actual, expected.value)
        return _subset(actual, expected.value)


def execute_authoring_plan(
    service: AuthoringService,
    plan: AuthoringReconciliationPlan,
    *,
    preview_callback: PreviewCallback | None = None,
) -> AuthoringExecutionResult:
    """Execute one G4 plan with deterministic checkpoints and read-back checks."""
    return AuthoringExecutor(service).execute(plan, preview_callback=preview_callback)


__all__ = [
    "AuthoringExecutionResult",
    "AuthoringExecutionStatus",
    "AuthoringExecutor",
    "AuthoringOperationOutcome",
    "AuthoringPhaseCheckpoint",
    "PreviewCallback",
    "execute_authoring_plan",
]
