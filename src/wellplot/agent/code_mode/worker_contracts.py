"""Shared worker result contract for the canonical semantic graph."""

from __future__ import annotations

from dataclasses import dataclass

from ...model.intent import AuthoringDocumentIntent
from ..semantic_runtime import SemanticDiagnostic, SemanticMetrics


@dataclass(frozen=True, slots=True)
class CanonicalWorkerResult:
    """Stable worker result consumed by the shared Code Mode graph."""

    success: bool
    intent_fragment: AuthoringDocumentIntent | None
    diagnostics: tuple[SemanticDiagnostic, ...]
    metrics: SemanticMetrics


__all__ = ["CanonicalWorkerResult"]
