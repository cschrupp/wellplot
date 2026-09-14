###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
###############################################################################

"""Pure contracts for restricted Wellplot authoring programs.

These models are the durable boundary between a future restricted program
kernel and the canonical :class:`~wellplot.model.intent.AuthoringDocumentIntent`.
They intentionally contain no parser, interpreter, SDK, capability, provider,
or persistence behavior.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..model.intent import AuthoringDocumentIntent


class _ProgramModel(BaseModel):
    """Strict, immutable base for program-kernel contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ProgramSource(_ProgramModel):
    """Verbatim source text and optional stable provenance for one program."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=False)

    text: str = Field(min_length=1)
    logical_name: str | None = Field(default=None, min_length=1)


class AuthoringProgram(_ProgramModel):
    """One restricted Wellplot program before syntax or policy validation."""

    source: ProgramSource


class ProgramSourcePosition(_ProgramModel):
    """One 1-based source position."""

    line: int = Field(ge=1)
    column: int = Field(ge=1)


class ProgramSourceSpan(_ProgramModel):
    """An inclusive source range with positions ordered from start to end."""

    start: ProgramSourcePosition
    end: ProgramSourcePosition

    @model_validator(mode="after")
    def validate_position_order(self) -> Self:
        """Reject a span whose end precedes its start."""
        start = (self.start.line, self.start.column)
        end = (self.end.line, self.end.column)
        if end < start:
            raise ValueError("Program source span end must not precede its start.")
        return self


class ProgramDiagnosticSeverity(StrEnum):
    """Severity for a compact program diagnostic."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ProgramDiagnostic(_ProgramModel):
    """A compact, repair-oriented diagnostic from the program kernel."""

    stage: str = Field(min_length=1)
    message: str = Field(min_length=1)
    severity: ProgramDiagnosticSeverity = ProgramDiagnosticSeverity.ERROR
    code: str | None = Field(default=None, min_length=1)
    span: ProgramSourceSpan | None = None
    remediation_hint: str | None = Field(default=None, min_length=1)


class ProgramMetrics(_ProgramModel):
    """Measured program-kernel work, where zero is a genuine measurement."""

    program_chars: int = Field(default=0, ge=0)
    program_ast_nodes: int = Field(default=0, ge=0)
    program_statements: int = Field(default=0, ge=0)
    program_calls: int = Field(default=0, ge=0)
    program_repairs: int = Field(default=0, ge=0)
    program_loop_iterations: int = Field(default=0, ge=0)
    program_nesting_depth: int = Field(default=0, ge=0)
    created_objects: int = Field(default=0, ge=0)


class ProgramArtifact(_ProgramModel):
    """Validated in-memory intent fragment emitted by the future program kernel."""

    intent_fragment: AuthoringDocumentIntent


class ProgramExecutionResult(_ProgramModel):
    """Explicit success or failure evidence for one program-kernel attempt."""

    program: AuthoringProgram
    success: bool
    artifact: ProgramArtifact | None = None
    diagnostics: tuple[ProgramDiagnostic, ...] = ()
    metrics: ProgramMetrics = Field(default_factory=ProgramMetrics)

    @model_validator(mode="after")
    def validate_execution_evidence(self) -> Self:
        """Require artifact and diagnostic evidence consistent with the result."""
        has_error = any(
            diagnostic.severity is ProgramDiagnosticSeverity.ERROR
            for diagnostic in self.diagnostics
        )
        if self.success:
            if self.artifact is None:
                raise ValueError("Successful program execution requires an artifact.")
            if has_error:
                raise ValueError("Successful program execution cannot include error diagnostics.")
            return self

        if self.artifact is not None:
            raise ValueError("Unsuccessful program execution cannot include an artifact.")
        if not self.diagnostics:
            raise ValueError("Unsuccessful program execution requires at least one diagnostic.")
        return self


__all__ = [
    "AuthoringProgram",
    "ProgramArtifact",
    "ProgramDiagnostic",
    "ProgramDiagnosticSeverity",
    "ProgramExecutionResult",
    "ProgramMetrics",
    "ProgramSource",
    "ProgramSourcePosition",
    "ProgramSourceSpan",
]
