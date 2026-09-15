"""Tests for the bounded report program worker."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from wellplot.agent.code_mode.enrichment import HeaderSlotInspectionSummary, ReportContext
from wellplot.agent.code_mode.planner import ReportTask
from wellplot.agent.code_mode.report_worker import (
    ReportProgramCompiler,
    _validate_report_intent,
    _worker_capabilities,
)
from wellplot.agent.providers.base import (
    ProgramGenerationRequest,
    ProgramGenerationResult,
    ProviderFailureCategory,
    ProviderMetrics,
    ProviderRequestError,
)
from wellplot.authoring_program.builders import HandleBuilder
from wellplot.authoring_program.errors import ProgramDryRunError
from wellplot.authoring_program.intent_builder import IntentBuilder
from wellplot.authoring_program.interpreter import interpret_authoring_program
from wellplot.authoring_program.models import AuthoringProgram, ProgramSource
from wellplot.capabilities import create_builtin_registry
from wellplot.model.authoring import AuthoringDocumentSpec
from wellplot.model.intent import AuthoringDocumentIntent, AuthoringRemoveIntent


@dataclass
class _Backend:
    """Fake provider returning deterministic report program candidates."""

    responses: list[str] = field(default_factory=list)
    error: Exception | None = None
    requests: list[ProgramGenerationRequest] = field(default_factory=list)

    async def generate_program(self, request: ProgramGenerationRequest) -> ProgramGenerationResult:
        """Record one request and return the next configured candidate."""
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return ProgramGenerationResult(
            text=self.responses.pop(0),
            metrics=ProviderMetrics(input_tokens=10, output_tokens=20, total_tokens=30),
        )


def _document() -> AuthoringDocumentSpec:
    """Build a minimal existing report for private report dry-runs."""
    return AuthoringDocumentSpec(
        name="cm-44",
        title="Current report",
        sections=[
            {
                "id": "existing",
                "title": "Existing section",
                "tracks": [
                    {
                        "id": "existing-track",
                        "title": "Existing track",
                        "kind": "normal",
                        "width_mm": 20,
                    }
                ],
            }
        ],
    )


def _task() -> ReportTask:
    """Build the report task used by worker tests."""
    return ReportTask(
        goal="Set the report heading and output settings.",
        capability_ids=("report.standard",),
        requirements=("Set the title and preserve the existing report structure.",),
        constraints=("Do not create or modify sections.",),
    )


def _context() -> ReportContext:
    """Build only stable report slot identities, without current values."""
    return ReportContext(
        header_slots=(
            HeaderSlotInspectionSummary(slot_id="well", key="well", label="Well"),
            HeaderSlotInspectionSummary(slot_id="service_title_1"),
        )
    )


def _program() -> str:
    """Return a report-only program using the complete CM-44 primitive set."""
    return (
        "report = wp.report(title='Updated report', subtitle='CM-44')\n"
        "wp.page(report, size='letter', orientation='landscape')\n"
        "wp.depth(report, unit='ft', scale='1:240')\n"
        "wp.output(report, backend='matplotlib', output_path='result.pdf', dpi=150)\n"
        "wp.tail(report, enabled=True)\n"
        "wp.remark(report, remark_id='scope', text='Report-only update.')\n"
    )


def _compiler(backend: _Backend) -> ReportProgramCompiler:
    """Build a worker with the built-in v2 capability registry."""
    return ReportProgramCompiler(backend=backend, registry=create_builtin_registry())


def _run(coroutine: object) -> object:
    """Run one worker coroutine using the repository's synchronous test style."""
    return asyncio.run(coroutine)  # type: ignore[arg-type]


def test_report_primitives_compile_to_one_canonical_report_intent() -> None:
    """Primitive report calls preserve values and units without a second IR."""
    source = (
        "report = wp.report(title='Updated', subtitle='Subtitle')\n"
        "wp.header_field(report, key='well', value='FORGE', unit='name', label='Well')\n"
        "wp.service_title(report, slot_id='service_title_1', value='Quicklook')\n"
        "wp.detail_field(report, key='detail.run', value='ONE', unit='run')\n"
        "wp.page(report, size='letter', continuous=False)\n"
        "wp.depth(report, unit='ft', scale='1:240')\n"
        "wp.output(report, backend='matplotlib', output_path='result.pdf', dpi=150)\n"
        "wp.tail(report, enabled=True)\n"
        "wp.remark(report, remark_id='scope', text='Supported scope.')\n"
    )
    builder = IntentBuilder(handles=HandleBuilder(builder_id="cm44-primitives"))

    interpret_authoring_program(
        AuthoringProgram(source=ProgramSource(text=source, logical_name="report.wpa")),
        builder.runtime_environment(),
    )

    intent = builder.intent()
    assert intent.title == "Updated"
    assert intent.header is not None
    assert intent.header.general_fields[0].value.unit == "name"
    assert intent.header.service_titles[0].slot_id == "service_title_1"
    assert intent.header.detail_fields[0].value.value == "ONE"
    assert intent.page.continuous is False
    assert intent.depth.scale == "1:240"
    assert intent.output.output_path == "result.pdf"
    assert intent.tail.enabled is True
    assert intent.remarks[0].text == "Supported scope."


