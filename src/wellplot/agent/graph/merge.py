###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Deterministic merge of capability artifacts into Wellplot document intent."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

from ...capabilities import CapabilityRegistry
from ...model.intent import AuthoringDocumentIntent
from .models import CompiledArtifact

_LIST_ID_FIELDS: dict[str, str] = {
    "sections": "section_id",
    "remarks": "remark_id",
    "curve_bindings": "binding_id",
    "raster_bindings": "binding_id",
    "fills": "fill_id",
    "annotations": "annotation_id",
    "removals": "object_id",
}


def _plain(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="python", exclude_unset=True)
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def _merge_list(field_name: str, left: list[Any], right: list[Any]) -> list[Any]:
    """Merge list intent fields while rejecting conflicting stable identities."""
    id_field = _LIST_ID_FIELDS.get(field_name)
    if id_field is None:
        return [*left, *right]

    merged = list(left)
    by_id: dict[str, object] = {}
    for item in merged:
        if isinstance(item, dict) and item.get(id_field) is not None:
            by_id[str(item[id_field])] = item

    for item in right:
        if not isinstance(item, dict) or item.get(id_field) is None:
            merged.append(item)
            continue
        object_id = str(item[id_field])
        previous = by_id.get(object_id)
        if previous is None:
            merged.append(item)
            by_id[object_id] = item
            continue
        if previous != item:
            raise ValueError(
                f"Conflicting compiled artifacts for {field_name}.{object_id}. "
                "Workers must not author the same stable target independently."
            )
    return merged


def merge_document_intents(fragments: Iterable[AuthoringDocumentIntent]) -> AuthoringDocumentIntent:
    """Merge non-overlapping desired-state fragments deterministically."""
    merged: dict[str, object] = {}
    for fragment in fragments:
        payload = fragment.model_dump(mode="python", exclude_unset=True)
        for field_name, value in payload.items():
            if field_name not in merged:
                merged[field_name] = _plain(value)
                continue
            previous = merged[field_name]
            if isinstance(previous, list) and isinstance(value, list):
                merged[field_name] = _merge_list(field_name, previous, list(_plain(value)))
                continue
            normalized = _plain(value)
            if previous != normalized:
                raise ValueError(
                    f"Conflicting compiled values for root intent field {field_name!r}."
                )
    return AuthoringDocumentIntent.model_validate(merged)


def merge_compiled_artifacts(
    artifacts: Iterable[CompiledArtifact],
    *,
    registry: CapabilityRegistry,
) -> AuthoringDocumentIntent:
    """Validate each payload with its capability and merge compiled fragments."""
    fragments: list[AuthoringDocumentIntent] = []
    for artifact in artifacts:
        spec = registry.get(artifact.capability_id)
        typed = spec.artifact_model.model_validate(artifact.payload)
        fragments.append(spec.compiler(typed))
    return merge_document_intents(fragments)
