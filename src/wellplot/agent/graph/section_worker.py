###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Scoped section compiler used by dynamic LangGraph workers."""

from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic import BaseModel

from ...capabilities import CapabilityRegistry
from .models import CompilationMode, CompiledArtifact, SectionPlan
from .provider_adapter import StructuredModelProtocol


@dataclass(slots=True)
class SectionCompiler:
    """Compile one isolated section plan into a capability artifact."""

    model: StructuredModelProtocol
    registry: CapabilityRegistry

    async def compile(
        self,
        *,
        request: str,
        plan: SectionPlan,
        current_document: dict[str, object],
        source_manifest: dict[str, object],
        mode: CompilationMode = "reconstruct",
    ) -> CompiledArtifact:
        """Compile the requested section without mutating shared document state."""
        section_spec = self.registry.get(plan.capability_id)
        if section_spec.category != "section":
            raise ValueError(f"{plan.capability_id!r} is not a section capability.")

        selected_ids = [plan.capability_id, *(item.capability_id for item in plan.components)]
        worker_catalog = self.registry.worker_catalog(selected_ids)
        revision_instruction = (
            " In revision mode, this selected section is the only section you may compile; omit "
            "unchanged fields so deterministic reconciliation preserves them."
            if mode == "revise"
            else ""
        )
        instructions = (
            "You are one isolated Wellplot section compiler. Compile only the supplied section "
            "plan. Do not modify other sections or report-wide settings. Use only the supplied "
            "capabilities and source information. Return the typed artifact required by the "
            "section capability. Do not emit MCP calls or an operation sequence. The result is "
            "desired state; Wellplot's deterministic compiler/executor will decide how to "
            "reach it." + revision_instruction
        )
        context = {
            "original_request": request,
            "mode": mode,
            "section_plan": plan.model_dump(mode="json"),
            "current_document": current_document,
            "source_manifest": source_manifest,
            "capabilities": worker_catalog,
        }
        artifact: BaseModel = await self.model.generate(
            instructions=instructions,
            user_message=(
                f"Compile section {plan.section_id!r}. The artifact schema is supplied as the "
                "required function schema.\n\nContext:\n"
                + json.dumps(context, indent=2, default=str)
            ),
            response_model=section_spec.artifact_model,
            tool_name="submit_section_artifact",
            tool_description=f"Submit the typed artifact for section {plan.section_id!r}.",
            max_rounds=3,
        )
        return CompiledArtifact(
            worker_id=f"section:{plan.section_id}",
            capability_id=section_spec.capability_id,
            target_id=plan.section_id,
            payload=artifact.model_dump(mode="json", exclude_unset=True),
            covered_component_ids=[item.component_id for item in plan.components],
        )