def test_report_worker_dry_runs_without_mutating_document() -> None:
    """A valid report program changes only the private dry-run copy."""
    backend = _Backend(responses=[_program()])
    document = _document()
    before = document.model_dump(mode="python")

    result = _run(
        _compiler(backend).compile(
            task=_task(),
            report_context=_context(),
            document=document,
            timeout_seconds=10,
        )
    )

    assert result.success is True
    assert result.artifact is not None
    assert result.artifact.intent_fragment.title == "Updated report"
    assert result.metrics.program_repairs == 0
    assert len(backend.requests) == 1
    assert document.model_dump(mode="python") == before


def test_report_worker_prompt_contains_only_bounded_report_context() -> None:
    """The provider sees slot identity, not document values or section state."""
    backend = _Backend(responses=[_program()])

    _run(
        _compiler(backend).compile(
            task=_task(),
            report_context=_context(),
            document=_document(),
            timeout_seconds=10,
        )
    )

    prompt = backend.requests[0].user_prompt
    assert "report.standard" in prompt
    assert '"slot_id":"well"' in prompt
    assert "Current report" not in prompt
    assert "existing-track" not in prompt
    assert "result.pdf" not in prompt
    assert "/" not in prompt.split("sdk_reference", maxsplit=1)[0]


def test_report_worker_rejects_noop_and_section_programs() -> None:
    """The report boundary rejects empty programs and mixed section output."""
    noop_backend = _Backend(responses=["report = wp.report()\n", "report = wp.report()\n"])
    mixed_backend = _Backend(
        responses=[
            "report = wp.report(title='Updated')\n"
            "section = wp.section(report, id_hint='new', title='Forbidden')\n",
            "report = wp.report(title='Still mixed')\n"
            "section = wp.section(report, id_hint='new', title='Forbidden')\n",
        ]
    )

    first = _run(
        _compiler(noop_backend).compile(
            task=_task(),
            report_context=_context(),
            document=_document(),
            timeout_seconds=10,
        )
    )
    second = _run(
        _compiler(mixed_backend).compile(
            task=_task(),
            report_context=_context(),
            document=_document(),
            timeout_seconds=10,
        )
    )

    assert first.success is False
    assert first.diagnostics[0].code == "program.dry_run_error"
    assert second.success is False
    assert second.diagnostics[0].code == "program.dry_run_error"
    assert len(noop_backend.requests) == 2
    assert len(mixed_backend.requests) == 2


def test_report_worker_repairs_once_with_same_bounded_context() -> None:
    """A failed report candidate receives one grounded repair and no document state."""
    backend = _Backend(
        responses=[
            "report = wp.report()\n",
            _program(),
        ]
    )
    result = _run(
        _compiler(backend).compile(
            task=_task(),
            report_context=_context(),
            document=_document(),
            timeout_seconds=10,
        )
    )

    assert result.success is True
    assert result.metrics.program_repairs == 1
    assert len(backend.requests) == 2
    repair_prompt = backend.requests[1].user_prompt
    assert '"slot_id":"well"' in repair_prompt
    assert "Current report" not in repair_prompt
    assert "existing-track" not in repair_prompt


def test_report_worker_propagates_initial_provider_failure() -> None:
    """A provider failure before source exists is not converted into fake evidence."""
    backend = _Backend(
        error=ProviderRequestError(
            ProviderFailureCategory.TRANSPORT,
            "Provider transport failed.",
        )
    )

    with pytest.raises(ProviderRequestError, match="Provider transport failed"):
        _run(
            _compiler(backend).compile(
                task=_task(),
                report_context=_context(),
                document=_document(),
                timeout_seconds=10,
            )
        )


def test_report_worker_rejects_non_report_capabilities_before_provider_call() -> None:
    """The worker cannot be widened by selecting a section capability."""
    with pytest.raises(ValueError, match="cannot select section capability"):
        _worker_capabilities(
            ReportTask(goal="Invalid", capability_ids=("section.log_plot",)),
            create_builtin_registry(),
        )


def test_report_boundary_rejects_removals_even_when_the_intent_is_report_scoped() -> None:
    """Report workers cannot turn the report-only slice into a deletion API."""
    intent = AuthoringDocumentIntent(
        title="Updated",
        removals=[AuthoringRemoveIntent(object_kind="report", object_id="report")],
    )

    with pytest.raises(ProgramDryRunError, match="may not emit removals"):
        _validate_report_intent(intent)
