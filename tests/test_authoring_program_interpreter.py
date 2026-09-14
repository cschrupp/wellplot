"""Adversarial execution tests for the CM-12 restricted interpreter."""

from __future__ import annotations

import ast
import builtins
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

import pytest

import wellplot.authoring_program.runtime as runtime_module
from wellplot.authoring_program.errors import (
    ProgramCapabilityError,
    ProgramLimitError,
    ProgramNameError,
    ProgramPolicyError,
    ProgramTypeError,
)
from wellplot.authoring_program.interpreter import interpret_authoring_program
from wellplot.authoring_program.models import AuthoringProgram, ProgramSource
from wellplot.authoring_program.runtime import (
    HandleMethodRegistry,
    RootMethodRegistry,
    RuntimeBudget,
    RuntimeEnvironment,
    RuntimeHandle,
    RuntimeValue,
)


def _program(source: str) -> AuthoringProgram:
    """Wrap source in the immutable program contract used by the interpreter."""
    return AuthoringProgram(source=ProgramSource(text=source, logical_name="example.wpa"))


def _runtime(
    *,
    root_overrides: Mapping[str, Callable[..., RuntimeValue]] | None = None,
    handle_overrides: Mapping[tuple[str, str], Callable[..., RuntimeValue]] | None = None,
) -> RuntimeEnvironment:
    """Build a deterministic generic registry without Wellplot SDK concepts."""
    root_methods: dict[str, Callable[..., RuntimeValue]] = {
        "section": lambda _args, _kwargs: RuntimeHandle(token="section:1", kind="section"),
        "scalar": lambda _args, _kwargs: "not-a-handle",
        "data": lambda _args, _kwargs: ["a", "b"],
    }
    handle_methods: dict[tuple[str, str], Callable[..., RuntimeValue]] = {
        ("section", "track"): lambda _args, _kwargs: RuntimeHandle(token="track:1", kind="track"),
        ("track", "curve"): lambda _args, _kwargs: None,
    }
    if root_overrides is not None:
        root_methods.update(root_overrides)
    if handle_overrides is not None:
        handle_methods.update(handle_overrides)
    return RuntimeEnvironment(
        root_methods=RootMethodRegistry(methods=root_methods),
        handle_methods=HandleMethodRegistry(methods=handle_methods),
    )


def test_interpreter_runs_registered_root_and_handle_methods_in_source_order() -> None:
    """A valid program yields deterministic generic journal and measured metrics."""
    result = interpret_authoring_program(
        _program(
            "enabled = True\n"
            "section = wp.section(title='Main')\n"
            "track = section.track(title='Gamma')\n"
            "channels = ['GR', 'SP']\n"
            "if enabled:\n"
            "    for channel in channels:\n"
            "        track.curve(channel, style={'color': 'green'})\n"
        ),
        _runtime(),
    )

    assert [(entry.receiver, entry.method) for entry in result.journal] == [
        ("wp", "section"),
        ("section:1", "track"),
        ("track:1", "curve"),
        ("track:1", "curve"),
    ]
    assert result.journal[2].args == ("GR",)
    assert result.journal[2].kwargs == {"style": {"color": "green"}}
    assert result.journal[1].result_handle == "track:1"
    assert result.counters.executed_calls == 4
    assert result.counters.executed_loop_iterations == 2
    assert result.metrics.program_calls == 4
    assert result.metrics.program_loop_iterations == 2
    assert result.metrics.program_chars > 0
    assert result.metrics.program_ast_nodes > 0
    assert result.metrics.program_repairs == 0


def test_interpreter_supports_the_tuple_loop_target_already_admitted_by_cm11() -> None:
    """CM-12 executes, but does not extend, the existing flat tuple target grammar."""
    result = interpret_authoring_program(
        _program(
            "section = wp.section(title='Main')\n"
            "track = section.track(title='Resistivity')\n"
            "pairs = [('ILD', 'Deep'), ('ILM', 'Medium')]\n"
            "for channel, label in pairs:\n"
            "    track.curve(channel, label=label)\n"
        ),
        _runtime(),
    )

    assert [entry.args for entry in result.journal[-2:]] == [("ILD",), ("ILM",)]
    assert [entry.kwargs for entry in result.journal[-2:]] == [
        {"label": "Deep"},
        {"label": "Medium"},
    ]


