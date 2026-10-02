"""Provider-neutral reconciled semantic IR for planner-level evaluation.

This module is intentionally parallel to ``semantic_ir_v2``.  SI-V2 remains
frozen historical evidence; V2R makes reference/depth ownership explicit
without moving typed-worker or report-authoring details into the planner.
"""

from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _SemanticIRV2RModel(BaseModel):
    """Strict immutable configuration for the reconciled planner IR."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


def _require_nonempty_items(values: tuple[str, ...]) -> tuple[str, ...]:
    """Reject blank entries without changing caller order."""
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError("Semantic IR text collections cannot contain blank items.")
    return values


class CurveSemanticIntentV2R(_SemanticIRV2RModel):
    """Semantic intent for one ordinary scalar presentation."""

    kind: Literal["curve"]
    semantic_id: str = Field(min_length=1)
    requirements: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()

    @field_validator("requirements", "constraints")
    @classmethod
    def validate_text_items(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Preserve non-empty feature requirements."""
        return _require_nonempty_items(values)


class RasterSemanticIntentV2R(_SemanticIRV2RModel):
    """Semantic intent for one ordinary raster presentation."""

    kind: Literal["raster"]
    semantic_id: str = Field(min_length=1)
    requirements: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()

    @field_validator("requirements", "constraints")
    @classmethod
    def validate_text_items(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Preserve non-empty feature requirements."""
        return _require_nonempty_items(values)


class FillSemanticIntentV2R(_SemanticIRV2RModel):
    """Semantic fill attached to one scalar feature."""

    kind: Literal["fill"]
    semantic_id: str = Field(min_length=1)
    target_semantic_id: str = Field(min_length=1)
    requirements: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()

    @field_validator("requirements", "constraints")
    @classmethod
    def validate_text_items(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Preserve non-empty feature requirements."""
        return _require_nonempty_items(values)


class AnnotationSemanticIntentV2R(_SemanticIRV2RModel):
    """Semantic annotation inside the section visualization domain."""

    kind: Literal["annotation"]
    semantic_id: str = Field(min_length=1)
    requirements: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()

    @field_validator("requirements", "constraints")
    @classmethod
    def validate_text_items(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Preserve non-empty feature requirements."""
        return _require_nonempty_items(values)


class ExtensionSemanticIntentV2R(_SemanticIRV2RModel):
    """Provider-neutral hook for a registered semantic extension."""

    kind: Literal["extension"]
    semantic_id: str = Field(min_length=1)
    semantic_key: str = Field(min_length=1)
    requirements: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()

    @field_validator("requirements", "constraints")
    @classmethod
    def validate_text_items(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Preserve non-empty feature requirements."""
        return _require_nonempty_items(values)


SemanticFeatureV2R: TypeAlias = Annotated[
    CurveSemanticIntentV2R
    | RasterSemanticIntentV2R
    | FillSemanticIntentV2R
    | AnnotationSemanticIntentV2R
    | ExtensionSemanticIntentV2R,
    Field(discriminator="kind"),
]


class ReferenceSemanticIntentV2R(_SemanticIRV2RModel):
    """Section-owned reference meaning, separate from data feature kind."""

    kind: Literal["companion_depth_lane", "reference_track"]
    target_semantic_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_target(self) -> ReferenceSemanticIntentV2R:
        """Require a target only when data is assigned to a reference track."""
        if self.kind == "reference_track" and self.target_semantic_id is None:
            raise ValueError("reference_track intent requires target_semantic_id.")
        if self.kind == "companion_depth_lane" and self.target_semantic_id is not None:
            raise ValueError("companion_depth_lane intent cannot target a data feature.")
        return self


class ReportWorkIntentV2R(_SemanticIRV2RModel):
    """Coarse report work; report construction remains report-worker-owned."""

    goal: str = Field(min_length=1)
    requirements: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()

    @field_validator("requirements", "constraints")
    @classmethod
    def validate_text_items(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Preserve report requirements without introducing report AST fields."""
        return _require_nonempty_items(values)


class SectionSemanticIntentV2R(_SemanticIRV2RModel):
    """One ordered semantic log section."""

    kind: Literal["log_plot"]
    goal: str = Field(min_length=1)
    existing_section_hint: str | None = Field(default=None, min_length=1)
    source_hints: tuple[str, ...] = ()
    features: tuple[SemanticFeatureV2R, ...] = Field(min_length=1)
    reference_intent: ReferenceSemanticIntentV2R | None = None
    requirements: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()

    @field_validator("source_hints", "requirements", "constraints")
    @classmethod
    def validate_text_items(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Preserve section context and requirements."""
        return _require_nonempty_items(values)

    @model_validator(mode="after")
    def validate_feature_ids(self) -> SectionSemanticIntentV2R:
        """Reject identity collapse and invalid reference targets."""
        feature_ids = [feature.semantic_id for feature in self.features]
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError("Semantic feature IDs must be unique within a section.")
        if (
            self.reference_intent
            and self.reference_intent.kind == "reference_track"
            and self.reference_intent.target_semantic_id
            not in {feature.semantic_id for feature in self.features}
        ):
            raise ValueError("Reference target must identify a section feature.")
        curve_ids = {
            feature.semantic_id
            for feature in self.features
            if isinstance(feature, CurveSemanticIntentV2R)
        }
        for feature in self.features:
            if isinstance(feature, FillSemanticIntentV2R) and (
                feature.target_semantic_id not in curve_ids
            ):
                raise ValueError("Fill target must reference a curve in the same section.")
        return self


class SemanticIRV2R(_SemanticIRV2RModel):
    """Provider-neutral reconciled semantic intent."""

    summary: str = Field(min_length=1)
    report_work: ReportWorkIntentV2R | None = None
    sections: tuple[SectionSemanticIntentV2R, ...] = ()
    unresolved_requirements: tuple[str, ...] = ()

    @field_validator("unresolved_requirements")
    @classmethod
    def validate_text_items(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Preserve unsupported requirements for later handling."""
        return _require_nonempty_items(values)

    @model_validator(mode="after")
    def validate_work(self) -> SemanticIRV2R:
        """Require at least one report or section semantic intent."""
        if self.report_work is None and not self.sections:
            raise ValueError("SemanticIRV2R must contain report or section intent.")
        return self


__all__ = [
    "AnnotationSemanticIntentV2R",
    "CurveSemanticIntentV2R",
    "ExtensionSemanticIntentV2R",
    "FillSemanticIntentV2R",
    "RasterSemanticIntentV2R",
    "ReferenceSemanticIntentV2R",
    "ReportWorkIntentV2R",
    "SectionSemanticIntentV2R",
    "SemanticFeatureV2R",
    "SemanticIRV2R",
]
