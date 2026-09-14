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

"""Direct AST interpreter for the CM-11 restricted authoring-program grammar."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import NoReturn

from .errors import (
    AuthoringProgramError,
    ProgramLimitError,
    ProgramNameError,
    ProgramPolicyError,
    ProgramTypeError,
)
from .grammar import DEFAULT_PROGRAM_POLICY_LIMITS, ProgramPolicyLimits, source_span_from_ast
from .models import AuthoringProgram, ProgramMetrics
from .runtime import (
    DEFAULT_RUNTIME_BUDGET,
    CommandJournal,
    CommandJournalEntry,
    RuntimeBudget,
    RuntimeCounters,
    RuntimeEnvironment,
    RuntimeValue,
    is_runtime_handle,
    runtime_value_item_count,
)
from .validator import validate_authoring_program

_SDK_ROOT_NAME = "wp"
_MISSING = object()


@dataclass(frozen=True)
class ProgramInterpretation:
    """Generic execution evidence before a future slice compiles canonical intent."""

    journal: tuple[CommandJournalEntry, ...]
    metrics: ProgramMetrics
    counters: RuntimeCounters


def interpret_authoring_program(
    program: AuthoringProgram,
    runtime: RuntimeEnvironment,
    *,
    policy_limits: ProgramPolicyLimits = DEFAULT_PROGRAM_POLICY_LIMITS,
    runtime_budget: RuntimeBudget = DEFAULT_RUNTIME_BUDGET,
) -> ProgramInterpretation:
    """Validate then interpret one program through explicit runtime registries.

    This is intentionally the only public interpreter entry point. It accepts a
    source-bearing :class:`AuthoringProgram`, reruns CM-11 validation, and never
    accepts a caller-provided AST as executable input.
    """
    if not isinstance(program, AuthoringProgram):
        raise ProgramTypeError("Interpreter input must be an AuthoringProgram.")
    if not isinstance(runtime, RuntimeEnvironment):
        raise ProgramTypeError("Interpreter runtime must be a RuntimeEnvironment.")
    if not isinstance(policy_limits, ProgramPolicyLimits):
        raise ProgramTypeError("Interpreter policy limits must be ProgramPolicyLimits.")
    if not isinstance(runtime_budget, RuntimeBudget):
        raise ProgramTypeError("Interpreter runtime budget must be RuntimeBudget.")

    tree = validate_authoring_program(program, limits=policy_limits)
    interpreter = _RestrictedInterpreter(
        program=program,
        tree=tree,
        runtime=runtime,
        runtime_budget=runtime_budget,
    )
    return interpreter.run()


class _RestrictedInterpreter:
    """Execute only AST node types already accepted by the CM-11 validator."""

    def __init__(
        self,
        *,
        program: AuthoringProgram,
        tree: ast.Module,
        runtime: RuntimeEnvironment,
        runtime_budget: RuntimeBudget,
    ) -> None:
        """Initialize isolated root, local, counter, and journal state."""
        self._program = program
        self._tree = tree
        self._runtime = runtime
        self._budget = runtime_budget
        self._locals: dict[str, RuntimeValue] = {}
        self._journal = CommandJournal()
        self._executed_calls = 0
        self._executed_loop_iterations = 0
        self._runtime_value_items = 0
        self._max_nesting_depth = 0
        self._current_nesting_depth = 0
        self._created_objects = 0

    def run(self) -> ProgramInterpretation:
        """Interpret each validated statement in source order and return evidence."""
        for statement in self._tree.body:
            self._execute_statement(statement)

        counters = RuntimeCounters(
            executed_calls=self._executed_calls,
            executed_loop_iterations=self._executed_loop_iterations,
            runtime_value_items=self._runtime_value_items,
            journal_entries=len(self._journal.entries),
        )
        return ProgramInterpretation(
            journal=self._journal.entries,
            counters=counters,
            metrics=ProgramMetrics(
                program_chars=len(self._program.source.text),
                program_ast_nodes=_count_ast_nodes(self._tree),
                program_statements=_count_statements(self._tree),
                program_calls=self._executed_calls,
                program_loop_iterations=self._executed_loop_iterations,
                program_nesting_depth=self._max_nesting_depth,
                created_objects=self._created_objects,
            ),
        )

    def _execute_statement(self, statement: ast.stmt) -> None:
        """Dispatch one validated statement without Python code evaluation."""
        if isinstance(statement, ast.Expr):
            self._evaluate_expression(statement.value)
            return
        if isinstance(statement, ast.Assign):
            self._execute_assignment(statement)
            return
        if isinstance(statement, ast.For):
            self._execute_for(statement)
            return
        if isinstance(statement, ast.If):
            self._execute_if(statement)
            return
        self._policy_error(
            f"Unsupported validated statement '{type(statement).__name__}'.",
            statement,
        )

    def _execute_assignment(self, statement: ast.Assign) -> None:
        """Bind one ordinary local name while protecting the predefined root."""
        if len(statement.targets) != 1 or not isinstance(statement.targets[0], ast.Name):
            self._policy_error("Assignments must target one local name.", statement)
        name = statement.targets[0].id
        if name == _SDK_ROOT_NAME:
            self._policy_error("The predefined root cannot be overwritten.", statement.targets[0])
        self._locals[name] = self._evaluate_expression(statement.value)

    def _execute_for(self, statement: ast.For) -> None:
        """Execute a validated local or literal list/tuple loop with lexical targets."""
        iterable = self._evaluate_expression(statement.iter)
        if type(iterable) not in (list, tuple):
            self._type_error("For-loop iterables must evaluate to a list or tuple.", statement.iter)

        target_names = self._loop_target_names(statement.target)
        previous_values = {name: self._locals.get(name, _MISSING) for name in target_names}
        count_iterations = not _contains_nested_for(statement.body)
        self._enter_nesting()
        try:
            for value in iterable:
                if count_iterations:
                    self._record_loop_iteration(statement)
                self._bind_loop_value(target_names, value, statement.target)
                for child in statement.body:
                    self._execute_statement(child)
        finally:
            self._restore_loop_bindings(previous_values)
            self._leave_nesting()

    def _execute_if(self, statement: ast.If) -> None:
        """Execute only deterministic boolean or equality conditions from CM-11."""
        body = statement.body if self._evaluate_condition(statement.test) else statement.orelse
        self._enter_nesting()
        try:
            for child in body:
                self._execute_statement(child)
        finally:
            self._leave_nesting()

    def _evaluate_expression(self, expression: ast.expr) -> RuntimeValue:
        """Materialize one allowed expression and charge only new safe values."""
        if isinstance(expression, ast.Constant):
            return self._charge_runtime_value(expression.value, expression)
        if isinstance(expression, ast.List):
            value = [self._evaluate_container_item(item) for item in expression.elts]
            return self._charge_runtime_value(value, expression)
        if isinstance(expression, ast.Tuple):
            value = tuple(self._evaluate_container_item(item) for item in expression.elts)
            return self._charge_runtime_value(value, expression)
        if isinstance(expression, ast.Dict):
            value: dict[str, RuntimeValue] = {}
            for key, item in zip(expression.keys, expression.values, strict=True):
                if key is None:
                    self._policy_error("Dictionary unpacking is not allowed.", expression)
                raw_key = self._evaluate_container_item(key)
                if type(raw_key) is not str:
                    self._type_error("Runtime dictionary keys must be strings.", key)
                value[raw_key] = self._evaluate_container_item(item)
            return self._charge_runtime_value(value, expression)
        if isinstance(expression, ast.Name):
            return self._resolve_local_name(expression)
        if isinstance(expression, ast.Call):
            return self._execute_call(expression)
        self._policy_error(
            f"Unsupported validated expression '{type(expression).__name__}'.",
            expression,
        )
        raise AssertionError("Program policy errors do not return.")

    def _evaluate_container_item(self, expression: ast.expr) -> RuntimeValue:
        """Evaluate a nested literal without charging it separately from its container."""
        if isinstance(expression, ast.Constant):
            return expression.value
        if isinstance(expression, ast.List):
            return [self._evaluate_container_item(item) for item in expression.elts]
        if isinstance(expression, ast.Tuple):
            return tuple(self._evaluate_container_item(item) for item in expression.elts)
        if isinstance(expression, ast.Dict):
            value: dict[str, RuntimeValue] = {}
            for key, item in zip(expression.keys, expression.values, strict=True):
                if key is None:
                    self._policy_error("Dictionary unpacking is not allowed.", expression)
                raw_key = self._evaluate_container_item(key)
                if type(raw_key) is not str:
                    self._type_error("Runtime dictionary keys must be strings.", key)
                value[raw_key] = self._evaluate_container_item(item)
            return value
        if isinstance(expression, ast.Name):
            return self._resolve_local_name(expression)
        if isinstance(expression, ast.Call):
            return self._execute_call(expression)
        self._policy_error("Container values must be allowed literals or local values.", expression)
        raise AssertionError("Program policy errors do not return.")

    def _execute_call(self, call: ast.Call) -> RuntimeValue:
        """Resolve one explicit registry call and record it after a safe return."""
        if not isinstance(call.func, ast.Attribute) or not isinstance(call.func.value, ast.Name):
            self._policy_error("Calls must use one root or local-handle method.", call.func)
        receiver_name = call.func.value.id
        method = call.func.attr
        args = tuple(self._evaluate_expression(argument) for argument in call.args)
        kwargs = self._evaluate_call_keywords(call)
        self._reserve_call(call)

        try:
            if receiver_name == _SDK_ROOT_NAME:
                receiver = _SDK_ROOT_NAME
                result = self._runtime.dispatch_root(method, args, kwargs)
            else:
                handle = self._resolve_local_name(call.func.value)
                if not is_runtime_handle(handle):
                    self._type_error("Call receivers must be runtime handles.", call.func.value)
                receiver = handle.token
                result = self._runtime.dispatch_handle(handle, method, args, kwargs)
        except AuthoringProgramError as error:
            self._raise_with_span(error, call)

        result = self._charge_runtime_value(result, call)
        self._journal.append(
            receiver=receiver,
            method=method,
            args=args,
            kwargs=kwargs,
            result=result,
        )
        if is_runtime_handle(result):
            self._created_objects += 1
        return result

    def _evaluate_call_keywords(self, call: ast.Call) -> dict[str, RuntimeValue]:
        """Evaluate explicit public keyword arguments without Python call expansion."""
        values: dict[str, RuntimeValue] = {}
        for keyword in call.keywords:
            if keyword.arg is None:
                self._policy_error("Keyword expansion is not allowed.", keyword)
            if keyword.arg in values:
                self._policy_error("Duplicate keyword arguments are not allowed.", keyword)
            values[keyword.arg] = self._evaluate_expression(keyword.value)
        return values

    def _evaluate_condition(self, expression: ast.expr) -> bool:
        """Evaluate a CM-11 condition without host-object truthiness or operators."""
        if isinstance(expression, ast.Constant):
            if type(expression.value) is bool:
                return expression.value
            self._type_error("If conditions must evaluate to booleans.", expression)
        if isinstance(expression, ast.Name):
            value = self._resolve_local_name(expression)
            if type(value) is bool:
                return value
            self._type_error("If conditions must evaluate to booleans.", expression)
        if isinstance(expression, ast.Compare):
            if len(expression.ops) != 1 or len(expression.comparators) != 1:
                self._policy_error("If comparisons require one equality operator.", expression)
            left = self._evaluate_expression(expression.left)
            right = self._evaluate_expression(expression.comparators[0])
            if not _is_safe_comparison_value(left) or not _is_safe_comparison_value(right):
                self._type_error(
                    "If comparisons require scalar or literal-container values.",
                    expression,
                )
            if isinstance(expression.ops[0], ast.Eq):
                return left == right
            if isinstance(expression.ops[0], ast.NotEq):
                return left != right
            self._policy_error("If comparisons support only == and !=.", expression)
        self._policy_error("If conditions must be boolean or equality comparisons.", expression)
        raise AssertionError("Program policy errors do not return.")

    def _resolve_local_name(self, expression: ast.Name) -> RuntimeValue:
        """Resolve one ordinary local without exposing a Python builtins namespace."""
        if expression.id == _SDK_ROOT_NAME:
            self._name_error(
                "The predefined root is available only as a call receiver.",
                expression,
            )
        value = self._locals.get(expression.id, _MISSING)
        if value is _MISSING:
            self._name_error(f"Name '{expression.id}' has no runtime value.", expression)
        assert value is not _MISSING
        return value

    def _loop_target_names(self, target: ast.expr) -> tuple[str, ...]:
        """Return the exact flat loop target shape already admitted by CM-11."""
        if isinstance(target, ast.Name):
            return (target.id,)
        if isinstance(target, ast.Tuple) and all(
            isinstance(item, ast.Name) for item in target.elts
        ):
            return tuple(item.id for item in target.elts if isinstance(item, ast.Name))
        self._policy_error("For-loop targets must be local names or flat tuples.", target)
        raise AssertionError("Program policy errors do not return.")

    def _bind_loop_value(
        self,
        target_names: tuple[str, ...],
        value: RuntimeValue,
        target: ast.expr,
    ) -> None:
        """Bind one loop value to its temporary lexical target names."""
        if len(target_names) == 1:
            self._locals[target_names[0]] = value
            return
        if type(value) not in (list, tuple) or len(value) != len(target_names):
            self._type_error(
                "Tuple loop targets require matching list or tuple values.",
                target,
            )
        for name, item in zip(target_names, value, strict=True):
            self._locals[name] = item

    def _restore_loop_bindings(self, previous_values: dict[str, object]) -> None:
        """Restore or remove temporary loop names after every loop outcome."""
        for name, previous in previous_values.items():
            if previous is _MISSING:
                self._locals.pop(name, None)
            else:
                assert _is_runtime_value(previous)
                self._locals[name] = previous

    def _reserve_call(self, call: ast.Call) -> None:
        """Charge one dispatch before a callback can run or write a journal entry."""
        next_calls = self._executed_calls + 1
        if next_calls > self._budget.max_executed_calls:
            self._limit_error(
                f"Program executed {next_calls} calls; limit is {self._budget.max_executed_calls}.",
                call,
            )
        next_entries = len(self._journal.entries) + 1
        if next_entries > self._budget.max_journal_entries:
            self._limit_error(
                "Program would exceed the command journal entry limit "
                f"of {self._budget.max_journal_entries}.",
                call,
            )
        self._executed_calls = next_calls

    def _record_loop_iteration(self, node: ast.For) -> None:
        """Charge one leaf loop iteration against the global dynamic budget."""
        next_iterations = self._executed_loop_iterations + 1
        if next_iterations > self._budget.max_loop_iterations:
            self._limit_error(
                "Program executed "
                f"{next_iterations} leaf loop iterations; limit is "
                f"{self._budget.max_loop_iterations}.",
                node,
            )
        self._executed_loop_iterations = next_iterations

    def _charge_runtime_value(self, value: object, node: ast.AST) -> RuntimeValue:
        """Validate and charge one newly materialized value before local binding."""
        try:
            item_count = runtime_value_item_count(value)
        except ProgramTypeError as error:
            self._raise_with_span(error, node)
        next_items = self._runtime_value_items + item_count
        if next_items > self._budget.max_runtime_value_items:
            self._limit_error(
                "Program materialized "
                f"{next_items} runtime value items; limit is "
                f"{self._budget.max_runtime_value_items}.",
                node,
            )
        self._runtime_value_items = next_items
        assert _is_runtime_value(value)
        return value

    def _enter_nesting(self) -> None:
        """Track actual executed control nesting for program metrics."""
        self._current_nesting_depth += 1
        self._max_nesting_depth = max(
            self._max_nesting_depth,
            self._current_nesting_depth,
        )

    def _leave_nesting(self) -> None:
        """Leave one executed loop or conditional scope."""
        self._current_nesting_depth -= 1

    def _raise_with_span(self, error: AuthoringProgramError, node: ast.AST) -> NoReturn:
        """Preserve a typed error while attaching a source span when absent."""
        diagnostic = error.to_diagnostic()
        if diagnostic.span is not None:
            raise error
        raise type(error)(
            diagnostic.message,
            span=source_span_from_ast(node),
            remediation_hint=diagnostic.remediation_hint,
        ) from None

    def _policy_error(self, message: str, node: ast.AST) -> NoReturn:
        """Raise one policy diagnostic at a validated source location."""
        raise ProgramPolicyError(message, span=source_span_from_ast(node))

    def _name_error(self, message: str, node: ast.AST) -> NoReturn:
        """Raise one name diagnostic at a validated source location."""
        raise ProgramNameError(message, span=source_span_from_ast(node))

    def _type_error(self, message: str, node: ast.AST) -> NoReturn:
        """Raise one type diagnostic at a validated source location."""
        raise ProgramTypeError(message, span=source_span_from_ast(node))

    def _limit_error(self, message: str, node: ast.AST) -> NoReturn:
        """Raise one dynamic-limit diagnostic at a validated source location."""
        raise ProgramLimitError(message, span=source_span_from_ast(node))


def _contains_nested_for(statements: list[ast.stmt]) -> bool:
    """Return whether a loop body contains a deeper loop that owns leaf counting."""
    pending: list[ast.AST] = list(statements)
    while pending:
        node = pending.pop()
        if isinstance(node, ast.For):
            return True
        pending.extend(ast.iter_child_nodes(node))
    return False


def _is_safe_comparison_value(value: RuntimeValue) -> bool:
    """Permit equality only for safe primitives and literal container values."""
    if type(value) in (type(None), bool, int, float, str):
        return True
    if type(value) is list or type(value) is tuple:
        return all(_is_safe_comparison_value(item) for item in value)
    if type(value) is dict:
        return all(
            type(key) is str and _is_safe_comparison_value(item) for key, item in value.items()
        )
    return False


def _is_runtime_value(value: object) -> bool:
    """Return whether a value has already survived recursive runtime validation."""
    try:
        runtime_value_item_count(value)
    except ProgramTypeError:
        return False
    return True


def _count_ast_nodes(tree: ast.AST) -> int:
    """Count parsed AST nodes without importing or executing generated source."""
    pending = [tree]
    count = 0
    while pending:
        node = pending.pop()
        count += 1
        pending.extend(ast.iter_child_nodes(node))
    return count


def _count_statements(tree: ast.AST) -> int:
    """Count statement nodes for the measured program-kernel metrics."""
    pending = [tree]
    count = 0
    while pending:
        node = pending.pop()
        if isinstance(node, ast.stmt):
            count += 1
        pending.extend(ast.iter_child_nodes(node))
    return count


__all__ = ["ProgramInterpretation", "interpret_authoring_program"]
