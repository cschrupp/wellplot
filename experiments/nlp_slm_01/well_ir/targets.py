"""Canonical placement target algebra for WELL-IR 1.2-candidate."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, model_validator

from .selectors import ResolvedRef

Relation = Literal["with", "beside", "before", "after"]


class AbsoluteTrackTarget(BaseModel):
    mode: Literal["track"] = "track"
    reference: ResolvedRef

    @model_validator(mode="after")
    def _track_kind(self) -> AbsoluteTrackTarget:
        if self.reference.kind != "track":
            raise ValueError("absolute track target requires kind=track reference")
        return self


class RelativeTarget(BaseModel):
    mode: Literal["relative"] = "relative"
    relation: Relation
    reference: ResolvedRef

    @model_validator(mode="after")
    def _relative_ref_kind(self) -> RelativeTarget:
        if self.relation in {"with", "beside", "before", "after"} and self.reference.kind not in {
            "curve",
            "track",
        }:
            raise ValueError("relative target reference must be curve or track")
        return self


class AppendTarget(BaseModel):
    """Append a new track at the end of the section (WELL-IR 1.2)."""

    mode: Literal["append"] = "append"


PlacementTarget = Annotated[
    Union[AbsoluteTrackTarget, RelativeTarget, AppendTarget],
    Field(discriminator="mode"),
]
