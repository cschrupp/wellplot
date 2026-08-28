###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Report-wide compiler node."""

from __future__ import annotations

import json
from dataclasses import dataclass

from ...capabilities import CapabilityRegistry
from .models import CompiledArtifact, ReconstructionPlan
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
    ) -> CompiledArtifact:
        """Compile only report-wide requirements from one semantic plan."""
        spec = self.registry.get(plan.report_capability_id)
        if spec.category != "report":
            raise ValueError(f"{plan.report_capability_id!r} is not a report capability.")
        context = {
            "original_request": request,
            "report_goal": plan.report_goal,
            "report_values": plan.report_values,
            "postconditions": plan.postconditions,
            "current_document": current_document,
            "source_manifest": source_manifest,
            "capability": spec.worker_descriptor(),
        }
        artifact = await self.model.generate(
            instructions=(
                "You are the report-wide compiler. Compile only report/header/page/depth/output/"
                "remarks/tail requirements. Do not author section-local tracks, bindings, fills, "
                "or annotations. Return desired state, not an operation sequence or MCP calls."
            ),
            user_message=(
                "Compile the report-wide portion of the reconstruction.\n\nContext:\n"
                + json.dumps(context, indent=2, default=str)
            ),
            response_model=spec.artifact_model,
            tool_name="submit_report_artifact",
            tool_description="Submit typed report-wide desired state.",
            max_rounds=3,
        )
        return CompiledArtifact(
            worker_id="report",
            capability_id=spec.capability_id,
            target_id="report",
            payload=artifact.model_dump(mode="json", exclude_unset=True),
        )
