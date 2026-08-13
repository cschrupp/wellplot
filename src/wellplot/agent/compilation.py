###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Typed request compilation contracts for the provider-facing agent layer."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from copy import deepcopy
from typing import Any, Literal, Self

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, create_model, model_validator

from ..model.intent import (
    AuthoringClearIntent,
    AuthoringDocumentIntent,
    AuthoringRemoveIntent,
    AuthoringSectionIntent,
    AuthoringTrackIntent,
)


class AuthoringRequestItem(BaseModel):
    """One deterministic request item that must be accounted for by the provider."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    item_id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class AuthoringRequestManifest(BaseModel):
    """Compact, stable request inventory used for intent coverage validation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    items: list[AuthoringRequestItem] = Field(min_length=1)


AuthoringCoverageStatus = Literal[
    "mapped",
    "preserved",
    "unsupported",
    "inconsistent",
]

AuthoringRequestAction = Literal[
    "add",
    "update",
    "remove",
    "clear",
    "preserve",
    "set",
    "explain",
]

AuthoringRequestObjectFamily = Literal[
    "report",
    "header",
    "header_slot",
    "service_title",
    "section",
    "track",
    "curve_binding",
    "raster_binding",
    "fill",
    "annotation",
    "page",
    "output",
    "depth",
    "remarks",
    "tail",
    "unknown",
]

AuthoringRequestBranch = Literal[
    "report",
    "header",
    "section",
    "track",
    "curve_binding",
    "raster_binding",
    "fill",
    "annotation",
    "page",
    "output",
    "depth",
    "remarks",
    "tail",
    "unknown",
]


class AuthoringRequestInventoryItem(BaseModel):
    """One compact provider classification for a natural-language request item."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    request_item_id: str = Field(min_length=1)
    status: AuthoringCoverageStatus
    action: AuthoringRequestAction
    object_family: AuthoringRequestObjectFamily
    top_level_branch: AuthoringRequestBranch | None = None
    target: str | None = Field(default=None, min_length=1)
    natural_parent: str | None = Field(
        default=None,
        min_length=1,
        validation_alias=AliasChoices("natural_parent", "parent_scope"),
        serialization_alias="natural_parent",
    )
    explicit_values: dict[str, Any] = Field(default_factory=dict)
    preserve_constraints: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    reason: str | None = Field(default=None, min_length=1)

    @property
    def parent_scope(self) -> str | None:
        """Keep the pre-K3 name available to internal callers and adapters."""
        return self.natural_parent

    @model_validator(mode="after")
    def normalize_branch(self) -> AuthoringRequestInventoryItem:
        """Derive the hierarchy branch when a provider omits the redundant value."""
        if self.top_level_branch is None:
            branch = _OBJECT_FAMILY_BRANCHES.get(self.object_family, "unknown")
            object.__setattr__(self, "top_level_branch", branch)
        return self


class AuthoringRequestWorkUnit(BaseModel):
    """One parent-scoped clause preserved for a downstream branch compiler."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    unit_id: str = Field(min_length=1)
    request_item_id: str = Field(min_length=1)
    clause_text: str = Field(min_length=1)
    status: AuthoringCoverageStatus
    action: AuthoringRequestAction
    branch: AuthoringRequestBranch
    object_family: AuthoringRequestObjectFamily
    target: str | None = Field(default=None, min_length=1)
    natural_parent: str | None = Field(default=None, min_length=1)
    explicit_values: dict[str, Any] = Field(default_factory=dict)
    preserve_constraints: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    reason: str | None = Field(default=None, min_length=1)


class AuthoringRequestInventory(BaseModel):
    """Compact provider output used before scoped typed-intent compilation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    items: list[AuthoringRequestInventoryItem] = Field(min_length=1)


class AuthoringIntentCoverage(BaseModel):
    """Provider claim linking one request item to typed intent paths."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    request_item_id: str = Field(min_length=1)
    status: AuthoringCoverageStatus
    intent_paths: list[str] = Field(default_factory=list)
    reason: str | None = Field(default=None, min_length=1)


