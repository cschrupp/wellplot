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

"""Capability-neutral execution substrate for restricted authoring programs.

The runtime intentionally knows no Wellplot concepts.  Program calls resolve
only through explicit root and handle registries, and callbacks exchange a
small recursive value universe.  The command journal is execution evidence,
not application state or an authoring operation model.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TypeAlias

from .errors import (
    AuthoringProgramError,
    ProgramCapabilityError,
    ProgramTypeError,
)


@dataclass(frozen=True)
class RuntimeHandle:
    """Opaque, registry-routable identity returned by a registered method."""

    token: str
    kind: str

    def __post_init__(self) -> None:
        """Require stable public identity components for registry dispatch."""
        if not isinstance(self.token, str) or not self.token:
            raise ValueError("Runtime handle token must be a non-empty string.")
        if not isinstance(self.kind, str) or not self.kind:
            raise ValueError("Runtime handle kind must be a non-empty string.")
        if self.token.startswith("_") or self.kind.startswith("_"):
            raise ValueError("Runtime handle identity components must be public.")


RuntimeValue: TypeAlias = (
    None
    | bool
    | int
    | float
    | str
    | RuntimeHandle
    | list["RuntimeValue"]
    | tuple["RuntimeValue", ...]
    | dict[str, "RuntimeValue"]
)
RuntimeMethod: TypeAlias = Callable[
    [tuple[RuntimeValue, ...], Mapping[str, RuntimeValue]], RuntimeValue
]


@dataclass(frozen=True)
class RuntimeBudget:
    """Independent dynamic budgets applied while one program is interpreted."""

    max_executed_calls: int = 250
    max_loop_iterations: int = 100
    max_runtime_value_items: int = 2_000
    max_journal_entries: int = 250

    def __post_init__(self) -> None:
        """Require positive integer resource limits without host introspection."""
        values = (
            ("max_executed_calls", self.max_executed_calls),
            ("max_loop_iterations", self.max_loop_iterations),
            ("max_runtime_value_items", self.max_runtime_value_items),
            ("max_journal_entries", self.max_journal_entries),
        )
        for name, value in values:
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer.")


DEFAULT_RUNTIME_BUDGET = RuntimeBudget()


@dataclass(frozen=True)
class RuntimeCounters:
    """Measured dynamic work from one completed or interrupted interpretation."""

    executed_calls: int = 0
    executed_loop_iterations: int = 0
    runtime_value_items: int = 0
    journal_entries: int = 0

    def __post_init__(self) -> None:
        """Keep externally visible counter snapshots non-negative."""
        values = (
            ("executed_calls", self.executed_calls),
            ("executed_loop_iterations", self.executed_loop_iterations),
            ("runtime_value_items", self.runtime_value_items),
            ("journal_entries", self.journal_entries),
        )
        for name, value in values:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer.")


@dataclass(frozen=True)
class CommandJournalEntry:
    """One generic recorded registry dispatch in deterministic program order."""

    sequence: int
    receiver: str
    method: str
    args: tuple[RuntimeValue, ...]
    kwargs: Mapping[str, RuntimeValue]
    result_handle: str | None


@dataclass
class CommandJournal:
    """Append-only generic execution evidence maintained by the interpreter."""

    _entries: list[CommandJournalEntry] = field(default_factory=list, init=False, repr=False)

    @property
    def entries(self) -> tuple[CommandJournalEntry, ...]:
        """Return an immutable snapshot of entries recorded so far."""
        return tuple(self._entries)

    def append(
        self,
        *,
        receiver: str,
        method: str,
        args: tuple[RuntimeValue, ...],
        kwargs: Mapping[str, RuntimeValue],
        result: RuntimeValue,
    ) -> CommandJournalEntry:
        """Record a validated dispatch after its callback has returned safely."""
        entry = CommandJournalEntry(
            sequence=len(self._entries) + 1,
            receiver=receiver,
            method=method,
            args=tuple(clone_runtime_value(value) for value in args),
            kwargs=MappingProxyType(
                {key: clone_runtime_value(value) for key, value in kwargs.items()}
            ),
            result_handle=result.token if type(result) is RuntimeHandle else None,
        )
        self._entries.append(entry)
        return entry


@dataclass(frozen=True)
class RootMethodRegistry:
    """Explicitly approved methods available from the predefined program root."""

    methods: Mapping[str, RuntimeMethod]

    def __post_init__(self) -> None:
        """Freeze and validate the root method table before interpretation."""
        object.__setattr__(self, "methods", _freeze_method_mapping(self.methods, "root method"))

    def resolve(self, method: str) -> RuntimeMethod:
        """Return one approved root method or a compact capability diagnostic."""
        callback = self.methods.get(method)
        if callback is None:
            raise ProgramCapabilityError(f"Root method 'wp.{method}' is not registered.")
        return callback


@dataclass(frozen=True)
class HandleMethodRegistry:
    """Explicitly approved methods keyed by opaque runtime-handle kind."""

    methods: Mapping[tuple[str, str], RuntimeMethod]

    def __post_init__(self) -> None:
        """Freeze and validate the handle-kind method table before interpretation."""
        frozen_methods: dict[tuple[str, str], RuntimeMethod] = {}
        for key, callback in self.methods.items():
            if not isinstance(key, tuple) or len(key) != 2:
                raise ValueError("Handle method registry keys must be (kind, method) tuples.")
            kind, method = key
            _validate_registry_name(kind, "handle kind")
            _validate_registry_name(method, "handle method")
            if not callable(callback):
                raise ValueError("Handle method registry values must be callable.")
            frozen_methods[(kind, method)] = callback
        object.__setattr__(self, "methods", MappingProxyType(frozen_methods))

    def resolve(self, handle: RuntimeHandle, method: str) -> RuntimeMethod:
        """Return one approved handle method or a compact capability diagnostic."""
        callback = self.methods.get((handle.kind, method))
        if callback is None:
            raise ProgramCapabilityError(
                f"Method '{method}' is not registered for handle kind '{handle.kind}'."
            )
        return callback


@dataclass(frozen=True)
class RuntimeEnvironment:
    """Immutable registries used for all restricted-program dispatch."""

    root_methods: RootMethodRegistry
    handle_methods: HandleMethodRegistry

    def dispatch_root(
        self,
        method: str,
        args: tuple[RuntimeValue, ...],
        kwargs: Mapping[str, RuntimeValue],
    ) -> RuntimeValue:
        """Dispatch an approved root method without dynamic Python lookup."""
        return _invoke_registered_method(
            self.root_methods.resolve(method),
            args=args,
            kwargs=kwargs,
            description=f"root method 'wp.{method}'",
        )

    def dispatch_handle(
        self,
        handle: RuntimeHandle,
        method: str,
        args: tuple[RuntimeValue, ...],
        kwargs: Mapping[str, RuntimeValue],
    ) -> RuntimeValue:
        """Dispatch an approved handle method without dynamic Python lookup."""
        return _invoke_registered_method(
            self.handle_methods.resolve(handle, method),
            args=args,
            kwargs=kwargs,
            description=f"handle method '{handle.kind}.{method}'",
        )


def runtime_value_item_count(value: RuntimeValue) -> int:
    """Validate one value and return its deterministic recursive item count.

    Scalars and handles count as one. Lists and tuples count as one container
    plus their values. Dictionaries count as one container, one item per string
    key, and the recursive count of each value. Cyclic containers are invalid.
    """
    return _runtime_value_item_count(value, active_container_ids=set())


def clone_runtime_value(value: RuntimeValue) -> RuntimeValue:
    """Return an isolated validated copy suitable for registry boundaries."""
    runtime_value_item_count(value)
    return _clone_runtime_value(value)


def _freeze_method_mapping(
    methods: Mapping[str, RuntimeMethod],
    label: str,
) -> Mapping[str, RuntimeMethod]:
    """Freeze one public-name method mapping after defensive validation."""
    frozen_methods: dict[str, RuntimeMethod] = {}
    for name, callback in methods.items():
        _validate_registry_name(name, label)
        if not callable(callback):
            raise ValueError(f"{label.capitalize()} registry values must be callable.")
        frozen_methods[name] = callback
    return MappingProxyType(frozen_methods)


def _validate_registry_name(name: object, label: str) -> None:
    """Reject empty and private registry keys before they become callable names."""
    if not isinstance(name, str) or not name or name.startswith("_"):
        raise ValueError(f"{label.capitalize()} names must be non-empty public strings.")


def _invoke_registered_method(
    callback: RuntimeMethod,
    *,
    args: tuple[RuntimeValue, ...],
    kwargs: Mapping[str, RuntimeValue],
    description: str,
) -> RuntimeValue:
    """Isolate a registered callback and reject unsupported returned values."""
    callback_args = tuple(clone_runtime_value(value) for value in args)
    callback_kwargs = MappingProxyType(
        {key: clone_runtime_value(value) for key, value in kwargs.items()}
    )
    try:
        result = callback(callback_args, callback_kwargs)
    except AuthoringProgramError:
        raise
    except Exception:
        raise ProgramCapabilityError(
            f"Registered {description} did not complete successfully."
        ) from None
    return clone_runtime_value(result)


def _runtime_value_item_count(value: object, *, active_container_ids: set[int]) -> int:
    """Validate the recursive runtime value universe without host object access."""
    if type(value) in (type(None), bool, int, float, str, RuntimeHandle):
        return 1

    if type(value) is list or type(value) is tuple:
        return _container_item_count(value, active_container_ids=active_container_ids)

    if type(value) is dict:
        container_id = id(value)
        if container_id in active_container_ids:
            raise ProgramTypeError("Runtime containers cannot be cyclic.")
        active_container_ids.add(container_id)
        try:
            total = 1
            for key, item in value.items():
                if type(key) is not str:
                    raise ProgramTypeError("Runtime dictionary keys must be strings.")
                total += 1
                total += _runtime_value_item_count(item, active_container_ids=active_container_ids)
            return total
        finally:
            active_container_ids.remove(container_id)

    raise ProgramTypeError(
        "Runtime values support only scalars, lists, tuples, "
        "string-keyed dictionaries, and handles."
    )


def _container_item_count(
    value: list[object] | tuple[object, ...],
    *,
    active_container_ids: set[int],
) -> int:
    """Count one list or tuple after rejecting cyclic container graphs."""
    container_id = id(value)
    if container_id in active_container_ids:
        raise ProgramTypeError("Runtime containers cannot be cyclic.")
    active_container_ids.add(container_id)
    try:
        return 1 + sum(
            _runtime_value_item_count(item, active_container_ids=active_container_ids)
            for item in value
        )
    finally:
        active_container_ids.remove(container_id)


def _clone_runtime_value(value: RuntimeValue) -> RuntimeValue:
    """Copy a previously validated safe value without using generic deepcopy."""
    if type(value) in (type(None), bool, int, float, str, RuntimeHandle):
        return value
    if type(value) is list:
        return [_clone_runtime_value(item) for item in value]
    if type(value) is tuple:
        return tuple(_clone_runtime_value(item) for item in value)
    if type(value) is dict:
        return {key: _clone_runtime_value(item) for key, item in value.items()}
    raise AssertionError("Runtime value validation must precede cloning.")


__all__ = [
    "CommandJournal",
    "CommandJournalEntry",
    "DEFAULT_RUNTIME_BUDGET",
    "HandleMethodRegistry",
    "RootMethodRegistry",
    "RuntimeBudget",
    "RuntimeCounters",
    "RuntimeEnvironment",
    "RuntimeHandle",
    "RuntimeMethod",
    "RuntimeValue",
    "clone_runtime_value",
    "runtime_value_item_count",
]
