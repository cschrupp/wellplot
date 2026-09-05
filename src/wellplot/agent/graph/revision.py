###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Compile natural-language revisions against an existing canonical document."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from langgraph.graph.state import CompiledStateGraph

from ...model.authoring import AuthoringDocumentSpec
from ...model.intent import AuthoringDocumentIntent
from .models import ReconstructionPlan


@dataclass(frozen=True)
class RevisionCompilationResult:
    """Typed evidence from one compile-only document revision.

    The merged intent deliberately contains only report changes and the
    planner-selected sections. ``preserved_section_ids`` records the existing
    sections that deterministic reconciliation must leave untouched.
    """

    existing_document: AuthoringDocumentSpec
    plan: ReconstructionPlan
    intent: AuthoringDocumentIntent
    source_manifest: dict[str, Any]
    affected_section_ids: tuple[str, ...]
    preserved_section_ids: tuple[str, ...]


async def compile_document_revision(
    graph: CompiledStateGraph,
    *,
    request: str,
    current_document: AuthoringDocumentSpec,
    source_manifest: Mapping[str, Any] | None = None,
    logfile_path: str | None = None,
) -> RevisionCompilationResult:
    """Compile a scoped revision without mutating ``current_document``.

    The graph receives a JSON-safe snapshot rather than the canonical object.
    It may compile only the sections selected in its revision plan. Existing
    sections omitted by the plan are intentionally absent from the resulting
    partial intent and remain owned by the deterministic reconciler.
    """
    if not request.strip():
        raise ValueError("Revision request must be non-empty.")

    existing_snapshot = current_document.model_copy(deep=True)
    result = await graph.ainvoke(
        {
            "request": request,
            "mode": "revise",
            "logfile_path": logfile_path,
            "current_document": existing_snapshot.model_dump(mode="json"),
            "source_manifest": dict(source_manifest or {}),
            "compiled_artifacts": [],
            "diagnostics": [],
            "repair_attempt": 0,
        }
    )
    plan = ReconstructionPlan.model_validate(result["plan"])
    intent = AuthoringDocumentIntent.model_validate(result["merged_intent"])
    resolved_source_manifest = result.get("source_manifest", dict(source_manifest or {}))
    if not isinstance(resolved_source_manifest, Mapping):
        raise ValueError("Graph revision returned an invalid source_manifest.")
    affected_section_ids = tuple(section.section_id for section in plan.sections)
    intent_section_ids = (
        tuple(section.section_id for section in intent.sections)
        if isinstance(intent.sections, list)
        else ()
    )
    unexpected_section_ids = sorted(set(intent_section_ids) - set(affected_section_ids))
    if unexpected_section_ids:
        raise ValueError(
            "Revision compilation produced sections not selected by the revision plan: "
            f"{unexpected_section_ids!r}."
        )

    preserved_section_ids = tuple(
        section.id
        for section in existing_snapshot.sections
        if section.id not in affected_section_ids
    )
    return RevisionCompilationResult(
        existing_document=existing_snapshot,
        plan=plan,
        intent=intent,
        source_manifest=dict(resolved_source_manifest),
        affected_section_ids=affected_section_ids,
        preserved_section_ids=preserved_section_ids,
    )


__all__ = ["RevisionCompilationResult", "compile_document_revision"]