class AuthoringIntentSubmission(BaseModel):
    """One typed desired state plus coverage for the request manifest."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    intent: AuthoringDocumentIntent
    coverage: list[AuthoringIntentCoverage] = Field(min_length=1)


AuthoringCompilationScope = Literal[
    "report",
    "structure",
    "scalar",
    "raster",
    "annotation",
]


class _ScopedCompilationModel(BaseModel):
    """Strict base for generated provider-facing scoped intent views."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="after")
    def reject_explicit_nulls(self) -> Self:
        """Keep scoped submissions consistent with canonical intent semantics."""
        for field_name in self.model_fields_set:
            if getattr(self, field_name) is None:
                raise ValueError(
                    f"Intent field '{field_name}' cannot be null; use "
                    '{"operation": "clear"} to clear it explicitly.'
                )
        return self


def _project_model(
    name: str,
    source: type[BaseModel],
    field_names: tuple[str, ...],
    *,
    overrides: dict[str, tuple[object, object]] | None = None,
) -> type[BaseModel]:
    """Generate a strict model view from canonical Pydantic field definitions."""
    definitions: dict[str, tuple[object, object]] = {}
    for field_name in field_names:
        source_field = source.model_fields[field_name]
        definitions[field_name] = (
            source_field.annotation,
            deepcopy(source_field),
        )
    if overrides:
        definitions.update(overrides)
    return create_model(
        name,
        __base__=_ScopedCompilationModel,
        __module__=__name__,
        **definitions,
    )


AuthoringTrackStructureIntent = _project_model(
    "AuthoringTrackStructureIntent",
    AuthoringTrackIntent,
    (
        "track_id",
        "section_id",
        "title",
        "kind",
        "width_mm",
        "x_scale",
        "grid",
        "track_header",
        "extensions",
    ),
)

_section_tracks_field = deepcopy(AuthoringSectionIntent.model_fields["tracks"])
AuthoringSectionStructureIntent = _project_model(
    "AuthoringSectionStructureIntent",
    AuthoringSectionIntent,
    (
        "section_id",
        "title",
        "subtitle",
        "depth_range",
        "data_source",
        "tracks",
        "extensions",
    ),
    overrides={
        "tracks": (
            list[AuthoringTrackStructureIntent] | AuthoringClearIntent | None,
            _section_tracks_field,
        )
    },
)

_document_sections_field = deepcopy(AuthoringDocumentIntent.model_fields["sections"])


def _remove_intent_model(
    name: str,
    object_kinds: tuple[str, ...],
    *,
    include_parent_scope: bool = True,
) -> type[BaseModel]:
    """Generate one removal view restricted to a compilation scope."""
    object_kind_field = deepcopy(AuthoringRemoveIntent.model_fields["object_kind"])
    field_names = ("operation", "object_kind", "object_id")
    if include_parent_scope:
        field_names += ("section_id", "track_id")
    return _project_model(
        name,
        AuthoringRemoveIntent,
        field_names,
        overrides={
            "object_kind": (
                Literal.__getitem__(object_kinds),
                object_kind_field,
            )
        },
    )


AuthoringReportRemoveIntent = _remove_intent_model(
    "AuthoringReportRemoveIntent",
    ("report", "page", "depth", "output", "header", "tail", "remark"),
    include_parent_scope=False,
)
AuthoringStructureRemoveIntent = _remove_intent_model(
    "AuthoringStructureRemoveIntent",
    ("section", "track"),
)
AuthoringScalarRemoveIntent = _remove_intent_model(
    "AuthoringScalarRemoveIntent",
    ("curve_binding", "fill"),
)
AuthoringRasterRemoveIntent = _remove_intent_model(
    "AuthoringRasterRemoveIntent",
    ("raster_binding",),
)
AuthoringAnnotationRemoveIntent = _remove_intent_model(
    "AuthoringAnnotationRemoveIntent",
    ("annotation",),
)


