###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Typed semantic IR used by the LangGraph reconstruction workflow."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SemanticComponentPlan(BaseModel):
    """One capability requested inside a section.

    This is deliberately semantic rather than a low-level mutation. ``values``
    contains facts explicitly requested by the scientist; defaults are resolved
    later by capability compilers and Wellplot's deterministic domain layer.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    component_id: str = Field(min_length=1)
    capability_id: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    values: dict[str, Any] = Field(default_factory=dict)
    source_hints: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)


class SectionPlan(BaseModel):
    """Semantic plan for one independently compilable plot section."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    section_id: str = Field(min_length=1)
    capability_id: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    values: dict[str, Any] = Field(default_factory=dict)
    components: list[SemanticComponentPlan] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)


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
