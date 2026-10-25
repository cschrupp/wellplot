"""Canonical replacements for the retired D1-D3 program-engine tests."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from scripts import nlp_d4_live_acceptance as d4
from scripts.verify_cbl_packet import _check_remarks, verify_cbl_packet
from tests._mcp_fixtures import REPO_ROOT
from tests.test_nlp_d4_live_acceptance import _build_rehearsal_cbl_artifact

from wellplot.agent.code_mode import typed_section_worker as section_worker
from wellplot.agent.code_mode.canonical_workers import (
    CanonicalReportWorker,
    ReportSemanticResponse,
    _normalize_report_slot_groups,
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
from wellplot.agent.code_mode.semantic_actions import (
    ReconstructSectionAction,
    SemanticActionError,
)
from wellplot.agent.code_mode.typed_section_worker import (
    CanonicalSectionWorker,
    _normalize_reconstruct_request_semantics,
    _normalize_reconstruct_track_dimensions,
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
    assert "empty header-slot inventory does not prevent" in backend.requests[0].user_prompt
    assert len(backend.requests) == 1


def test_cbl_remark_verifier_accepts_semantic_paraphrases() -> None:
    """The mutable verifier checks the frozen meaning without exact prose."""
    payload = {
        "remarks": [
            {
                "title": "Scope Boundary",
                "text": "Reconstruct the supported heading, passes, remarks, and tail.",
            },
            {
                "title": "Input Provenance",
                "text": "Use the staged DLIS source files for both passes.",
            },
            {
                "title": "Public Reproduction Boundary",
                "text": "Keep the WellPlot boundary clear and do not copy vendor disclaimers.",
            },
        ]
    }
    errors: list[str] = []

    _check_remarks(payload, errors)

    assert errors == []


def test_cbl_remark_verifier_rejects_unrelated_remarks() -> None:
    """An unrelated successful-looking remark set cannot satisfy CBL-02."""
    errors: list[str] = []

    _check_remarks({"remarks": [{"title": "Notes", "text": "A routine summary."}]}, errors)

    assert len(errors) == 3


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


def test_canonical_report_worker_uses_generic_labeled_report_requirements() -> None:
    """Paraphrased report instructions preserve a renamed remark verbatim."""
    report_context = ReportContext(
        header_slots=(
            HeaderSlotInspectionSummary(
                slot_id="general.company",
                key="company",
                label="Company",
            ),
            HeaderSlotInspectionSummary(slot_id="service_title.1"),
        ),
        general_slot_ids=("general.company",),
        service_title_slot_ids=("service_title.1",),
    )
    backend = _StructuredFixtureBackend([{"title": "Provider Draft"}])
    result = asyncio.run(
        CanonicalReportWorker(backend=backend).compile(
            task=ReportTask(
                goal="Capture labeled report details.",
                capability_ids=("report.standard",),
                requirements=(
                    "Company: North Star Labs",
                    "Service titles: Cement Review",
                    "Remark 1: Scope Boundary — Preserve this exact sentence, "
                    "including punctuation.",
                ),
            ),
            report_context=report_context,
            document=_document(),
            authoritative_request=(
                "Please record the labeled details below.\n"
                "Company: North Star Labs\n"
                "Service titles: Cement Review\n"
                "Remark 1: Scope Boundary — Preserve this exact sentence, including punctuation."
            ),
            timeout_seconds=10,
        )
    )
    assert result.success is True
    assert result.intent_fragment is not None
    assert result.intent_fragment.header is not None
    assert result.intent_fragment.remarks is not None
    assert result.intent_fragment.remarks[0].title == "Scope Boundary"
    assert result.intent_fragment.remarks[0].text == (
        "Preserve this exact sentence, including punctuation."
    )


def test_cbl_captured_report_prose_is_normalized_from_authoritative_request() -> None:
    """Captured CBL report output is corrected by request-owned prose semantics."""
    request = next(
        case["request"] for case in d4.load_cases(REPO_ROOT) if case["turn_id"] == "D4-C01:C01"
    )
    captured = json.loads(
        (REPO_ROOT / "tests/fixtures/d5_5j_qwen_smoke_003_report_sections.json").read_text()
    )
    response = ReportSemanticResponse.model_validate(captured["report"])
    general = (
        ("company", "Company"),
        ("well", "Well"),
        ("field", "Field"),
        ("county", "County"),
        ("country", "Country"),
        ("section", "Section"),
        ("township", "Township"),
        ("range", "Range"),
        ("footage", "Footage"),
        ("latitude", "Latitude"),
        ("longitude", "Longitude"),
        ("logging_date", "Logging Date"),
        ("elevation_kb", "KB"),
        ("elevation_gl", "GL"),
        ("elevation_df", "DF"),
        ("measured_from", "Measured From"),
        ("top_log_interval", "Top Log Interval"),
        ("bottom_log_interval", "Bottom Log Interval"),
        ("fluid_type", "Fluid Type"),
    )
    details = (
        ("detail.row_2.column_1.cell_1", "run_number", "Run"),
        ("detail.row_4.column_1.cell_1", "driller_depth", "Driller Depth"),
        ("detail.row_5.column_1.cell_1", "logged_depth", "Logged Depth"),
        ("detail.row_12.value_1", "fluid_density", "Fluid Density"),
        ("detail.row_19.column_1.cell_1", "bottom_temperature", "Bottom Temperature"),
        ("detail.row_23.value_1", "logged_by", "Logged By"),
        ("detail.row_24.value_1", "witnessed_by", "Witnessed By"),
    )
    header_slots = (
        tuple(
            HeaderSlotInspectionSummary(slot_id=f"general.{key}", key=key, label=label)
            for key, label in general
        )
        + tuple(
            HeaderSlotInspectionSummary(slot_id=slot_id, key=key, label=label)
            for slot_id, key, label in details
        )
        + tuple(
            HeaderSlotInspectionSummary(slot_id=f"service_title.{index}") for index in (1, 2, 3)
        )
    )
    context = ReportContext(
        header_slots=header_slots,
        general_slot_ids=tuple(f"general.{key}" for key, _ in general),
        service_title_slot_ids=("service_title.1", "service_title.2", "service_title.3"),
        detail_slot_ids=tuple(slot_id for slot_id, _, _ in details),
    )

    normalized = _normalize_report_slot_groups(
        response,
        context,
        authoritative_request=request,
    )

    values = {field.slot_id: field.value for field in normalized.general_fields}
    assert values["general.company"] == "University of Utah"
    assert values["general.country"] == "Utah"
    assert values["general.measured_from"] == "Kelly Bushing"
    assert len(normalized.detail_fields) == 7
    assert [item.value for item in normalized.service_titles] == [
        "Cement Bond Log",
        "Variable Density Log",
        "Gamma Ray - CCL",
    ]
    assert [item.title for item in normalized.remarks] == [
        "Supported Reconstruction Scope",
        "Data Sources",
        "Public Data and IP Notice",
    ]
    assert normalized.page_size is None
    assert normalized.page_orientation is None
    assert normalized.tail_enabled is True


def test_cbl_captured_section_output_is_normalized_from_authoritative_request() -> None:
    """Captured Qwen section output uses request-owned presentation semantics."""
    request = next(
        case["request"] for case in d4.load_cases(REPO_ROOT) if case["turn_id"] == "D4-C01:C01"
    )
    captured = json.loads(
        (REPO_ROOT / "tests/fixtures/d5_5j_qwen_smoke_003_report_sections.json").read_text()
    )
    for section_payload, section_hint in zip(
        captured["sections"], ("Main Pass", "Repeat Pass"), strict=True
    ):
        action = ReconstructSectionAction.model_validate(section_payload)
        task = SectionTask(
            goal=f"Configure the captured CBL {section_hint.lower()}.",
            capability_ids=(
                "section.log_plot",
                "track.normal",
                "track.reference",
                "track.array",
                "binding.curve",
                "binding.raster",
            ),
            existing_section_hint=section_hint,
            requirements=(),
        )
        normalized = _normalize_reconstruct_track_dimensions(
            action,
            task,
            authoritative_request=request,
        )
        normalized = _normalize_reconstruct_request_semantics(
            normalized,
            task=task,
            authoritative_request=request,
        )
        tracks = normalized.section.tracks
        assert [track.width_mm for track in tracks] == [50.0, 10.0, 44.0, 48.0]
        assert tracks[0].bindings[0].label == "Gamma Ray (ECGR_STGC) QTGC-B"
        assert tracks[3].bindings[0].label == "VDL VariableDensity (VDL) QSLT-B"
        assert tracks[3].bindings[0].profile == "vdl"
        assert tracks[3].bindings[0].colorbar_position == "header"
        assert tracks[3].bindings[0].sample_axis.source_origin == 40
        assert tracks[3].bindings[0].sample_axis.source_step == 10
        assert tracks[3].grid.vertical_main_visible is False
        assert tracks[3].grid.vertical_secondary_visible is False


def test_shared_cbl_label_is_restored_when_generated_labels_are_missing() -> None:
    """Shared request labels apply independently of ordinal scale matching."""
    action = ReconstructSectionAction.model_validate(
        {
            "action": "reconstruct",
            "section": {
                "title": "Main Pass",
                "source_candidate": "source-1",
                "tracks": [
                    {
                        "semantic_id": "cbl",
                        "kind": "normal",
                        "title": "CBL",
                        "bindings": [
                            {
                                "semantic_id": "cbl-full",
                                "channel": "CBL",
                                "scale": {"minimum": 0, "maximum": 100},
                            },
                            {
                                "semantic_id": "cbl-zoom",
                                "channel": "CBL",
                                "scale": {"minimum": 0, "maximum": 10},
                            },
                        ],
                    }
                ],
            },
        }
    )
    normalized = section_worker._normalize_track_request_semantics(
        action.section.tracks[0],
        'Both labels are "CBL Amplitude (CBL) QSLT-B". '
        "The first is linear 0..100, #111111, width 0.75. "
        "The second is linear 0..10, #2563eb dashed, width 0.65.",
    )
    assert [binding.label for binding in normalized.bindings] == [
        "CBL Amplitude (CBL) QSLT-B",
        "CBL Amplitude (CBL) QSLT-B",
    ]
    first, second = normalized.bindings
    assert (first.scale.minimum, first.scale.maximum) == (0, 100)
    assert (second.scale.minimum, second.scale.maximum) == (0, 10)
    assert first.style.color == "#111111"
    assert first.style.line_style == "solid"
    assert first.style.line_width == 0.75
    assert second.style.color == "#2563eb"
    assert second.style.line_style == "dashed"
    assert second.style.line_width == 0.65


def test_report_page_request_is_preserved_when_explicit() -> None:
    """An explicit page request remains model-owned after host normalization."""
    response = ReportSemanticResponse.model_validate(
        {"page_size": "letter", "page_orientation": "landscape"}
    )
    normalized = _normalize_report_slot_groups(
        response,
        ReportContext(),
        authoritative_request="Use letter page size in landscape orientation.",
    )
    assert normalized.page_size == "letter"
    assert normalized.page_orientation == "landscape"


def test_section_normalization_matches_reordered_tracks_by_identity() -> None:
    """Reordered model tracks receive dimensions and styles by identity, not position."""
    action = ReconstructSectionAction.model_validate(
        {
            "action": "reconstruct",
            "section": {
                "title": "Main",
                "source_candidate": "source-1",
                "tracks": [
                    {
                        "semantic_id": "model-depth",
                        "kind": "reference",
                        "title": "Depth",
                        "bindings": [{"semantic_id": "cali", "channel": "CALI"}],
                    },
                    {
                        "semantic_id": "model-combo",
                        "kind": "normal",
                        "title": "Combo",
                        "bindings": [{"semantic_id": "gr", "channel": "GR"}],
                    },
                ],
            },
        }
    )
    task = SectionTask(
        goal="Build the requested tracks.",
        capability_ids=("section.log_plot", "track.normal", "track.reference"),
        existing_section_hint=None,
        requirements=(
            "Track 1 (combo): normal, 42 mm",
            "Track 2 (depth): reference, 12 mm",
            "Track 1: GR -> Gamma Ray.",
            "Track 2: CALI -> Caliper.",
            "Combo bindings: GR -> Gamma Ray, linear 5..125, #123456 dashed, width 0.65",
            "Depth bindings: CALI -> Caliper, linear 1..10, #abcdef dotted, width 0.40",
        ),
    )
    normalized = _normalize_reconstruct_track_dimensions(action, task)
    normalized = _normalize_reconstruct_request_semantics(
        normalized,
        task=task,
        authoritative_request="Build the requested tracks.",
    )
    depth, combo = normalized.section.tracks
    assert (depth.semantic_id, depth.width_mm, depth.kind) == ("depth", 12, "reference")
    assert (combo.semantic_id, combo.width_mm, combo.kind) == ("combo", 42, "normal")
    assert combo.bindings[0].scale is not None
    assert combo.bindings[0].scale.minimum == 5
    assert combo.bindings[0].style is not None
    assert combo.bindings[0].style.color == "#123456"
    assert depth.bindings[0].style is not None
    assert depth.bindings[0].style.color == "#abcdef"


def test_cbl_dimension_forms_and_task_title_are_normalized_by_host() -> None:
    """Frozen CBL request wins over the captured planner's anonymous dimensions."""
    cbl_request = next(
        case["request"] for case in d4.load_cases(REPO_ROOT) if case["turn_id"] == "D4-C01:C01"
    )
    action = ReconstructSectionAction.model_validate(
        {
            "action": "reconstruct",
            "section": {
                "title": "CBL/VDL Report",
                "source_candidate": "source-1",
                "tracks": [
                    {
                        "semantic_id": "vdl_main",
                        "kind": "array",
                        "title": "VDL",
                        "x_scale": {"minimum": 0, "maximum": 1},
                        "bindings": [{"semantic_id": "vdl", "channel": "VDL"}],
                    },
                    {
                        "semantic_id": "combo_main",
                        "kind": "normal",
                        "title": "Combo",
                        "bindings": [{"semantic_id": "ecgr", "channel": "ECGR_STGC"}],
                    },
                    {
                        "semantic_id": "cbl_main",
                        "kind": "normal",
                        "title": "CBL",
                        "bindings": [{"semantic_id": "cbl", "channel": "CBL"}],
                    },
                    {
                        "semantic_id": "depth_main",
                        "kind": "reference",
                        "title": "Depth",
                        "bindings": [{"semantic_id": "stit", "channel": "STIT"}],
                    },
                ],
            },
        }
    )
    # This is the sanitized Main Pass task captured from the failed Qwen CBL
    # smoke.  Keep the anonymous track wording and all captured task metadata;
    # the authoritative frozen request remains the source of dimensions.
    task = SectionTask.model_validate(
        {
            "goal": (
                "Configure the Main Pass section with Combo, Depth, CBL, and VDL "
                "tracks using CBL_Main.dlis data."
            ),
            "capability_ids": (
                "section.log_plot",
                "track.normal",
                "track.reference",
                "track.array",
                "binding.curve",
                "binding.raster",
            ),
            "existing_section_hint": "Main Pass",
            "source_hints": ("CBL_Main.dlis",),
            "requirements": ("Normal track, width 50mm",),
        }
    )

    normalized = _normalize_reconstruct_track_dimensions(
        action,
        task,
        authoritative_request=cbl_request,
    )
    normalized = _normalize_reconstruct_request_semantics(
        normalized,
        task=task,
        authoritative_request=cbl_request,
    )
    by_id = {track.semantic_id: track for track in normalized.section.tracks}
    assert normalized.section.title == "Main Pass"
    assert {key: track.width_mm for key, track in by_id.items()} == {
        "combo": 50,
        "depth": 10,
        "cbl": 44,
        "vdl": 48,
    }