def _removals_override(remove_model: type[BaseModel]) -> dict[str, tuple[object, object]]:
    """Return one generated removals-field definition for a scoped fragment."""
    return {
        "removals": (
            list[remove_model],
            deepcopy(AuthoringDocumentIntent.model_fields["removals"]),
        )
    }


AuthoringReportIntentFragment = _project_model(
    "AuthoringReportIntentFragment",
    AuthoringDocumentIntent,
    (
        "title",
        "subtitle",
        "output",
        "page",
        "depth",
        "header",
        "tail",
        "remarks",
        "removals",
    ),
    overrides=_removals_override(AuthoringReportRemoveIntent),
)
AuthoringStructureIntentFragment = _project_model(
    "AuthoringStructureIntentFragment",
    AuthoringDocumentIntent,
    ("sections", "removals"),
    overrides={
        "sections": (
            list[AuthoringSectionStructureIntent] | AuthoringClearIntent | None,
            _document_sections_field,
        ),
        **_removals_override(AuthoringStructureRemoveIntent),
    },
)
AuthoringScalarIntentFragment = _project_model(
    "AuthoringScalarIntentFragment",
    AuthoringDocumentIntent,
    ("curve_bindings", "fills", "removals"),
    overrides=_removals_override(AuthoringScalarRemoveIntent),
)
AuthoringRasterIntentFragment = _project_model(
    "AuthoringRasterIntentFragment",
    AuthoringDocumentIntent,
    ("raster_bindings", "removals"),
    overrides=_removals_override(AuthoringRasterRemoveIntent),
)
AuthoringAnnotationIntentFragment = _project_model(
    "AuthoringAnnotationIntentFragment",
    AuthoringDocumentIntent,
    ("annotations", "removals"),
    overrides=_removals_override(AuthoringAnnotationRemoveIntent),
)


def _submission_model(
    name: str,
    fragment_model: type[BaseModel],
) -> type[BaseModel]:
    """Generate one submission wrapper for a scoped canonical intent view."""
    return create_model(
        name,
        __base__=_ScopedCompilationModel,
        __module__=__name__,
        intent=(fragment_model, ...),
        coverage=(list[AuthoringIntentCoverage], Field(min_length=1)),
    )


AuthoringReportIntentSubmission = _submission_model(
    "AuthoringReportIntentSubmission",
    AuthoringReportIntentFragment,
)
AuthoringStructureIntentSubmission = _submission_model(
    "AuthoringStructureIntentSubmission",
    AuthoringStructureIntentFragment,
)
AuthoringScalarIntentSubmission = _submission_model(
    "AuthoringScalarIntentSubmission",
    AuthoringScalarIntentFragment,
)
AuthoringRasterIntentSubmission = _submission_model(
    "AuthoringRasterIntentSubmission",
    AuthoringRasterIntentFragment,
)
AuthoringAnnotationIntentSubmission = _submission_model(
    "AuthoringAnnotationIntentSubmission",
    AuthoringAnnotationIntentFragment,
)

_SCOPE_SUBMISSION_MODELS: dict[str, type[BaseModel]] = {
    "report": AuthoringReportIntentSubmission,
    "structure": AuthoringStructureIntentSubmission,
    "scalar": AuthoringScalarIntentSubmission,
    "raster": AuthoringRasterIntentSubmission,
    "annotation": AuthoringAnnotationIntentSubmission,
}
_SCOPE_ORDER: tuple[AuthoringCompilationScope, ...] = (
    "report",
    "structure",
    "scalar",
    "raster",
    "annotation",
)

_OBJECT_FAMILY_SCOPES: dict[str, AuthoringCompilationScope] = {
    "report": "report",
    "header": "report",
    "header_slot": "report",
    "service_title": "report",
    "page": "report",
    "output": "report",
    "depth": "report",
    "remarks": "report",
    "tail": "report",
    "section": "structure",
    "track": "structure",
    "curve_binding": "scalar",
    "fill": "scalar",
    "raster_binding": "raster",
    "annotation": "annotation",
}

