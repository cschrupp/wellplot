"""Canonical replacements for the retired D1-D3 program-engine tests."""

from __future__ import annotations

import asyncio
import json
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
    HeaderSlotInspectionSummary,
    ReportContext,
    ResolvedSectionContext,
    SourceContext,
)
from wellplot.agent.code_mode.planner import ReportTask, SectionTask, SemanticPlan
from wellplot.agent.code_mode.semantic_actions import ReconstructSectionAction
from wellplot.agent.code_mode.typed_section_worker import (
    CanonicalSectionWorker,
    _normalize_reconstruct_request_semantics,
)
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
        labels=("fixture.las", "fixture"),
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


def test_canonical_report_worker_receives_slot_groups_and_enforces_them() -> None:
    """Report context distinguishes service titles from general fields."""
    report_context = ReportContext(
        header_slots=(
            HeaderSlotInspectionSummary(slot_id="general.well"),
            HeaderSlotInspectionSummary(slot_id="service_title.1"),
            HeaderSlotInspectionSummary(slot_id="detail.location"),
        ),
        general_slot_ids=("general.well",),
        service_title_slot_ids=("service_title.1",),
        detail_slot_ids=("detail.location",),
    )
    backend = _StructuredFixtureBackend(
        [
            {
                "general_fields": [{"slot_id": "service_title.1", "value": "Cement Bond Log"}],
            }
        ]
    )
    rejected = asyncio.run(
        CanonicalReportWorker(backend=backend).compile(
            task=ReportTask(
                goal="Set report service titles.",
                capability_ids=("report.standard",),
                requirements=("Set the service title.",),
            ),
            report_context=report_context,
            document=_document(),
            authoritative_request="Set the service title.",
            timeout_seconds=10,
        )
    )
    assert rejected.success is False
    assert rejected.diagnostics[0].code == "semantic_context_validation_failure"

    backend = _StructuredFixtureBackend(
        [
            {
                "general_fields": [{"slot_id": "general.well", "value": "FORGE"}],
                "service_titles": [{"slot_id": "service_title.1", "value": "Cement Bond Log"}],
                "detail_fields": [{"slot_id": "detail.location", "value": "Utah"}],
            }
        ]
    )
    accepted = asyncio.run(
        CanonicalReportWorker(backend=backend).compile(
            task=ReportTask(
                goal="Set report service titles.",
                capability_ids=("report.standard",),
                requirements=("Set the service title.",),
            ),
            report_context=report_context,
            document=_document(),
            authoritative_request="Set the service title.",
            timeout_seconds=10,
        )
    )
    assert accepted.success is True
    payload = json.loads(backend.requests[0].user_prompt)
    assert payload["report_context"]["slot_groups"]["service_titles"] == [
        {"slot_id": "service_title.1", "key": "", "label": ""}
    ]


def test_canonical_report_worker_routes_unique_detail_aliases_safely() -> None:
    """Normalize model detail-key aliases without accepting unknown slots."""
    report_context = ReportContext(
        header_slots=(
            HeaderSlotInspectionSummary(slot_id="general.well", key="well", label="Well"),
            HeaderSlotInspectionSummary(slot_id="service_title.1"),
            HeaderSlotInspectionSummary(
                slot_id="detail.depth.value",
                key="driller_depth",
                label="Driller Depth",
            ),
        ),
        general_slot_ids=("general.well",),
        service_title_slot_ids=("service_title.1",),
        detail_slot_ids=("detail.depth.value",),
    )
    backend = _StructuredFixtureBackend(
        [
            {
                "general_fields": [
                    {"slot_id": "general.well", "value": "FORGE"},
                    {"slot_id": "general.driller_depth", "value": "4980.00 ft"},
                ],
                "service_titles": [{"slot_id": "service_title.1", "value": "CBL"}],
            }
        ]
    )
    result = asyncio.run(
        CanonicalReportWorker(backend=backend).compile(
            task=ReportTask(goal="Set report values.", capability_ids=("report.standard",)),
            report_context=report_context,
            document=_document(),
            authoritative_request="Set the report values.",
            timeout_seconds=10,
        )
    )
    assert result.success is True
    assert result.intent_fragment is not None
    assert result.intent_fragment.header is not None
    assert result.intent_fragment.header.detail_fields[0].slot_id == "detail.depth.value"


