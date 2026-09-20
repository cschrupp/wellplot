"""CM-56 shadow-harness tests for real planner/enricher boundaries."""

from __future__ import annotations

from pathlib import Path

from scripts.cm56_typed_section_shadow import (
    CASE_PATH,
    SOURCE_ROOT,
    audit_input_sufficiency,
    build_fixture_enricher,
    build_source_candidates,
    case_corpus_sha256,
    classify_outcome,
    load_case_definitions,
)

from wellplot.agent.code_mode.planner import SectionTask, SemanticPlan
from wellplot.agent.code_mode.typed_section_worker import (
    build_typed_section_input,
    serialize_typed_section_input,
)
from wellplot.capabilities import create_builtin_registry
from wellplot.model.authoring import AuthoringDocumentSpec


def _document() -> AuthoringDocumentSpec:
    """Build a valid host document for enrichment inspection."""
    return AuthoringDocumentSpec(
        name="cm56",
        sections=[
            {
                "id": "existing",
                "title": "Existing",
                "tracks": [
                    {
                        "id": "existing-track",
                        "title": "Existing",
                        "kind": "normal",
                        "width_mm": 20,
                    }
                ],
            }
        ],
    )


def test_case_corpus_has_ten_frozen_cases_and_physical_sources() -> None:
    """The CM-56 live matrix is finite, named, and backed by real files."""
    cases = load_case_definitions()
    assert len(cases) == 10
    assert {case["case_id"] for case in cases} == {
        "cbl_continuity",
        "scalar_linear",
        "reverse_scale",
        "repeated_channel",
        "source_selection",
        "vdl_sample_axis",
        "log_scale",
        "tangential_scale",
        "generic_raster",
        "waveform",
    }
    assert CASE_PATH.is_file()
    for case in cases:
        for source in case["sources"]:
            assert (SOURCE_ROOT / source["filename"]).is_file()


def test_real_enricher_projects_cbl_sources_and_channels_without_discovery() -> None:
    """Fixture enrichment uses only the two explicit CBL candidates."""
    case = next(case for case in load_case_definitions() if case["case_id"] == "cbl_continuity")
    plan = SemanticPlan(
        summary="CM-56 CBL continuity",
        section_tasks=(
            SectionTask(
                goal="Main Pass",
                capability_ids=(
                    "section.log_plot",
                    "track.normal",
                    "track.reference",
                    "track.array",
                    "binding.curve",
                    "binding.raster",
                ),
                source_hints=("main",),
                requirements=("5000", "1200", "source origin 40"),
            ),
            SectionTask(
                goal="Repeat Pass",
                capability_ids=(
                    "section.log_plot",
                    "track.normal",
                    "track.reference",
                    "track.array",
                    "binding.curve",
                    "binding.raster",
                ),
                source_hints=("repeat",),
                requirements=("5000", "1200", "source origin 40"),
            ),
        ),
    )
    enriched = build_fixture_enricher(case).enrich(
        plan=plan,
        document=_document(),
        source_candidates=build_source_candidates(case),
    )
    assert [source.candidate_id for source in enriched.sections[0].sources] == ["main-source"]
    assert [source.candidate_id for source in enriched.sections[1].sources] == ["repeat-source"]
    assert {channel.mnemonic for channel in enriched.sections[0].sources[0].channels} >= {
        "CBL",
        "VDL",
    }
    assert all(
        source.canonical_path.startswith(str(Path(SOURCE_ROOT)))
        for section in enriched.sections
        for source in section.sources
    )


def test_input_audit_uses_serialized_task_and_selected_context() -> None:
    """Input sufficiency is checked before output evaluation."""
    case = next(case for case in load_case_definitions() if case["case_id"] == "cbl_continuity")
    task = SectionTask(
        goal="Main Pass",
        capability_ids=(
            "section.log_plot",
            "track.normal",
            "track.reference",
            "track.array",
            "binding.curve",
            "binding.raster",
        ),
        source_hints=("main",),
        requirements=("5000", "1200", "source origin 40"),
    )
    plan = SemanticPlan(summary="CM-56", section_tasks=(task,))
    enriched = build_fixture_enricher(case).enrich(
        plan=plan,
        document=_document(),
        source_candidates=build_source_candidates(case),
    )
    serialized = serialize_typed_section_input(
        build_typed_section_input(
            task,
            section_context=enriched.sections[0],
            registry=create_builtin_registry(),
        )
    )
    audit = audit_input_sufficiency(
        case,
        task=task,
        section_context=enriched.sections[0],
        serialized_input=serialized,
    )
    assert audit.sufficient
    assert not audit.missing_fact_ids


def test_classification_prioritizes_input_insufficiency_over_semantic_output() -> None:
    """Hidden required facts are reported before a provider/model diagnosis."""
    assert (
        classify_outcome(
            planner_success=True,
            enrichment_success=True,
            representability_gap=False,
            input_sufficient=False,
            typed_structured_valid=True,
            typed_context_valid=True,
            typed_compiler_valid=True,
            semantic_acceptance=False,
        )
        == "INPUT_INSUFFICIENT"
    )
    assert (
        classify_outcome(
            planner_success=True,
            enrichment_success=True,
            representability_gap=False,
            input_sufficient=True,
            typed_structured_valid=False,
            typed_context_valid=False,
            typed_compiler_valid=False,
            semantic_acceptance=False,
            provider_failure_category="invalid_response",
        )
        == "SCHEMA_COMPATIBILITY_FAILURE"
    )


def test_case_corpus_digest_is_stable() -> None:
    """The live runner can pin the exact case corpus bytes."""
    digest = case_corpus_sha256()
    assert len(digest) == 64
    assert digest == case_corpus_sha256()