_OBJECT_FAMILY_BRANCHES: dict[str, AuthoringRequestBranch] = {
    "report": "report",
    "header": "header",
    "header_slot": "header",
    "service_title": "header",
    "section": "section",
    "track": "track",
    "curve_binding": "curve_binding",
    "raster_binding": "raster_binding",
    "fill": "fill",
    "annotation": "annotation",
    "page": "page",
    "output": "output",
    "depth": "depth",
    "remarks": "remarks",
    "tail": "tail",
    "unknown": "unknown",
}

_OBJECT_FAMILY_INTENT_ROOTS: dict[str, frozenset[str]] = {
    "report": frozenset(
        {
            "title",
            "subtitle",
            "output",
            "page",
            "depth",
            "header",
            "header_slot",
            "service_title",
            "tail",
            "remarks",
        }
    ),
    "header": frozenset({"header"}),
    "header_slot": frozenset({"header"}),
    "service_title": frozenset({"header"}),
    "page": frozenset({"page"}),
    "output": frozenset({"output"}),
    "depth": frozenset({"depth"}),
    "remarks": frozenset({"remarks"}),
    "tail": frozenset({"tail"}),
    "section": frozenset({"sections"}),
    "track": frozenset({"sections"}),
    "curve_binding": frozenset({"curve_bindings"}),
    "raster_binding": frozenset({"raster_bindings"}),
    "fill": frozenset({"fills"}),
    "annotation": frozenset({"annotations"}),
}

_OBJECT_FAMILY_OPERATION_KINDS: dict[str, frozenset[str]] = {
    "report": frozenset(
        {
            "report",
            "output",
            "page",
            "depth",
            "header",
            "header_slot",
            "service_title",
            "tail",
            "remark",
        }
    ),
    "header": frozenset({"header", "header_slot", "service_title"}),
    "header_slot": frozenset({"header_slot"}),
    "service_title": frozenset({"service_title"}),
    "page": frozenset({"page"}),
    "output": frozenset({"output"}),
    "depth": frozenset({"depth"}),
    "remarks": frozenset({"remark"}),
    "tail": frozenset({"tail"}),
    "section": frozenset({"section"}),
    "track": frozenset({"track"}),
    "curve_binding": frozenset({"curve_binding"}),
    "raster_binding": frozenset({"raster_binding"}),
    "fill": frozenset({"fill"}),
    "annotation": frozenset({"annotation"}),
}

_REQUEST_ACTION_OPERATION_ACTIONS: dict[str, frozenset[str]] = {
    "add": frozenset({"create", "update"}),
    "update": frozenset({"create", "update", "move"}),
    "set": frozenset({"create", "update"}),
    "remove": frozenset({"remove"}),
    "clear": frozenset({"remove", "update"}),
}


def _intent_path_root(path: str) -> str:
    """Return the canonical root field named by one provider coverage path."""
    return re.split(r"[.\[]", path.strip(), maxsplit=1)[0]


def _intent_value_is_clear(value: object) -> bool:
    """Return whether one typed field carries the explicit canonical clear marker."""
    return isinstance(value, AuthoringClearIntent)


def _intent_value_is_populated(value: object) -> bool:
    """Return whether one supplied intent value can fulfill an add/set/update request."""
    if value is None or _intent_value_is_clear(value):
        return False
    if isinstance(value, (str, bytes, list, tuple, dict)):
        return bool(value)
    return True


def _family_removal_kind(object_family: str) -> str:
    """Return the canonical singular removal kind for one request family."""
    return "remark" if object_family == "remarks" else object_family


