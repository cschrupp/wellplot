"""Provider-neutral Semantic IR v2 models for architecture evaluation."""

from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _SemanticIRModel(BaseModel):
    """Strict immutable configuration for the provider-neutral IR."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


def _require_nonempty_items(values: tuple[str, ...]) -> tuple[str, ...]:
    """Reject blank entries without changing the caller's order."""
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError("Semantic IR text collections cannot contain blank items.")
    return values


class CurveSemanticIntent(_SemanticIRModel):
    """Semantic intent for one scalar curve presentation."""

    kind: Literal["curve"]
    semantic_id: str = Field(min_length=1)
    reference: bool = False
    requirements: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()

    @field_validator("requirements", "constraints")
    @classmethod
    def validate_text_items(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Preserve non-empty feature requirements."""
        return _require_nonempty_items(values)


class RasterSemanticIntent(_SemanticIRModel):
    """Semantic intent for one array/raster presentation."""

    kind: Literal["raster"]
    semantic_id: str = Field(min_length=1)
    reference: bool = False
    requirements: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()

    @field_validator("requirements", "constraints")
    @classmethod
    def validate_text_items(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Preserve non-empty feature requirements."""
        return _require_nonempty_items(values)


class FillSemanticIntent(_SemanticIRModel):
    """Semantic curve-fill intent attached to one curve feature."""

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


class AnnotationSemanticIntent(_SemanticIRModel):
    """Semantic typed-annotation intent for a section."""

    kind: Literal["annotation"]
    semantic_id: str = Field(min_length=1)
    requirements: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()

    @field_validator("requirements", "constraints")
    @classmethod
    def validate_text_items(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Preserve non-empty feature requirements."""
        return _require_nonempty_items(values)


class ExtensionSemanticIntent(_SemanticIRModel):
    """Provider-neutral hook for a registered plugin semantic concept."""

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


SemanticFeatureV2: TypeAlias = Annotated[
    CurveSemanticIntent
    | RasterSemanticIntent
    | FillSemanticIntent
    | AnnotationSemanticIntent
    | ExtensionSemanticIntent,
    Field(discriminator="kind"),
]


class ReportSemanticIntent(_SemanticIRModel):
    """Semantic report intent; the host supplies the report capability root."""

    goal: str = Field(min_length=1)
    requirements: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()

    @field_validator("requirements", "constraints")
    @classmethod
    def validate_text_items(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Preserve report requirements."""
        return _require_nonempty_items(values)


class SectionSemanticIntentV2(_SemanticIRModel):
    """Semantic intent for one independently ordered log-plot section."""

    kind: Literal["log_plot"]
    goal: str = Field(min_length=1)
    existing_section_hint: str | None = Field(default=None, min_length=1)
    source_hints: tuple[str, ...] = ()
    features: tuple[SemanticFeatureV2, ...] = Field(min_length=1)
    requirements: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()

    @field_validator("source_hints", "requirements", "constraints")
    @classmethod
    def validate_text_items(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Preserve section context and requirements."""
        return _require_nonempty_items(values)

    @model_validator(mode="after")
    def validate_feature_ids(self) -> SectionSemanticIntentV2:
        """Reject identity collapse before capability lowering."""
        feature_ids = [feature.semantic_id for feature in self.features]
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError("Semantic feature IDs must be unique within a section.")
        curve_ids = {
            feature.semantic_id
            for feature in self.features
            if isinstance(feature, CurveSemanticIntent)
        }
        for feature in self.features:
            if isinstance(feature, FillSemanticIntent) and (
                feature.target_semantic_id not in curve_ids
            ):
                raise ValueError(
                    "Fill semantic target must reference a curve feature in the same section."
                )
        return self


class SemanticIRV2(_SemanticIRModel):
    """Provider-neutral semantic intent lowered to the existing SemanticPlan."""

    summary: str = Field(min_length=1)
    report: ReportSemanticIntent | None = None
    sections: tuple[SectionSemanticIntentV2, ...] = ()
    unresolved_requirements: tuple[str, ...] = ()

    @field_validator("unresolved_requirements")
    @classmethod
    def validate_text_items(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Preserve unsupported requirements for later handling."""
        return _require_nonempty_items(values)

    @model_validator(mode="after")
    def validate_work(self) -> SemanticIRV2:
        """Require at least one report or section semantic intent."""
        if self.report is None and not self.sections:
            raise ValueError("SemanticIRV2 must contain report or section intent.")
        return self


__all__ = [
    "AnnotationSemanticIntent",
    "CurveSemanticIntent",
    "ExtensionSemanticIntent",
    "FillSemanticIntent",
    "RasterSemanticIntent",
    "ReportSemanticIntent",
    "SectionSemanticIntentV2",
    "SemanticFeatureV2",
    "SemanticIRV2",
]
