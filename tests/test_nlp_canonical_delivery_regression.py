"""Canonical replacements for the retired D1-D3 program-engine tests."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts import nlp_d4_live_acceptance as d4
from scripts.verify_cbl_packet import _check_remarks, verify_cbl_packet
from tests._mcp_fixtures import REPO_ROOT
from tests.test_nlp_d4_live_acceptance import _build_rehearsal_cbl_artifact

from wellplot.agent.code_mode import typed_section_worker as section_worker
from wellplot.agent.code_mode.canonical_workers import (
    CanonicalReportWorker,
    ReportSemanticResponse,
    _apply_compiled_report_requirements,
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
from wellplot.agent.code_mode.obligations import (
    OwnerKind,
    ValidationIssue,
    ValidationIssueSet,
    compile_request_contract,
    extract_supported_obligations,
    validate_section_obligations,
    verify_document_obligations,
)
from wellplot.agent.code_mode.planner import (
    ReportTask,
    SectionTask,
    SemanticPlan,
    _attach_compiled_requirements,
    _canonical_plan_from_wire,
    _PlannerWirePlan,
    _PlannerWireSectionTask,
    _validate_extraction_coverage,
)
from wellplot.agent.code_mode.semantic_actions import (
    ReconstructSectionAction,
    SemanticActionError,
)
from wellplot.agent.code_mode.typed_section_worker import (
    CanonicalSectionWorker,
    _normalize_reconstruct_request_semantics,
    _normalize_reconstruct_track_dimensions,
    apply_compiled_requirements,
)
from wellplot.agent.providers.base import (
    ProviderMetrics,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from wellplot.authoring import load_authoring_document
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


def _context_for_request(request: str) -> EnrichedSemanticContext:
    """Attach one compiled request contract to the canonical worker fixture."""
    base = _context()
    plan = _attach_compiled_requirements(
        base.plan.model_copy(update={"section_tasks": (base.plan.section_tasks[0],)}),
        compile_request_contract(request),
    )
    return base.model_copy(update={"plan": plan})


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
    assert result.success is True, result.diagnostics
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
    assert result.success is True, result.diagnostics
    assert len(backend.requests) == 2


def test_canonical_report_worker_prefers_explicit_planner_slot_values() -> None:
    """Compiled report facts replace conflicting values in valid inspected slots."""
    authoritative_request = (
        "Set the report metadata to:\n"
        "Company: University of Utah; State: Utah; Logged Depth: TD Not Tag\n\n"
        "Use these service titles, in order:\n"
        '"Cement Bond Log"'
    )
    compilation = compile_request_contract(authoritative_request)
    assert compilation.status.value == "EXTRACTION_COMPLETE"
    report_obligations = tuple(
        item for item in compilation.requirements.requirements if item.owner_kind.value == "report"
    )
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
                    {"slot_id": "general.company", "value": "wrong value"},
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
                obligations=report_obligations,
            ),
            report_context=report_context,
            document=_document(),
            authoritative_request=authoritative_request,
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
    authoritative_request = (
        "Set the report metadata to:\nCompany: FORGE\n\n"
        "For each pass, use a depth = reference track."
    )
    compilation = compile_request_contract(authoritative_request)
    report_obligations = tuple(
        item for item in compilation.requirements.requirements if item.owner_kind.value == "report"
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
                obligations=report_obligations,
            ),
            report_context=report_context,
            document=_document(),
            authoritative_request=authoritative_request,
            timeout_seconds=10,
        )
    )
    assert result.success is True
    assert result.intent_fragment is not None
    assert result.intent_fragment.depth is None


def test_canonical_report_worker_merges_planner_metadata_with_raw_request() -> None:
    """Compiled metadata is applied without downstream prose parsing."""
    authoritative_request = (
        "Set the report metadata to:\n"
        "Company: University of Utah; State: Utah\n\n"
        "For each pass, use the requested tracks."
    )
    compilation = compile_request_contract(authoritative_request)
    assert compilation.status.value == "EXTRACTION_COMPLETE"
    report_obligations = tuple(
        item for item in compilation.requirements.requirements if item.owner_kind.value == "report"
    )
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
                obligations=report_obligations,
            ),
            report_context=report_context,
            document=_document(),
            authoritative_request=authoritative_request,
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
    authoritative_request = (
        "Set the report metadata to:\n"
        "Company: North Star Labs\n\n"
        "Use these service titles, in order:\n"
        '"Cement Review"\n\n'
        "Include the remarks:\n"
        "1. Scope Boundary — Preserve this exact sentence, including punctuation."
    )
    compilation = compile_request_contract(authoritative_request)
    assert compilation.status.value == "EXTRACTION_COMPLETE"
    report_obligations = tuple(
        item for item in compilation.requirements.requirements if item.owner_kind.value == "report"
    )
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
                obligations=report_obligations,
            ),
            report_context=report_context,
            document=_document(),
            authoritative_request=authoritative_request,
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


def test_cbl_captured_report_uses_compiled_request_requirements() -> None:
    """Captured CBL report semantics are applied from the compiled contract."""
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
        ("location", "Location"),
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

    compilation = compile_request_contract(request)
    assert compilation.status.value == "EXTRACTION_COMPLETE"
    report_obligations = tuple(
        item for item in compilation.requirements.requirements if item.owner_kind.value == "report"
    )
    normalized = _apply_compiled_report_requirements(
        response,
        context,
        report_obligations,
    )
    normalized = _normalize_report_slot_groups(normalized, context)

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


def _compiled_cbl_capture() -> tuple[object, ...]:
    """Compile D4-C01 and apply its host-owned requirements to captured sections."""
    request = next(
        case["request"] for case in d4.load_cases(REPO_ROOT) if case["turn_id"] == "D4-C01:C01"
    )
    captured = json.loads(
        (REPO_ROOT / "tests/fixtures/d5_5j_qwen_smoke_003_report_sections.json").read_text()
    )
    section_hints = ("Main Pass", "Repeat Pass")
    plan = _attach_compiled_requirements(
        SemanticPlan(
            summary="Configure both CBL passes.",
            report_task=ReportTask(
                goal="Populate report metadata and remarks.",
                capability_ids=("report.standard",),
            ),
            section_tasks=tuple(
                SectionTask(
                    goal=f"Configure the CBL {section_hint.lower()}.",
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
                for section_hint in section_hints
            ),
        ),
        compile_request_contract(request),
    )
    actions = []
    for section_payload, section_hint in zip(captured["sections"], section_hints, strict=True):
        action = ReconstructSectionAction.model_validate(section_payload)
        section_task = next(
            bound_task
            for bound_task in plan.section_tasks
            if bound_task.existing_section_hint == section_hint
        )
        normalized = apply_compiled_requirements(action, section_task.obligations)
        validate_section_obligations(
            normalized,
            section_task.obligations,
            section_title=section_task.existing_section_hint,
        )
        actions.append(normalized)
    return plan.requirement_compilation, plan, tuple(actions)


def _authority_g_worker_context(plan: SemanticPlan) -> EnrichedSemanticContext:
    """Build provider-free source context for the sanitized Authority-G turn."""
    channels = tuple(
        ChannelContext(
            mnemonic=mnemonic,
            kind="array" if mnemonic == "VDL" else "scalar",
        )
        for mnemonic in (
            "ECGR_STGC",
            "TT",
            "TENS",
            "MTEM",
            "STIT",
            "TDSP",
            "VSEC",
            "CBL",
            "VDL",
        )
    )
    sources = (
        SourceContext(
            candidate_id="source-1",
            labels=("CBL_Main.dlis", "CBL_Main"),
            canonical_path="/fixture/CBL_Main.dlis",
            source_format="dlis",
            channels=channels,
        ),
        SourceContext(
            candidate_id="source-2",
            labels=("CBL_Repeat.dlis", "CBL_Repeat"),
            canonical_path="/fixture/CBL_Repeat.dlis",
            source_format="dlis",
            channels=channels,
        ),
    )
    return EnrichedSemanticContext(
        plan=plan,
        sections=(
            ResolvedSectionContext(task_index=0, section_id="main_pass", sources=sources),
            ResolvedSectionContext(task_index=1, section_id="repeat_pass", sources=sources),
        ),
        report=ReportContext(),
    )


def _authority_g_response() -> dict[str, object]:
    """Load the sanitized exact Main Pass response captured in Authority G."""
    captured = json.loads(
        (REPO_ROOT / "tests/fixtures/d5_authority_g_main_pass_section_response.json").read_text(
            encoding="utf-8"
        )
    )
    assert captured["provenance"]["checkpoint"] == "59350813e19389fea06fc30f07f37969e66fb1d1"
    assert captured["provenance"]["captured_response_digest"] == (
        "6d3d898350bb8c1585a55ee798a2611e3180a786b37ca8a9222f5076fb4054e9"
    )
    return captured["response"]


def test_authority_g_captured_response_uses_one_shared_track_binding() -> None:
    """Exact G response grounds combo once and completes canonical validation."""
    _compilation, plan, _actions = _compiled_cbl_capture()
    task = next(task for task in plan.section_tasks if task.existing_section_hint == "Main Pass")
    response = _authority_g_response()
    action = section_worker.SectionSemanticActionResponse.model_validate(response).root
    bindings = section_worker.resolve_section_object_bindings(action, task.obligations)

    assert bindings.track_index("combo") == 0
    applied = apply_compiled_requirements(action, task.obligations, object_bindings=bindings)
    assert applied.section.tracks[0].width_mm == 50
    context = _authority_g_worker_context(plan)
    section_context = context.sections[0]
    issues = section_worker._collect_validation_issues(
        applied,
        task.obligations,
        section_context=section_context,
        section_title=task.existing_section_hint,
        object_bindings=bindings,
    )
    assert issues.issues == ()
    validate_section_obligations(
        applied,
        task.obligations,
        section_context=section_context,
        section_title=task.existing_section_hint,
        object_bindings=bindings,
    )

    worker_backend = _StructuredFixtureBackend([response])
    document = load_authoring_document(
        REPO_ROOT / "tests/fixtures/agentic_cbl/cased_hole_starter.log.yaml"
    )
    result = asyncio.run(
        CanonicalSectionWorker(worker_backend).compile(
            task_index=0,
            context=context,
            document=document,
            authoritative_request=next(
                case["request"]
                for case in d4.load_cases(REPO_ROOT)
                if case["turn_id"] == "D4-C01:C01"
            ),
            timeout_seconds=10,
        )
    )
    assert result.success is True, result.diagnostics
    assert len(worker_backend.requests) == 1


def test_binding_owner_slug_and_display_track_owner_share_identity() -> None:
    """Normalized binding slugs attach to the matching display-form track owner."""
    _compilation, plan, _actions = _compiled_cbl_capture()
    task = next(task for task in plan.section_tasks if task.existing_section_hint == "Main Pass")
    obligations = tuple(
        item.model_copy(update={"owner_ref": "Combo"})
        if item.owner_kind is OwnerKind.TRACK and item.owner_ref == "combo"
        else item
        for item in task.obligations
    )
    action = section_worker.SectionSemanticActionResponse.model_validate(
        _authority_g_response()
    ).root

    bindings = section_worker.resolve_section_object_bindings(action, obligations)

    assert bindings.track_index("Combo") == 0
    assert bindings.track_index("combo") == 0
    applied = apply_compiled_requirements(action, obligations, object_bindings=bindings)
    validate_section_obligations(
        applied,
        obligations,
        section_title=task.existing_section_hint,
        object_bindings=bindings,
    )


def test_grounding_rejects_duplicate_explicit_identity() -> None:
    """Duplicate exact titles are ambiguous even when one track looks plausible."""
    _compilation, plan, _actions = _compiled_cbl_capture()
    task = next(task for task in plan.section_tasks if task.existing_section_hint == "Main Pass")
    requirements = tuple(item for item in task.obligations if item.owner_ref == "combo")
    action = ReconstructSectionAction.model_validate(
        {
            "action": "reconstruct",
            "section": {
                "title": "Main Pass",
                "source_candidate": "source-1",
                "tracks": [
                    {
                        "semantic_id": "candidate-a",
                        "kind": "normal",
                        "title": "Combo",
                        "bindings": [{"semantic_id": "a", "channel": "GR"}],
                    },
                    {
                        "semantic_id": "candidate-b",
                        "kind": "normal",
                        "title": "Combo",
                        "bindings": [{"semantic_id": "b", "channel": "GR"}],
                    },
                ],
            },
        }
    )

    with pytest.raises(SemanticActionError, match="multiple proposal tracks") as error:
        section_worker.resolve_section_object_bindings(action, requirements)
    assert error.value.code == "worker_grounding_ambiguous"


def test_grounding_rejects_partial_channel_overlap() -> None:
    """Two partial tracks do not satisfy one complete ordered track signature."""
    _compilation, plan, _actions = _compiled_cbl_capture()
    task = next(task for task in plan.section_tasks if task.existing_section_hint == "Main Pass")
    requirements = tuple(item for item in task.obligations if item.owner_ref == "combo")
    action = ReconstructSectionAction.model_validate(
        {
            "action": "reconstruct",
            "section": {
                "title": "Main Pass",
                "source_candidate": "source-1",
                "tracks": [
                    {
                        "semantic_id": "candidate-a",
                        "kind": "normal",
                        "title": "First",
                        "bindings": [
                            {"semantic_id": "a1", "channel": "ECGR_STGC"},
                            {"semantic_id": "a2", "channel": "TT"},
                        ],
                    },
                    {
                        "semantic_id": "candidate-b",
                        "kind": "normal",
                        "title": "Second",
                        "bindings": [
                            {"semantic_id": "b1", "channel": "TENS"},
                            {"semantic_id": "b2", "channel": "MTEM"},
                        ],
                    },
                ],
            },
        }
    )

    with pytest.raises(SemanticActionError) as error:
        section_worker.resolve_section_object_bindings(action, requirements)
    assert error.value.code == "worker_grounding_unresolved"


def test_grounding_rejects_two_owners_assigned_to_one_track() -> None:
    """Global assignment detects owner collisions instead of resolving locally."""
    _compilation, plan, _actions = _compiled_cbl_capture()
    task = next(task for task in plan.section_tasks if task.existing_section_hint == "Main Pass")
    requirements = tuple(item for item in task.obligations if item.owner_ref in {"combo", "depth"})
    action = ReconstructSectionAction.model_validate(
        {
            "action": "reconstruct",
            "section": {
                "title": "Main Pass",
                "source_candidate": "source-1",
                "tracks": [
                    {
                        "semantic_id": "combo",
                        "kind": "normal",
                        "title": "depth",
                        "bindings": [{"semantic_id": "gr", "channel": "GR"}],
                    }
                ],
            },
        }
    )

    with pytest.raises(SemanticActionError) as error:
        section_worker.resolve_section_object_bindings(action, requirements)
    assert error.value.code == "worker_grounding_conflict"


def test_grounding_signature_preserves_repeated_binding_multiplicity() -> None:
    """The structural signature distinguishes two CBL occurrences from one."""
    _compilation, plan, _actions = _compiled_cbl_capture()
    task = next(task for task in plan.section_tasks if task.existing_section_hint == "Main Pass")
    kind_fact = next(
        item for item in task.obligations if item.owner_ref == "combo" and item.field == "kind"
    ).model_copy(update={"owner_ref": "repeat", "value": "normal", "requirement_id": "repeat-kind"})
    channel_fact = next(
        item for item in task.obligations if item.owner_ref == "combo" and item.field == "channel"
    )
    repeated = tuple(
        channel_fact.model_copy(
            update={
                "owner_ref": "repeat",
                "value": "CBL",
                "slot_key": f"repeat.binding.{index}",
                "requirement_id": f"repeat-channel-{index}",
            }
        )
        for index in (1, 2)
    )
    action = ReconstructSectionAction.model_validate(
        {
            "action": "reconstruct",
            "section": {
                "title": "Main Pass",
                "source_candidate": "source-1",
                "tracks": [
                    {
                        "semantic_id": "candidate",
                        "kind": "normal",
                        "title": "Other",
                        "bindings": [
                            {"semantic_id": "cbl-a", "channel": "CBL"},
                            {"semantic_id": "cbl-b", "channel": "CBL"},
                        ],
                    }
                ],
            },
        }
    )

    bindings = section_worker.resolve_section_object_bindings(action, (kind_fact, *repeated))
    assert bindings.track_index("repeat") == 0
    one_occurrence = action.model_copy(
        update={
            "section": action.section.model_copy(
                update={
                    "tracks": (
                        action.section.tracks[0].model_copy(
                            update={"bindings": action.section.tracks[0].bindings[:1]}
                        ),
                    )
                }
            )
        }
    )
    with pytest.raises(SemanticActionError) as error:
        section_worker.resolve_section_object_bindings(one_occurrence, (kind_fact, *repeated))
    assert error.value.code == "worker_grounding_unresolved"


def test_grounding_does_not_repair_wrong_structural_kind() -> None:
    """Exact identity may bind a proposal, but host application leaves wrong kind intact."""
    _compilation, plan, _actions = _compiled_cbl_capture()
    task = next(task for task in plan.section_tasks if task.existing_section_hint == "Main Pass")
    kind_fact = next(
        item for item in task.obligations if item.owner_ref == "combo" and item.field == "kind"
    )
    action = ReconstructSectionAction.model_validate(
        {
            "action": "reconstruct",
            "section": {
                "title": "Main Pass",
                "source_candidate": "source-1",
                "tracks": [
                    {
                        "semantic_id": "combo",
                        "kind": "reference",
                        "title": "Combo",
                        "bindings": [{"semantic_id": "gr", "channel": "GR"}],
                    }
                ],
            },
        }
    )
    bindings = section_worker.resolve_section_object_bindings(action, (kind_fact,))
    applied = apply_compiled_requirements(action, (kind_fact,), object_bindings=bindings)
    assert applied.section.tracks[0].kind == "reference"
    issues = section_worker._collect_validation_issues(
        applied,
        (kind_fact,),
        section_context=ResolvedSectionContext(task_index=0),
        section_title=None,
        object_bindings=bindings,
    )
    assert [(issue.field, issue.expected_value) for issue in issues.issues] == [("kind", "normal")]


def test_structural_fallback_requires_exact_channel_cardinality() -> None:
    """An extra channel prevents fallback from treating a signature as equivalent."""
    _compilation, plan, _actions = _compiled_cbl_capture()
    task = next(task for task in plan.section_tasks if task.existing_section_hint == "Main Pass")
    requirements = tuple(item for item in task.obligations if item.owner_ref == "combo")
    captured = _authority_g_response()
    payload = json.loads(json.dumps(captured))
    payload["section"]["tracks"][0]["semantic_id"] = "candidate"
    payload["section"]["tracks"][0]["title"] = "Unrelated"
    payload["section"]["tracks"][0]["bindings"].append({"semantic_id": "extra", "channel": "EXTRA"})
    action = section_worker.SectionSemanticActionResponse.model_validate(payload).root

    with pytest.raises(SemanticActionError) as error:
        section_worker.resolve_section_object_bindings(action, requirements)
    assert error.value.code == "worker_grounding_unresolved"


def test_grounding_rejects_conflicting_exact_and_structural_evidence() -> None:
    """An exact owner name cannot override a different full structural match."""
    _compilation, plan, _actions = _compiled_cbl_capture()
    task = next(task for task in plan.section_tasks if task.existing_section_hint == "Main Pass")
    requirements = tuple(item for item in task.obligations if item.owner_ref == "combo")
    payload = json.loads(json.dumps(_authority_g_response()))
    payload["section"]["tracks"][0]["semantic_id"] = "combo"
    payload["section"]["tracks"][0]["bindings"] = [{"semantic_id": "wrong", "channel": "GR"}]
    payload["section"]["tracks"].append(
        {
            "semantic_id": "structural-match",
            "kind": "normal",
            "title": "Other",
            "bindings": [
                {"semantic_id": f"binding-{index}", "channel": channel}
                for index, channel in enumerate(("ECGR_STGC", "TT", "TENS", "MTEM"))
            ],
        }
    )
    action = section_worker.SectionSemanticActionResponse.model_validate(payload).root

    with pytest.raises(SemanticActionError) as error:
        section_worker.resolve_section_object_bindings(action, requirements)
    assert error.value.code == "worker_grounding_ambiguous"


def test_repair_contract_uses_the_previously_bound_track() -> None:
    """Repair paths derive from the exact host binding, not another name lookup."""
    _compilation, plan, _actions = _compiled_cbl_capture()
    task = next(task for task in plan.section_tasks if task.existing_section_hint == "Main Pass")
    response = _authority_g_response()
    action = section_worker.SectionSemanticActionResponse.model_validate(response).root
    bindings = section_worker.resolve_section_object_bindings(action, task.obligations)
    baseline = apply_compiled_requirements(action, task.obligations, object_bindings=bindings)
    requirement = next(
        item for item in task.obligations if item.owner_ref == "combo" and item.field == "width_mm"
    )
    issue = ValidationIssue(
        requirement_id=requirement.requirement_id,
        owner_kind=requirement.owner_kind,
        owner_ref=requirement.owner_ref,
        field=requirement.field,
        expected_value=requirement.value,
        code="fixture_issue",
    )

    contract = section_worker._build_repair_contract(
        baseline,
        ValidationIssueSet(issues=(issue,)),
        object_bindings=bindings,
    )
    assert len(contract.operations) == 1
    assert contract.operations[0].path_prefix == "section.tracks[main_pass.combo].width_mm"


def test_unresolved_authority_g_response_is_bounded_before_correction() -> None:
    """An unresolved G proposal returns a worker result after one model response."""
    _compilation, plan, _actions = _compiled_cbl_capture()
    response = json.loads(json.dumps(_authority_g_response()))
    combo = response["section"]["tracks"][0]
    combo["semantic_id"] = "unrelated-track"
    combo["title"] = "Unrelated"
    combo["bindings"] = [{"semantic_id": "only", "channel": "GR"}]
    backend = _StructuredFixtureBackend([response])
    observed_actions: list[dict[str, object]] = []
    context = _authority_g_worker_context(plan)
    document = load_authoring_document(
        REPO_ROOT / "tests/fixtures/agentic_cbl/cased_hole_starter.log.yaml"
    )

    result = asyncio.run(
        CanonicalSectionWorker(backend, action_observer=observed_actions.append).compile(
            task_index=0,
            context=context,
            document=document,
            authoritative_request=next(
                case["request"]
                for case in d4.load_cases(REPO_ROOT)
                if case["turn_id"] == "D4-C01:C01"
            ),
            timeout_seconds=10,
        )
    )
    assert result.success is False
    assert result.diagnostics[0].code == "worker_grounding_unresolved"
    assert result.stage_evidence.normalization == "FAIL"
    assert len(backend.requests) == 1
    assert observed_actions == [
        {
            "event": "SECTION_ACTION_VALIDATED",
            "attempt": 1,
            "action": section_worker.SectionSemanticActionResponse.model_validate(
                response
            ).root.model_dump(mode="json", exclude_unset=True),
        }
    ]


def test_incomplete_single_track_action_gets_bounded_grounding_correction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A uniquely grounded partial add_track can be completed without relaxing binding."""
    _compilation, plan, _actions = _compiled_cbl_capture()
    section_tasks = list(plan.section_tasks)
    main_index = next(
        index
        for index, task in enumerate(section_tasks)
        if task.existing_section_hint == "Main Pass"
    )
    main_task = section_tasks[main_index]
    aliased_obligations = tuple(
        item.model_copy(update={"owner_ref": "Combo"})
        if item.owner_kind is OwnerKind.TRACK and item.owner_ref == "combo"
        else item
        for item in main_task.obligations
    )
    section_tasks[main_index] = main_task.model_copy(update={"obligations": aliased_obligations})
    plan = plan.model_copy(update={"section_tasks": tuple(section_tasks)})
    full_response = _authority_g_response()
    first_track = full_response["section"]["tracks"][0]
    initial_response = {"action": "add_track", "track": first_track}
    backend = _StructuredFixtureBackend([initial_response, full_response])
    context = _authority_g_worker_context(plan)
    document = load_authoring_document(
        REPO_ROOT / "tests/fixtures/agentic_cbl/cased_hole_starter.log.yaml"
    )

    binding_refs: list[object] = []
    original_apply = section_worker.apply_compiled_requirements
    original_collect = section_worker._collect_validation_issues
    original_validate = section_worker.validate_section_obligations

    def apply_spy(
        action: object, obligations: tuple[object, ...], *, object_bindings: object
    ) -> object:
        binding_refs.append(object_bindings)
        return original_apply(action, obligations, object_bindings=object_bindings)

    def collect_spy(*args: object, **kwargs: object) -> object:
        binding_refs.append(kwargs["object_bindings"])
        return original_collect(*args, **kwargs)

    def validate_spy(*args: object, **kwargs: object) -> object:
        binding_refs.append(kwargs["object_bindings"])
        return original_validate(*args, **kwargs)

    monkeypatch.setattr(section_worker, "apply_compiled_requirements", apply_spy)
    monkeypatch.setattr(section_worker, "_collect_validation_issues", collect_spy)
    monkeypatch.setattr(section_worker, "validate_section_obligations", validate_spy)
    observed_actions: list[dict[str, object]] = []
    result = asyncio.run(
        CanonicalSectionWorker(backend, action_observer=observed_actions.append).compile(
            task_index=0,
            context=context,
            document=document,
            authoritative_request=next(
                case["request"]
                for case in d4.load_cases(REPO_ROOT)
                if case["turn_id"] == "D4-C01:C01"
            ),
            timeout_seconds=10,
        )
    )

    assert result.success is True, result.diagnostics
    assert result.stage_evidence.normalization == "PASS"
    assert result.stage_evidence.worker_obligation == "PASS"
    assert result.stage_evidence.semantic_lowering == "PASS"
    assert result.stage_evidence.correction == "PASS"
    assert len(backend.requests) == 2
    assert [event["attempt"] for event in observed_actions] == [1, 2]
    assert observed_actions[0]["action"]["action"] == "add_track"
    assert observed_actions[1]["action"]["action"] == "reconstruct"
    assert len(binding_refs) >= 3
    assert all(item is binding_refs[0] for item in binding_refs)


