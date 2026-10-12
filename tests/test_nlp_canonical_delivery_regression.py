"""Canonical replacements for the retired D1-D3 program-engine tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from scripts.verify_cbl_packet import verify_cbl_packet
from tests._mcp_fixtures import REPO_ROOT
from tests.test_nlp_d4_live_acceptance import _build_rehearsal_cbl_artifact

from wellplot.agent.code_mode.canonical_workers import (
    CanonicalReportWorker,
)
from wellplot.agent.code_mode.enrichment import (
    ChannelContext,
    EnrichedSemanticContext,
    ExistingCurveContext,
    ReportContext,
    ResolvedSectionContext,
    SourceContext,
)
from wellplot.agent.code_mode.planner import ReportTask, SectionTask, SemanticPlan
from wellplot.agent.code_mode.typed_section_worker import CanonicalSectionWorker
from wellplot.agent.providers.base import (
    ProviderMetrics,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from wellplot.model.authoring import (
    AuthoringDataSource,
    AuthoringDocumentSpec,
    AuthoringScale,
    AuthoringSectionSpec,
    CurveBindingSpec,
    NormalTrackSpec,
)


@dataclass
class _StructuredFixtureBackend:
    """Return predeclared canonical response mappings without a provider."""

    responses: list[dict[str, object]]
    requests: list[StructuredGenerationRequest] = field(default_factory=list)

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[object],
    ) -> StructuredGenerationResult[object]:
        """Validate one response through the production Pydantic boundary."""
        self.requests.append(request)
        value = response_model.model_validate(self.responses.pop(0))
        return StructuredGenerationResult(value=value, metrics=ProviderMetrics())


def _document() -> AuthoringDocumentSpec:
    """Build a minimal canonical document with one grounded GR curve."""
    return AuthoringDocumentSpec(
        name="canonical-delivery-regression",
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


def _context() -> EnrichedSemanticContext:
    """Build inspected source and existing-curve context for section actions."""
    source = SourceContext(
        candidate_id="source-1",
        canonical_path="/workspace/fixture.las",
        source_format="las",
        channels=(
            ChannelContext(mnemonic="GR", kind="scalar", unit="gAPI"),
            ChannelContext(mnemonic="CALI", kind="scalar", unit="in"),
        ),
    )
    resolved = ResolvedSectionContext(
        task_index=0,
        section_id="main",
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
        ),
    )
    task = SectionTask(
        goal="Apply one canonical section action.",
        capability_ids=("section.log_plot", "track.normal", "binding.curve"),
        existing_section_hint="Main Log",
        requirements=("Apply the requested semantic change.",),
    )
    return EnrichedSemanticContext(
        plan=SemanticPlan(summary="canonical regression", section_tasks=(task,)),
        sections=(resolved,),
        report=ReportContext(),
    )


def _run_section(response: dict[str, object]) -> object:
    """Compile one response through the canonical section worker."""
    backend = _StructuredFixtureBackend([response])
    return asyncio.run(
        CanonicalSectionWorker(backend=backend).compile(
            task_index=0,
            context=_context(),
            document=_document(),
            authoritative_request="Apply the requested semantic change.",
            timeout_seconds=10,
        )
    )


def test_canonical_report_worker_owns_report_title_only() -> None:
    """D2A report semantics lower through the sparse canonical response."""
    backend = _StructuredFixtureBackend([{"title": "Gamma Ray Quality Control Review"}])
    result = asyncio.run(
        CanonicalReportWorker(backend=backend).compile(
            task=ReportTask(
                goal="Change the report title.",
                capability_ids=("report.standard",),
                requirements=("Change the report title.",),
            ),
            report_context=ReportContext(),
            document=_document(),
            authoritative_request="Change the report title.",
            timeout_seconds=10,
        )
    )
    assert result.success is True
    assert result.intent_fragment is not None
    assert result.intent_fragment.title == "Gamma Ray Quality Control Review"
    assert len(backend.requests) == 1


def test_canonical_section_worker_updates_existing_scale() -> None:
    """D1 existing-curve scale changes use a request-local handle."""
    result = _run_section(
        {
            "action": "update_curve_scale",
            "target": {"handle": "curve-1"},
            "scale": {"kind": "linear", "minimum": 10, "maximum": 100},
        }
    )
    assert result.success is True
    assert result.intent_fragment is not None
    binding = result.intent_fragment.curve_bindings[0]
    assert binding.binding_id == "main.gr.GR"
    assert binding.scale.minimum == 10


def test_canonical_section_worker_creates_grounded_track_and_curve() -> None:
    """D2B creation resolves the CALI channel from inspected source context."""
    result = _run_section(
        {
            "action": "add_track",
            "track": {
                "semantic_id": "caliper-qc",
                "kind": "normal",
                "title": "Caliper QC",
                "width_mm": 28,
                "bindings": [
                    {
                        "kind": "curve",
                        "semantic_id": "cali",
                        "channel": "CALI",
                        "label": "Caliper QC",
                        "scale": {"kind": "linear", "minimum": 6, "maximum": 12},
                    }
                ],
            },
        }
    )
    assert result.success is True
    assert result.intent_fragment is not None
    track = result.intent_fragment.sections[0].tracks[0]
    assert track.title == "Caliper QC"
    assert track.bindings[0].channel == "CALI"


def test_canonical_section_worker_creates_grounded_fill() -> None:
    """D2C fill creation preserves the grounded parent binding identity."""
    result = _run_section(
        {
            "action": "add_fill",
            "target": {"handle": "curve-1"},
            "fill": {
                "kind": "to_lower_limit",
                "semantic_id": "gr-fill",
                "target_binding": "GR",
                "color": "#f2e8a0",
                "alpha": 0.2,
            },
        }
    )
    assert result.success is True
    assert result.intent_fragment is not None
    fill = result.intent_fragment.fills[0]
    assert fill.binding_id == "main.gr.GR"
    assert fill.kind == "to_lower_limit"


def test_canonical_section_worker_rejects_unavailable_channel_without_intent() -> None:
    """D2D/D2E missing-channel semantics fail closed before reconciliation."""
    result = _run_section(
        {
            "action": "add_track",
            "track": {
                "semantic_id": "nphi-qc",
                "kind": "normal",
                "title": "NPHI QC",
                "bindings": [{"kind": "curve", "semantic_id": "nphi", "channel": "NPHI"}],
            },
        }
    )
    assert result.success is False
    assert result.intent_fragment is None
    assert result.diagnostics[0].code == "channel_missing"


def test_canonical_cbl_verifier_accepts_generated_artifact() -> None:
    """D3 CBL grading remains provider-free and uses the generated artifact."""
    from tempfile import TemporaryDirectory

    with TemporaryDirectory(dir=REPO_ROOT) as temporary:
        artifact = _build_rehearsal_cbl_artifact(Path(temporary))
        result = verify_cbl_packet(
            artifact,
            execution_evidence={"persisted": True, "rendered": True},
        )
    assert result["acceptance_status"] == "PASS"
    assert all(item["status"] == "PASS" for item in result["requirements"])
