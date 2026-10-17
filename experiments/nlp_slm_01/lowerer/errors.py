"""Lowerer error types."""

from __future__ import annotations


class LowererError(Exception):
    """Base lowerer failure."""


class PreconditionError(LowererError):
    """Op preconditions not satisfied against D0/context."""


class AmbiguousLoweringError(LowererError):
    """Deterministic planner cannot choose a unique lowering."""