def test_grounding_correction_cannot_change_the_already_matched_track() -> None:
    """A correction cannot exploit the shape repair to rewrite its grounded sibling."""
    _compilation, plan, _actions = _compiled_cbl_capture()
    full_response = _authority_g_response()
    initial_response = {
        "action": "add_track",
        "track": full_response["section"]["tracks"][0],
    }
    corrected_response = json.loads(json.dumps(full_response))
    corrected_response["section"]["tracks"][0]["title"] = "Renamed track"
    backend = _StructuredFixtureBackend([initial_response, corrected_response])
    context = _authority_g_worker_context(plan)
    document = load_authoring_document(
        REPO_ROOT / "tests/fixtures/agentic_cbl/cased_hole_starter.log.yaml"
    )

    result = asyncio.run(
        CanonicalSectionWorker(backend).compile(
            task_index=0,
            context=context,
            document=document,
            authoritative_request=next(
                case["request"]
                for case in d4.load_cases(REPO_ROOT)
                if case["turn_id"] == "D4-C01:C01"
            ),
            timeout_seconds=10,
        )
    )

    assert result.success is False
    assert result.diagnostics[0].code == "worker_correction_scope_violation"
    assert result.stage_evidence.normalization == "PASS"
    assert result.stage_evidence.worker_obligation == "FAIL"
    assert len(backend.requests) == 2


