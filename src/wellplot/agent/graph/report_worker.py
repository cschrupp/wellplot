###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Report-wide compiler node."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass

from ...capabilities import CapabilityRegistry
from ..execution_trace import current_agent_trace
from .models import CompilationMode, CompiledArtifact, ReconstructionPlan
from .prompt_context import compact_prompt_json
from .provider_adapter import StructuredModelProtocol


@dataclass(slots=True)
class ReportCompiler:
    """Compile report-wide desired state into one capability artifact."""

    model: StructuredModelProtocol
    registry: CapabilityRegistry

    async def compile(
        self,
        *,
        request: str,
        plan: ReconstructionPlan,
        current_document: dict[str, object],
        source_manifest: dict[str, object],
        mode: CompilationMode = "reconstruct",
    ) -> CompiledArtifact:
        """Compile only report-wide requirements from one semantic plan."""
        spec = self.registry.get(plan.report_capability_id)
        if spec.category != "report":
            raise ValueError(f"{plan.report_capability_id!r} is not a report capability.")
        revision_instruction = (
            " In revision mode, omit unchanged report-wide values so their current state is "
            "preserved."
            if mode == "revise"
            else ""
        )
        context = {
            "original_request": request,
            "report_goal": plan.report_goal,
            "report_values": plan.report_values,
            "postconditions": plan.postconditions,
            "mode": mode,
            "current_document": current_document,
            "source_manifest": source_manifest,
            # The required function schema is sent separately; do not duplicate it here.
            "capability": spec.planning_descriptor(),
        }
        trace = current_agent_trace()
        stage = trace.stage("report", target_id="report") if trace is not None else nullcontext()
        with stage:
            artifact = await self.model.generate(
                instructions=(
                    "You are the report-wide compiler. Compile only report/header/page/depth/"
                    "output/remarks/tail requirements. Do not author section-local tracks, "
                    "bindings, fills, or annotations. Return desired state, not an operation "
                    "sequence or MCP calls. " + revision_instruction
                ),
                user_message=(
                    "Compile the report-wide portion of the reconstruction.\n\nContext:\n"
                    + compact_prompt_json(context)
                ),
                response_model=spec.artifact_model,
                tool_name="submit_report_artifact",
                tool_description="Submit typed report-wide desired state.",
                max_rounds=3,
            )
            if trace is not None:
                trace.record(
                    "structured_output",
                    status="accepted",
                    payload=artifact.model_dump(mode="json", exclude_unset=True),
                )
        return CompiledArtifact(
            worker_id="report",
            capability_id=spec.capability_id,
            target_id="report",
            payload=artifact.model_dump(mode="json", exclude_unset=True),
        )