def test_canonical_report_worker_accepts_equivalent_detail_alias_duplicates() -> None:
    """Prefer explicit detail ownership when the model repeats the same value by alias."""
    report_context = ReportContext(
        header_slots=(
            HeaderSlotInspectionSummary(slot_id="general.logging_date", key="logging_date"),
            HeaderSlotInspectionSummary(
                slot_id="detail.date",
                key="date",
                label="Date",
            ),
        ),
        general_slot_ids=("general.logging_date",),
        detail_slot_ids=("detail.date",),
    )
    backend = _StructuredFixtureBackend(
        [
            {
                "general_fields": [
                    {"slot_id": "general.logging_date", "value": "08-May-2023"},
                    {"slot_id": "general.date", "value": "08-May-2023"},
                ],
                "detail_fields": [
                    {"slot_id": "detail.date", "value": "08-May-2023"},
                ],
            }
        ]
    )
    result = asyncio.run(
        CanonicalReportWorker(backend=backend).compile(
            task=ReportTask(goal="Set report dates.", capability_ids=("report.standard",)),
            report_context=report_context,
            document=_document(),
            authoritative_request="Set the report dates.",
            timeout_seconds=10,
        )
    )
    assert result.success is True
    assert result.intent_fragment is not None
    assert [field.slot_id for field in result.intent_fragment.header.detail_fields] == [
        "detail.date"
    ]


def test_canonical_report_worker_rejects_conflicting_detail_alias_duplicates() -> None:
    """Reject duplicate aliases when their values disagree."""
    report_context = ReportContext(
        header_slots=(
            HeaderSlotInspectionSummary(slot_id="detail.date", key="date", label="Date"),
        ),
        detail_slot_ids=("detail.date",),
    )
    backend = _StructuredFixtureBackend(
        [
            {
                "general_fields": [{"slot_id": "general.date", "value": "09-May-2023"}],
                "detail_fields": [{"slot_id": "detail.date", "value": "08-May-2023"}],
            }
        ]
    )
    result = asyncio.run(
        CanonicalReportWorker(backend=backend).compile(
            task=ReportTask(goal="Set report dates.", capability_ids=("report.standard",)),
            report_context=report_context,
            document=_document(),
            authoritative_request="Set the report dates.",
            timeout_seconds=10,
        )
    )
    assert result.success is False
    assert result.diagnostics[0].code == "semantic_context_validation_failure"


def test_canonical_report_worker_retries_unknown_slot_response() -> None:
    """Repair one bounded report response that includes unsupported slot aliases."""
    report_context = ReportContext(
        header_slots=(
            HeaderSlotInspectionSummary(slot_id="general.well", key="well", label="Well"),
            HeaderSlotInspectionSummary(
                slot_id="detail.temperature",
                key="bottom_temperature",
                label="Bottom Temperature",
            ),
        ),
        general_slot_ids=("general.well",),
        detail_slot_ids=("detail.temperature",),
    )
    backend = _StructuredFixtureBackend(
        [
            {
                "general_fields": [
                    {"slot_id": "general.well", "value": "FORGE"},
                    {"slot_id": "general.maximum_temperature", "value": "177.2 degF"},
                ]
            },
            {
                "general_fields": [{"slot_id": "general.well", "value": "FORGE"}],
                "detail_fields": [{"slot_id": "detail.temperature", "value": "177.2 degF"}],
            },
        ]
    )
    result = asyncio.run(
        CanonicalReportWorker(backend=backend).compile(
            task=ReportTask(goal="Set report values.", capability_ids=("report.standard",)),
            report_context=report_context,
            document=_document(),
            authoritative_request="Set the report values.",
            timeout_seconds=10,
        )
    )
    assert result.success is True
    assert len(backend.requests) == 2