def _has_matching_removal(intent: BaseModel, object_family: str) -> bool:
    """Return whether a scoped intent explicitly removes the requested family."""
    removals = getattr(intent, "removals", ())
    expected_kind = _family_removal_kind(object_family)
    return any(
        isinstance(removal, AuthoringRemoveIntent) and removal.object_kind == expected_kind
        for removal in removals
    )


def validate_scoped_intent_semantics(
    inventory: Iterable[AuthoringRequestInventoryItem],
    intent: BaseModel,
    coverage: Iterable[AuthoringIntentCoverage],
) -> list[str]:
    """Reject typed submissions that contradict their inventoried request actions.

    Coverage paths are provider claims, so structural validation alone is not enough.
    This gate confirms that an ``add``, ``set``, ``update``, ``remove``, or ``clear``
    request points at a compatible supplied field in the scoped typed fragment.
    """
    inventory_by_id = {item.request_item_id: item for item in inventory}
    coverage_by_id = {entry.request_item_id: entry for entry in coverage}
    supplied_fields = intent.model_fields_set
    errors: list[str] = []

    for request_item_id, item in inventory_by_id.items():
        if item.status in {"unsupported", "inconsistent"}:
            continue
        entry = coverage_by_id.get(request_item_id)
        if entry is None or entry.status not in {"mapped", "preserved"}:
            continue

        roots = {_intent_path_root(path) for path in entry.intent_paths if path.strip()}
        expected_roots = _OBJECT_FAMILY_INTENT_ROOTS.get(item.object_family, frozenset())
        scope_root = _OBJECT_FAMILY_SCOPES.get(item.object_family)

        if item.action == "preserve":
            if "removals" in roots or any(
                root in supplied_fields and _intent_value_is_clear(getattr(intent, root))
                for root in roots
                if root != "removals"
            ):
                errors.append(
                    f"Coverage for {request_item_id!r} marks {item.object_family!r} "
                    "as preserved but submits a destructive intent."
                )
            continue

        allowed_roots = expected_roots | {"removals"}
        if scope_root is not None:
            allowed_roots = allowed_roots | {scope_root}
        incompatible_roots = sorted(root for root in roots if root not in allowed_roots)
        if incompatible_roots:
            errors.append(
                f"Coverage for {request_item_id!r} maps {item.object_family!r} to "
                f"incompatible intent path roots {incompatible_roots!r}."
            )
            continue

        if item.action == "remove":
            if "removals" not in roots or not _has_matching_removal(intent, item.object_family):
                errors.append(
                    f"Request {request_item_id!r} removes {item.object_family!r}, but the "
                    "submitted intent does not include a matching removal."
                )
            continue

        expected_root = next((root for root in roots if root in expected_roots), None)
        if expected_root is None and scope_root in roots:
            expected_root = next(
                (root for root in expected_roots if root in supplied_fields),
                None,
            )
        if expected_root is None:
            errors.append(
                f"Request {request_item_id!r} {item.action}s {item.object_family!r}, but "
                "coverage does not point to its canonical intent field."
            )
            continue

        value = getattr(intent, expected_root, None)
        if item.action == "clear":
            if not _intent_value_is_clear(value) and not _has_matching_removal(
                intent,
                item.object_family,
            ):
                errors.append(
                    f"Request {request_item_id!r} clears {item.object_family!r}, but the "
                    "submitted intent does not include an explicit clear or removal."
                )
            continue

        if expected_root not in supplied_fields:
            errors.append(
                f"Request {request_item_id!r} {item.action}s {item.object_family!r}, but "
                f"the submitted intent omits {expected_root!r}."
            )
        elif _intent_value_is_clear(value):
            errors.append(
                f"Request {request_item_id!r} {item.action}s {item.object_family!r}, but "
                f"the submitted intent explicitly clears {expected_root!r}."
            )
        elif not _intent_value_is_populated(value):
            errors.append(
                f"Request {request_item_id!r} {item.action}s {item.object_family!r}, but "
                f"the submitted {expected_root!r} value is empty."
            )

    return errors


