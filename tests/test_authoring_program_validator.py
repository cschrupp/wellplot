"""Pure adversarial tests for the CM-11 restricted program grammar."""

from __future__ import annotations

import ast
import builtins
import sys
from collections.abc import Callable
from dataclasses import replace

import pytest

from wellplot.authoring_program.errors import (
    ProgramLimitError,
    ProgramNameError,
    ProgramPolicyError,
    ProgramSyntaxError,
)
from wellplot.authoring_program.grammar import (
    DEFAULT_PROGRAM_POLICY_LIMITS,
    ProgramPolicyLimits,
    source_span_from_ast,
)
from wellplot.authoring_program.models import AuthoringProgram, ProgramSource
from wellplot.authoring_program.validator import validate_authoring_program


def _program(source: str) -> AuthoringProgram:
    """Wrap source in the CM-10 program contract."""
    return AuthoringProgram(source=ProgramSource(text=source, logical_name="example.wpa"))


def test_policy_limits_match_the_initial_migration_budgets() -> None:
    """CM-11 centralizes the initial static limits in one immutable policy."""
    assert (
        ProgramPolicyLimits(
            max_source_chars=16_000,
            max_ast_nodes=1_500,
            max_statements=300,
            max_calls=250,
            max_loop_iterations=100,
            max_nesting=8,
        )
        == DEFAULT_PROGRAM_POLICY_LIMITS
    )

    with pytest.raises(ValueError, match="max_calls"):
        ProgramPolicyLimits(max_calls=0)


def test_validator_accepts_assignment_method_calls_literals_and_keywords() -> None:
    """The initial language accepts only compact, explicit construction steps."""
    tree = validate_authoring_program(
        _program(
            "section = wp.add_section(title='Main')\n"
            "track = section.add('track.normal', title='Gamma Ray')\n"
            "track.add('binding.curve', channel='GR', style={'color': 'green'})\n"
        )
    )

    assert isinstance(tree, ast.Module)
    assert len(tree.body) == 3


def test_validator_accepts_bounded_literal_and_local_literal_for_loops() -> None:
    """Literal sequence bounds and plan-approved tuple targets remain static."""
    tree = validate_authoring_program(
        _program(
            "section = wp.add_section(title='Main')\n"
            "track = section.add('track.normal', title='Resistivity')\n"
            "channels = [('ILD', 'Deep'), ('ILM', 'Medium')]\n"
            "for channel, label in channels:\n"
            "    track.add('binding.curve', channel=channel, label=label)\n"
        )
    )

    assert isinstance(tree.body[-1], ast.For)


def test_validator_accepts_boolean_and_literal_comparison_if_conditions() -> None:
    """The initial conditional grammar avoids operators and handle truthiness."""
    tree = validate_authoring_program(
        _program(
            "enabled = True\n"
            "mode = 'repeat'\n"
            "if enabled:\n"
            "    wp.report()\n"
            "if mode == 'repeat':\n"
            "    wp.report()\n"
        )
    )

    assert sum(isinstance(node, ast.If) for node in tree.body) == 2


def test_parser_error_has_a_compact_syntax_diagnostic_with_a_source_span() -> None:
    """Parser exceptions become stable program diagnostics without source dumps."""
    with pytest.raises(ProgramSyntaxError) as raised:
        validate_authoring_program(_program("section = wp.add_section(\n"))

    diagnostic = raised.value.to_diagnostic()

    assert diagnostic.code == "program.syntax_error"
    assert diagnostic.stage == "syntax"
    assert diagnostic.span is not None
    assert diagnostic.span.start.line == 1
    assert "example.wpa" not in diagnostic.message
    assert "Traceback" not in diagnostic.model_dump_json()


@pytest.mark.parametrize(
    "source",
    [
        "import os\n",
        "from pathlib import Path\n",
        "def build():\n    wp.report()\n",
        "async def build():\n    wp.report()\n",
        "@decorator\ndef build():\n    wp.report()\n",
        "class Builder:\n    pass\n",
        "lambda: wp.report()\n",
        "while True:\n    wp.report()\n",
        "with context:\n    wp.report()\n",
        "try:\n    wp.report()\nexcept Exception:\n    wp.report()\n",
        "raise RuntimeError()\n",
        "del item\n",
        "global item\n",
        "nonlocal item\n",
        "yield item\n",
        "await wp.report()\n",
        "[item for item in ['GR']]\n",
        "{item for item in ['GR']}\n",
        "{item: item for item in ['GR']}\n",
        "(item for item in ['GR'])\n",
        "if (enabled := True):\n    wp.report()\n",
        "values = items[0]\n",
        "value = 1 + 2\n",
        "value = -1\n",
        "value = True and False\n",
        "f'{value}'\n",
        "match value:\n    case _:\n        wp.report()\n",
        "assert True\n",
    ],
)
def test_validator_rejects_syntax_outside_the_explicit_allowlist(source: str) -> None:
    """Every omitted Python feature is rejected before it can gain semantics."""
    with pytest.raises(ProgramPolicyError) as raised:
        validate_authoring_program(_program(source))

    diagnostic = raised.value.to_diagnostic()
    assert diagnostic.code == "program.policy_error"
    assert diagnostic.span is not None