def test_grounding_correction_fails_closed_on_identity_structure_disagreement() -> None:
    """An identity/title collision cannot be treated as a recoverable omission."""
    _compilation, plan, _actions = _compiled_cbl_capture()
    response = _authority_g_response()
    track = json.loads(json.dumps(response["section"]["tracks"][0]))
    track["title"] = "Depth"
    action = section_worker.SectionSemanticActionResponse.model_validate(
        {"action": "add_track", "track": track}
    ).root
    task = next(task for task in plan.section_tasks if task.existing_section_hint == "Main Pass")
    relevant = tuple(item for item in task.obligations if item.owner_ref in {"combo", "depth"})

    assert section_worker._recoverable_single_track_omission(action, relevant) is None


def test_correction_identity_drift_is_rejected_with_frozen_binding() -> None:
    """Raw correction cannot rename an existing track before host reapplication."""
    _compilation, plan, _actions = _compiled_cbl_capture()
    task = next(task for task in plan.section_tasks if task.existing_section_hint == "Main Pass")
    action = section_worker.SectionSemanticActionResponse.model_validate(
        _authority_g_response()
    ).root
    bindings = section_worker.resolve_section_object_bindings(action, task.obligations)
    baseline = apply_compiled_requirements(action, task.obligations, object_bindings=bindings)
    requirement = next(
        item for item in task.obligations if item.owner_ref == "combo" and item.field == "width_mm"
    )
    issue = ValidationIssue(
        requirement_id=requirement.requirement_id,
        owner_kind=requirement.owner_kind,
        owner_ref=requirement.owner_ref,
        field=requirement.field,
        expected_value=requirement.value,
        code="fixture_issue",
    )
    contract = section_worker._build_repair_contract(
        baseline,
        ValidationIssueSet(issues=(issue,)),
        object_bindings=bindings,
    )
    changed_track = baseline.section.tracks[0].model_copy(update={"semantic_id": "renamed-track"})
    candidate = baseline.model_copy(
        update={
            "section": baseline.section.model_copy(
                update={"tracks": (changed_track, *baseline.section.tracks[1:])}
            )
        }
    )

    with pytest.raises(SemanticActionError) as error:
        section_worker._verify_repair_candidate(
            baseline, candidate, contract, object_bindings=bindings
        )
    assert error.value.code == "worker_correction_scope_violation"