def validate_reconciliation_fulfillment(
    inventory: Iterable[AuthoringRequestInventoryItem],
    operations: Iterable[Mapping[str, object]],
) -> list[str]:
    """Reject an operation plan whose mutation kinds contradict mapped requests.

    A typed fragment can be structurally valid yet resolve into a different action
    once identities and existing document state are considered. This second gate
    prevents execution of that contradictory plan. A request already satisfied by
    the existing document may legitimately produce no operation.
    """
    normalized_operations = [dict(operation) for operation in operations]
    errors: list[str] = []
    for item in inventory:
        if item.status != "mapped" or item.action == "preserve":
            continue
        expected_kinds = _OBJECT_FAMILY_OPERATION_KINDS.get(item.object_family, frozenset())
        if not expected_kinds:
            continue
        relevant_operations = [
            operation
            for operation in normalized_operations
            if operation.get("object_kind") in expected_kinds
        ]
        if not relevant_operations:
            continue
        compatible_actions = _REQUEST_ACTION_OPERATION_ACTIONS.get(item.action, frozenset())
        if any(operation.get("action") in compatible_actions for operation in relevant_operations):
            continue
        found_actions = sorted(
            {
                str(operation.get("action"))
                for operation in relevant_operations
                if operation.get("action") is not None
            }
        )
        errors.append(
            f"Request {item.request_item_id!r} {item.action}s {item.object_family!r}, "
            f"but the reconciliation plan only contains incompatible actions {found_actions!r}."
        )
    return errors


def _strip_bullet(line: str) -> str:
    """Remove one common bullet or numbered-list prefix."""
    return re.sub(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)", "", line).strip()


