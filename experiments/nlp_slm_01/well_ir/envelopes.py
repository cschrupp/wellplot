"""Result envelopes for WELL-IR v1."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from .operations import WellIrOp
from .selectors import UnresolvedQuery
from .version import WELL_IR_VERSION

Status = Literal["ok", "ambiguous", "unsupported", "invalid"]

UnsupportedReason = Literal[
    "operation_not_supported",
    "reference_not_found",
    "capability_not_available",
]


class Ambiguity(BaseModel):
    field: str
    candidates: list[str | int]
    query: str | None = None


class OkEnvelope(BaseModel):
    status: Literal["ok"] = "ok"
    well_ir_version: str = WELL_IR_VERSION
    ops: list[WellIrOp]


class AmbiguousEnvelope(BaseModel):
    status: Literal["ambiguous"] = "ambiguous"
    well_ir_version: str = WELL_IR_VERSION
    ambiguities: list[Ambiguity]


class UnsupportedEnvelope(BaseModel):
    status: Literal["unsupported"] = "unsupported"
    well_ir_version: str = WELL_IR_VERSION
    reason: UnsupportedReason
    reference: UnresolvedQuery | None = None
    detail: str | None = None


class InvalidEnvelope(BaseModel):
    status: Literal["invalid"] = "invalid"
    well_ir_version: str = WELL_IR_VERSION
    detail: str


WellIrResult = Annotated[
    Union[OkEnvelope, AmbiguousEnvelope, UnsupportedEnvelope, InvalidEnvelope],
    Field(discriminator="status"),
]
