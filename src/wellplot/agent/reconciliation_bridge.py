###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Compile generic reconciliation operations into typed branch submissions."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, TypeAdapter

from ..authoring_reconciler import (
    AuthoringOperation,
    AuthoringOperationAction,
    AuthoringOperationObjectKind,
    AuthoringReconciliationPlan,
)
from ..authoring_service import (
    AuthoringService,
    AuthoringTarget,
    CreateAnnotationRequest,
    CreateCurveBindingRequest,
    CreateFillRequest,
    CreateRasterBindingRequest,
    CreateRemarkRequest,
    CreateRequest,
    CreateSectionRequest,
    CreateTrackRequest,
    CurveBindingPatch,
    DepthPatch,
    HeaderValuePatch,
    MoveRequest,
    PagePatch,
    RasterBindingPatch,
    RemarkPatch,
    RemoveRequest,
    ReportPatch,
    SectionPatch,
    ServiceTitlePatch,
    TrackPatch,
    UpdateAnnotationRequest,
    UpdateCurveBindingRequest,
    UpdateDepthRequest,
    UpdateFillRequest,
    UpdateHeaderRequest,
    UpdateHeaderSlotRequest,
    UpdateOutputRequest,
    UpdatePageRequest,
    UpdateRasterBindingRequest,
    UpdateRemarkRequest,
    UpdateReportRequest,
    UpdateRequest,
    UpdateSectionRequest,
    UpdateServiceTitleRequest,
    UpdateTailRequest,
    UpdateTrackRequest,
)
from ..model.authoring import (
    AnnotationSpec,
    AuthoringDepthSpec,
    AuthoringHeaderSpec,
    AuthoringOutputSpec,
    AuthoringPageSpec,
    AuthoringRemarkSpec,
    AuthoringSectionSpec,
    AuthoringTailSpec,
    CurveBindingSpec,
    CurveFillSpec,
    RasterBindingSpec,
    TrackSpec,
)
from .compilation import (
    AuthoringCompilationScope,
    AuthoringRequestWorkUnit,
    branch_operation_submission_model,
    operation_request_object_kind,
)

_OBJECT_SCOPE: dict[AuthoringOperationObjectKind, AuthoringCompilationScope] = {
    AuthoringOperationObjectKind.REPORT: "report",
    AuthoringOperationObjectKind.PAGE: "report",
    AuthoringOperationObjectKind.DEPTH: "report",
    AuthoringOperationObjectKind.OUTPUT: "report",
    AuthoringOperationObjectKind.HEADER: "report",
    AuthoringOperationObjectKind.HEADER_SLOT: "report",
    AuthoringOperationObjectKind.TAIL: "report",
    AuthoringOperationObjectKind.REMARK: "report",
    AuthoringOperationObjectKind.SECTION: "structure",
    AuthoringOperationObjectKind.TRACK: "structure",
    AuthoringOperationObjectKind.CURVE_BINDING: "scalar",
    AuthoringOperationObjectKind.FILL: "scalar",
    AuthoringOperationObjectKind.RASTER_BINDING: "raster",
    AuthoringOperationObjectKind.ANNOTATION: "annotation",
}

_OBJECT_FAMILY_BRANCH: dict[AuthoringOperationObjectKind, str] = {
    AuthoringOperationObjectKind.REPORT: "report",
    AuthoringOperationObjectKind.PAGE: "page",
    AuthoringOperationObjectKind.DEPTH: "depth",
    AuthoringOperationObjectKind.OUTPUT: "output",
    AuthoringOperationObjectKind.HEADER: "header",
    AuthoringOperationObjectKind.HEADER_SLOT: "header",
    AuthoringOperationObjectKind.TAIL: "tail",
    AuthoringOperationObjectKind.REMARK: "remarks",
    AuthoringOperationObjectKind.SECTION: "section",
    AuthoringOperationObjectKind.TRACK: "track",
    AuthoringOperationObjectKind.CURVE_BINDING: "curve_binding",
    AuthoringOperationObjectKind.FILL: "fill",
    AuthoringOperationObjectKind.RASTER_BINDING: "raster_binding",
    AuthoringOperationObjectKind.ANNOTATION: "annotation",
}