def test_canonical_report_worker_prefers_explicit_planner_slot_values() -> None:
    """Use planner-owned report clauses instead of ambiguous model synonyms."""
    report_context = ReportContext(
        header_slots=(
            HeaderSlotInspectionSummary(slot_id="general.company", key="company", label="Company"),
            HeaderSlotInspectionSummary(slot_id="general.country", key="country", label="Country"),
            HeaderSlotInspectionSummary(
                slot_id="detail.logged_depth",
                key="logged_depth",
                label="Logged Depth",
            ),
            HeaderSlotInspectionSummary(slot_id="service_title.1"),
        ),
        general_slot_ids=("general.company", "general.country"),
        service_title_slot_ids=("service_title.1",),
        detail_slot_ids=("detail.logged_depth",),
    )
    backend = _StructuredFixtureBackend(
        [
            {
                "general_fields": [
                    {"slot_id": "general.location", "value": "wrong slot"},
                ],
                "detail_fields": [
                    {"slot_id": "detail.logged_depth", "value": "wrong value"},
                ],
            }
        ]
    )
    result = asyncio.run(
        CanonicalReportWorker(backend=backend).compile(
            task=ReportTask(
                goal="Set report metadata.",
                capability_ids=("report.standard",),
                requirements=(
                    "Company: University of Utah",
                    "State: Utah",
                    "Logged depth: TD Not Tag",
                    "Service titles: Cement Bond Log",
                ),
            ),
            report_context=report_context,
            document=_document(),
            authoritative_request="Set report metadata.",
            timeout_seconds=10,
        )
    )
    assert result.success is True
    assert result.intent_fragment is not None
    assert result.intent_fragment.header is not None
    general = {
        field.slot_id: field.value.value for field in result.intent_fragment.header.general_fields
    }
    detail = {
        field.slot_id: field.value.value for field in result.intent_fragment.header.detail_fields
    }
    assert general == {"general.company": "University of Utah", "general.country": "Utah"}
    assert detail == {"detail.logged_depth": "TD Not Tag"}


def test_canonical_report_worker_preserves_depth_for_section_track_requests() -> None:
    """A section depth-track phrase must not mutate the document depth axis."""
    report_context = ReportContext(
        header_slots=(
            HeaderSlotInspectionSummary(
                slot_id="general.company",
                key="company",
                label="Company",
            ),
        ),
        general_slot_ids=("general.company",),
    )
    backend = _StructuredFixtureBackend(
        [
            {
                "general_fields": [{"slot_id": "general.company", "value": "FORGE"}],
                "depth_scale": "normal",
            }
        ]
    )
    result = asyncio.run(
        CanonicalReportWorker(backend=backend).compile(
            task=ReportTask(
                goal="Reconstruct a section with a depth reference track.",
                capability_ids=("report.standard",),
                requirements=("Set the report metadata to: Company: FORGE; On depth: reference.",),
            ),
            report_context=report_context,
            document=_document(),
            authoritative_request=(
                "Set the report metadata to: Company: FORGE;\n"
                "For each pass, use a depth = reference track."
            ),
            timeout_seconds=10,
        )
    )
    assert result.success is True
    assert result.intent_fragment is not None
    assert result.intent_fragment.depth is None


def test_canonical_report_worker_merges_planner_metadata_with_raw_request() -> None:
    """Use normalized planner clauses when the scientist request omits colons."""
    report_context = ReportContext(
        header_slots=(
            HeaderSlotInspectionSummary(
                slot_id="general.company",
                key="company",
                label="Company",
            ),
            HeaderSlotInspectionSummary(
                slot_id="general.country",
                key="country",
                label="Country",
            ),
        ),
        general_slot_ids=("general.company", "general.country"),
    )
    backend = _StructuredFixtureBackend([{"title": "CBL", "general_fields": []}])
    result = asyncio.run(
        CanonicalReportWorker(backend=backend).compile(
            task=ReportTask(
                goal="Set report metadata.",
                capability_ids=("report.standard",),
                requirements=(
                    "Company: University of Utah",
                    "State: Utah",
                ),
            ),
            report_context=report_context,
            document=_document(),
            authoritative_request=(
                "Set the report metadata to:\n"
                "Company University of Utah; state Utah.\n"
                "For each pass, use the requested tracks."
            ),
            timeout_seconds=10,
        )
    )
    assert result.success is True
    assert result.intent_fragment is not None
    assert result.intent_fragment.header is not None
    values = {
        field.slot_id: field.value.value for field in result.intent_fragment.header.general_fields
    }
    assert values == {
        "general.company": "University of Utah",
        "general.country": "Utah",
    }