def test_canonical_section_worker_marks_normalization_failure_separately() -> None:
    """A host normalization failure is not reported as worker-obligation failure."""
    base_context = _context()
    task = base_context.plan.section_tasks[0].model_copy(
        update={"requirements": ("Track 1 (gamma): reference, 42 mm",)}
    )
    context = base_context.model_copy(
        update={"plan": base_context.plan.model_copy(update={"section_tasks": (task,)})}
    )
    response = {
        "action": "reconstruct",
        "section": {
            "source_candidate": "source-1",
            "title": "Main",
            "tracks": [
                {
                    "semantic_id": "gamma",
                    "kind": "normal",
                    "title": "Gamma Ray",
                    "bindings": [{"semantic_id": "gr", "channel": "GR"}],
                }
            ],
        },
    }
    backend = _StructuredFixtureBackend([response, response])
    result = asyncio.run(
        CanonicalSectionWorker(backend=backend).compile(
            task_index=0,
            context=context,
            document=_document(),
            authoritative_request="Build the requested track.",
            timeout_seconds=10,
        )
    )
    assert result.success is False
    assert result.stage_evidence.normalization == "FAIL"
    assert result.stage_evidence.worker_obligation == "NOT_REACHED"


def test_canonical_section_worker_marks_obligation_failure_separately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An obligation failure records normalization success and obligation failure."""
    context = _context()
    response = {
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

    def raise_obligation_failure(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise ValueError("obligation")

    monkeypatch.setattr(
        section_worker,
        "validate_section_obligations",
        raise_obligation_failure,
    )
    result = asyncio.run(
        CanonicalSectionWorker(backend=_StructuredFixtureBackend([response, response])).compile(
            task_index=0,
            context=context,
            document=_document(),
            authoritative_request="Build the requested track.",
            timeout_seconds=10,
        )
    )
    assert result.success is False
    assert result.stage_evidence.normalization == "PASS"
    assert result.stage_evidence.worker_obligation == "FAIL"
    assert result.stage_evidence.semantic_lowering == "NOT_REACHED"


def test_canonical_section_worker_marks_lowering_action_error_separately() -> None:
    """A canonical lowering error records both prior stages as passed."""
    response = {
        "action": "add_track",
        "track": {
            "semantic_id": "quality",
            "kind": "normal",
            "title": "Quality",
            "width_mm": 28,
            "bindings": [
                {
                    "kind": "curve",
                    "semantic_id": "gr",
                    "channel": "GR",
                    "label": "Gamma Ray",
                    "scale": {"kind": "linear", "minimum": 0, "maximum": 150},
                }
            ],
        },
    }
    context = _context()
    ungrounded_section = context.sections[0].model_copy(update={"section_id": None})
    context = context.model_copy(update={"sections": (ungrounded_section,)})
    result = asyncio.run(
        CanonicalSectionWorker(backend=_StructuredFixtureBackend([response])).compile(
            task_index=0,
            context=context,
            document=_document(),
            authoritative_request="Build the requested track.",
            timeout_seconds=10,
        )
    )
    assert result.success is False
    assert result.diagnostics[0].code == "section_missing"
    assert result.stage_evidence.normalization == "PASS"
    assert result.stage_evidence.worker_obligation == "PASS"
    assert result.stage_evidence.semantic_lowering == "FAIL"


def test_section_normalization_rejects_requested_track_kind_mismatch() -> None:
    """A requested kind mismatch fails instead of being silently discarded."""
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
                        "bindings": [{"semantic_id": "gr", "channel": "GR"}],
                    }
                ],
            },
        }
    )
    task = SectionTask(
        goal="Build a reference track.",
        capability_ids=("section.log_plot", "track.reference"),
        existing_section_hint=None,
        requirements=("Track 1 (combo): reference, 42 mm", "Track 1: GR -> Gamma Ray."),
    )
    with pytest.raises(SemanticActionError, match="requested kind 'reference'"):
        _normalize_reconstruct_track_dimensions(action, task)


def test_section_normalization_does_not_fallback_to_track_position() -> None:
    """An unmatched explicit track block cannot mutate the first response track."""
    action = ReconstructSectionAction.model_validate(
        {
            "action": "reconstruct",
            "section": {
                "title": "Main",
                "source_candidate": "source-1",
                "tracks": [
                    {
                        "semantic_id": "unrelated",
                        "kind": "normal",
                        "title": "Unrelated",
                        "bindings": [{"semantic_id": "cali", "channel": "CALI"}],
                    }
                ],
            },
        }
    )
    task = SectionTask(
        goal="Build the combo track.",
        capability_ids=("section.log_plot", "track.normal"),
        existing_section_hint=None,
        requirements=(
            "Combo bindings: GR -> Gamma Ray, linear 5..125, #123456 dashed, width 0.65",
        ),
    )
    with pytest.raises(SemanticActionError, match="could not be matched by identity"):
        _normalize_reconstruct_request_semantics(
            action,
            task=task,
            authoritative_request="Build the combo track.",
        )


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
        existing_section_hint=None,
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
    assert binding.label == "Gamma Ray"


def test_section_normalization_extracts_inline_raster_clause_and_label() -> None:
    """Inline On-track prose preserves raster presentation without track-position fallback."""
    action = ReconstructSectionAction.model_validate(
        {
            "action": "reconstruct",
            "section": {
                "title": "Main",
                "source_candidate": "source-1",
                "tracks": [
                    {
                        "semantic_id": "model-vdl",
                        "kind": "array",
                        "title": "VDL",
                        "x_scale": {"minimum": 0, "maximum": 1},
                        "bindings": [{"semantic_id": "raster", "channel": "VDL", "kind": "raster"}],
                    }
                ],
            },
        }
    )
    normalized = _normalize_reconstruct_request_semantics(
        action,
        task=SectionTask(
            goal="Configure VDL.",
            capability_ids=("section.log_plot", "track.array", "binding.raster"),
            existing_section_hint="Main",
            requirements=(),
        ),
        authoritative_request=(
            'On vdl, plot VDL as a raster labelled "Synthetic VDL". '
            "Use a linear track scale 200..1200, profile vdl, gray_r, "
            "colorbar enabled with label Amplitude in the header, and sample axis "
            "enabled in us from 200 to 1200 with 7 ticks, source origin 40 and step 10. "
            "Hide both vertical main and secondary grid lines."
        ),
    )
    track = normalized.section.tracks[0]
    binding = track.bindings[0]
    assert track.x_scale.minimum == 200
    assert track.x_scale.maximum == 1200
    assert track.grid.vertical_main_visible is False
    assert track.grid.vertical_secondary_visible is False
    assert binding.label == "Synthetic VDL"
    assert binding.profile == "vdl"
    assert binding.colormap == "gray_r"
    assert binding.colorbar_label == "Amplitude"
    assert binding.colorbar_position == "header"
    assert binding.sample_axis.source_origin == 40
    assert binding.sample_axis.source_step == 10


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
