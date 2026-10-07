"""Tests for the bounded generic section program worker."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

import pytest

import wellplot.authoring_program.program_runtime as runtime_module
from wellplot.agent.code_mode.enrichment import (
    ChannelContext,
    EnrichedSemanticContext,
    ExistingCurveContext,
    LoadedSource,
    ReportContext,
    ResolvedSectionContext,
    SourceContext,
)
from wellplot.agent.code_mode.planner import SectionTask, SemanticPlan
from wellplot.agent.code_mode.program_worker import (
    SECTION_PROGRAM_CAPABILITIES,
    ProgramSectionCompiler,
    _fresh_builder,
    _sdk_reference,
)
from wellplot.agent.providers.base import (
    ProgramGenerationRequest,
    ProgramGenerationResult,
    ProviderFailureCategory,
    ProviderMetrics,
    ProviderRequestError,
)
from wellplot.authoring_executor import execute_authoring_plan
from wellplot.authoring_program.builders import HandleBuilder
from wellplot.authoring_program.errors import ProgramTypeError
from wellplot.authoring_program.intent_builder import IntentBuilder
from wellplot.authoring_program.interpreter import interpret_authoring_program
from wellplot.authoring_program.models import AuthoringProgram, ProgramSource
from wellplot.authoring_service import AuthoringService
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


def _document(
    *,
    collision_binding: bool = True,
    section_id: str = "existing",
) -> AuthoringDocumentSpec:
    """Build a document with identities that must seed every worker attempt."""
    binding_id = "pilot.scalar.GR" if collision_binding else "existing.GR"
    return AuthoringDocumentSpec(
        name="cm-42",
        title="Current report",
        sections=[
            {
                "id": section_id,
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
    channel_specs: tuple[ChannelContext, ...] | None = None,
    candidate_ids: tuple[str, ...] = ("pilot.las",),
) -> EnrichedSemanticContext:
    """Build indexed enrichment with only the selected source projection."""
    selected_task = task or _task()
    tasks = [selected_task]
    selected_channels = channel_specs or (
        ChannelContext(mnemonic=channel, kind="scalar", unit="gAPI"),
    )
    sources = tuple(
        SourceContext(
            candidate_id=candidate_id,
            canonical_path=f"/approved/{candidate_id}",
            source_format="las",
            dataset_name="pilot",
            channels=selected_channels,
        )
        for candidate_id in candidate_ids
    )
    sections = [
        ResolvedSectionContext(
            task_index=0,
            section_id=section_id,
            sources=sources,
            channels=(
                {
                    "mnemonic": item.mnemonic,
                    "kind": item.kind,
                    "unit": item.unit,
                    "shape": item.shape,
                }
                for item in selected_channels
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


def _revision_program(*, title: str = "Revised section") -> str:
    """Return a program that uses only the opaque host-selected target."""
    return (
        "report = wp.report()\n"
        "section = wp.target_section(report)\n"
        f"wp.update_section(section, title='{title}')\n"
    )


def _fill_task() -> SectionTask:
    """Build the bounded existing-section task used by D2C worker tests."""
    return SectionTask(
        goal="Add a grounded lower-limit fill to the GR curve.",
        capability_ids=(
            "section.log_plot",
            "track.normal",
            "binding.curve",
            "fill.curve",
        ),
        existing_section_hint="Existing section",
        requirements=("Create one grounded lower-limit fill on the GR track.",),
    )


def _fill_program(*, binding_id: str = "existing.GR") -> str:
    """Return one existing-section program that creates a track-local fill."""
    return (
        "report = wp.report()\n"
        "section = wp.target_section(report)\n"
        "track = wp.target_track(section, track_id='existing-track')\n"
        f"curve = wp.target_curve(track, binding_id={binding_id!r})\n"
        "wp.fill(track, curve, kind='to_lower_limit', "
        "color='#d9d9d9', alpha=0.25)\n"
    )


def _fill_context(*, include_other_track: bool = False) -> EnrichedSemanticContext:
    """Build a grounded existing-curve context for D2C worker tests."""
    task = _fill_task()
    base = _context(task=task, section_id="existing")
    section = base.sections[0].model_copy(
        update={
            "existing_curves": (
                ExistingCurveContext(
                    track_id="existing-track",
                    track_title="Existing track",
                    track_kind="normal",
                    binding_id="existing.GR",
                    channel="GR",
                    label="GR",
                ),
                *(
                    (
                        ExistingCurveContext(
                            track_id="other-track",
                            track_title="Other track",
                            track_kind="normal",
                            binding_id="other.CALI",
                            channel="CALI",
                            label="CALI",
                        ),
                    )
                    if include_other_track
                    else ()
                ),
            )
        }
    )
    return base.model_copy(update={"sections": (section,)})


def _fill_document(*, include_other_track: bool = False) -> AuthoringDocumentSpec:
    """Build a document with one grounded curve and an optional sibling track."""
    tracks: list[dict[str, object]] = [
        {
            "id": "existing-track",
            "title": "Existing track",
            "kind": "normal",
            "width_mm": 20,
            "bindings": [{"binding_id": "existing.GR", "channel": "GR"}],
        }
    ]
    if include_other_track:
        tracks.append(
            {
                "id": "other-track",
                "title": "Other track",
                "kind": "normal",
                "width_mm": 20,
                "bindings": [{"binding_id": "other.CALI", "channel": "CALI"}],
            }
        )
    return AuthoringDocumentSpec(
        name="cm-d2c-worker",
        title="Current report",
        sections=[
            {
                "id": "existing",
                "title": "Existing section",
                "tracks": tracks,
            }
        ],
    )


def _generic_binding_task() -> SectionTask:
    """Build a generic section task requiring scalar and array bindings."""
    return SectionTask(
        goal="Create a generic section with scalar and array displays.",
        capability_ids=(
            "binding.curve",
            "binding.raster",
            "section.log_plot",
            "track.array",
            "track.normal",
        ),
        requirements=(
            "Bind exact scalar source channel 'CBL' twice for two presentations.",
            "Bind exact array source channel 'VDL' as a raster.",
        ),
        constraints=(),
    )


def _generic_binding_program(*, invented_channels: bool) -> str:
    """Return a generic two-track program with optionally invented channel names."""
    cbl_channel = "CBL_0_100" if invented_channels else "CBL"
    vdl_channel = "VDL_WAVEFORM" if invented_channels else "VDL"
    return (
        "report = wp.report()\n"
        "source = wp.source('pilot.las')\n"
        "section = wp.section(report, id_hint='pilot', title='Pilot', source=source)\n"
        "cbl = wp.track(section, id_hint='cbl', kind='normal', "
        "title='CBL', width_mm=44)\n"
        "vdl = wp.track(section, id_hint='vdl', kind='array', "
        "title='VDL', width_mm=48)\n"
        f"wp.curve(cbl, channel='{cbl_channel}', id_hint='broad')\n"
        f"wp.curve(cbl, channel='{cbl_channel}', id_hint='tight')\n"
        f"wp.raster(vdl, channel='{vdl_channel}')\n"
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
    assert "Exact executable Wellplot SDK contract" in prompt


def test_worker_prompt_projects_only_selected_document_track_inventory() -> None:
    """Track grounding comes from the selected canonical section, not request text."""
    backend = _Backend(
        responses=[
            "report = wp.report()\n"
            "section = wp.target_section(report)\n"
            "track = wp.target_track(section, track_id='combo')\n"
            "wp.curve(track, channel='GR', label='GR')\n"
        ]
    )
    document = AuthoringDocumentSpec(
        name="cm-d3-inventory",
        title="Current report",
        sections=[
            {
                "id": "existing",
                "title": "Existing section",
                "tracks": [
                    {
                        "id": "combo",
                        "title": "Combo",
                        "kind": "normal",
                        "width_mm": 50,
                        "bindings": [],
                    }
                ],
            },
            {
                "id": "sibling",
                "title": "Sibling section",
                "tracks": [
                    {
                        "id": "hidden",
                        "title": "Hidden",
                        "kind": "normal",
                        "width_mm": 20,
                        "bindings": [{"binding_id": "sibling.GR", "channel": "GR"}],
                    }
                ],
            },
        ],
    )
    context = _context(section_id="existing")

    result = _run(
        _compiler(backend).compile(
            task_index=0,
            context=context,
            document=document,
            timeout_seconds=10,
        )
    )

    assert result.success is True
    payload = json.loads(backend.requests[0].user_prompt.split("\n\n", 1)[1])
    assert payload["section_context"]["existing_tracks"] == [
        {
            "track_id": "combo",
            "title": "Combo",
            "kind": "normal",
            "width_mm": 50.0,
            "binding_ids": [],
        }
    ]
    assert "hidden" not in backend.requests[0].user_prompt
    assert (
        "Grounded existing track inventory; use exact identities only:" in payload["sdk_reference"]
    )


def test_worker_sdk_reference_exposes_only_exact_context_grounded_contract() -> None:
    """Section docs contain legal keywords and only host-approved channels."""
    context = _context(
        channel_specs=(
            ChannelContext(mnemonic="CBL", kind="scalar", unit="mV"),
            ChannelContext(mnemonic="VDL", kind="array", shape=(128, 64)),
        )
    )

    reference = _sdk_reference(context.sections[0])

    assert "scale_minimum" in reference
    assert "scale_maximum" in reference
    assert "scale_kind" in reference
    assert "wp.track(section):" in reference
    assert "wp.curve(track):" in reference
    assert "wp.raster(track):" in reference
    assert "scale_linear" not in reference
    assert "x_scale" not in reference
    assert "high" not in reference
    assert "'CHANNEL'" not in reference
    assert "'REFERENCE_CHANNEL'" not in reference
    assert "'ARRAY_CHANNEL'" not in reference
    assert 'wp.curve(normal, channel="CBL")' in reference
    assert 'wp.raster(array, channel="VDL")' in reference


def test_d2c_declares_fill_capability_and_sdk_vocabulary() -> None:
    """Expose only the existing grounded fill-creation operation to the worker."""
    assert "fill.curve" in SECTION_PROGRAM_CAPABILITIES
    reference = _sdk_reference(_fill_context().sections[0])

    assert "wp.fill(track, binding[, other_binding])" in reference
    assert "kind, id_hint, label, color, alpha" in reference
    assert "fill_id" not in reference
    assert "select_fill" not in reference
    assert "update_fill" not in reference
    assert "remove_fill" not in reference


def test_d2c_grounded_fill_compiles_without_mutating_document() -> None:
    """Compile one fill from an exact grounded curve identity."""
    backend = _Backend(responses=[_fill_program()])
    document = _fill_document()
    before = document.model_dump(mode="python")

    result = _run(
        _compiler(backend).compile(
            task_index=0,
            context=_fill_context(),
            document=document,
            timeout_seconds=10,
        )
    )

    assert result.success is True
    assert result.artifact is not None
    section = result.artifact.intent_fragment.sections[0]
    assert section.section_id == "existing"
    assert section.tracks is not None
    assert len(section.tracks) == 1
    track = section.tracks[0]
    assert track.track_id == "existing-track"
    assert track.fills is not None
    assert len(track.fills) == 1
    fill = track.fills[0]
    assert fill.kind == "to_lower_limit"
    assert fill.binding_id == "existing.GR"
    assert fill.color == "#d9d9d9"
    assert fill.alpha == 0.25
    assert document.model_dump(mode="python") == before


def test_d2c_invented_binding_is_rejected_at_worker_boundary() -> None:
    """An existing-target fill cannot substitute an invented binding identity."""
    program = _fill_program(binding_id="existing.GR.404")
    backend = _Backend(responses=[program, program])

    result = _run(
        _compiler(backend).compile(
            task_index=0,
            context=_fill_context(),
            document=_fill_document(),
            timeout_seconds=10,
        )
    )

    assert result.success is False
    assert len(backend.requests) == 2
    assert any("not an existing grounded binding" in str(item) for item in result.diagnostics)


def test_d2c_cross_track_binding_is_rejected_at_worker_boundary() -> None:
    """A sibling-track binding cannot be used by a fill on the selected track."""
    program = _fill_program(binding_id="other.CALI")
    backend = _Backend(responses=[program, program])

    result = _run(
        _compiler(backend).compile(
            task_index=0,
            context=_fill_context(include_other_track=True),
            document=_fill_document(include_other_track=True),
            timeout_seconds=10,
        )
    )

    assert result.success is False
    assert len(backend.requests) == 2
    assert result.diagnostics


def test_worker_sdk_reference_uses_exact_single_candidate_without_fake_ids() -> None:
    """A single source example uses only the host-issued opaque candidate ID."""
    backend = _Backend(responses=[_program()])
    context = _context(candidate_ids=("source-1",))

    _run(
        _compiler(backend).compile(
            task_index=0,
            context=context,
            document=_document(),
            timeout_seconds=10,
        )
    )

    prompt = backend.requests[0].user_prompt
    assert "candidate-id" not in prompt
    assert "source-1" in prompt
    assert "/approved/source-1" not in prompt


def test_worker_sdk_reference_enumerates_multiple_candidates_without_paths() -> None:
    """Multiple source examples remain limited to the exact host-issued IDs."""
    backend = _Backend(responses=[_program()])
    context = _context(candidate_ids=("pilot.las", "source-2"))

    _run(
        _compiler(backend).compile(
            task_index=0,
            context=context,
            document=_document(),
            timeout_seconds=10,
        )
    )

    prompt = backend.requests[0].user_prompt
    assert "candidate-id" not in prompt
    assert "pilot.las" in prompt
    assert "source-2" in prompt
    assert "/approved/" not in prompt
    assert "source=source_1" not in prompt
    assert "source=source_2" not in prompt


def test_worker_sdk_reference_omits_source_example_without_candidates() -> None:
    """No source candidate means no executable source call or source argument."""
    backend = _Backend(responses=[_program()])
    context = _context(candidate_ids=())

    _run(
        _compiler(backend).compile(
            task_index=0,
            context=context,
            document=_document(),
            timeout_seconds=10,
        )
    )

    prompt = backend.requests[0].user_prompt
    assert "source_1 = wp.source(" not in prompt
    assert "source=source_1" not in prompt


def test_worker_repair_reuses_the_same_grounded_sdk_reference() -> None:
    """Initial and repair prompts share the same source-handle documentation."""
    backend = _Backend(
        responses=[
            _generic_binding_program(invented_channels=True),
            _generic_binding_program(invented_channels=False),
        ]
    )
    context = _context(
        channel_specs=(
            ChannelContext(mnemonic="CBL", kind="scalar", unit="mV"),
            ChannelContext(mnemonic="VDL", kind="array", shape=(128, 64)),
        )
    )

    result = _run(
        _compiler(backend).compile(
            task_index=0,
            context=context,
            document=_document(),
            timeout_seconds=10,
        )
    )

    assert result.success is True
    assert "candidate-id" not in backend.requests[0].user_prompt
    assert "candidate-id" not in backend.requests[1].user_prompt
    assert _sdk_reference(context.sections[0]) in backend.requests[1].user_prompt
    assert "pilot.las" in backend.requests[0].user_prompt
    assert "/approved/" not in backend.requests[1].user_prompt


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


def test_repair_prompt_reuses_bounded_exact_channel_facts() -> None:
    """A repair can correct invented channels from the same bounded facts as generation."""
    backend = _Backend(
        responses=[
            _generic_binding_program(invented_channels=True),
            _generic_binding_program(invented_channels=False),
        ]
    )
    context = _context(
        task=_generic_binding_task(),
        channel_specs=(
            ChannelContext(mnemonic="CBL", kind="scalar", unit="mV"),
            ChannelContext(mnemonic="VDL", kind="array", shape=(128, 64)),
        ),
    )
    result = _run(
        _compiler(backend).compile(
            task_index=0,
            context=context,
            document=_document(),
            timeout_seconds=10,
        )
    )

    assert result.success is True
    assert len(backend.requests) == 2
    reference = _sdk_reference(context.sections[0])
    initial_payload = json.loads(backend.requests[0].user_prompt.split("\n\n", 1)[1])
    assert initial_payload["sdk_reference"] == reference
    repair_prompt = backend.requests[1].user_prompt
    assert reference in repair_prompt
    assert '"mnemonic":"CBL"' in repair_prompt
    assert '"kind":"scalar"' in repair_prompt
    assert '"mnemonic":"VDL"' in repair_prompt
    assert '"kind":"array"' in repair_prompt
    assert "Multiple bindings may reference the same source channel." in repair_prompt
    assert "/approved/" not in repair_prompt
    repair_context = repair_prompt.split(
        "\n\nRelevant SDK documentation:",
        maxsplit=1,
    )[0]
    assert "CBL_0_100" not in repair_context
    assert "VDL_WAVEFORM" not in repair_context


def test_interpreter_still_rejects_unsupported_worker_keyword() -> None:
    """The kernel remains strict when a program invents a curve keyword."""
    source = (
        "report = wp.report()\n"
        "section = wp.section(report, title='Pilot')\n"
        "track = wp.track(section, kind='normal', title='GR', width_mm=30)\n"
        "wp.curve(track, channel='GR', scale_linear=0)\n"
    )
    builder = IntentBuilder(handles=HandleBuilder(builder_id="cm53r3-contract"))

    with pytest.raises(ProgramTypeError, match="scale_linear"):
        interpret_authoring_program(
            AuthoringProgram(source=ProgramSource(text=source, logical_name="invalid.wpa")),
            builder.runtime_environment(),
        )


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


def test_existing_section_revision_uses_opaque_host_target() -> None:
    """An existing revision carries the host identity without exposing it to the provider."""
    secret_id = "canonical-secret-section-17"
    backend = _Backend(responses=[_revision_program()])
    result = _run(
        _compiler(backend).compile(
            task_index=0,
            context=_context(section_id=secret_id),
            document=_document(section_id=secret_id),
            timeout_seconds=10,
        )
    )

    assert result.success is True
    assert result.artifact is not None
    section = result.artifact.intent_fragment.sections[0]
    assert section.model_dump(exclude_unset=True) == {
        "section_id": secret_id,
        "title": "Revised section",
    }
    assert secret_id not in backend.requests[0].user_prompt


def test_existing_revision_private_application_preserves_omissions_and_siblings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Private reconciliation changes only the host target and requested field."""
    secret_id = "canonical-secret-section-17"
    document = AuthoringDocumentSpec(
        name="cm-47",
        title="Current report",
        sections=[
            {
                "id": secret_id,
                "title": "Original section",
                "subtitle": "Keep this subtitle",
                "tracks": [
                    {
                        "id": "existing-track",
                        "title": "Existing track",
                        "kind": "normal",
                        "width_mm": 20,
                    }
                ],
            },
            {
                "id": "sibling",
                "title": "Sibling section",
                "tracks": [
                    {
                        "id": "sibling-track",
                        "title": "Sibling track",
                        "kind": "normal",
                        "width_mm": 18,
                    }
                ],
            },
        ],
    )
    captured: dict[str, AuthoringDocumentSpec] = {}

    def capture_private_execution(service: AuthoringService, plan: object) -> object:
        """Capture the isolated post-state while preserving normal execution."""
        result = execute_authoring_plan(service, plan)  # type: ignore[arg-type]
        captured["document"] = result.document
        return result

    monkeypatch.setattr(runtime_module, "execute_authoring_plan", capture_private_execution)
    backend = _Backend(responses=[_revision_program()])
    result = _run(
        _compiler(backend).compile(
            task_index=0,
            context=_context(section_id=secret_id),
            document=document,
            timeout_seconds=10,
        )
    )

    assert result.success is True
    private = captured["document"]
    target, sibling = private.sections
    assert target.title == "Revised section"
    assert target.subtitle == "Keep this subtitle"
    assert target.tracks[0].id == "existing-track"
    assert sibling.id == "sibling"
    assert sibling.tracks[0].id == "sibling-track"
    assert document.sections[0].title == "Original section"