@pytest.mark.parametrize(
    "source",
    [
        "open('file')\n",
        "arbitrary()\n",
        "wp.report().add('track.normal')\n",
        "for value in some_call():\n    wp.report()\n",
        "for value in section.items:\n    wp.report()\n",
        "for value in ['GR']:\n    wp.report()\nelse:\n    wp.report()\n",
        "target.value = 3\n",
        "items[0] = 'GR'\n",
        "left, right = ('GR', 'CCL')\n",
        "wp.report(*values)\n",
        "wp.report(**options)\n",
        "if mode > 'repeat':\n    wp.report()\n",
        "section = wp.add_section(title='Main')\nif section:\n    wp.report()\n",
    ],
)
def test_validator_rejects_dynamic_calls_mutation_and_unbounded_control_flow(source: str) -> None:
    """Static shape checks reject behavior that later runtime rules cannot trust."""
    with pytest.raises(ProgramPolicyError) as raised:
        validate_authoring_program(_program(source))

    assert raised.value.to_diagnostic().span is not None


@pytest.mark.parametrize(
    "source",
    [
        "_private = wp.report()\n",
        "wp.__class__()\n",
        "section = wp.add_section(title='Main')\nsection._private()\n",
        "unknown.add('track.normal')\n",
        "for value in unknown:\n    wp.report()\n",
    ],
)
def test_validator_rejects_private_and_unknown_names(source: str) -> None:
    """The syntactic environment has only the SDK root and introduced locals."""
    with pytest.raises(ProgramNameError) as raised:
        validate_authoring_program(_program(source))

    diagnostic = raised.value.to_diagnostic()
    assert diagnostic.code == "program.name_error"
    assert diagnostic.span is not None


def test_validator_rejects_excessive_source_and_ast_size() -> None:
    """Large source and giant literals fail static limits before interpretation."""
    with pytest.raises(ProgramLimitError):
        validate_authoring_program(
            _program("wp.report()\n"),
            limits=replace(DEFAULT_PROGRAM_POLICY_LIMITS, max_source_chars=5),
        )

    giant_literal = f"values = {list(range(1_600))!r}\n"
    with pytest.raises(ProgramLimitError):
        validate_authoring_program(_program(giant_literal))

    with pytest.raises(ProgramLimitError):
        validate_authoring_program(
            _program("wp.report()\n"),
            limits=replace(DEFAULT_PROGRAM_POLICY_LIMITS, max_ast_nodes=1),
        )


def test_validator_rejects_excessive_statements_calls_loops_and_nesting() -> None:
    """Every static execution budget is checked before future interpretation."""
    with pytest.raises(ProgramLimitError):
        validate_authoring_program(
            _program("wp.report()\nwp.report()\n"),
            limits=replace(DEFAULT_PROGRAM_POLICY_LIMITS, max_statements=1),
        )
    with pytest.raises(ProgramLimitError):
        validate_authoring_program(
            _program("wp.report()\nwp.report()\n"),
            limits=replace(DEFAULT_PROGRAM_POLICY_LIMITS, max_calls=1),
        )
    with pytest.raises(ProgramLimitError):
        validate_authoring_program(
            _program("for item in ['GR', 'CCL']:\n    wp.report()\n"),
            limits=replace(DEFAULT_PROGRAM_POLICY_LIMITS, max_loop_iterations=1),
        )
    with pytest.raises(ProgramLimitError):
        validate_authoring_program(
            _program("if True:\n    if True:\n        wp.report()\n"),
            limits=replace(DEFAULT_PROGRAM_POLICY_LIMITS, max_nesting=1),
        )


def test_source_span_conversion_is_centralized_for_ast_diagnostics() -> None:
    """AST coordinates are mapped once rather than reconstructed by each rule."""
    node = ast.parse("wp.report()\n").body[0]
    span = source_span_from_ast(node)

    assert span is not None
    assert span.start.line == 1
    assert span.start.column == 1
    assert span.end.line == 1


def test_validator_never_executes_source_or_invokes_dangerous_builtins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validation inspects an AST and never converts source syntax into behavior."""
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
            # CPython implements ast.parse through compile(..., PyCF_ONLY_AST).
            # Permit that parse-only implementation detail, but no bytecode compilation.
            flags = args[3] if len(args) > 3 else kwargs.get("flags")
            if name == "compile" and isinstance(flags, int) and flags & ast.PyCF_ONLY_AST:
                assert callable(original)
                return original(*args, **kwargs)
            if called_from_authoring_program():
                calls.append(name)
                raise AssertionError("Validation must not invoke dangerous builtins.")
            assert callable(original)
            return original(*args, **kwargs)

        return guarded

    for name in ("open", "compile", "eval", "exec", "__import__"):
        monkeypatch.setattr(builtins, name, guarded_builtin(name, getattr(builtins, name)))

    tree = validate_authoring_program(_program("wp.report()\n"))

    assert isinstance(tree, ast.Module)
    assert not calls