def test_nested_loops_count_leaf_iterations_globally_and_preserve_journal_order() -> None:
    """Nested loop work multiplies at runtime rather than using static call counts."""
    source = (
        "section = wp.section(title='Main')\n"
        "track = section.track(title='QC')\n"
        "for left in ['A', 'B', 'C']:\n"
        "    for right in ['1', '2', '3']:\n"
        "        track.curve(left, label=right)\n"
    )

    first = interpret_authoring_program(_program(source), _runtime())
    second = interpret_authoring_program(_program(source), _runtime())

    assert first.counters.executed_loop_iterations == 9
    assert first.counters.executed_calls == 11
    assert first.journal == second.journal
    assert first.metrics == second.metrics


def test_interpreter_runs_only_the_validated_if_branch() -> None:
    """Equality uses safe scalar values rather than arbitrary Python truthiness."""
    result = interpret_authoring_program(
        _program(
            "mode = 'repeat'\n"
            "if mode == 'repeat':\n"
            "    section = wp.section(title='Repeat')\n"
            "else:\n"
            "    section = wp.section(title='Main')\n"
        ),
        _runtime(),
    )

    assert len(result.journal) == 1
    assert result.journal[0].kwargs == {"title": "Repeat"}


@pytest.mark.parametrize(
    ("source", "error_type"),
    [
        ("wp.unknown()\n", ProgramCapabilityError),
        ("unknown.track()\n", ProgramNameError),
        (
            "section = wp.section(title='Main')\nsection.unknown()\n",
            ProgramCapabilityError,
        ),
        ("value = wp.scalar()\nvalue.track()\n", ProgramTypeError),
        ("wp.section(options={1: 'not-a-string-key'})\n", ProgramTypeError),
        ("wp = wp.section(title='Main')\n", ProgramPolicyError),
    ],
)
def test_interpreter_rejects_unavailable_or_invalid_runtime_operations(
    source: str,
    error_type: type[Exception],
) -> None:
    """All runtime violations remain typed program diagnostics, never Python errors."""
    with pytest.raises(error_type) as raised:
        interpret_authoring_program(_program(source), _runtime())

    assert "Traceback" not in raised.value.to_diagnostic().model_dump_json()


def test_interpreter_rejects_unsupported_callback_return_values() -> None:
    """Registry callbacks cannot inject arbitrary Python objects into locals."""
    result = object()
    runtime = _runtime(root_overrides={"bad": lambda _args, _kwargs: result})

    with pytest.raises(ProgramTypeError, match="Runtime values support only"):
        interpret_authoring_program(_program("value = wp.bad()\n"), runtime)


def test_interpreter_isolates_callback_inputs_and_wraps_callback_failures() -> None:
    """Callbacks cannot mutate program locals or expose host exception details."""

    def mutate_argument(
        args: tuple[RuntimeValue, ...],
        _kwargs: Mapping[str, RuntimeValue],
    ) -> RuntimeValue:
        assert type(args[0]) is list
        args[0].append(object())
        return RuntimeHandle(token="section:2", kind="section")

    runtime = _runtime(
        root_overrides={
            "mutate": mutate_argument,
            "fail": lambda _args, _kwargs: _raise_value_error(),
        }
    )
    result = interpret_authoring_program(
        _program("values = ['GR']\nsection = wp.mutate(values)\nsection.track(title=values)\n"),
        runtime,
    )

    assert result.journal[0].args == (["GR"],)
    assert result.journal[1].kwargs == {"title": ["GR"]}

    with pytest.raises(ProgramCapabilityError) as raised:
        interpret_authoring_program(_program("wp.fail()\n"), runtime)

    assert "sensitive callback detail" not in str(raised.value)
    assert "Traceback" not in raised.value.to_diagnostic().model_dump_json()