def _is_bullet(line: str) -> bool:
    """Return whether one line starts a list item."""
    return bool(re.match(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)", line))


def build_request_manifest(text: str) -> AuthoringRequestManifest:
    """Split a natural-language request into stable, reviewable request items."""
    items: list[str] = []
    current: str | None = None
    paragraph: list[str] = []

    def flush_current() -> None:
        nonlocal current
        if current:
            items.append(current.strip())
        current = None

    def flush_paragraph() -> None:
        if paragraph:
            items.append(" ".join(paragraph).strip())
            paragraph.clear()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            flush_current()
            flush_paragraph()
            continue
        if _is_bullet(raw_line):
            flush_paragraph()
            flush_current()
            current = _strip_bullet(raw_line)
            continue
        if current is not None:
            current = f"{current} {line}".strip()
            continue
        if line.endswith(":"):
            flush_paragraph()
            paragraph.append(line)
            continue
        paragraph.append(line)

    flush_current()
    flush_paragraph()
    normalized_items = [item for item in items if item]
    if not normalized_items and text.strip():
        normalized_items = [text.strip()]
    return AuthoringRequestManifest(
        items=[
            AuthoringRequestItem(item_id=f"request-{index:03d}", text=item)
            for index, item in enumerate(normalized_items, start=1)
        ]
    )


def build_request_work_units(
    manifest: AuthoringRequestManifest,
    inventory: AuthoringRequestInventory,
) -> tuple[AuthoringRequestWorkUnit, ...]:
    """Join provider classifications to original clauses in manifest order.

    Work units deliberately retain one request clause each. This prevents a
    mixed prompt from becoming one provider-owned document graph while still
    giving each downstream compiler the natural target, parent, values, and
    preserve assertions it needs.
    """
    manifest_by_id = {item.item_id: item for item in manifest.items}
    units: list[AuthoringRequestWorkUnit] = []
    for item in inventory.items:
        manifest_item = manifest_by_id.get(item.request_item_id)
        if manifest_item is None:
            continue
        branch = item.top_level_branch or _OBJECT_FAMILY_BRANCHES.get(item.object_family, "unknown")
        units.append(
            AuthoringRequestWorkUnit(
                unit_id=f"unit-{item.request_item_id}",
                request_item_id=item.request_item_id,
                clause_text=manifest_item.text,
                status=item.status,
                action=item.action,
                branch=branch,
                object_family=item.object_family,
                target=item.target,
                natural_parent=item.natural_parent,
                explicit_values=deepcopy(item.explicit_values),
                preserve_constraints=list(item.preserve_constraints),
                dependencies=list(item.dependencies),
                reason=item.reason,
            )
        )
    return tuple(units)


def validate_intent_coverage(
    manifest: AuthoringRequestManifest,
    coverage: Iterable[AuthoringIntentCoverage],
) -> list[str]:
    """Return deterministic errors for incomplete or contradictory coverage."""
    entries = list(coverage)
    expected_ids = {item.item_id for item in manifest.items}
    seen_ids: set[str] = set()
    errors: list[str] = []
    for entry in entries:
        if entry.request_item_id in seen_ids:
            errors.append(f"Duplicate coverage for {entry.request_item_id!r}.")
        seen_ids.add(entry.request_item_id)
        if entry.request_item_id not in expected_ids:
            errors.append(f"Coverage references unknown request item {entry.request_item_id!r}.")
        if entry.status in {"mapped", "preserved"} and not entry.intent_paths:
            errors.append(f"Coverage for {entry.request_item_id!r} needs at least one intent path.")
        if entry.status in {"unsupported", "inconsistent"} and not entry.reason:
            errors.append(
                f"Coverage for {entry.request_item_id!r} needs a reason for status "
                f"{entry.status!r}."
            )
    missing_ids = sorted(expected_ids - seen_ids)
    errors.extend(f"Missing coverage for request item {item_id!r}." for item_id in missing_ids)
    return errors


def validate_request_inventory(
    manifest: AuthoringRequestManifest,
    inventory: Iterable[AuthoringRequestInventoryItem],
) -> list[str]:
    """Return deterministic errors for an incomplete compact request inventory."""
    entries = list(inventory)
    expected_ids = {item.item_id for item in manifest.items}
    seen_ids: set[str] = set()
    errors: list[str] = []
    for entry in entries:
        if entry.request_item_id in seen_ids:
            errors.append(f"Duplicate inventory for {entry.request_item_id!r}.")
        seen_ids.add(entry.request_item_id)
        if entry.request_item_id not in expected_ids:
            errors.append(f"Inventory references unknown request item {entry.request_item_id!r}.")
        if entry.status in {"mapped", "preserved"}:
            if entry.object_family == "unknown":
                errors.append(
                    f"Inventory for {entry.request_item_id!r} needs a known object family."
                )
            expected_branch = _OBJECT_FAMILY_BRANCHES.get(entry.object_family, "unknown")
            if entry.top_level_branch != expected_branch:
                errors.append(
                    f"Inventory for {entry.request_item_id!r} maps {entry.object_family!r} "
                    f"to branch {entry.top_level_branch!r}; expected {expected_branch!r}."
                )
            if entry.action == "explain":
                errors.append(f"Inventory for {entry.request_item_id!r} needs an authoring action.")
        if entry.status in {"unsupported", "inconsistent"} and not entry.reason:
            errors.append(
                f"Inventory for {entry.request_item_id!r} needs a reason for status "
                f"{entry.status!r}."
            )
    missing_ids = sorted(expected_ids - seen_ids)
    errors.extend(f"Missing inventory for request item {item_id!r}." for item_id in missing_ids)
    return errors


def group_request_inventory(
    inventory: AuthoringRequestInventory,
) -> dict[AuthoringCompilationScope, tuple[AuthoringRequestInventoryItem, ...]]:
    """Group actionable inventory items by canonical compilation scope."""
    grouped: dict[AuthoringCompilationScope, list[AuthoringRequestInventoryItem]] = {}
    for item in inventory.items:
        if item.status in {"unsupported", "inconsistent"}:
            continue
        scope = _OBJECT_FAMILY_SCOPES.get(item.object_family)
        if scope is None:
            continue
        grouped.setdefault(scope, []).append(item)
    return {scope: tuple(grouped[scope]) for scope in _SCOPE_ORDER if scope in grouped}


def scoped_submission_model(scope: AuthoringCompilationScope) -> type[BaseModel]:
    """Return the generated submission model for one canonical object scope."""
    return _SCOPE_SUBMISSION_MODELS[scope]


def _reject_duplicate_identities(payload: dict[str, Any]) -> None:
    """Reject duplicate canonical identities before contextual resolution."""
    identity_fields = {
        "sections": "section_id",
        "curve_bindings": "binding_id",
        "raster_bindings": "binding_id",
        "fills": "fill_id",
        "annotations": "annotation_id",
        "remarks": "remark_id",
    }
    for field_name, identity_field in identity_fields.items():
        values = payload.get(field_name)
        if not isinstance(values, list):
            continue
        seen: set[str] = set()
        for value in values:
            if not isinstance(value, dict):
                continue
            identity = str(value.get(identity_field, "")).strip()
            if identity and identity in seen:
                raise ValueError(f"Duplicate {identity_field} {identity!r} in {field_name}.")
            seen.add(identity)

    sections = payload.get("sections")
    if not isinstance(sections, list):
        return
    for section in sections:
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("section_id", "")).strip()
        tracks = section.get("tracks")
        if not isinstance(tracks, list):
            continue
        seen_tracks: set[str] = set()
        for track in tracks:
            if not isinstance(track, dict):
                continue
            track_id = str(track.get("track_id", "")).strip()
            if track_id and track_id in seen_tracks:
                raise ValueError(f"Duplicate track_id {track_id!r} in section {section_id!r}.")
            seen_tracks.add(track_id)


