"""Pure contract tests for the CM-10 Authoring Program boundary."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from wellplot.authoring_program.errors import (
    AuthoringProgramError,
    ProgramCapabilityError,
    ProgramDryRunError,
    ProgramLimitError,
    ProgramNameError,
    ProgramPolicyError,
    ProgramSyntaxError,
    ProgramTypeError,
)
from wellplot.authoring_program.models import (
    AuthoringProgram,
    ProgramArtifact,
    ProgramDiagnostic,
    ProgramDiagnosticSeverity,
    ProgramExecutionResult,
    ProgramMetrics,
    ProgramSource,
    ProgramSourcePosition,
    ProgramSourceSpan,
)
from wellplot.model.intent import AuthoringDocumentIntent


def _program() -> AuthoringProgram:
    """Return one source-bearing program for result-contract tests."""
    return AuthoringProgram(source=ProgramSource(text="report.title('Quicklook')\n"))


def _span() -> ProgramSourceSpan:
    """Return a valid multi-position source span."""
    return ProgramSourceSpan(
        start=ProgramSourcePosition(line=2, column=3),
        end=ProgramSourcePosition(line=2, column=12),
    )


def _artifact() -> ProgramArtifact:
    """Return the smallest valid artifact using the canonical intent model."""
    return ProgramArtifact(intent_fragment=AuthoringDocumentIntent())


def test_program_source_preserves_verbatim_text_and_rejects_extra_fields() -> None:
    """Source text is preserved until the later parser owns normalization."""
    source = ProgramSource(text="  report.title('Quicklook')\n", logical_name="example.wpa")

    assert source.text == "  report.title('Quicklook')\n"
    assert source.logical_name == "example.wpa"
    assert source.model_dump(mode="json") == {
        "text": "  report.title('Quicklook')\n",
        "logical_name": "example.wpa",
    }

    with pytest.raises(ValidationError):
        ProgramSource(text="report.title('Quicklook')", unexpected=True)


def test_source_positions_and_spans_require_a_non_reversed_one_based_range() -> None:
    """Source locations are compact and validate without parsing any source."""
    assert _span().model_dump(mode="json") == {
        "start": {"line": 2, "column": 3},
        "end": {"line": 2, "column": 12},
    }

    with pytest.raises(ValidationError):
        ProgramSourcePosition(line=0, column=1)
    with pytest.raises(ValidationError):
        ProgramSourceSpan(
            start=ProgramSourcePosition(line=3, column=1),
            end=ProgramSourcePosition(line=2, column=10),
        )


def test_diagnostic_is_strict_serializable_and_supports_optional_repair_context() -> None:
    """Diagnostics carry concise, source-local information without tracebacks."""
    diagnostic = ProgramDiagnostic(
        stage=" policy ",
        code="program.policy_error",
        message=" imports are not supported ",
        severity=ProgramDiagnosticSeverity.WARNING,
        span=_span(),
        remediation_hint="Remove the import and use an allowed SDK call.",
    )

    assert diagnostic.stage == "policy"
    assert diagnostic.message == "imports are not supported"
    assert diagnostic.model_dump(mode="json")["severity"] == "warning"

    with pytest.raises(ValidationError):
        ProgramDiagnostic(stage="parse", message="invalid", unknown=True)


def test_program_metrics_default_to_genuine_zero_and_reject_negative_measurements() -> None:
    """Runtime measurements use numbers rather than evaluation-only sentinels."""
    metrics = ProgramMetrics()

    assert metrics.model_dump(mode="json") == {
        "program_chars": 0,
        "program_ast_nodes": 0,
        "program_statements": 0,
        "program_calls": 0,
        "program_repairs": 0,
        "program_loop_iterations": 0,
        "program_nesting_depth": 0,
        "created_objects": 0,
    }

    with pytest.raises(ValidationError):
        ProgramMetrics(program_calls=-1)


def test_artifact_reuses_the_canonical_authoring_document_intent() -> None:
    """CM-10 adds no alternate desired-state or operation representation."""
    artifact = _artifact()

    assert isinstance(artifact.intent_fragment, AuthoringDocumentIntent)
    assert artifact.model_dump(mode="json", exclude_none=True) == {
        "intent_fragment": {"removals": []}
    }


def test_execution_result_requires_consistent_success_and_failure_evidence() -> None:
    """Artifacts and diagnostics make execution state explicit and deterministic."""
    successful = ProgramExecutionResult(
        program=_program(),
        success=True,
        artifact=_artifact(),
        diagnostics=(
            ProgramDiagnostic(
                stage="compile",
                severity=ProgramDiagnosticSeverity.INFO,
                message="Program compiled.",
            ),
        ),
    )
    failed_diagnostic = ProgramDiagnostic(stage="syntax", message="Unsupported syntax.")

    assert successful.artifact is not None
    assert (
        ProgramExecutionResult(
            program=_program(),
            success=False,
            diagnostics=(failed_diagnostic,),
        ).artifact
        is None
    )

    with pytest.raises(ValidationError, match="requires an artifact"):
        ProgramExecutionResult(program=_program(), success=True)
    with pytest.raises(ValidationError, match="cannot include error diagnostics"):
        ProgramExecutionResult(
            program=_program(),
            success=True,
            artifact=_artifact(),
            diagnostics=(failed_diagnostic,),
        )
    with pytest.raises(ValidationError, match="cannot include an artifact"):
        ProgramExecutionResult(
            program=_program(),
            success=False,
            artifact=_artifact(),
            diagnostics=(failed_diagnostic,),
        )
    with pytest.raises(ValidationError, match="requires at least one diagnostic"):
        ProgramExecutionResult(program=_program(), success=False)


@pytest.mark.parametrize(
    ("error_type", "code", "stage"),
    [
        (ProgramSyntaxError, "program.syntax_error", "syntax"),
        (ProgramPolicyError, "program.policy_error", "policy"),
        (ProgramNameError, "program.name_error", "name"),
        (ProgramTypeError, "program.type_error", "type"),
        (ProgramCapabilityError, "program.capability_error", "capability"),
        (ProgramLimitError, "program.limit_error", "limit"),
        (ProgramDryRunError, "program.dry_run_error", "dry_run"),
    ],
)
def test_program_errors_have_stable_codes_and_compact_diagnostics(
    error_type: type[AuthoringProgramError],
    code: str,
    stage: str,
) -> None:
    """Every semantic error category converts to one stable repair diagnostic."""
    error = error_type(
        "Unsupported program request.",
        span=_span(),
        remediation_hint="Use the supported program contract.",
    )

    diagnostic = error.to_diagnostic()

    assert str(error) == "Unsupported program request."
    assert diagnostic.code == code
    assert diagnostic.stage == stage
    assert diagnostic.severity is ProgramDiagnosticSeverity.ERROR
    assert diagnostic.span == _span()
    assert diagnostic.remediation_hint == "Use the supported program contract."
    assert "Traceback" not in diagnostic.model_dump_json()
