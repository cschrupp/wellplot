"""Tests for the bounded generic section program worker."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from wellplot.agent.code_mode.enrichment import (
    ChannelContext,
    EnrichedSemanticContext,
    LoadedSource,
    ReportContext,
    ResolvedSectionContext,
    SourceContext,
)
from wellplot.agent.code_mode.planner import SectionTask, SemanticPlan
from wellplot.agent.code_mode.program_worker import ProgramSectionCompiler, _fresh_builder
from wellplot.agent.providers.base import (
    ProgramGenerationRequest,
    ProgramGenerationResult,
    ProviderFailureCategory,
    ProviderMetrics,
    ProviderRequestError,
)
from wellplot.capabilities import create_builtin_registry
from wellplot.model.authoring import AuthoringDocumentSpec


@dataclass
class _Backend:
    """Fake provider returning deterministic program candidates."""

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


def _document(*, collision_binding: bool = True) -> AuthoringDocumentSpec:
    """Build a document with identities that must seed every worker attempt."""
    binding_id = "pilot.scalar.GR" if collision_binding else "existing.GR"
    return AuthoringDocumentSpec(
        name="cm-42",
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
                        "bindings": [{"binding_id": binding_id, "channel": "OLD"}],
                    }
                ],
            }
        ],
    )


def _task(goal: str = "Create the scalar pilot section.") -> SectionTask:
    """Build the scalar-section semantic task used by the pilot."""
    return SectionTask(
        goal=goal,
        capability_ids=("section.log_plot", "track.normal", "binding.curve"),
        requirements=("Create one normal track for GR.",),
        constraints=("Keep the section scalar and concise.",),
    )


def _context(
    *,
    task: SectionTask | None = None,
    extra_task: SectionTask | None = None,
    section_id: str | None = None,
    channel: str = "GR",
) -> EnrichedSemanticContext:
    """Build indexed enrichment with only the selected source projection."""
    selected_task = task or _task()
    tasks = [selected_task]
    sections = [
        ResolvedSectionContext(
            task_index=0,
            section_id=section_id,
            sources=(
                SourceContext(
                    candidate_id="pilot.las",
                    canonical_path="/approved/pilot.las",
                    source_format="las",
                    dataset_name="pilot",
                    channels=(ChannelContext(mnemonic=channel, kind="scalar", unit="gAPI"),),
                ),
            ),
            channels=(
                {
                    "mnemonic": channel,
                    "kind": "scalar",
                    "unit": "gAPI",
                },
            ),
        )
    ]
    if extra_task is not None:
        tasks.append(extra_task)
        sections.append(
            ResolvedSectionContext(
                task_index=1,
                section_id=None,
                sources=(),
                channels=(),
            )
        )
    return EnrichedSemanticContext(
        plan=SemanticPlan(summary="CM-42 pilot", section_tasks=tuple(tasks)),
        sections=tuple(sections),
        report=ReportContext(),
    )


def _program(*, section_id: str = "pilot", channel: str = "GR") -> str:
    """Return executable syntax from the CM-42 worker reference."""
    return (
        "report = wp.report()\n"
        f"section = wp.section(report, id_hint='{section_id}', title='Scalar Pilot')\n"
        "track = wp.track(section, id_hint='scalar', kind='normal', "
        "title='Gamma Ray', width_mm=30)\n"
        f"wp.curve(track, channel='{channel}', label='GR')\n"
    )


def _source_program() -> str:
    """Return a program that selects the host-registered candidate explicitly."""
    return (
        "report = wp.report()\n"
        "source = wp.source('pilot.las')\n"
        "section = wp.section(report, id_hint='pilot', title='Pilot', source=source)\n"
        "track = wp.track(section, id_hint='normal', kind='normal', "
        "title='Gamma Ray', width_mm=30)\n"
        "wp.curve(track, channel='GR', label='GR')\n"
    )


def _compiler(backend: _Backend) -> ProgramSectionCompiler:
    """Build the worker with the built-in v2 capability registry."""
    return ProgramSectionCompiler(backend=backend, registry=create_builtin_registry())


def _run(coroutine: object) -> object:
    """Run one worker coroutine using the repository's synchronous test style."""
    return asyncio.run(coroutine)  # type: ignore[arg-type]


def test_new_scalar_section_compiles_and_dry_runs_without_mutating_document() -> None:
    """The scalar pilot emits one section, normal track, and scalar curve."""
    backend = _Backend(responses=[_program()])
    document = _document()
    before = document.model_dump(mode="python")

    result = _run(
        _compiler(backend).compile(
            task_index=0,
            context=_context(),
            document=document,
            timeout_seconds=10,
        )
    )

    assert result.success is True
    assert result.artifact is not None
    assert result.metrics.program_repairs == 0
    intent = result.artifact.intent_fragment
    assert len(intent.sections or []) == 1
    section = intent.sections[0]
    assert section.section_id == "pilot"
    assert len(section.tracks or []) == 1
    track = section.tracks[0]
    assert track.kind == "normal"
    assert len(track.bindings or []) == 1
    assert track.bindings[0].channel == "GR"
    assert track.bindings[0].binding_id == "pilot.scalar.GR.2"
    assert document.model_dump(mode="python") == before
    assert len(backend.requests) == 1


