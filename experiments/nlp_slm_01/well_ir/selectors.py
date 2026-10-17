"""Closed typed selector algebra for WELL-IR 1.2-candidate."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


ReferentKind = Literal["curve", "track", "fill"]


class ResolvedRef(BaseModel):
    """Uniquely bound workspace, request-local handle, or program-local reference."""

    kind: ReferentKind
    ref: str | int | None = None
    local_ref: str | None = None
    handle: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _promote_handle(cls, data: object) -> object:
        if isinstance(data, dict) and data.get("handle") and not data.get("ref") and not data.get("local_ref"):
            # Request-local curve-N / fill-N selectors from WELL-IR 1.2
            out = dict(data)
            out["ref"] = data["handle"]
            return out
        return data

    @model_validator(mode="after")
    def _exactly_one_binding(self) -> ResolvedRef:
        has_ref = self.ref is not None
        has_local = self.local_ref is not None
        if has_ref == has_local:
            raise ValueError("ResolvedRef requires exactly one of ref or local_ref")
        if has_local and not str(self.local_ref).startswith("$"):
            raise ValueError("local_ref must start with '$'")
        if self.kind == "track" and has_ref and not isinstance(self.ref, (int, str)):
            raise ValueError("track ref must be an int logical track number or string id/title")
        if self.kind in {"curve", "fill"} and has_ref and not isinstance(self.ref, str):
            raise ValueError(f"{self.kind} ref must be a string symbol")
        return self


class UnresolvedQuery(BaseModel):
    """Non-executable diagnostic query (envelope only; never inside ok ops)."""

    kind: ReferentKind
    query: str
    family: str | None = None


CurveRef = Annotated[ResolvedRef, Field(description="Resolved curve selector")]
TrackRef = Annotated[ResolvedRef, Field(description="Resolved track selector")]
FillRef = Annotated[ResolvedRef, Field(description="Resolved fill selector")]