def test_correction_structural_kind_change_is_rejected() -> None:
    """A REPLACE authority for presentation cannot authorize a track-kind edit."""
    request = (
        "In the Main Log section.\nOn gamma: "
        "GR -> Gamma Ray, linear 0..150, #111111, width 1; "
        "CALI -> Caliper, linear 0..20, #111111, width 1."
    )
    obligations = compile_request_contract(request).requirements.requirements
    baseline = ReconstructSectionAction.model_validate(
        {
            "action": "reconstruct",
            "section": {
                "title": "Main Log",
                "source_candidate": "source-1",
                "tracks": [
                    {
                        "semantic_id": "gamma",
                        "kind": "normal",
                        "title": "Gamma",
                        "width_mm": 20,
                        "bindings": [{"semantic_id": "gr", "channel": "GR"}],
                    }
                ],
            },
        }
    )
    bindings = section_worker.resolve_section_object_bindings(baseline, obligations)
    label_issue = next(
        item for item in obligations if item.owner_ref == "gamma" and item.field == "channel"
    )
    issue = ValidationIssue(
        requirement_id=label_issue.requirement_id,
        owner_kind=label_issue.owner_kind,
        owner_ref=label_issue.owner_ref,
        field=label_issue.field,
        expected_value=label_issue.value,
        code="fixture_issue",
    )
    contract = section_worker._build_repair_contract(
        baseline,
        ValidationIssueSet(issues=(issue,)),
        object_bindings=bindings,
    )
    candidate_data = baseline.model_dump(mode="json", exclude_unset=True)
    candidate_data["section"]["tracks"][0]["kind"] = "reference"
    candidate = section_worker.SectionSemanticActionResponse.model_validate(candidate_data).root

    with pytest.raises(SemanticActionError) as error:
        section_worker._verify_repair_candidate(
            baseline, candidate, contract, object_bindings=bindings
        )
    assert error.value.code == "worker_correction_scope_violation"


