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

"""Parsing and source-coordinate helpers for restricted authoring programs."""

from __future__ import annotations

import ast
from dataclasses import dataclass

from .errors import ProgramSyntaxError
from .models import AuthoringProgram, ProgramSourcePosition, ProgramSourceSpan


@dataclass(frozen=True)
class ProgramPolicyLimits:
    """Immutable static budgets for one restricted authoring program."""

    max_source_chars: int = 16_000
    max_ast_nodes: int = 1_500
    max_statements: int = 300
    max_calls: int = 250
    max_loop_iterations: int = 100
    max_nesting: int = 8

    def __post_init__(self) -> None:
        """Require each static limit to be a positive integer."""
        for field_name in (
            "max_source_chars",
            "max_ast_nodes",
            "max_statements",
            "max_calls",
            "max_loop_iterations",
            "max_nesting",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{field_name} must be a positive integer.")


DEFAULT_PROGRAM_POLICY_LIMITS = ProgramPolicyLimits()


def parse_authoring_program(program: AuthoringProgram) -> ast.Module:
    """Parse source into an AST without compiling or executing it."""
    filename = program.source.logical_name or "<authoring_program>"
    try:
        return ast.parse(program.source.text, filename=filename, mode="exec")
    except SyntaxError as error:
        message = error.msg or "Program source cannot be parsed."
        raise ProgramSyntaxError(
            message,
            span=source_span_from_syntax_error(error),
            remediation_hint="Correct the source syntax and retry.",
        ) from None


def source_span_from_ast(node: ast.AST) -> ProgramSourceSpan | None:
    """Map Python AST coordinates to the stable program source-span contract."""
    line = getattr(node, "lineno", None)
    column = getattr(node, "col_offset", None)
    if not isinstance(line, int) or not isinstance(column, int):
        return None

    end_line = getattr(node, "end_lineno", None)
    end_column = getattr(node, "end_col_offset", None)
    resolved_end_line = end_line if isinstance(end_line, int) else line
    resolved_end_column = end_column if isinstance(end_column, int) else column + 1

    return _source_span_from_coordinates(
        line=line,
        column=column + 1,
        end_line=resolved_end_line,
        end_column=max(column + 1, resolved_end_column),
    )


def source_span_from_syntax_error(error: SyntaxError) -> ProgramSourceSpan | None:
    """Map a parser error location to the stable program source-span contract."""
    line = error.lineno
    column = error.offset
    if not isinstance(line, int) or not isinstance(column, int):
        return None

    end_line = error.end_lineno if isinstance(error.end_lineno, int) else line
    end_column = error.end_offset if isinstance(error.end_offset, int) else column
    return _source_span_from_coordinates(
        line=line,
        column=max(1, column),
        end_line=end_line,
        end_column=max(1, end_column),
    )


def _source_span_from_coordinates(
    *,
    line: int,
    column: int,
    end_line: int,
    end_column: int,
) -> ProgramSourceSpan:
    """Create one ordered inclusive span from already-normalized coordinates."""
    start = ProgramSourcePosition(line=line, column=column)
    end = ProgramSourcePosition(line=end_line, column=end_column)
    if (end.line, end.column) < (start.line, start.column):
        end = start
    return ProgramSourceSpan(start=start, end=end)


__all__ = [
    "DEFAULT_PROGRAM_POLICY_LIMITS",
    "ProgramPolicyLimits",
    "parse_authoring_program",
    "source_span_from_ast",
    "source_span_from_syntax_error",
]
