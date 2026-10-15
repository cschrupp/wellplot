"""Deterministic WELL-IR lowering for SLM-01."""

from .apply import LoweringResult, apply_well_ir, check_invariants
from .context import DocumentState, WorkspaceContext, default_triple_combo_d0, default_workspace_from_d0
from .errors import LowererError, PreconditionError

__all__ = [
    "DocumentState",
    "LowererError",
    "LoweringResult",
    "PreconditionError",
    "WorkspaceContext",
    "apply_well_ir",
    "check_invariants",
    "default_triple_combo_d0",
    "default_workspace_from_d0",
]