def test_allocator_suffixes_a_colliding_new_section_id() -> None:
    """Existing section identities are reserved before the program is interpreted."""
    backend = _Backend(responses=[_program(section_id="existing")])

    result = _run(
        _compiler(backend).compile(
            task_index=0,
            context=_context(),
            document=_document(),
            timeout_seconds=10,
        )
    )

    assert result.success is True
    assert result.artifact is not None
    assert result.artifact.intent_fragment.sections[0].section_id == "existing.2"


def test_worker_prompt_is_scoped_to_the_indexed_section() -> None:
    """The worker prompt excludes other tasks, report inventory, and full document state."""
    backend = _Backend(responses=[_program()])
    context = _context(
        task=_task("Target section only."),
        extra_task=_task("Other section must not leak into this prompt."),
    )

    _run(
        _compiler(backend).compile(
            task_index=0,
            context=context,
            document=_document(),
            timeout_seconds=10,
        )
    )

    prompt = backend.requests[0].user_prompt
    assert "Target section only." in prompt
    assert "Other section must not leak" not in prompt
    assert "Current report" not in prompt
    assert "header_slots" not in prompt
    assert "/approved/pilot.las" not in prompt
    assert "Executable Wellplot SDK reference" in prompt


def test_source_candidate_is_associated_without_exposing_canonical_path() -> None:
    """The worker can attach a host source while its prompt remains path-free."""
    backend = _Backend(responses=[_source_program()])
    result = _run(
        _compiler(backend).compile(
            task_index=0,
            context=_context(),
            document=_document(),
            timeout_seconds=10,
        )
    )

    assert result.success is True
    assert result.artifact is not None
    section = result.artifact.intent_fragment.sections[0]
    assert section.data_source is not None
    assert section.data_source.source_path == "/approved/pilot.las"
    assert "/approved/pilot.las" not in backend.requests[0].user_prompt


def test_each_worker_attempt_gets_fresh_source_handle_provenance() -> None:
    """Repair attempts cannot reuse source handles issued by a prior builder."""
    context = _context()
    document = _document()
    first = _fresh_builder(document, section_context=context.sections[0])
    second = _fresh_builder(document, section_context=context.sections[0])

    first_source = first.source("pilot.las")
    second_source = second.source("pilot.las")
    assert first_source != second_source
    assert first_source.builder_id != second_source.builder_id
    assert not hasattr(first_source, "canonical_path")


def test_existing_section_task_is_rejected_without_provider_call() -> None:
    """CM-42 does not turn a resolved section into accidental duplicate creation."""
    backend = _Backend(responses=[_program()])

    with pytest.raises(ValueError, match="new section reconstruction only"):
        _run(
            _compiler(backend).compile(
                task_index=0,
                context=_context(section_id="existing"),
                document=_document(),
                timeout_seconds=10,
            )
        )

    assert backend.requests == []


def test_repair_uses_fresh_identity_state_and_counts_one_repair() -> None:
    """A repaired candidate is rerun with the same seeded identities, not suffixes."""
    backend = _Backend(
        responses=[
            _program(channel="MISSING"),
            _program(),
        ]
    )
    result = _run(
        _compiler(backend).compile(
            task_index=0,
            context=_context(),
            document=_document(),
            timeout_seconds=10,
        )
    )

    assert result.success is True
    assert result.metrics.program_repairs == 1
    assert result.artifact is not None
    assert result.artifact.intent_fragment.sections[0].section_id == "pilot"
    assert (
        result.artifact.intent_fragment.sections[0].tracks[0].bindings[0].binding_id
        == "pilot.scalar.GR.2"
    )
    assert len(backend.requests) == 2


def test_failed_repaired_candidate_stops_without_recursive_repair() -> None:
    """One failed repaired candidate terminates the worker without another coordinator call."""
    backend = _Backend(
        responses=[
            _program(channel="MISSING"),
            "report = wp.report(title='still forbidden')\n",
        ]
    )
    result = _run(
        _compiler(backend).compile(
            task_index=0,
            context=_context(),
            document=_document(),
            timeout_seconds=10,
        )
    )

    assert result.success is False
    assert result.artifact is None
    assert result.metrics.program_repairs == 1
    assert len(backend.requests) == 2
    assert any(diagnostic.code == "program.dry_run_error" for diagnostic in result.diagnostics)


def test_initial_provider_failure_is_propagated_without_fake_program() -> None:
    """A provider failure before source exists cannot be represented as program evidence."""
    backend = _Backend(
        error=ProviderRequestError(
            ProviderFailureCategory.TRANSPORT,
            "Provider transport failed.",
        )
    )

    with pytest.raises(ProviderRequestError, match="Provider transport failed"):
        _run(
            _compiler(backend).compile(
                task_index=0,
                context=_context(),
                document=_document(),
                timeout_seconds=10,
            )
        )


def test_loaded_source_contract_remains_without_sample_payloads() -> None:
    """The worker imports only bounded CM-41 source contracts, not parser objects."""
    loaded = LoadedSource(dataset_name="pilot")
    assert loaded.channels == ()