def test_section_worker_normalizes_explicit_curve_presentation() -> None:
    """Apply explicit request scale/style semantics after model generation."""
    action = ReconstructSectionAction.model_validate(
        {
            "action": "reconstruct",
            "section": {
                "title": "Main",
                "source_candidate": "source-1",
                "tracks": [
                    {
                        "semantic_id": "combo",
                        "kind": "normal",
                        "title": "Combo",
                        "bindings": [
                            {"semantic_id": "gr", "channel": "GR"},
                        ],
                    }
                ],
            },
        }
    )
    task = SectionTask(
        goal="Build the combo track.",
        capability_ids=("section.log_plot", "track.normal", "binding.curve"),
        requirements=(
            "Combo bindings: GR -> Gamma Ray, linear 5..125, #123456 dashed, width 0.65",
        ),
    )
    normalized = _normalize_reconstruct_request_semantics(
        action,
        task=task,
        authoritative_request="Build the combo track.",
    )
    binding = normalized.section.tracks[0].bindings[0]
    assert binding.scale.minimum == 5
    assert binding.scale.maximum == 125
    assert binding.style.color == "#123456"
    assert binding.style.line_style == "dashed"
    assert binding.style.line_width == 0.65


def test_canonical_section_worker_exposes_source_labels_without_paths() -> None:
    """Section workers receive bounded source names needed for grounded selection."""
    backend = _StructuredFixtureBackend(
        [
            {
                "action": "add_track",
                "track": {
                    "semantic_id": "cali-qc",
                    "kind": "normal",
                    "title": "CALI QC",
                    "bindings": [{"kind": "curve", "semantic_id": "cali", "channel": "CALI"}],
                },
            }
        ]
    )
    result = asyncio.run(
        CanonicalSectionWorker(backend=backend).compile(
            task_index=0,
            context=_context(),
            document=_document(),
            authoritative_request="Add CALI from fixture.las.",
            timeout_seconds=10,
        )
    )
    assert result.success is True
    payload = json.loads(backend.requests[0].user_prompt)
    source = payload["section_context"]["sources"][0]
    assert source["labels"] == ["fixture.las", "fixture"]
    assert "canonical_path" not in json.dumps(payload)


def test_canonical_section_worker_retries_incomplete_reconstruction() -> None:
    """Request one bounded correction when explicit reconstruction content is omitted."""
    base_context = _context()
    task = base_context.plan.section_tasks[0].model_copy(
        update={
            "requirements": (
                "Track 1: GR -> Gamma Ray.",
                "Track 2: CALI -> Caliper.",
                "Track 1 (gamma): normal, 42 mm",
                "Track 2 (cali): normal, 18 mm",
            )
        }
    )
    context = base_context.model_copy(
        update={"plan": base_context.plan.model_copy(update={"section_tasks": (task,)})}
    )
    incomplete = {
        "action": "reconstruct",
        "section": {
            "source_candidate": "source-1",
            "title": "Main",
            "tracks": [
                {
                    "semantic_id": "gr",
                    "kind": "normal",
                    "title": "Gamma Ray",
                    "bindings": [{"semantic_id": "gr", "channel": "GR"}],
                }
            ],
        },
    }
    complete = {
        "action": "reconstruct",
        "section": {
            "source_candidate": "source-1",
            "title": "Main",
            "tracks": [
                {
                    "semantic_id": "gr",
                    "kind": "normal",
                    "title": "Gamma Ray",
                    "bindings": [{"semantic_id": "gr", "channel": "GR"}],
                },
                {
                    "semantic_id": "cali",
                    "kind": "normal",
                    "title": "Caliper",
                    "bindings": [{"semantic_id": "cali", "channel": "CALI"}],
                },
            ],
        },
    }
    backend = _StructuredFixtureBackend([incomplete, complete])
    result = asyncio.run(
        CanonicalSectionWorker(backend=backend).compile(
            task_index=0,
            context=context,
            document=_document(),
            authoritative_request="Build both requested tracks.",
            timeout_seconds=10,
        )
    )
    assert result.success is True
    assert len(backend.requests) == 2
    assert result.intent_fragment is not None
    assert [track.width_mm for track in result.intent_fragment.sections[0].tracks] == [42, 18]


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
