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
            "unresolved_requirements rather than inventing one. " + mode_instruction
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

            components_by_id: dict[str, str] = {}
            for component in section.components:
                if component.component_id in components_by_id:
                    raise ValueError(
                        f"Component id {component.component_id!r} appears more than once "
                        f"in section {section.section_id!r}."
                    )
                self.registry.get(component.capability_id)
                components_by_id[component.component_id] = component.capability_id

            for component in section.components:
                spec = self.registry.get(component.capability_id)
                parent_capability_ids = {section.capability_id}
                for dependency_id in component.depends_on:
                    dependency_capability_id = components_by_id.get(dependency_id)
                    if dependency_capability_id is None:
                        raise ValueError(
                            f"Component {component.component_id!r} in section "
                            f"{section.section_id!r} depends on unknown component "
                            f"{dependency_id!r}."
                        )
                    parent_capability_ids.add(dependency_capability_id)
                if spec.allowed_parents and not (parent_capability_ids & set(spec.allowed_parents)):
                    raise ValueError(
                        f"Capability {spec.capability_id!r} cannot be a component of section "
                        f"{section.section_id!r} without a parent capability in "
                        f"{list(spec.allowed_parents)!r}."
                    )