@dataclass(frozen=True)
class TypedReconciliationCompilation:
    """Typed branch submissions and context compiled from one generic plan."""

    submissions: tuple[BaseModel, ...]
    work_units: tuple[AuthoringRequestWorkUnit, ...]
    defaults_provenance_by_operation: dict[str, dict[str, str]]


def _plain(value: object) -> object:
    """Convert models and nested collections into JSON-compatible values."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", exclude_none=False)
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _merge(current: object, patch: object) -> dict[str, Any]:
    """Merge a partial operation patch into a canonical object mapping."""
    current_mapping = dict(_plain(current)) if isinstance(_plain(current), Mapping) else {}
    patch_mapping = dict(_plain(patch)) if isinstance(_plain(patch), Mapping) else {}
    for key, value in patch_mapping.items():
        if isinstance(value, Mapping) and isinstance(current_mapping.get(key), Mapping):
            current_mapping[key] = _merge(current_mapping[key], value)
        else:
            current_mapping[key] = value
    return current_mapping


def _resolve_clears(value: object, defaults: object | None = None) -> object:
    """Resolve explicit clear markers before building typed service requests."""
    if isinstance(value, Mapping) and value.get("operation") == "clear":
        return _plain(defaults) if defaults is not None else None
    if isinstance(value, Mapping):
        default_mapping = defaults if isinstance(defaults, Mapping) else {}
        return {key: _resolve_clears(item, default_mapping.get(key)) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_clears(item) for item in value]
    return _plain(value)


def _omit_undefined(value: object) -> object:
    """Drop omitted optional fields before validating a complete create object."""
    if isinstance(value, Mapping):
        return {key: _omit_undefined(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_omit_undefined(item) for item in value]
    return value


def _header_value_patch(
    value: object,
    *,
    service_title: bool = False,
) -> dict[str, Any]:
    """Flatten an intent report value for the stable header-slot contract."""
    patch = _resolve_clears(value)
    if not isinstance(patch, Mapping):
        return {}
    flattened = dict(patch)
    report_value = flattened.get("value")
    if isinstance(report_value, Mapping):
        flattened.pop("value")
        flattened.update(report_value)
    allowed = {"value", "source_key", "unit", "provenance", "availability"}
    if service_title:
        allowed.update({"font_size", "auto_adjust", "bold", "italic", "alignment"})
    return {key: item for key, item in flattened.items() if key in allowed}


def _scope_for(operation: AuthoringOperation) -> AuthoringCompilationScope:
    """Return the typed submission branch for one canonical object kind."""
    try:
        return _OBJECT_SCOPE[operation.object_kind]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported reconciliation object kind {operation.object_kind!r}."
        ) from exc


def _required_scope(operation: AuthoringOperation, name: str) -> str:
    """Return a required section or track parent identity."""
    value = operation.section_id if name == "section" else operation.track_id
    if not value:
        raise ValueError(f"Operation {operation.operation_id!r} requires {name}_id.")
    return value


def _clear_payload(operation: AuthoringOperation) -> bool:
    """Return whether an operation requests a canonical reset."""
    return "clear" in operation.payload


def _update_request(
    service: AuthoringService,
    operation: AuthoringOperation,
) -> UpdateRequest:
    """Compile one generic update into its canonical typed request."""
    kind = operation.object_kind
    raw_patch = operation.payload.get("patch", {})
    if _clear_payload(operation):
        if kind == AuthoringOperationObjectKind.PAGE:
            return UpdatePageRequest(
                patch=PagePatch.model_validate(AuthoringPageSpec().model_dump())
            )
        if kind == AuthoringOperationObjectKind.DEPTH:
            return UpdateDepthRequest(
                patch=DepthPatch.model_validate(AuthoringDepthSpec().model_dump())
            )
        if kind == AuthoringOperationObjectKind.OUTPUT:
            return UpdateOutputRequest(output=AuthoringOutputSpec())
        if kind == AuthoringOperationObjectKind.HEADER:
            return UpdateHeaderRequest(header=AuthoringHeaderSpec())
        if kind == AuthoringOperationObjectKind.TAIL:
            return UpdateTailRequest(tail=AuthoringTailSpec())
        raise ValueError(f"Cannot clear {kind.value!r} through typed reconciliation.")

    if kind == AuthoringOperationObjectKind.REPORT:
        return UpdateReportRequest(
            patch=ReportPatch.model_validate(
                _resolve_clears(raw_patch, {"title": None, "subtitle": None})
            )
        )
    if kind == AuthoringOperationObjectKind.PAGE:
        return UpdatePageRequest(
            patch=PagePatch.model_validate(
                _resolve_clears(raw_patch, AuthoringPageSpec().model_dump())
            )
        )
    if kind == AuthoringOperationObjectKind.DEPTH:
        return UpdateDepthRequest(
            patch=DepthPatch.model_validate(
                _resolve_clears(raw_patch, AuthoringDepthSpec().model_dump())
            )
        )
    if kind == AuthoringOperationObjectKind.OUTPUT:
        current = service.get(AuthoringTarget(object_kind="output", object_id="output"))
        value = _merge(current, _resolve_clears(raw_patch, AuthoringOutputSpec().model_dump()))
        return UpdateOutputRequest(output=AuthoringOutputSpec.model_validate(value))
    if kind == AuthoringOperationObjectKind.TAIL:
        current = service.get(AuthoringTarget(object_kind="tail", object_id="tail"))
        value = _merge(current, _resolve_clears(raw_patch, AuthoringTailSpec().model_dump()))
        return UpdateTailRequest(tail=AuthoringTailSpec.model_validate(value))
    if kind == AuthoringOperationObjectKind.HEADER:
        current = service.document.header or AuthoringHeaderSpec()
        value = _merge(current, _resolve_clears(raw_patch))
        return UpdateHeaderRequest(header=AuthoringHeaderSpec.model_validate(value))
    if kind == AuthoringOperationObjectKind.HEADER_SLOT:
        service_title_ids = {ref.object_id for ref in service.list("service_title")}
        if operation.object_id in service_title_ids:
            patch = ServiceTitlePatch.model_validate(
                _header_value_patch(raw_patch, service_title=True)
            )
            return UpdateServiceTitleRequest(slot_id=operation.object_id, patch=patch)
        patch = HeaderValuePatch.model_validate(_header_value_patch(raw_patch))
        return UpdateHeaderSlotRequest(slot_id=operation.object_id, patch=patch)
    if kind == AuthoringOperationObjectKind.SECTION:
        return UpdateSectionRequest(
            section_id=operation.object_id,
            patch=SectionPatch.model_validate(
                _resolve_clears(
                    raw_patch,
                    {
                        "subtitle": None,
                        "depth_range": None,
                        "data_source": None,
                        "extensions": {},
                    },
                )
            ),
        )
    if kind == AuthoringOperationObjectKind.TRACK:
        return UpdateTrackRequest(
            section_id=_required_scope(operation, "section"),
            track_id=operation.object_id,
            patch=TrackPatch.model_validate(
                _resolve_clears(
                    raw_patch,
                    {
                        "x_scale": None,
                        "reference": None,
                        "grid": None,
                        "track_header": None,
                        "extensions": {},
                    },
                )
            ),
        )
    if kind == AuthoringOperationObjectKind.CURVE_BINDING:
        return UpdateCurveBindingRequest(
            section_id=_required_scope(operation, "section"),
            track_id=_required_scope(operation, "track"),
            binding_id=operation.object_id,
            patch=CurveBindingPatch.model_validate(
                _resolve_clears(
                    raw_patch,
                    {"style": None},
                )
            ),
        )
    if kind == AuthoringOperationObjectKind.RASTER_BINDING:
        return UpdateRasterBindingRequest(
            section_id=_required_scope(operation, "section"),
            track_id=_required_scope(operation, "track"),
            binding_id=operation.object_id,
            patch=RasterBindingPatch.model_validate(
                _resolve_clears(
                    raw_patch,
                    {"style": None},
                )
            ),
        )
    if kind == AuthoringOperationObjectKind.ANNOTATION:
        value = TypeAdapter(AnnotationSpec).validate_python(operation.payload.get("object"))
        return UpdateAnnotationRequest(
            section_id=_required_scope(operation, "section"),
            track_id=_required_scope(operation, "track"),
            annotation_id=operation.object_id,
            annotation=value,
        )
    if kind == AuthoringOperationObjectKind.FILL:
        current = service.get(
            AuthoringTarget(
                object_kind="fill",
                object_id=operation.object_id,
                section_id=_required_scope(operation, "section"),
                track_id=_required_scope(operation, "track"),
            )
        )
        value = _merge(current, _resolve_clears(raw_patch))
        return UpdateFillRequest(
            section_id=_required_scope(operation, "section"),
            track_id=_required_scope(operation, "track"),
            fill_id=operation.object_id,
            fill=CurveFillSpec.model_validate(value),
        )
    if kind == AuthoringOperationObjectKind.REMARK:
        return UpdateRemarkRequest(
            remark_id=operation.object_id,
            patch=RemarkPatch.model_validate(raw_patch),
        )
    raise ValueError(f"Update is unsupported for {kind.value!r}.")


def _create_request(operation: AuthoringOperation) -> CreateRequest:
    """Compile one generic create into its canonical typed request."""
    raw = _omit_undefined(_resolve_clears(operation.payload.get("object", {})))
    kind = operation.object_kind
    if not isinstance(raw, Mapping):
        raise ValueError(f"Create operation {operation.operation_id!r} requires an object mapping.")
    if kind == AuthoringOperationObjectKind.SECTION:
        return CreateSectionRequest(section=AuthoringSectionSpec.model_validate(raw))
    if kind == AuthoringOperationObjectKind.TRACK:
        return CreateTrackRequest(
            section_id=_required_scope(operation, "section"),
            track=TypeAdapter(TrackSpec).validate_python(raw),
        )
    if kind == AuthoringOperationObjectKind.CURVE_BINDING:
        return CreateCurveBindingRequest(
            section_id=_required_scope(operation, "section"),
            track_id=_required_scope(operation, "track"),
            binding=CurveBindingSpec.model_validate(raw),
        )
    if kind == AuthoringOperationObjectKind.RASTER_BINDING:
        return CreateRasterBindingRequest(
            section_id=_required_scope(operation, "section"),
            track_id=_required_scope(operation, "track"),
            binding=RasterBindingSpec.model_validate(raw),
        )
    if kind == AuthoringOperationObjectKind.ANNOTATION:
        return CreateAnnotationRequest(
            section_id=_required_scope(operation, "section"),
            track_id=_required_scope(operation, "track"),
            annotation=TypeAdapter(AnnotationSpec).validate_python(raw),
        )
    if kind == AuthoringOperationObjectKind.FILL:
        return CreateFillRequest(
            section_id=_required_scope(operation, "section"),
            track_id=_required_scope(operation, "track"),
            fill=CurveFillSpec.model_validate(raw),
        )
    if kind == AuthoringOperationObjectKind.REMARK:
        return CreateRemarkRequest(remark=AuthoringRemarkSpec.model_validate(raw))
    raise ValueError(f"Create is unsupported for {kind.value!r}.")


def _typed_request(
    service: AuthoringService, operation: AuthoringOperation
) -> CreateRequest | UpdateRequest | RemoveRequest | MoveRequest:
    """Compile one reconciliation operation into a service request."""
    if operation.action == AuthoringOperationAction.CREATE:
        return _create_request(operation)
    if operation.action == AuthoringOperationAction.UPDATE:
        return _update_request(service, operation)
    if operation.action == AuthoringOperationAction.REMOVE:
        return RemoveRequest(
            target=AuthoringTarget(
                object_kind=operation.object_kind.value,
                object_id=operation.object_id,
                section_id=operation.section_id,
                track_id=operation.track_id,
            )
        )
    if operation.action == AuthoringOperationAction.MOVE:
        return MoveRequest(
            object_kind=operation.object_kind.value,
            object_id=operation.object_id,
            section_id=operation.section_id,
            new_index=int(operation.payload["new_index"]),
        )
    raise ValueError(f"Unsupported reconciliation action {operation.action!r}.")


def compile_reconciliation_plan(
    plan: AuthoringReconciliationPlan,
    *,
    service: AuthoringService,
    defaults_provenance: Mapping[str, str] | None = None,
) -> TypedReconciliationCompilation:
    """Compile a ready generic plan into typed branch submissions."""
    if not plan.ready:
        reasons = "; ".join(issue.message for issue in plan.issues)
        raise ValueError(f"Cannot compile a blocked reconciliation plan: {reasons}")

    operations_by_scope: dict[AuthoringCompilationScope, list[dict[str, Any]]] = defaultdict(list)
    work_units: list[AuthoringRequestWorkUnit] = []
    defaults_by_operation: dict[str, dict[str, str]] = {}
    default_values = dict(defaults_provenance or {})
    for operation in plan.operations:
        scope = _scope_for(operation)
        request = _typed_request(service, operation)
        unit_id = f"reconcile-{operation.operation_id}"
        request_item_id = f"reconcile:{operation.operation_id}"
        family = (
            "remarks"
            if operation.object_kind == AuthoringOperationObjectKind.REMARK
            else operation.object_kind.value
        )
        if operation.object_kind == AuthoringOperationObjectKind.HEADER_SLOT:
            family = operation_request_object_kind(request)
        branch = _OBJECT_FAMILY_BRANCH[operation.object_kind]
        parent = operation.track_id or operation.section_id
        action = (
            "add" if operation.action == AuthoringOperationAction.CREATE else operation.action.value
        )
        if operation.action == AuthoringOperationAction.MOVE:
            action = "update"
        work_units.append(
            AuthoringRequestWorkUnit(
                unit_id=unit_id,
                request_item_id=request_item_id,
                clause_text=operation.reason,
                status="mapped",
                action=action,
                branch=branch,
                object_family=family,
                target=operation.object_id,
                natural_parent=parent,
                explicit_values=dict(_plain(operation.payload)),
                dependencies=list(operation.depends_on),
                phase=operation.phase,
            )
        )
        operations_by_scope[scope].append(
            {
                "operation_id": operation.operation_id,
                "work_unit_id": unit_id,
                "depends_on": list(operation.depends_on),
                "action": operation.action.value,
                "request": request,
            }
        )
        defaults_by_operation[operation.operation_id] = {
            path: source for path, source in default_values.items() if operation.object_id in path
        }

    submissions: list[BaseModel] = []
    work_unit_by_scope: dict[AuthoringCompilationScope, list[AuthoringRequestWorkUnit]] = (
        defaultdict(list)
    )
    operation_scope_by_id = {
        operation.operation_id: _scope_for(operation) for operation in plan.operations
    }
    for unit in work_units:
        operation_id = unit.unit_id.removeprefix("reconcile-")
        work_unit_by_scope[operation_scope_by_id[operation_id]].append(unit)
    for scope in ("report", "structure", "scalar", "raster", "annotation"):
        scoped_operations = operations_by_scope.get(scope, [])
        if not scoped_operations:
            continue
        submission_model = branch_operation_submission_model(scope)
        scoped_units = work_unit_by_scope[scope]
        submissions.append(
            submission_model.model_validate(
                {
                    "branch": scope,
                    "operations": scoped_operations,
                    "coverage": [
                        {
                            "unit_id": unit.unit_id,
                            "status": "mapped",
                            "operation_ids": [operation["operation_id"]],
                        }
                        for unit, operation in zip(
                            scoped_units,
                            scoped_operations,
                            strict=True,
                        )
                    ],
                }
            )
        )
    return TypedReconciliationCompilation(
        submissions=tuple(submissions),
        work_units=tuple(work_units),
        defaults_provenance_by_operation=defaults_by_operation,
    )


__all__ = ["TypedReconciliationCompilation", "compile_reconciliation_plan"]
