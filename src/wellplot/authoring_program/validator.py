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

"""Static allowlist validation for restricted authoring-program syntax."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from typing import NoReturn

from .errors import ProgramLimitError, ProgramNameError, ProgramPolicyError
from .grammar import (
    DEFAULT_PROGRAM_POLICY_LIMITS,
    ProgramPolicyLimits,
    parse_authoring_program,
    source_span_from_ast,
)
from .models import AuthoringProgram

_SDK_ROOT_NAME = "wp"
_ALLOWED_NODE_TYPES = (
    ast.Module,
    ast.Expr,
    ast.Assign,
    ast.For,
    ast.If,
    ast.Call,
    ast.Attribute,
    ast.Name,
    ast.Constant,
    ast.List,
    ast.Tuple,
    ast.Dict,
    ast.keyword,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Load,
    ast.Store,
)
_ALLOWED_CONSTANT_TYPES = (type(None), bool, int, float, str)


def validate_authoring_program(
    program: AuthoringProgram,
    *,
    limits: ProgramPolicyLimits = DEFAULT_PROGRAM_POLICY_LIMITS,
) -> ast.Module:
    """Parse and statically validate one program without executing any syntax."""
    _validate_source_size(program, limits)
    tree = parse_authoring_program(program)
    _validate_static_limits(tree, limits)
    return _StaticProgramValidator(limits).validate(tree)


def _validate_source_size(program: AuthoringProgram, limits: ProgramPolicyLimits) -> None:
    """Reject source that exceeds the bounded parser input size."""
    source_chars = len(program.source.text)
    if source_chars > limits.max_source_chars:
        raise ProgramLimitError(
            f"Program source has {source_chars} characters; limit is {limits.max_source_chars}.",
            remediation_hint="Reduce the program source length and retry.",
        )


def _validate_static_limits(tree: ast.Module, limits: ProgramPolicyLimits) -> None:
    """Reject AST-wide limits before inspecting individual statement semantics."""
    nodes = tuple(_iter_ast_nodes(tree))
    ast_nodes = len(nodes)
    if ast_nodes > limits.max_ast_nodes:
        raise ProgramLimitError(
            f"Program has {ast_nodes} AST nodes; limit is {limits.max_ast_nodes}.",
            remediation_hint="Reduce literal size or program complexity and retry.",
        )

    statements = sum(1 for node in nodes if isinstance(node, ast.stmt))
    if statements > limits.max_statements:
        raise ProgramLimitError(
            f"Program has {statements} statements; limit is {limits.max_statements}.",
            remediation_hint="Split the requested work into smaller programs.",
        )

    calls = sum(1 for node in nodes if isinstance(node, ast.Call))
    if calls > limits.max_calls:
        raise ProgramLimitError(
            f"Program has {calls} calls; limit is {limits.max_calls}.",
            remediation_hint="Use fewer SDK calls or split the requested work.",
        )


def _iter_ast_nodes(root: ast.AST) -> Iterator[ast.AST]:
    """Yield one AST tree without using helpers that lazily import at validation time."""
    pending = [root]
    while pending:
        node = pending.pop()
        yield node
        children = tuple(ast.iter_child_nodes(node))
        pending.extend(reversed(children))


class _StaticProgramValidator(ast.NodeVisitor):
    """Validate only the initial restricted language without evaluating it."""

    def __init__(self, limits: ProgramPolicyLimits) -> None:
        """Initialize the syntactic environment and static budget counters."""
        self._limits = limits
        self._local_names: set[str] = set()
        self._handle_names: set[str] = set()
        self._literal_values: dict[str, ast.expr] = {}
        self._literal_sequence_lengths: dict[str, int] = {}
        self._loop_iterations = 0
        self._loop_multiplier = 1
        self._nesting_depth = 0
        self._condition_depth = 0

    def validate(self, tree: ast.Module) -> ast.Module:
        """Validate the parsed tree and return it unchanged for CM-12."""
        self.visit(tree)
        return tree

    def generic_visit(self, node: ast.AST) -> None:
        """Reject every AST node outside the explicitly allowed grammar."""
        if not isinstance(node, _ALLOWED_NODE_TYPES):
            self._policy_error(f"Unsupported syntax: {type(node).__name__} is not allowed.", node)
        super().generic_visit(node)

    def visit_Expr(self, node: ast.Expr) -> None:  # noqa: N802
        """Allow expression statements only for method calls."""
        if not isinstance(node.value, ast.Call):
            self._policy_error("Expression statements must be method calls.", node.value)
        self.visit(node.value)

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        """Allow one local-name assignment with no mutation or destructuring."""
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            self._policy_error("Assignments must target one local name.", node)

        target = node.targets[0]
        self._validate_public_identifier(target.id, target)
        if target.id == _SDK_ROOT_NAME:
            self._policy_error("The SDK root name cannot be reassigned.", target)

        self.visit(node.value)
        self._local_names.add(target.id)
        self._record_local_value(target.id, node.value)

    def visit_For(self, node: ast.For) -> None:  # noqa: N802
        """Allow only statically bounded loops over literal local sequences."""
        if node.orelse:
            self._policy_error("For-loop else clauses are not allowed.", node.orelse[0])

        iteration_count = self._resolve_loop_iteration_count(node.iter)
        target_names = self._loop_target_names(node.target)

        estimated_iterations = self._loop_multiplier * iteration_count
        next_total = self._loop_iterations + estimated_iterations
        if next_total > self._limits.max_loop_iterations:
            self._limit_error(
                "loop iterations",
                next_total,
                self._limits.max_loop_iterations,
                node,
                "Use shorter literal sequences or split the program.",
            )

        self._loop_iterations = next_total
        self._local_names.update(target_names)
        previous_multiplier = self._loop_multiplier
        self._loop_multiplier *= iteration_count
        self._enter_nesting(node)
        try:
            for statement in node.body:
                self.visit(statement)
            for statement in node.orelse:
                self.visit(statement)
        finally:
            self._nesting_depth -= 1
            self._loop_multiplier = previous_multiplier

    def visit_If(self, node: ast.If) -> None:  # noqa: N802
        """Allow only literal- or local-literal deterministic conditions."""
        self._condition_depth += 1
        try:
            self.visit(node.test)
        finally:
            self._condition_depth -= 1

        self._enter_nesting(node)
        try:
            for statement in node.body:
                self.visit(statement)
            for statement in node.orelse:
                self.visit(statement)
        finally:
            self._nesting_depth -= 1

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        """Allow one public method call on the root or a known local handle."""
        if not isinstance(node.func, ast.Attribute):
            self._policy_error("Calls must use a root or local-handle method.", node.func)
        receiver = self._validate_method_attribute(node.func)
        if receiver != _SDK_ROOT_NAME and receiver not in self._handle_names:
            self._name_error(
                f"Call receiver '{receiver}' is not a known local handle.",
                node.func.value,
            )

        for argument in node.args:
            if isinstance(argument, ast.Starred):
                self._policy_error("Starred call arguments are not allowed.", argument)
            self.visit(argument)
        for keyword in node.keywords:
            self.visit(keyword)

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
        """Allow one public attribute on the root or a known local handle."""
        receiver = self._validate_method_attribute(node)
        if receiver != _SDK_ROOT_NAME and receiver not in self._handle_names:
            self._name_error(
                f"Attribute receiver '{receiver}' is not a known local handle.",
                node.value,
            )

    def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
        """Allow only the SDK root and names introduced by allowed syntax."""
        self._validate_public_identifier(node.id, node)
        if not isinstance(node.ctx, ast.Load):
            self._policy_error("Names may be assigned only through allowed statements.", node)
        if node.id != _SDK_ROOT_NAME and node.id not in self._local_names:
            self._name_error(f"Name '{node.id}' has not been introduced.", node)

        if self._condition_depth:
            value = self._literal_values.get(node.id)
            if not self._is_boolean_literal(value):
                self._policy_error("If conditions must use a literal boolean or comparison.", node)

    def visit_Constant(self, node: ast.Constant) -> None:  # noqa: N802
        """Allow only scalar literals that the future runtime can represent."""
        if type(node.value) not in _ALLOWED_CONSTANT_TYPES:
            self._policy_error(
                "Only null, boolean, numeric, and string literals are allowed.",
                node,
            )

        if self._condition_depth and type(node.value) is not bool:
            self._policy_error("If conditions must use a literal boolean or comparison.", node)

    def visit_Dict(self, node: ast.Dict) -> None:  # noqa: N802
        """Reject dictionary unpacking while allowing literal key-value pairs."""
        if any(key is None for key in node.keys):
            self._policy_error("Dictionary unpacking is not allowed.", node)
        self.generic_visit(node)

    def visit_keyword(self, node: ast.keyword) -> None:  # noqa: N802
        """Reject keyword expansion and private keyword names."""
        if node.arg is None:
            self._policy_error("Keyword expansion is not allowed.", node)
        self._validate_public_identifier(node.arg, node)
        self.visit(node.value)

    def visit_Compare(self, node: ast.Compare) -> None:  # noqa: N802
        """Allow one equality comparison only as an if condition."""
        if not self._condition_depth:
            self._policy_error("Comparisons are allowed only as if conditions.", node)
        if len(node.ops) != 1 or len(node.comparators) != 1:
            self._policy_error("If comparisons must have one equality operator.", node)
        if not isinstance(node.ops[0], ast.Eq | ast.NotEq):
            self._policy_error("If comparisons support only == and !=.", node)

        self._validate_comparison_operand(node.left)
        self._validate_comparison_operand(node.comparators[0])

    def _record_local_value(self, name: str, value: ast.expr) -> None:
        """Track only syntax-derived literal values and future local handles."""
        self._literal_values.pop(name, None)
        self._literal_sequence_lengths.pop(name, None)
        self._handle_names.discard(name)

        if self._is_literal_value(value):
            self._literal_values[name] = value
            sequence_length = self._literal_sequence_length(value)
            if sequence_length is not None:
                self._literal_sequence_lengths[name] = sequence_length
            return

        if isinstance(value, ast.Name):
            if value.id in self._literal_values:
                self._literal_values[name] = self._literal_values[value.id]
            if value.id in self._literal_sequence_lengths:
                self._literal_sequence_lengths[name] = self._literal_sequence_lengths[value.id]
            if value.id in self._handle_names:
                self._handle_names.add(name)
            return

        if isinstance(value, ast.Call):
            self._handle_names.add(name)

    def _resolve_loop_iteration_count(self, iterable: ast.expr) -> int:
        """Return a statically provable iteration count or reject the iterable."""
        if isinstance(iterable, ast.Name):
            self.visit(iterable)
            count = self._literal_sequence_lengths.get(iterable.id)
            if count is not None:
                return count
            self._policy_error("For-loop iterables must be literal sequences.", iterable)

        count = self._literal_sequence_length(iterable)
        if count is None:
            self._policy_error("For-loop iterables must be literal sequences.", iterable)
        self.visit(iterable)
        return count

    def _loop_target_names(self, target: ast.expr) -> tuple[str, ...]:
        """Return one flat public-name loop target, including plan-approved tuples."""
        if isinstance(target, ast.Name):
            self._validate_public_identifier(target.id, target)
            return (target.id,)
        if isinstance(target, ast.Tuple) and all(
            isinstance(item, ast.Name) for item in target.elts
        ):
            names = tuple(item.id for item in target.elts if isinstance(item, ast.Name))
            for item in target.elts:
                assert isinstance(item, ast.Name)
                self._validate_public_identifier(item.id, item)
            return names
        self._policy_error(
            "For-loop targets must use local names or one flat tuple of names.",
            target,
        )
        raise AssertionError("Program policy errors do not return.")

    def _validate_method_attribute(self, attribute: ast.Attribute) -> str:
        """Return an allowed one-name receiver for one attribute or method access."""
        self._validate_public_identifier(attribute.attr, attribute)
        if not isinstance(attribute.value, ast.Name):
            self._policy_error(
                "Attribute chains and call chaining are not allowed.",
                attribute.value,
            )
        self._validate_public_identifier(attribute.value.id, attribute.value)
        if attribute.value.id != _SDK_ROOT_NAME and attribute.value.id not in self._local_names:
            self._name_error(
                f"Name '{attribute.value.id}' has not been introduced.",
                attribute.value,
            )
        return attribute.value.id

    def _validate_comparison_operand(self, node: ast.expr) -> None:
        """Allow literal values and names bound to syntax-derived literal values."""
        if isinstance(node, ast.Name):
            self._validate_public_identifier(node.id, node)
            if node.id not in self._literal_values:
                self._name_error(f"Comparison name '{node.id}' is not a local literal.", node)
            return
        if self._is_literal_value(node):
            return
        self._policy_error("If comparisons require literal values or local literals.", node)

    def _is_literal_value(self, node: ast.expr | None) -> bool:
        """Return whether an expression is composed only of allowed literals."""
        if isinstance(node, ast.Constant):
            return type(node.value) in _ALLOWED_CONSTANT_TYPES
        if isinstance(node, ast.List | ast.Tuple):
            return all(self._is_literal_value(item) for item in node.elts)
        if isinstance(node, ast.Dict):
            return all(
                key is not None and self._is_literal_value(key) and self._is_literal_value(value)
                for key, value in zip(node.keys, node.values, strict=True)
            )
        return False

    def _literal_sequence_length(self, node: ast.expr) -> int | None:
        """Return a direct list or tuple length when every item is literal."""
        if isinstance(node, ast.List | ast.Tuple) and self._is_literal_value(node):
            return len(node.elts)
        return None

    def _is_boolean_literal(self, node: ast.expr | None) -> bool:
        """Return whether a tracked local name was assigned a boolean literal."""
        return isinstance(node, ast.Constant) and type(node.value) is bool

    def _enter_nesting(self, node: ast.AST) -> None:
        """Increment and enforce the shared loop/conditional nesting budget."""
        self._nesting_depth += 1
        if self._nesting_depth > self._limits.max_nesting:
            self._limit_error(
                "nesting depth",
                self._nesting_depth,
                self._limits.max_nesting,
                node,
                "Flatten nested loops or conditions.",
            )

    def _validate_public_identifier(self, identifier: str, node: ast.AST) -> None:
        """Reject all private and dunder names before they reach runtime semantics."""
        if identifier.startswith("_"):
            self._name_error(f"Private name '{identifier}' is not allowed.", node)

    def _limit_error(
        self,
        label: str,
        value: int,
        maximum: int,
        node: ast.AST,
        remediation_hint: str,
    ) -> None:
        """Raise one bounded-resource diagnostic with a stable error category."""
        raise ProgramLimitError(
            f"Program has {value} {label}; limit is {maximum}.",
            span=source_span_from_ast(node),
            remediation_hint=remediation_hint,
        )

    def _policy_error(self, message: str, node: ast.AST) -> NoReturn:
        """Raise one source-local policy diagnostic."""
        raise ProgramPolicyError(
            message,
            span=source_span_from_ast(node),
            remediation_hint="Use only the restricted Authoring Program syntax.",
        )

    def _name_error(self, message: str, node: ast.AST) -> NoReturn:
        """Raise one source-local name diagnostic."""
        raise ProgramNameError(
            message,
            span=source_span_from_ast(node),
            remediation_hint="Use the SDK root or a previously introduced local name.",
        )


__all__ = ["validate_authoring_program"]