_CBL_MIGRATION_CASES = (
    ("C01", "combo", "kind", "normal", None),
    ("C02", "combo", "width_mm", 50.0, None),
    ("C03", "combo", "channel", "ECGR_STGC", "combo.binding.1"),
    ("C04", "combo", "label", "Gamma Ray (ECGR_STGC) QTGC-B", "combo.binding.1"),
    ("C05", "combo", "scale_kind", "linear", "combo.binding.1"),
    ("C06", "combo", "scale_minimum", 0.0, "combo.binding.1"),
    ("C07", "combo", "scale_maximum", 150.0, "combo.binding.1"),
    ("C08", "combo", "scale_reverse", True, "combo.binding.2"),
    ("C09", "combo", "color", "#16a34a", "combo.binding.1"),
    ("C10", "combo", "line_width", 0.8, "combo.binding.1"),
    ("C11", "combo", "line_style", "dashed", "combo.binding.3"),
    ("C12", "cbl", "label", "CBL Amplitude (CBL) QSLT-B", "cbl.binding.2"),
    ("C13", "vdl", "track_scale_kind", "linear", None),
    ("C14", "vdl", "track_scale_minimum", 200.0, None),
    ("C15", "vdl", "track_scale_maximum", 1200.0, None),
    ("C16", "vdl", "vertical_main_visible", False, None),
    ("C17", "vdl", "vertical_secondary_visible", False, None),
    ("C18", "vdl", "label", "VDL VariableDensity (VDL) QSLT-B", "vdl.binding.raster"),
    ("C19", "vdl", "raster_profile", "vdl", "vdl.binding.raster"),
    ("C20", "vdl", "raster_colormap", "gray_r", "vdl.binding.raster"),
    ("C21", "vdl", "colorbar_enabled", True, "vdl.binding.raster"),
    ("C22", "vdl", "sample_axis_source_step", 10.0, "vdl.binding.raster"),
)


def _compiled_value(action: ReconstructSectionAction, case: tuple[object, ...]) -> object:
    """Read one migration-matrix value from its identity-bound canonical owner."""
    _case_id, owner, field, _expected, slot_key = case
    track = next(
        item
        for item in action.section.tracks
        if str(owner).casefold() in item.semantic_id.casefold()
    )
    if field == "kind":
        return track.kind
    if field == "width_mm":
        return track.width_mm
    if field.startswith("track_scale_"):
        name = field.removeprefix("track_scale_")
        return getattr(track.x_scale, name)
    if field in {"vertical_main_visible", "vertical_secondary_visible"}:
        return getattr(track.grid, field)

    if slot_key.endswith(".binding.raster"):
        binding = next(item for item in track.bindings if item.profile is not None)
    else:
        index = int(slot_key.rsplit(".", maxsplit=1)[1]) - 1
        binding = track.bindings[index]
    if field == "channel" or field == "label":
        return getattr(binding, field)
    if field.startswith("scale_"):
        return getattr(binding.scale, field.removeprefix("scale_"))
    if field in {"color", "line_width", "line_style"}:
        return getattr(binding.style, field)
    if field == "raster_profile":
        return binding.profile
    if field == "raster_colormap":
        return binding.colormap
    if field.startswith("colorbar_"):
        return getattr(binding, field)
    if field.startswith("sample_axis_"):
        return getattr(binding.sample_axis, field.removeprefix("sample_axis_"))
    raise AssertionError(f"Unsupported matrix field: {field}")


