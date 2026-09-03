###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Natural-language document planner for complex Wellplot reconstruction."""

from __future__ import annotations

import json
from contextlib import nullcontext
from dataclasses import dataclass

from ...capabilities import CapabilityRegistry
from ..execution_trace import current_agent_trace
from .models import CompilationMode, ReconstructionPlan
from .provider_adapter import StructuredModelProtocol


@dataclass(slots=True)
class ReconstructionPlanner:
    """Compile a natural-language request into a semantic reconstruction plan."""

    model: StructuredModelProtocol
    registry: CapabilityRegistry

    async def plan(
        self,
        *,
        request: str,
        current_document: dict[str, object],
        source_manifest: dict[str, object],
        mode: CompilationMode = "reconstruct",
    ) -> ReconstructionPlan:
        """Return a validated plan using only registered capabilities."""
        catalog = self.registry.planning_catalog()
        if mode == "revise":
            mode_instruction = (
                "This is a revision of the current document. Plan only sections that are "
                "materially changed or newly requested. Do not include unchanged sections "
                "solely to reproduce them; omitted sections are preserved deterministically. "
                "Plan report-wide changes only when the request explicitly changes them."
            )
        else:
            mode_instruction = (
                "This is a reconstruction. Plan every section needed to satisfy the request."
            )
        instructions = (
            "You are the semantic planning stage of Wellplot's natural-language compiler. "
            "Decompose the scientist's request into report requirements and independently "
            "compilable sections. Select only capability ids from the supplied registry. "
            "Do not emit MCP calls, low-level mutations, defaults, or implementation steps. "
            "Preserve explicit values and constraints exactly. A section is a semantic/layout "
            "isolation boundary, not a tool family. Use components to describe the capabilities "
            "needed inside each section. If a requested capability is unavailable, record it in "
            "unresolved_requirements rather than inventing one. Every component must set "
            "parent_component_id: use null only for a direct child of its section; otherwise "
            "reference a parent component_id in that same section. This field expresses "
            "structural ownership, not execution order. In revision mode, include an unchanged "
            "parent component as context when a changed child needs it. " + mode_instruction
        )
        context = {
            "request": request,
            "mode": mode,
            "current_document": current_document,
            "source_manifest": source_manifest,
            "available_capabilities": catalog,
        }
        trace = current_agent_trace()
        stage = trace.stage("planner") if trace is not None else nullcontext()
        with stage:
            plan = await self.model.generate(
                instructions=instructions,
                user_message=(
                    "Create the ReconstructionPlan for this request. The response schema is "
                    "supplied as the required function schema.\n\nContext:\n"
                    + json.dumps(context, indent=2, default=str)
                ),
                response_model=ReconstructionPlan,
                tool_name="submit_reconstruction_plan",
                tool_description="Submit the semantic reconstruction plan.",
                max_rounds=3,
            )
            self._validate_capabilities(plan)
            if trace is not None:
                trace.record(
                    "structured_output",
                    status="accepted",
                    payload=plan.model_dump(mode="json"),
                )
        return plan

    def _validate_capabilities(self, plan: ReconstructionPlan) -> None:
        self.registry.get(plan.report_capability_id)
        for section in plan.sections:
            section_spec = self.registry.get(section.capability_id)
            if section_spec.category != "section":
                raise ValueError(
                    f"Plan assigned non-section capability {section.capability_id!r} "
                    f"to section {section.section_id!r}."
                )

            components_by_id = {}
            for component in section.components:
                self.registry.get(component.capability_id)
                components_by_id[component.component_id] = component

            for component in section.components:
                spec = self.registry.get(component.capability_id)
                parent_capability_id = section.capability_id
                if component.parent_component_id is not None:
                    parent_component = components_by_id[component.parent_component_id]
                    parent_capability_id = parent_component.capability_id
                if spec.allowed_parents and parent_capability_id not in spec.allowed_parents:
                    raise ValueError(
                        f"Capability {spec.capability_id!r} cannot have parent capability "
                        f"{parent_capability_id!r} in section {section.section_id!r}. "
                        f"Allowed parents: {list(spec.allowed_parents)!r}."
                    )
