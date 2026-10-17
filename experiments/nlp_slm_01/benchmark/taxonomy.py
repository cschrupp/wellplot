"""Failure taxonomy labels for SLM-01."""

from __future__ import annotations

from typing import Literal

ModelSemanticFailure = Literal[
    "alias_resolution",
    "composition",
    "relation",
    "units",
    "deictic",
    "ordering",
    "envelope_misuse",
]

InfrastructureFailure = Literal[
    "ir_limitation",
    "representational_ambiguity",
    "lowerer_bug",
    "context_assembler_bug",
    "gold_error",
    "syntax_or_schema",
    "other",
]

FailureLabel = ModelSemanticFailure | InfrastructureFailure

LEARNABLE = {
    "alias_resolution",
    "composition",
    "relation",
    "units",
    "deictic",
    "ordering",
    "envelope_misuse",
}

IR_BLOCKERS = {"ir_limitation", "representational_ambiguity"}

SEMANTIC_FAMILIES = (
    "curve_placement",
    "display_configuration",
    "intervals",
    "fills",
    "relational_targeting",
    "composition",
    "ambiguity_unsupported",
)