@pytest.mark.parametrize("case", _CBL_MIGRATION_CASES, ids=lambda case: case[0])
def test_compilation_matrix_c01_c22_has_independent_provenance(case: tuple[object, ...]) -> None:
    """Every Rev 2 compilation row is value-bearing and independently anchored."""
    compilation, plan, _actions = _compiled_cbl_capture()
    assert compilation.status.value == "EXTRACTION_COMPLETE"
    _validate_extraction_coverage(plan)
    _owner, owner, field, expected, slot_key = case
    assert any(
        item.owner_ref == owner
        and item.field == field
        and item.value == expected
        and item.slot_key == slot_key
        and item.provenance
        for item in compilation.requirements.requirements
    )


@pytest.mark.parametrize("case", _CBL_MIGRATION_CASES, ids=lambda case: f"M{case[0][1:]}")
def test_migration_matrix_m01_m22_applies_to_identity_bound_capture(
    case: tuple[object, ...],
) -> None:
    """Every Rev 3 migration row is applied to its canonical captured owner."""
    _compilation, _plan, actions = _compiled_cbl_capture()
    for action in actions:
        assert _compiled_value(action, case) == case[3]


def test_cbl_captured_section_output_uses_compiled_request_semantics() -> None:
    """Captured Main and Repeat sections pass the compiled requirement contract."""
    compilation, plan, actions = _compiled_cbl_capture()
    assert compilation.status.value == "EXTRACTION_COMPLETE"
    assert len(plan.scope_binding.expected_scope_ids) == 2
    assert len(actions) == 2
    for action in actions:
        tracks = action.section.tracks
        assert [track.width_mm for track in tracks] == [50.0, 10.0, 44.0, 48.0]
        assert tracks[0].bindings[0].label == "Gamma Ray (ECGR_STGC) QTGC-B"
        assert tracks[0].bindings[1].scale.reverse is True
        assert tracks[0].bindings[2].style.line_style == "dashed"
        assert tracks[2].bindings[0].style.color == "#111111"
        assert tracks[2].bindings[1].style.line_style == "dashed"
        assert tracks[3].bindings[0].label == "VDL VariableDensity (VDL) QSLT-B"
        assert tracks[3].bindings[0].profile == "vdl"
        assert tracks[3].bindings[0].colorbar_position == "header"
        assert tracks[3].bindings[0].sample_axis.unit == "us"
        assert tracks[3].bindings[0].sample_axis.minimum == 200
        assert tracks[3].bindings[0].sample_axis.maximum == 1200
        assert tracks[3].bindings[0].sample_axis.tick_count == 7
        assert tracks[3].bindings[0].sample_axis.source_origin == 40
        assert tracks[3].bindings[0].sample_axis.source_step == 10
        assert tracks[3].grid.vertical_main_visible is False
        assert tracks[3].grid.vertical_secondary_visible is False


def _request_presentation_projection(
    action: ReconstructSectionAction,
) -> dict[str, object]:
    """Project only request-authoritative presentation fields for parity checks."""
    tracks = []
    for track in action.section.tracks:
        track_data = {
            "kind": track.kind,
            "title": track.title,
            "width_mm": track.width_mm,
            "x_scale": (
                {
                    name: getattr(track.x_scale, name)
                    for name in ("kind", "minimum", "maximum", "reverse")
                }
                if track.x_scale
                else None
            ),
            "grid": (track.grid.model_dump(mode="json", exclude_none=True) if track.grid else None),
            "bindings": [],
        }
        bindings = []
        for binding in track.bindings:
            binding_data = {
                "kind": binding.kind,
                "channel": binding.channel,
                "label": binding.label,
            }
            for field_name in (
                "scale",
                "style",
                "profile",
                "colormap",
                "colorbar_enabled",
                "colorbar_label",
                "colorbar_position",
                "sample_axis",
            ):
                value = getattr(binding, field_name, None)
                if field_name == "style" and value is not None:
                    binding_data[field_name] = {
                        name: getattr(value, name) for name in ("color", "line_style", "line_width")
                    }
                elif field_name == "scale" and value is not None:
                    binding_data[field_name] = {
                        name: getattr(value, name)
                        for name in ("kind", "minimum", "maximum", "reverse")
                    }
                else:
                    binding_data[field_name] = (
                        value.model_dump(mode="json", exclude_none=True)
                        if hasattr(value, "model_dump")
                        else value
                    )
            bindings.append(binding_data)
        track_data["bindings"] = bindings
        tracks.append(track_data)
    return {"tracks": tracks}


def test_compiled_cbl_presentation_matches_retired_normalizers() -> None:
    """Legacy and compiled paths preserve the same request fields on both captures."""
    request = next(
        case["request"] for case in d4.load_cases(REPO_ROOT) if case["turn_id"] == "D4-C01:C01"
    )
    captured = json.loads(
        (REPO_ROOT / "tests/fixtures/d5_5j_qwen_smoke_003_report_sections.json").read_text()
    )
    _compilation, plan, compiled_actions = _compiled_cbl_capture()

    for section_payload, compiled_action, section_hint in zip(
        captured["sections"], compiled_actions, ("Main Pass", "Repeat Pass"), strict=True
    ):
        task = next(
            item for item in plan.section_tasks if item.existing_section_hint == section_hint
        )
        proposal = ReconstructSectionAction.model_validate(section_payload)
        legacy_action = _normalize_reconstruct_track_dimensions(
            proposal,
            task,
            authoritative_request=request,
        )
        legacy_action = _normalize_reconstruct_request_semantics(
            legacy_action,
            task=task,
            authoritative_request=request,
        )

        compiled_projection = _request_presentation_projection(compiled_action)
        legacy_projection = _request_presentation_projection(legacy_action)
        differences = []
        for track_index, (compiled_track, legacy_track) in enumerate(
            zip(compiled_projection["tracks"], legacy_projection["tracks"], strict=True)
        ):
            for field_name in compiled_track:
                if field_name == "bindings":
                    for binding_index, (compiled_binding, legacy_binding) in enumerate(
                        zip(
                            compiled_track["bindings"],
                            legacy_track["bindings"],
                            strict=True,
                        )
                    ):
                        for binding_field in compiled_binding:
                            if compiled_binding[binding_field] != legacy_binding[binding_field]:
                                differences.append(
                                    f"track[{track_index}].bindings[{binding_index}]"
                                    f".{binding_field}: compiled="
                                    f"{compiled_binding[binding_field]!r}; legacy="
                                    f"{legacy_binding[binding_field]!r}"
                                )
                    continue
                if compiled_track[field_name] != legacy_track[field_name]:
                    differences.append(
                        f"track[{track_index}].{field_name}: "
                        f"compiled={compiled_track[field_name]!r}; "
                        f"legacy={legacy_track[field_name]!r}"
                    )
        assert not differences, differences