def test_existing_target_id_is_not_an_executable_argument() -> None:
    """Generated code cannot provide a canonical ID to the target selector."""
    backend = _Backend(
        responses=[
            "report = wp.report()\nsection = wp.target_section(report, section_id='invented')\n",
            _revision_program(),
        ]
    )
    result = _run(
        _compiler(backend).compile(
            task_index=0,
            context=_context(section_id="canonical-secret-section-17"),
            document=_document(section_id="canonical-secret-section-17"),
            timeout_seconds=10,
        )
    )

    assert result.success is True
    assert len(backend.requests) == 2
    assert "canonical-secret-section-17" not in backend.requests[0].user_prompt
    assert "canonical-secret-section-17" not in backend.requests[1].user_prompt


def test_existing_target_requires_a_sparse_mutation() -> None:
    """Selecting the host target without changing it is not a successful revision."""
    backend = _Backend(
        responses=[
            "report = wp.report()\nsection = wp.target_section(report)\n",
            "report = wp.report()\nsection = wp.target_section(report)\n",
        ]
    )
    result = _run(
        _compiler(backend).compile(
            task_index=0,
            context=_context(section_id="existing"),
            document=_document(),
            timeout_seconds=10,
        )
    )

    assert result.success is False
    assert len(backend.requests) == 2
    assert any(diagnostic.code == "program.dry_run_error" for diagnostic in result.diagnostics)


def test_existing_target_cannot_create_a_sibling_section() -> None:
    """A revision candidate that creates another section is rejected before dry-run."""
    sibling_program = _program(section_id="sibling")
    backend = _Backend(responses=[sibling_program, sibling_program])
    result = _run(
        _compiler(backend).compile(
            task_index=0,
            context=_context(section_id="existing"),
            document=_document(),
            timeout_seconds=10,
        )
    )

    assert result.success is False
    assert len(backend.requests) == 2


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
