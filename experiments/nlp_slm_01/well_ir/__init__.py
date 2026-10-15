"""WELL-IR v1: domain-semantic intent representation for SLM-01."""

from .canonicalize import canonicalize, canonicalize_json, parse_well_ir
from .envelopes import (
    AmbiguousEnvelope,
    InvalidEnvelope,
    OkEnvelope,
    UnsupportedEnvelope,
    WellIrResult,
)
from .operations import WellIrOp
from .schema import well_ir_json_schema, write_json_schema
from .version import WELL_IR_SCHEMA_ID, WELL_IR_VERSION

__all__ = [
    "WELL_IR_SCHEMA_ID",
    "WELL_IR_VERSION",
    "AmbiguousEnvelope",
    "InvalidEnvelope",
    "OkEnvelope",
    "UnsupportedEnvelope",
    "WellIrOp",
    "WellIrResult",
    "canonicalize",
    "canonicalize_json",
    "parse_well_ir",
    "well_ir_json_schema",
    "write_json_schema",
]
