"""Provider-neutral diagnostics and measurements for the canonical engine."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SemanticModel(BaseModel):
    """Strict immutable base for canonical semantic runtime contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class SemanticDiagnosticSeverity(StrEnum):
    """Severity for a bounded canonical semantic diagnostic."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class SemanticDiagnostic(SemanticModel):
    """Sanitized diagnostic retained by the canonical semantic engine."""

    stage: str = Field(min_length=1)
    message: str = Field(min_length=1)
    severity: SemanticDiagnosticSeverity = SemanticDiagnosticSeverity.ERROR
    code: str | None = Field(default=None, min_length=1)
    remediation_hint: str | None = Field(default=None, min_length=1)


class SemanticMetrics(SemanticModel):
    """Bounded measurements for one canonical worker invocation."""

    program_chars: int = Field(default=0, ge=0)
    program_ast_nodes: int = Field(default=0, ge=0)
    program_statements: int = Field(default=0, ge=0)
    program_calls: int = Field(default=0, ge=0)
    program_repairs: int = Field(default=0, ge=0)
    program_loop_iterations: int = Field(default=0, ge=0)
    program_nesting_depth: int = Field(default=0, ge=0)
    created_objects: int = Field(default=0, ge=0)


__all__ = ["SemanticDiagnostic", "SemanticDiagnosticSeverity", "SemanticMetrics"]
