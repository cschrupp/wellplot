###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Typed semantic IR used by the LangGraph reconstruction workflow."""

from __future__ import annotations

from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

CompilationMode: TypeAlias = Literal["reconstruct", "revise"]


class SemanticComponentPlan(BaseModel):
    """One capability requested inside a section.

    This is deliberately semantic rather than a low-level mutation. ``values``
    contains facts explicitly requested by the scientist; defaults are resolved
    later by capability compilers and Wellplot's deterministic domain layer.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    component_id: str = Field(min_length=1)
    target_id: str = Field(
        min_length=1,
        description=(
            "Canonical object ID, distinct from component_id. For a track use its local "
            "ID within the section (e.g. combo), not a section-prefixed planning ID. "
            "For a binding use its unique binding_id. Reuse existing IDs when revising."
        ),
    )
    capability_id: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    values: dict[str, Any] = Field(default_factory=dict)
    source_hints: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    parent_component_id: str | None = Field(
        description=(
            "Structural parent component in this section. Use null only when the section "
            "is the direct parent; otherwise reference a component_id from the same section."
        )
    )


class PlannedSectionDataSource(BaseModel):
    """One explicit source selected for a planned section."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_path: str = Field(
        min_length=1,
        description=("Path to the staged source file, resolved relative to the target logfile."),
    )
    source_format: Literal["auto", "las", "dlis"] = Field(
        default="auto",
        description="Lowercase source format. Use auto only when the file suffix is reliable.",
    )


class SectionPlan(BaseModel):
    """Semantic plan for one independently compilable plot section."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    section_id: str = Field(min_length=1)
    capability_id: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    data_source: PlannedSectionDataSource | None = Field(
        default=None,
        description=(
            "Explicit source routing for this section. Required for a newly planned section "
            "that is not already represented in the inspected source manifest."
        ),
    )
    values: dict[str, Any] = Field(default_factory=dict)
    components: list[SemanticComponentPlan] = Field(
        default_factory=list,
        description=(
            "Ordered explicit component targets for every requested track, binding, fill "
            "and annotation. Empty only for section settings with no child edits. "
            "Do not encode child objects solely as prose constraints."
        ),
    )
    constraints: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_component_hierarchy(self) -> SectionPlan:
        """Require an acyclic local ownership tree for section components."""
        hidden_source_keys = sorted(
            {"data_source", "source_format", "source_path"}.intersection(self.values)
        )
        if hidden_source_keys:
            raise ValueError(
                "Section source routing must be declared through the typed data_source field, "
                "not SectionPlan.values. "
                f"Unsupported values keys: {hidden_source_keys!r}."
            )
        components_by_id: dict[str, SemanticComponentPlan] = {}
        for component in self.components:
            if component.component_id in components_by_id:
                raise ValueError(
                    f"Component id {component.component_id!r} appears more than once "
                    f"in section {self.section_id!r}."
                )
            components_by_id[component.component_id] = component

        for component in self.components:
            parent_id = component.parent_component_id
            if parent_id is None:
                continue
            if parent_id == component.component_id:
                raise ValueError(
                    f"Component {component.component_id!r} in section {self.section_id!r} "
                    "cannot be its own parent."
                )
            if parent_id not in components_by_id:
                raise ValueError(
                    f"Component {component.component_id!r} in section {self.section_id!r} "
                    f"references unknown parent component {parent_id!r}."
                )

        for component in self.components:
            seen = {component.component_id}
            parent_id = component.parent_component_id
            while parent_id is not None:
                if parent_id in seen:
                    raise ValueError(
                        f"Component parent relationship in section {self.section_id!r} "
                        f"contains a cycle at {parent_id!r}."
                    )
                seen.add(parent_id)
                parent_id = components_by_id[parent_id].parent_component_id
        return self


class ReconstructionPlan(BaseModel):
    """Planner output for one unrestricted natural-language reconstruction."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    summary: str = Field(min_length=1)
    report_capability_id: str = "report.standard"
    report_goal: str = "Preserve report-wide settings unless explicitly requested otherwise."
    report_values: dict[str, Any] = Field(default_factory=dict)
    sections: list[SectionPlan] = Field(min_length=1)
    postconditions: list[str] = Field(default_factory=list)
    unresolved_requirements: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_unique_section_ids(self) -> ReconstructionPlan:
        """Reject plans that assign the same stable identifier twice."""
        ids = [section.section_id for section in self.sections]
        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        if duplicates:
            raise ValueError(f"Section ids must be unique: {duplicates!r}.")
        return self


class CompiledArtifact(BaseModel):
    """Validated worker artifact stored in graph state as JSON-safe data."""

    model_config = ConfigDict(extra="forbid")

    worker_id: str
    capability_id: str
    target_id: str
    payload: dict[str, Any]
    covered_component_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ReconstructionDiagnostic(BaseModel):
    """Compact structured diagnostic emitted by any graph stage."""

    model_config = ConfigDict(extra="forbid")

    stage: str
    message: str
    severity: str = "info"
    target_id: str | None = None


class VisualCorrection(BaseModel):
    """Future visual-QA output routed back to one capability worker."""

    model_config = ConfigDict(extra="forbid")

    target_id: str
    capability_id: str
    issue: str
    requested_change: dict[str, Any] = Field(default_factory=dict)
