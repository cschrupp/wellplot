###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Scoped section compiler used by dynamic LangGraph workers."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from functools import partial

from pydantic import BaseModel

from ...authoring_service import AuthoringService
from ...capabilities import CapabilityRegistry
from ...capabilities.builtins import LogPlotSectionArtifact
from ...model.authoring import AuthoringDocumentSpec
from ..execution_trace import current_agent_trace
from .context_projection import section_document_context, section_source_context
from .executor import execute_document_intent
from .models import CompilationMode, CompiledArtifact, SectionPlan
from .prompt_context import compact_prompt_json
from .provider_adapter import StructuredModelProtocol
from .source_context import available_channels_from_source_manifest
from .worker_contracts import section_contract


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

        selected_ids = {plan.capability_id, *(item.capability_id for item in plan.components)}
        worker_catalog = tuple(
            self.registry.get(capability_id).planning_descriptor()
            for capability_id in sorted(selected_ids)
        )
        revision_instruction = (
            " In revision mode, this selected section is the only section you may compile; omit "
            "unchanged fields so deterministic reconciliation preserves them."
            if mode == "revise"
            else ""
        )
        instructions = (
            "You are one isolated Wellplot section compiler. Compile only the supplied section "
            "plan. Do not modify other sections or report-wide settings. Use only the supplied "
            "capabilities and source information. Call submit_section_artifact with the typed "
            "artifact as its function arguments, matching the supplied function schema. "
            "A JSON object in assistant text or a Markdown code block is not a submission. "
            "This submission function returns desired state; do not request editing tools or "
            "describe an operation sequence. The result is "
            "desired state; Wellplot's deterministic compiler/executor will decide how to "
            "reach it. Use component target_id as the canonical object ID and "
            "parent_component_id for ownership. Include every planned target. For new "
            "objects supply a display title, kind and width; omit unrequested optional "
            "settings to keep defaults. When section_plan declares data_source, return that "
            "exact source_path and source_format. Do not clear fields during construction."
            " Submit only requested changes and required identities, not a copy of the "
            "current document with all defaults expanded. For raster bindings, omit "
            "unrequested color_limits and normalization settings. The string 'null' is "
            "not an omitted value." + revision_instruction
        )
        context = {
            "original_request": request,
            "mode": mode,
            "section_plan": plan.model_dump(mode="json"),
            "current_document": section_document_context(current_document, plan.section_id),
            "source_manifest": section_source_context(source_manifest, plan.section_id),
            # The section artifact schema is already the required function schema.
            "capabilities": worker_catalog,
        }
        trace = current_agent_trace()
        stage = (
            trace.stage("section", target_id=plan.section_id)
            if trace is not None
            else nullcontext()
        )
        with stage:
            response_model = section_spec.artifact_model
            if response_model is LogPlotSectionArtifact:
                response_model = section_contract(
                    plan, current_document, self.registry, reconstruct=mode == "reconstruct"
                )
            artifact: BaseModel = await self.model.generate(
                instructions=instructions,
                user_message=(
                    f"Compile section {plan.section_id!r}. The artifact schema is supplied as "
                    "the required function schema.\n\nContext:\n" + compact_prompt_json(context)
                ),
                response_model=response_model,
                tool_name="submit_section_artifact",
                tool_description=f"Submit the typed artifact for section {plan.section_id!r}.",
                max_rounds=3,
                response_validator=(
                    partial(
                        self._validate_section,
                        plan=plan,
                        current_document=current_document,
                        source_manifest=source_manifest,
                    )
                    if section_spec.artifact_model is LogPlotSectionArtifact
                    else None
                ),
            )
            if trace is not None:
                trace.record(
                    "structured_output",
                    status="accepted",
                    payload=artifact.model_dump(mode="json", exclude_unset=True),
                )
        return CompiledArtifact(
            worker_id=f"section:{plan.section_id}",
            capability_id=section_spec.capability_id,
            target_id=plan.section_id,
            payload=artifact.model_dump(mode="json", exclude_unset=True),
            covered_component_ids=[item.component_id for item in plan.components],
        )

    def _validate_section(
        self,
        artifact: BaseModel,
        *,
        plan: SectionPlan,
        current_document: dict[str, object],
        source_manifest: dict[str, object],
    ) -> None:
        """Check applicability on a private snapshot before accepting a submission."""
        self._validate_targets(artifact, plan)
        document = AuthoringDocumentSpec.model_validate(current_document).model_copy(deep=True)
        # Use the same canonical conversion as the merge boundary, preserving
        # omitted fields from the provider's scoped construction model.
        spec = self.registry.get(plan.capability_id)
        canonical = spec.artifact_model.model_validate(
            artifact.model_dump(mode="json", exclude_unset=True)
        )
        intent = spec.compiler(canonical)
        result = execute_document_intent(
            AuthoringService(document),
            intent,
            available_channels=available_channels_from_source_manifest(source_manifest),
        )
        if not result.success:
            raise ValueError(
                "Section cannot be applied to the current scaffold:\n" + "\n".join(result.errors)
            )

    def _validate_targets(self, artifact: BaseModel, plan: SectionPlan) -> None:
        """Require every planned target at its explicit parent before acceptance."""
        if not plan.components:
            return
        tracks = artifact.section.tracks
        if not isinstance(tracks, list):
            raise ValueError("Planned component edits require explicit tracks in the artifact.")
        tracks_by_id = {track.track_id: track for track in tracks or []}
        if len(tracks_by_id) != len(tracks or []):
            raise ValueError("A section artifact must not repeat track IDs.")
        components = {item.component_id: item for item in plan.components}
        planned_track_ids = [
            item.target_id
            for item in plan.components
            if self.registry.get(item.capability_id).category == "track"
        ]
        if [track.track_id for track in tracks] != planned_track_ids:
            raise ValueError(
                f"Section {plan.section_id!r} tracks must preserve planned target order "
                f"{planned_track_ids!r}."
            )
        for component in plan.components:
            category = self.registry.get(component.capability_id).category
            if category == "track":
                found = component.target_id in tracks_by_id
            else:
                parent = components[component.parent_component_id]
                track = tracks_by_id.get(parent.target_id)
                collection, identity = {
                    "binding": ("bindings", "binding_id"),
                    "fill": ("fills", "fill_id"),
                    "annotation": ("annotations", "annotation_id"),
                }[category]
                children = getattr(track, collection, None)
                found = (
                    isinstance(children, list)
                    and sum(getattr(child, identity) == component.target_id for child in children)
                    == 1
                )
            if not found:
                raise ValueError(
                    f"Section {plan.section_id!r} omitted planned {category} target "
                    f"{component.target_id!r} at its declared parent."
                )