def test_compiled_kind_mismatch_is_reported_without_host_overlay() -> None:
    """A structural kind mismatch remains visible to validation after host application."""
    request = 'Add a reference track titled "Combo".'
    compilation = compile_request_contract(request)
    obligations = compilation.requirements.requirements
    proposal = ReconstructSectionAction.model_validate(
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

    object_bindings = section_worker.resolve_section_object_bindings(proposal, obligations)
    applied = apply_compiled_requirements(proposal, obligations, object_bindings=object_bindings)
    assert applied.section.tracks[0].kind == "normal"
    issues = section_worker._collect_validation_issues(
        applied,
        obligations,
        section_context=ResolvedSectionContext(task_index=0),
        section_title=None,
        object_bindings=object_bindings,
    )

    assert [(item.field, item.expected_value) for item in issues.issues] == [("kind", "reference")]


def test_post_lowering_verification_uses_repeated_binding_slot_identity() -> None:
    """Two same-channel CBL curves are checked against their ordered request slots."""
    _compilation, plan, _actions = _compiled_cbl_capture()
    main_task = next(
        task for task in plan.section_tasks if task.existing_section_hint == "Main Pass"
    )
    obligations = tuple(
        item
        for item in main_task.obligations
        if item.slot_key in {"cbl.binding.1", "cbl.binding.2"}
        and item.field in {"scale_kind", "scale_minimum", "scale_maximum"}
    )

    def document(first_maximum: float, second_maximum: float) -> SimpleNamespace:
        return SimpleNamespace(
            model_dump=lambda mode: {
                "sections": [
                    {
                        "id": "main_pass",
                        "tracks": [
                            {
                                "id": "cbl",
                                "bindings": [
                                    {
                                        "binding_id": "cbl-one",
                                        "channel": "CBL",
                                        "scale": {
                                            "kind": "linear",
                                            "minimum": 0.0,
                                            "maximum": first_maximum,
                                        },
                                    },
                                    {
                                        "binding_id": "cbl-two",
                                        "channel": "CBL",
                                        "scale": {
                                            "kind": "linear",
                                            "minimum": 0.0,
                                            "maximum": second_maximum,
                                        },
                                    },
                                ],
                            }
                        ],
                    }
                ]
            }
        )

    verify_document_obligations(document(100.0, 10.0), obligations)
    with pytest.raises(ValueError, match="scale_maximum"):
        verify_document_obligations(document(10.0, 100.0), obligations)


def test_authority_f_planner_phrase_is_not_a_compiled_track_identity() -> None:
    """Captured planner prose cannot become authoritative semantic identity."""
    request = next(
        case["request"] for case in d4.load_cases(REPO_ROOT) if case["turn_id"] == "D4-C01:C01"
    )
    captured_plan = json.loads(
        (REPO_ROOT / "tests/fixtures/authority_f_captured_planner_task.json").read_text()
    )
    phrase = "Create track 'combo' (normal, 50 mm) with"
    assert phrase in captured_plan["section_tasks"][0]["requirements"][0]

    plan = _attach_compiled_requirements(
        _canonical_plan_from_wire(_PlannerWirePlan.model_validate(captured_plan)),
        compile_request_contract(request),
    )
    assert plan.requirement_compilation is not None
    assert plan.requirement_compilation.status.value == "EXTRACTION_COMPLETE"

    for task in plan.section_tasks:
        assert phrase not in {item.owner_ref for item in task.obligations}
        assert any(item.owner_ref == "combo" for item in task.obligations)

    captured_sections = json.loads(
        (REPO_ROOT / "tests/fixtures/d5_5j_qwen_smoke_003_report_sections.json").read_text()
    )["sections"]
    for section_payload, task in zip(captured_sections, plan.section_tasks, strict=True):
        action = ReconstructSectionAction.model_validate(section_payload)
        compiled = apply_compiled_requirements(action, task.obligations)
        validate_section_obligations(
            compiled,
            task.obligations,
            section_title=task.existing_section_hint,
        )


def test_compiled_worker_path_cannot_reenter_legacy_request_parsers() -> None:
    """Static boundary check keeps authoritative parsing before worker execution."""
    worker_body = inspect.getsource(CanonicalSectionWorker.compile)
    assert "apply_compiled_requirements" in worker_body
    assert "_normalize_reconstruct_track_dimensions" not in worker_body
    assert "_normalize_reconstruct_request_semantics" not in worker_body
    assert "_normalize_track_request_semantics" not in worker_body
    assert "_normalize_curve_request_semantics" not in worker_body
    assert "extract_supported_obligations" not in worker_body
    assert "compile_request_contract" not in worker_body
    assert worker_body.count("resolve_section_object_bindings(") == 1
    assert worker_body.count("object_bindings=object_bindings") >= 4

    canonical_worker_source = inspect.getsource(section_worker)
    assert "def _resolve_requirement_track(" not in canonical_worker_source
    assert "def _resolve_issue_track(" not in canonical_worker_source
    assert "def _resolve_issue_binding(" not in canonical_worker_source

    wire_fields = set(_PlannerWireSectionTask.model_fields)
    assert not {"obligations", "requirement_refs", "scope_id"} & wire_fields


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


def test_canonical_section_worker_ignores_uncompiled_planner_dimension_prose() -> None:
    """Planner task prose does not become downstream semantic authority."""
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
            "title": "Main Log",
            "tracks": [
                {
                    "semantic_id": "gr",
                    "kind": "normal",
                    "title": "Gamma Ray",
                    "width_mm": 30,
                    "bindings": [
                        {
                            "semantic_id": "gamma",
                            "channel": "GR",
                            "label": "Gamma Ray",
                            "scale": {
                                "kind": "linear",
                                "minimum": 0,
                                "maximum": 150,
                                "reverse": False,
                            },
                            "style": {
                                "color": "#111111",
                                "line_width": 1,
                                "line_style": "solid",
                            },
                        }
                    ],
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
    assert result.success is True
    assert result.stage_evidence.normalization == "PASS"


def test_canonical_section_worker_marks_obligation_failure_separately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An obligation failure records normalization success and obligation failure."""
    request = "Track gamma: normal, width 30 mm."
    response = {
        "action": "reconstruct",
        "section": {
            "source_candidate": "source-1",
            "title": "Main Log",
            "tracks": [
                {
                    "semantic_id": "gamma",
                    "kind": "normal",
                    "title": "Gamma Ray",
                    "width_mm": 30,
                    "bindings": [
                        {
                            "semantic_id": "gr",
                            "channel": "GR",
                            "label": "Gamma Ray",
                            "scale": {
                                "kind": "linear",
                                "minimum": 0,
                                "maximum": 150,
                                "reverse": False,
                            },
                            "style": {
                                "color": "#111111",
                                "line_width": 1,
                                "line_style": "solid",
                            },
                        }
                    ],
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
    context = _context_for_request(request)
    result = asyncio.run(
        CanonicalSectionWorker(backend=_StructuredFixtureBackend([response, response])).compile(
            task_index=0,
            context=context,
            document=_document(),
            authoritative_request=request,
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


def test_canonical_section_worker_propagates_async_cancellation() -> None:
    """Section-worker cancellation remains control flow, not a semantic failure."""

    class CancellingBackend:
        async def generate_structured(
            self,
            request: StructuredGenerationRequest,
            *,
            response_model: type[object],
        ) -> StructuredGenerationResult[object]:
            del request, response_model
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            CanonicalSectionWorker(backend=CancellingBackend()).compile(
                task_index=0,
                context=_context(),
                document=_document(),
                authoritative_request="Set the Gamma Ray scale to linear 0..150.",
                timeout_seconds=10,
            )
        )


def test_canonical_section_worker_retries_incomplete_reconstruction() -> None:
    """One missing ordered binding is repaired under its exact compiled slot."""
    base_context = _context()
    request = (
        "In the Main Log section.\nOn gamma: "
        "GR -> Gamma Ray, linear 0..150, #111111, width 1; "
        "CALI -> Caliper, linear 0..20, #111111, width 1."
    )
    task = base_context.plan.section_tasks[0].model_copy(
        update={"obligations": extract_supported_obligations(request)}
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
                    "semantic_id": "gamma",
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
            "title": "Main Log",
            "tracks": [
                {
                    "semantic_id": "gamma",
                    "kind": "normal",
                    "title": "Gamma Ray",
                    "bindings": [
                        {
                            "semantic_id": "gr",
                            "channel": "GR",
                            "label": "Gamma Ray",
                            "scale": {
                                "kind": "linear",
                                "minimum": 0,
                                "maximum": 150,
                                "reverse": False,
                            },
                            "style": {
                                "color": "#111111",
                                "line_width": 1,
                                "line_style": "solid",
                            },
                        }
                    ],
                },
            ],
        },
    }
    complete["section"]["tracks"][0]["bindings"].append(
        {
            "semantic_id": "cali",
            "channel": "CALI",
            "label": "Caliper",
            "scale": {"kind": "linear", "minimum": 0, "maximum": 20, "reverse": False},
            "style": {"color": "#111111", "line_width": 1, "line_style": "solid"},
        }
    )
    backend = _StructuredFixtureBackend([incomplete, complete])
    result = asyncio.run(
        CanonicalSectionWorker(backend=backend).compile(
            task_index=0,
            context=context,
            document=_document(),
            authoritative_request=request,
            timeout_seconds=10,
        )
    )
    assert result.success is True, result.diagnostics
    assert len(backend.requests) == 2
    correction = json.loads(backend.requests[1].user_prompt)["correction"]
    host_baseline = correction["host_applied_candidate"]
    canonical_baseline = json.dumps(
        host_baseline, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    assert (
        correction["repair_contract"]["baseline_sha256"]
        == hashlib.sha256(canonical_baseline.encode()).hexdigest()
    )
    assert len(correction["repair_contract"]["operations"]) == 1
    assert correction["repair_contract"]["operations"][0]["operation"] == "ADD"
    assert result.intent_fragment is not None
    assert [
        binding.channel
        for track in result.intent_fragment.sections[0].tracks
        for binding in track.bindings
    ] == ["GR", "CALI"]


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


def test_canonical_section_worker_bounds_unauthorized_correction_scope() -> None:
    """An invalid correction is reported without escaping as a harness exception."""
    request = (
        "In the Main Log section.\nOn gamma: "
        "GR -> Gamma Ray, linear 0..150, #111111, width 1; "
        "CALI -> Caliper, linear 0..20, #111111, width 1."
    )
    context = _context_for_request(request)
    incomplete = {
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
    unauthorized_correction = {
        "action": "reconstruct",
        "section": {
            "source_candidate": "source-1",
            "title": "Main Log",
            "tracks": [
                {
                    "semantic_id": "gamma",
                    "kind": "normal",
                    "title": "Gamma Ray",
                    "bindings": [
                        {
                            "semantic_id": "gr",
                            "channel": "GR",
                            "label": "Gamma Ray",
                            "scale": {
                                "kind": "linear",
                                "minimum": 0,
                                "maximum": 150,
                                "reverse": False,
                            },
                            "style": {
                                "color": "#111111",
                                "line_width": 1,
                                "line_style": "solid",
                            },
                        }
                    ],
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
    result = asyncio.run(
        CanonicalSectionWorker(
            backend=_StructuredFixtureBackend([incomplete, unauthorized_correction])
        ).compile(
            task_index=0,
            context=context,
            document=_document(),
            authoritative_request=request,
            timeout_seconds=10,
        )
    )
    assert result.success is False
    assert result.diagnostics[0].code == "worker_correction_scope_violation"
    assert result.stage_evidence.normalization == "PASS"
    assert result.stage_evidence.worker_obligation == "FAIL"
    assert result.stage_evidence.semantic_lowering == "NOT_REACHED"


def test_repair_matrix_r23_r28_rejects_raw_sibling_change_before_overlay() -> None:
    """Adding a missing binding cannot authorize a sibling width replacement."""
    request = (
        "In the Main Log section.\nTrack combo: normal, width 50 mm.\n\n"
        "On gamma:\n"
        'GR -> "Gamma Ray", linear 0..100, #111111, width 0.75.\n'
        'GR -> "Gamma Ray", linear 0..10, #2563eb dashed, width 0.65.'
    )
    initial = {
        "action": "reconstruct",
        "section": {
            "title": "Main Log",
            "source_candidate": "source-1",
            "tracks": [
                {
                    "semantic_id": "combo",
                    "kind": "normal",
                    "title": "Combo",
                    "width_mm": 50,
                    "bindings": [
                        {
                            "semantic_id": "combo-cali",
                            "channel": "CALI",
                            "label": "Caliper",
                            "scale": {"minimum": 0, "maximum": 20},
                        }
                    ],
                },
                {
                    "semantic_id": "gamma",
                    "kind": "normal",
                    "title": "Gamma Ray",
                    "bindings": [
                        {
                            "semantic_id": "gamma-main",
                            "channel": "GR",
                            "label": "Gamma Ray",
                            "scale": {"minimum": 0, "maximum": 100},
                        }
                    ],
                },
            ],
        },
    }
    unauthorized_correction = json.loads(json.dumps(initial))
    unauthorized_correction["section"]["tracks"][0]["width_mm"] = 60
    unauthorized_correction["section"]["tracks"][1]["bindings"].append(
        {
            "semantic_id": "gamma-zoom",
            "channel": "GR",
            "label": "Gamma Ray",
            "scale": {"kind": "linear", "minimum": 0, "maximum": 10, "reverse": False},
            "style": {"color": "#2563eb", "line_width": 0.65, "line_style": "dashed"},
        }
    )
    backend = _StructuredFixtureBackend([initial, unauthorized_correction])
    result = asyncio.run(
        CanonicalSectionWorker(backend=backend).compile(
            task_index=0,
            context=_context_for_request(request),
            document=_document(),
            authoritative_request=request,
            timeout_seconds=10,
        )
    )
    assert result.success is False
    assert result.diagnostics[0].code == "worker_correction_scope_violation"
    assert len(backend.requests) == 2
    correction = json.loads(backend.requests[1].user_prompt)["correction"]
    assert correction["host_applied_candidate"]["section"]["tracks"][0]["width_mm"] == 50
    assert any(
        operation["operation"] == "ADD" for operation in correction["repair_contract"]["operations"]
    )


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
