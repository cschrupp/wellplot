###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Compile natural-language reconstructions into canonical document intent."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from langgraph.graph.state import CompiledStateGraph

from ...model.authoring import AuthoringDocumentSpec
from ...model.intent import AuthoringDocumentIntent
from .models import ReconstructionPlan


@dataclass(frozen=True)
class ReconstructionCompilationResult:
    """Typed evidence from one compile-only document reconstruction."""

    starting_document: AuthoringDocumentSpec
    plan: ReconstructionPlan
    intent: AuthoringDocumentIntent
    source_manifest: dict[str, Any]


async def compile_document_reconstruction(
    graph: CompiledStateGraph,
    *,
    request: str,
    current_document: AuthoringDocumentSpec,
    source_manifest: Mapping[str, Any] | None = None,
    logfile_path: str | None = None,
) -> ReconstructionCompilationResult:
    """Compile one reconstruction request without mutating ``current_document``.

    The graph receives a JSON-safe snapshot of the canonical starting document.
    It remains responsible only for language compilation; reconciliation and
    mutation stay at the deterministic application boundary.
    """
    if not request.strip():
        raise ValueError("Reconstruction request must be non-empty.")

    starting_snapshot = current_document.model_copy(deep=True)
    result = await graph.ainvoke(
        {
            "request": request,
            "mode": "reconstruct",
            "logfile_path": logfile_path,
            "current_document": starting_snapshot.model_dump(mode="json"),
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
        raise ValueError("Graph reconstruction returned an invalid source_manifest.")
    planned_section_ids = {section.section_id for section in plan.sections}
    intent_section_ids = (
        {section.section_id for section in intent.sections}
        if isinstance(intent.sections, list)
        else set()
    )
    unexpected_section_ids = sorted(intent_section_ids - planned_section_ids)
    if unexpected_section_ids:
        raise ValueError(
            "Reconstruction compilation produced sections not selected by the plan: "
            f"{unexpected_section_ids!r}."
        )

    return ReconstructionCompilationResult(
        starting_document=starting_snapshot,
        plan=plan,
        intent=intent,
        source_manifest=dict(resolved_source_manifest),
    )


__all__ = ["ReconstructionCompilationResult", "compile_document_reconstruction"]
