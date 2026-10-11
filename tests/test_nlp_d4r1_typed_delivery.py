"""Provider-free D4R1 tests for the typed semantic delivery workers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from pydantic import ValidationError
from tests._mcp_fixtures import REPO_ROOT, create_mcp_fixture_paths

from wellplot.agent import direct_notebook
from wellplot.agent.code_mode.enrichment import (
    ChannelContext,
    EnrichedSemanticContext,
    ExistingCurveContext,
    ReportContext,
    ResolvedSectionContext,
    SemanticEnricher,
    SourceCandidate,
    SourceContext,
)
from wellplot.agent.code_mode.facade import CodeModeCompileFacade
from wellplot.agent.code_mode.planner import ReportTask, SectionTask, SemanticPlan
from wellplot.agent.code_mode.source_loader import LogfileSourceLoader
from wellplot.agent.code_mode.typed_delivery import (
    DeliveryCurve,
    DeliveryFill,
    DeliveryRaster,
    DeliveryReportResponse,
    DeliveryScale,
    DeliverySection,
    DeliverySectionResponse,
    DeliverySlotValue,
    DeliveryTarget,
    DeliveryTrack,
    TypedDeliveryReportCompiler,
    TypedDeliverySectionCompiler,
)
from wellplot.agent.code_mode.workflow import CodeModeGraphDependencies
from wellplot.agent.providers.base import (
    ProgramGenerationRequest,
    ProviderMetrics,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from wellplot.api.serialize import report_to_dict
from wellplot.authoring_program.inspection import HeaderSlotInspectionSummary
from wellplot.authoring_service import AuthoringService
from wellplot.capabilities import create_builtin_registry
from wellplot.logfile import load_logfile
from wellplot.model.authoring import (
    AuthoringDataSource,
    AuthoringDocumentSpec,
    AuthoringScale,
    AuthoringSectionSpec,
    CurveBindingSpec,
    NormalTrackSpec,
)


@dataclass
class _TypedBackend:
    """Return predeclared structured responses and reject program generation."""

    responses: list[object]
    structured_requests: list[StructuredGenerationRequest] = field(default_factory=list)
    program_calls: int = 0

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[object],
    ) -> StructuredGenerationResult[object]:
        """Return one response without making any external call."""
        self.structured_requests.append(request)
        value = response_model.model_validate(self.responses.pop(0))
        return StructuredGenerationResult(value=value, metrics=ProviderMetrics())

    async def generate_program(self, request: ProgramGenerationRequest) -> object:
        """Prove the typed delivery route never falls back to source generation."""
        del request
        self.program_calls += 1
        raise AssertionError("D4R1 typed workers must not call generate_program")


def _document() -> AuthoringDocumentSpec:
    """Build a small canonical document with one grounded GR curve."""
    return AuthoringDocumentSpec(
        name="D4R1 fixture",
        sections=[
            AuthoringSectionSpec(
                id="main",
                title="Main Log",
                data_source=AuthoringDataSource(source_path="fixture.las", source_format="las"),
                tracks=[
                    NormalTrackSpec(
                        id="gr",
                        title="Gamma Ray",
                        width_mm=25,
                        bindings=[
                            CurveBindingSpec(
                                binding_id="main.gr.GR",
                                channel="GR",
                                label="GR",
                                scale=AuthoringScale(kind="linear", minimum=0, maximum=150),
                            )
                        ],
                    )
                ],
            )
        ],
    )


def _context(*, section_id: str | None = "main") -> EnrichedSemanticContext:
    """Build host-inspected source and existing-curve context."""
    channels = (
        ChannelContext(mnemonic="GR", kind="scalar", unit="gAPI"),
        ChannelContext(mnemonic="CALI", kind="scalar", unit="in"),
        ChannelContext(mnemonic="RT", kind="scalar", unit="ohm.m"),
        ChannelContext(mnemonic="DEPTH", kind="scalar", unit="ft"),
        ChannelContext(mnemonic="VDL", kind="array", unit="us"),
    )
    source = SourceContext(
        candidate_id="source-1",
        canonical_path="/authorized/fixture.las",
        source_format="las",
        channels=channels,
    )
    resolved = ResolvedSectionContext(
        task_index=0,
        section_id=section_id,
        sources=(source,),
        existing_curves=(
            ExistingCurveContext(
                track_id="gr",
                track_title="Gamma Ray",
                track_kind="normal",
                binding_id="main.gr.GR",
                channel="GR",
                label="GR",
                scale_kind="linear",
                scale_minimum=0,
                scale_maximum=150,
                reverse=False,
            ),
        )
        if section_id is not None
        else (),
    )
    task = SectionTask(
        goal="Apply one bounded typed section operation.",
        capability_ids=("section.log_plot", "binding.curve"),
        existing_section_hint="Main Log" if section_id is not None else None,
    )
    return EnrichedSemanticContext(
        plan=SemanticPlan(summary="D4R1 test plan", section_tasks=(task,)),
        sections=(resolved,),
        report=ReportContext(),
    )


def test_typed_delivery_contract_rejects_program_fields_and_invalid_children() -> None:
    """The provider-facing DTOs are strict and reject unsafe representations."""
    with pytest.raises(ValidationError):
        DeliverySectionResponse.model_validate({"mode": "reconstruct", "program": "wp.track(...)"})
    with pytest.raises(ValidationError):
        DeliveryTrack(
            semantic_id="array",
            kind="array",
            title="Waveform",
            curves=(DeliveryCurve(semantic_id="curve", channel="GR"),),
        )
    with pytest.raises(ValidationError):
        DeliveryTarget()


def test_typed_report_worker_uses_one_structured_call() -> None:
    """Report semantics compile from a typed response without program metrics."""
    backend = _TypedBackend(
        responses=[
            DeliveryReportResponse(
                title="Typed report title",
                general_fields=(DeliverySlotValue(slot_id="general.well", value="Well-01"),),
            )
        ]
    )
    result = asyncio.run(
        TypedDeliveryReportCompiler(backend=backend).compile(
            task=ReportTask(goal="Set the report title."),
            report_context=ReportContext(
                header_slots=(HeaderSlotInspectionSummary(slot_id="general.well", key="well"),)
            ),
            document=_document(),
            timeout_seconds=10,
        )
    )

    assert result.success is True
    assert result.intent_fragment is not None
    assert result.intent_fragment.title == "Typed report title"
    assert result.intent_fragment.header is not None
    assert len(backend.structured_requests) == 1
    assert backend.program_calls == 0
    assert result.metrics.program_calls == 0


@pytest.mark.parametrize(
    ("response", "expected_field"),
    [
        (
            DeliverySectionResponse(
                mode="update_curve_scale",
                target=DeliveryTarget(handle="curve-1"),
                scale=DeliveryScale(minimum=2, maximum=20),
            ),
            "curve_bindings",
        ),
        (
            DeliverySectionResponse(
                mode="add_track_curve",
                track=DeliveryTrack(
                    semantic_id="qc",
                    kind="normal",
                    title="Caliper QC",
                    curves=(
                        DeliveryCurve(
                            semantic_id="cali",
                            channel="CALI",
                            label="Caliper QC",
                            scale=DeliveryScale(minimum=6, maximum=12),
                        ),
                    ),
                ),
            ),
            "sections",
        ),
        (
            DeliverySectionResponse(
                mode="add_fill",
                target=DeliveryTarget(handle="curve-1"),
                fill=DeliveryFill(
                    semantic_id="lower",
                    target_binding="GR",
                    kind="to_lower_limit",
                    color="#d9d9d9",
                    alpha=0.25,
                ),
            ),
            "fills",
        ),
    ],
)
def test_typed_section_revisions_are_host_grounded(
    response: DeliverySectionResponse,
    expected_field: str,
) -> None:
    """Scale, track/curve, and fill revisions use only inspected identities."""
    backend = _TypedBackend(responses=[response])
    result = asyncio.run(
        TypedDeliverySectionCompiler(backend=backend).compile(
            task_index=0,
            context=_context(),
            document=_document(),
            timeout_seconds=10,
        )
    )

    assert result.success is True
    assert result.intent_fragment is not None
    assert expected_field in result.intent_fragment.model_fields_set
    assert len(backend.structured_requests) == 1
    assert backend.program_calls == 0
    assert result.metrics.program_calls == 0


def test_typed_reconstruction_preserves_track_kinds() -> None:
    """Reconstruction supports normal, reference, and array semantics."""
    response = DeliverySectionResponse(
        mode="reconstruct",
        section=DeliverySection(
            title="Reconstructed Log",
            source_candidate="source-1",
            tracks=(
                DeliveryTrack(
                    semantic_id="depth",
                    kind="reference",
                    title="Depth",
                    curves=(DeliveryCurve(semantic_id="depth", channel="DEPTH"),),
                ),
                DeliveryTrack(
                    semantic_id="gr",
                    kind="normal",
                    title="Gamma Ray",
                    curves=(DeliveryCurve(semantic_id="gr", channel="GR"),),
                ),
                DeliveryTrack(
                    semantic_id="vdl",
                    kind="array",
                    title="Variable Density",
                    rasters=(DeliveryRaster(semantic_id="vdl", channel="VDL"),),
                ),
            ),
        ),
    )
    backend = _TypedBackend(responses=[response])
    result = asyncio.run(
        TypedDeliverySectionCompiler(backend=backend).compile(
            task_index=0,
            context=_context(section_id=None),
            document=_document(),
            timeout_seconds=10,
        )
    )

    assert result.success is True
    assert result.intent_fragment is not None
    assert len(result.intent_fragment.sections[0].tracks) == 3
    assert backend.program_calls == 0


def test_typed_reconstruction_missing_channel_fails_closed() -> None:
    """A reconstruction response cannot invent an uninspected source channel."""
    response = DeliverySectionResponse(
        mode="reconstruct",
        section=DeliverySection(
            title="Reconstructed Log",
            source_candidate="source-1",
            tracks=(
                DeliveryTrack(
                    semantic_id="missing",
                    kind="normal",
                    title="Missing",
                    curves=(DeliveryCurve(semantic_id="nphi", channel="NPHI"),),
                ),
            ),
        ),
    )
    backend = _TypedBackend(responses=[response])
    result = asyncio.run(
        TypedDeliverySectionCompiler(backend=backend).compile(
            task_index=0,
            context=_context(section_id=None),
            document=_document(),
            timeout_seconds=10,
        )
    )

    assert result.success is False
    assert result.intent_fragment is None
    assert result.diagnostics[0].code == "typed.section_validation_error"
    assert backend.program_calls == 0


@dataclass
class _GraphPlanner:
    """Return one section task so the real compile graph dispatches typed work."""

    registry: object = field(default_factory=create_builtin_registry)

    async def plan(self, **_kwargs: object) -> SemanticPlan:
        """Return the bounded source-grounded revision task."""
        return SemanticPlan(
            summary="D4R1 typed graph revision",
            section_tasks=(
                SectionTask(
                    goal="Add the inspected CALI curve on a new QC track.",
                    capability_ids=(
                        "section.log_plot",
                        "track.normal",
                        "binding.curve",
                    ),
                    existing_section_hint="Main Log",
                    source_hints=("fixture.las",),
                ),
            ),
        )


def test_compile_graph_default_delivery_shape_has_zero_program_metrics() -> None:
    """The supported graph route dispatches one typed worker and no program worker."""
    with TemporaryDirectory(dir=REPO_ROOT) as temporary_directory:
        fixture = create_mcp_fixture_paths(Path(temporary_directory))
        spec = load_logfile(fixture.single_logfile, allowed_root=REPO_ROOT)
        document = AuthoringService.from_mapping(report_to_dict(spec)).document
        backend = _TypedBackend(
            responses=[
                DeliverySectionResponse(
                    mode="add_track_curve",
                    track=DeliveryTrack(
                        semantic_id="qc",
                        kind="normal",
                        title="Caliper QC",
                        width_mm=28,
                        curves=(
                            DeliveryCurve(
                                semantic_id="cali",
                                channel="CALI",
                                label="Caliper QC",
                                scale=DeliveryScale(minimum=6, maximum=12),
                            ),
                        ),
                    ),
                )
            ]
        )
        dependencies = CodeModeGraphDependencies(
            planner=_GraphPlanner(),
            enricher=SemanticEnricher(
                loader=LogfileSourceLoader(),
                allowed_roots={"server": REPO_ROOT},
            ),
            report_compiler=TypedDeliveryReportCompiler(backend=backend),
            section_compiler=TypedDeliverySectionCompiler(backend=backend),
        )
        facade = CodeModeCompileFacade(dependencies)
        result = asyncio.run(
            facade.compile(
                request="Add an inspected CALI curve.",
                mode="revise",
                document=document,
                source_candidates=(
                    SourceCandidate(
                        candidate_id="source-1",
                        root_id="server",
                        path=str(fixture.las_path),
                        labels=("fixture.las", "fixture", "las"),
                        trusted_format="las",
                    ),
                ),
                timeout_seconds=10,
            )
        )

    assert result.success is True
    assert result.metrics.total_calls == 0
    assert result.metrics.total_repairs == 0
    assert [(worker.kind, worker.success) for worker in result.workers] == [("section", True)]
    assert len(backend.structured_requests) == 1
    assert backend.program_calls == 0


def test_direct_notebook_default_session_uses_typed_compilers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public notebook composition selects typed workers by default."""
    backend = _TypedBackend(responses=[])

    def fake_provider_backend(**_kwargs: object) -> tuple[object, str]:
        return backend, "deterministic"

    monkeypatch.setattr(direct_notebook, "_provider_backend", fake_provider_backend)
    session, credential_source = direct_notebook._build_agent_session(
        provider="deterministic",
        model="d4r1-fixture-model",
        root=REPO_ROOT,
        api_key=None,
        base_url=None,
        timeout=10,
    )

    assert credential_source == "deterministic"
    dependencies = session.compiler.dependencies
    assert isinstance(dependencies.report_compiler, TypedDeliveryReportCompiler)
    assert isinstance(dependencies.section_compiler, TypedDeliverySectionCompiler)