def test_interpreter_enforces_dynamic_call_loop_and_value_budgets() -> None:
    """Runtime work limits account for actual loop dispatches and materialized values."""
    runtime = _runtime()

    with pytest.raises(ProgramLimitError, match="executed 3 calls"):
        interpret_authoring_program(
            _program(
                "section = wp.section(title='Main')\n"
                "for channel in ['A', 'B']:\n"
                "    section.track(title=channel)\n"
            ),
            runtime,
            runtime_budget=RuntimeBudget(max_executed_calls=2),
        )

    with pytest.raises(ProgramLimitError, match="leaf loop iterations"):
        interpret_authoring_program(
            _program(
                "section = wp.section(title='Main')\n"
                "track = section.track(title='QC')\n"
                "for left in ['A', 'B', 'C']:\n"
                "    for right in ['1', '2', '3']:\n"
                "        track.curve(left, label=right)\n"
            ),
            runtime,
            runtime_budget=RuntimeBudget(max_loop_iterations=8),
        )

    with pytest.raises(ProgramLimitError, match="runtime value items"):
        interpret_authoring_program(
            _program("value = wp.data()\n"),
            runtime,
            runtime_budget=RuntimeBudget(max_runtime_value_items=2),
        )


def test_interpreter_accepts_only_source_programs_and_restores_loop_bindings() -> None:
    """Raw AST input and post-loop variables cannot bypass the public boundary."""
    with pytest.raises(ProgramTypeError, match="AuthoringProgram"):
        interpret_authoring_program(ast.parse("wp.section()"), _runtime())  # type: ignore[arg-type]

    with pytest.raises(ProgramNameError, match="no runtime value"):
        interpret_authoring_program(
            _program(
                "section = wp.section(title='Main')\n"
                "for channel in ['GR']:\n"
                "    section.track(title=channel)\n"
                "section.track(title=channel)\n"
            ),
            _runtime(),
        )


def test_interpreter_never_uses_dangerous_builtins_or_dynamic_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CM-12 dispatches only registered callbacks and never evaluates source Python."""
    calls: list[str] = []

    def called_from_authoring_program() -> bool:
        frame = sys._getframe(1)
        while frame is not None:
            module_name = frame.f_globals.get("__name__", "")
            if isinstance(module_name, str) and module_name.startswith(
                "wellplot.authoring_program"
            ):
                return True
            frame = frame.f_back
        return False

    def guarded_builtin(name: str, original: object) -> Callable[..., object]:
        def guarded(*args: object, **kwargs: object) -> object:
            flags = args[3] if len(args) > 3 else kwargs.get("flags")
            if name == "compile" and isinstance(flags, int) and flags & ast.PyCF_ONLY_AST:
                assert callable(original)
                return original(*args, **kwargs)
            if called_from_authoring_program():
                calls.append(name)
                raise AssertionError("Interpreter must not invoke dangerous builtins.")
            assert callable(original)
            return original(*args, **kwargs)

        return guarded

    for name in ("open", "compile", "eval", "exec", "__import__", "setattr", "globals"):
        monkeypatch.setattr(builtins, name, guarded_builtin(name, getattr(builtins, name)))

    result = interpret_authoring_program(
        _program("section = wp.section(title='Main')\nsection.track(title='GR')\n"),
        _runtime(),
    )

    assert len(result.journal) == 2
    assert not calls

    interpreter_module = sys.modules[interpret_authoring_program.__module__]
    interpreter_path = interpreter_module.__file__
    assert interpreter_path is not None
    interpreter_source = Path(interpreter_path).read_text(encoding="utf-8")
    runtime_source = Path(runtime_module.__file__).read_text(encoding="utf-8")
    assert "getattr(" not in interpreter_source
    assert "getattr(" not in runtime_source


def _raise_value_error() -> RuntimeValue:
    """Raise an implementation-only exception for the callback boundary test."""
    raise ValueError("sensitive callback detail")
