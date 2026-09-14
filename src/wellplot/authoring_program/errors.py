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

"""Semantic error taxonomy for restricted Wellplot authoring programs."""

from __future__ import annotations

from typing import ClassVar

from ..errors import WellLogOSError
from .models import (
    ProgramDiagnostic,
    ProgramDiagnosticSeverity,
    ProgramSourceSpan,
)


class AuthoringProgramError(WellLogOSError):
    """Base error that exposes a compact, deterministic program diagnostic."""

    diagnostic_code: ClassVar[str] = "program.error"
    diagnostic_stage: ClassVar[str] = "program"

    def __init__(
        self,
        message: str,
        *,
        span: ProgramSourceSpan | None = None,
        remediation_hint: str | None = None,
    ) -> None:
        """Build the bounded diagnostic retained by this error."""
        self._diagnostic = ProgramDiagnostic(
            code=self.diagnostic_code,
            stage=self.diagnostic_stage,
            message=message,
            severity=ProgramDiagnosticSeverity.ERROR,
            span=span,
            remediation_hint=remediation_hint,
        )
        super().__init__(self._diagnostic.message)

    @property
    def diagnostic(self) -> ProgramDiagnostic:
        """Return the immutable diagnostic associated with this error."""
        return self._diagnostic

    def to_diagnostic(self) -> ProgramDiagnostic:
        """Return the stable, model-facing diagnostic for this error."""
        return self._diagnostic


class ProgramSyntaxError(AuthoringProgramError):
    """Raised when source uses syntax outside the supported language."""

    diagnostic_code = "program.syntax_error"
    diagnostic_stage = "syntax"


class ProgramPolicyError(AuthoringProgramError):
    """Raised when source violates a restricted-program policy."""

    diagnostic_code = "program.policy_error"
    diagnostic_stage = "policy"


class ProgramNameError(AuthoringProgramError):
    """Raised when a program refers to an unavailable name."""

    diagnostic_code = "program.name_error"
    diagnostic_stage = "name"


class ProgramTypeError(AuthoringProgramError):
    """Raised when a program value violates a required contract type."""

    diagnostic_code = "program.type_error"
    diagnostic_stage = "type"


class ProgramCapabilityError(AuthoringProgramError):
    """Raised when a program requests an unavailable capability."""

    diagnostic_code = "program.capability_error"
    diagnostic_stage = "capability"


class ProgramLimitError(AuthoringProgramError):
    """Raised when a program exceeds an enforced resource limit."""

    diagnostic_code = "program.limit_error"
    diagnostic_stage = "limit"


class ProgramDryRunError(AuthoringProgramError):
    """Raised when deterministic dry-run validation rejects a program result."""

    diagnostic_code = "program.dry_run_error"
    diagnostic_stage = "dry_run"


__all__ = [
    "AuthoringProgramError",
    "ProgramCapabilityError",
    "ProgramDryRunError",
    "ProgramLimitError",
    "ProgramNameError",
    "ProgramPolicyError",
    "ProgramSyntaxError",
    "ProgramTypeError",
]