def merge_scoped_intents(fragments: Iterable[BaseModel]) -> AuthoringDocumentIntent:
    """Merge non-overlapping scoped fragments into one canonical desired state."""
    merged: dict[str, Any] = {}
    removals: list[dict[str, Any]] = []
    for fragment in fragments:
        payload = fragment.model_dump(mode="json", exclude_unset=True)
        for field_name, value in payload.items():
            if field_name == "removals":
                if isinstance(value, list):
                    for removal in value:
                        if isinstance(removal, dict) and removal not in removals:
                            removals.append(removal)
                continue
            if field_name in merged and merged[field_name] != value:
                raise ValueError(f"Conflicting scoped intent values for field {field_name!r}.")
            merged[field_name] = value
    if removals:
        merged["removals"] = removals
    _reject_duplicate_identities(merged)
    return AuthoringDocumentIntent.model_validate(merged)


__all__ = [
    "AuthoringCoverageStatus",
    "AuthoringCompilationScope",
    "AuthoringAnnotationIntentFragment",
    "AuthoringAnnotationIntentSubmission",
    "AuthoringIntentCoverage",
    "AuthoringIntentSubmission",
    "AuthoringRasterIntentFragment",
    "AuthoringRasterIntentSubmission",
    "AuthoringReportIntentFragment",
    "AuthoringReportIntentSubmission",
    "AuthoringRequestAction",
    "AuthoringRequestItem",
    "AuthoringRequestInventory",
    "AuthoringRequestInventoryItem",
    "AuthoringRequestManifest",
    "AuthoringRequestWorkUnit",
    "AuthoringScalarIntentFragment",
    "AuthoringScalarIntentSubmission",
    "AuthoringSectionStructureIntent",
    "AuthoringStructureIntentFragment",
    "AuthoringStructureIntentSubmission",
    "AuthoringTrackStructureIntent",
    "build_request_manifest",
    "build_request_work_units",
    "group_request_inventory",
    "merge_scoped_intents",
    "scoped_submission_model",
    "validate_intent_coverage",
    "validate_reconciliation_fulfillment",
    "validate_request_inventory",
    "validate_scoped_intent_semantics",
]
