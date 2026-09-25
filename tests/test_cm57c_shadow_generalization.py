"""Deterministic CM-57C corpus and pre-live harness tests."""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest
import scripts.cm57c_shadow_generalization as cm57c
from pydantic import BaseModel
from scripts.cm56_typed_section_shadow import build_fixture_enricher, build_source_candidates

from wellplot.agent.code_mode.planner import SectionTask, SemanticPlan, SemanticPlanner
from wellplot.agent.code_mode.typed_section_worker import TypedSectionCompiler
from wellplot.agent.providers.base import ProviderMetrics, StructuredGenerationResult
from wellplot.capabilities import create_builtin_registry


class _ReplayBackend:
    """Return one case's production-shaped plan and semantic draft in memory."""

    def __init__(self, case: Mapping[str, object]) -> None:
        self.case = case
        expected_source = str(case["expected_sections"][0]["source_candidate"])
        source = next(
            source for source in case["sources"] if source["candidate_id"] == expected_source
        )
        task = SectionTask(
            goal=str(case["request"]),
            capability_ids=tuple(str(value) for value in case["expected_capabilities"]),
            source_hints=(str(source["labels"][0]),),
        )
        self.plan = SemanticPlan(
            summary="CM-57C in-memory production-path replay",
            section_tasks=(task,),
        )
        self.structured_calls = 0
        self.program_calls = 0

    async def generate_structured(
        self,
        request: object,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        del request
        self.structured_calls += 1
        if response_model is SemanticPlan:
            value = self.plan
        elif response_model is cm57c.SectionSemanticDraft:
            value = cm57c._gold_model(self.case)
        else:  # pragma: no cover - protects the test double from silent drift.
            raise AssertionError(f"Unexpected response model: {response_model!r}")
        return StructuredGenerationResult(value=value, metrics=ProviderMetrics())

    async def generate_program(self, request: object) -> object:
        del request
        self.program_calls += 1
        raise AssertionError("CM-57C must not use legacy program generation.")


def _case(case_id: str) -> Mapping[str, object]:
    return next(case for case in cm57c.load_case_definitions() if case["case_id"] == case_id)


def _complete_rows(cases: tuple[Mapping[str, object], ...]) -> list[dict[str, object]]:
    return [
        {
            "case_id": case["case_id"],
            "category": case["category"],
            "attempt_index": attempt,
            "authorized_checkpoint": cm57c.BASELINE_SHA,
            "pipeline_class": "SUCCESS",
            "scientific_acceptance": True,
            "unrequested_scientific_semantics": (),
        }
        for case in cases
        for attempt in range(cm57c.ATTEMPTS)
    ]


def test_corpus_is_unseen_and_passes_all_pre_live_audits() -> None:
    """Verify the new corpus passes deterministic anti-overlap audits."""
    cases = cm57c.load_case_definitions()

    audit = cm57c.audit_corpus(cases)

    assert audit["case_count"] == 16
    assert audit["old_case_id_overlap"] is False
    assert audit["old_request_overlap"] is False
    assert audit["semantic_tuple_overlap_count"] == 0


def test_prelive_report_is_provider_free_and_hash_locked() -> None:
    """Verify production provenance anchors without making provider calls."""
    report = cm57c.prelive_report()

    assert report["provider_calls"] == 0
    assert report["live_inference"] == "NOT_STARTED"
    assert report["response_schema_sha256"] == cm57c.RESPONSE_SCHEMA_SHA256
    assert report["metadata_projection_sha256"] == cm57c.EXPECTED_METADATA_SHA256
    assert report["prompt_hashes"]["base"] == cm57c.EXPECTED_BASE_PROMPT_SHA256
    assert report["prompt_hashes"]["request_only"] == cm57c.EXPECTED_PROMPT_SHA256[False]
    assert report["prompt_hashes"]["request_plus_metadata"] == cm57c.EXPECTED_PROMPT_SHA256[True]


def test_default_entrypoint_does_not_construct_a_provider(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify the default CLI path cannot construct a provider."""
    monkeypatch.setattr(
        cm57c,
        "_provider_configuration",
        lambda args: (_ for _ in ()).throw(AssertionError("provider construction")),
    )
    monkeypatch.setattr(sys, "argv", ["cm57c_shadow_generalization.py"])

    cm57c.main()

    report = json.loads(capsys.readouterr().out)
    assert report["provider_calls"] == 0
    assert report["live_inference"] == "NOT_STARTED"


def test_production_provider_input_excludes_case_gold_and_paths() -> None:
    """Verify provider serialization excludes evaluator gold and host paths."""
    case = _case("mixed_curve_raster_section")
    expected_source = str(case["expected_sections"][0]["source_candidate"])
    source = next(source for source in case["sources"] if source["candidate_id"] == expected_source)
    task = SectionTask(
        goal=str(case["request"]),
        capability_ids=tuple(str(value) for value in case["expected_capabilities"]),
        source_hints=(str(source["labels"][0]),),
    )
    enriched = build_fixture_enricher(case).enrich(
        plan=SemanticPlan(summary="input audit", section_tasks=(task,)),
        document=cm57c._document(),
        source_candidates=build_source_candidates(case),
    )
    provider_input = cm57c.build_typed_section_provider_input(
        task,
        authoritative_request=str(case["request"]),
        section_context=enriched.sections[0],
        registry=create_builtin_registry(),
    )
    serialized = cm57c.serialize_typed_section_provider_input(provider_input)

    assert "expected_sections" not in serialized
    assert "input_facts" not in serialized
    assert "mixed_curve_raster_section" not in serialized
    assert "canonical_path" not in serialized
    assert "scalar.las" not in serialized
    assert "main.dlis" not in serialized


def test_real_planner_enricher_typed_compiler_path_uses_no_legacy_program_call() -> None:
    """Exercise the real planner, enricher, and typed compiler path."""
    case = _case("mixed_curve_raster_section")
    backend = _ReplayBackend(case)
    registry = create_builtin_registry()
    planner = SemanticPlanner(backend=backend, registry=registry)
    compiler = TypedSectionCompiler(backend=backend, registry=registry)

    row = asyncio.run(
        cm57c.run_case_attempt(
            case,
            planner=planner,
            typed=compiler,
            registry=registry,
            attempt_index=0,
        )
    )

    assert row["pipeline_class"] == "SUCCESS"
    assert row["planner_capability_match"] is True
    assert row["input_sufficiency"]["sufficient"] is True
    assert row["typed_structured_valid"] is True
    assert row["typed_context_valid"] is True
    assert row["typed_compiler_valid"] is True
    assert row["scientific_acceptance"] is True
    assert backend.structured_calls == 2
    assert backend.program_calls == 0


def test_evaluator_includes_source_and_topology_checks_in_scientific_gate() -> None:
    """Ensure source and topology failures remain scientific gate failures."""
    case = _case("curve_linear_new_values")
    draft = cm57c._gold_model(case).model_copy(update={"source_candidate": "wrong-source"})

    evaluation = cm57c.evaluate_draft(draft, expected=case["expected_sections"][0])

    assert evaluation["scientific_acceptance"] is False
    assert evaluation["scientific_family_counts"]["source_selection"] == {
        "pass": 0,
        "fail": 1,
    }


def test_pipeline_failure_can_be_classified_without_input_audit() -> None:
    """Classify a planner failure even without provider-input evidence."""
    cases = cm57c.load_case_definitions()
    rows = _complete_rows(cases)
    rows[0]["pipeline_class"] = "PLANNER_FAILURE"

    assert cm57c._final_decision(rows, cases) == "GENERALIZATION_PIPELINE_FAILURE"


def test_population_integrity_rejects_duplicate_or_missing_rows() -> None:
    """Reject a population with duplicate and missing case-attempt keys."""
    cases = cm57c.load_case_definitions()
    rows = _complete_rows(cases)
    rows.pop()
    rows.append(dict(rows[0]))

    result = cm57c._population_integrity(rows, cases)

    assert result["complete"] is False
    assert "duplicate_case_attempt" in result["reasons"]
    assert "missing_or_unexpected_case_attempt" in result["reasons"]


def test_future_live_output_path_rejects_nonempty_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Reject non-empty future evidence rather than appending to it."""
    output = tmp_path / "cm57c-live-qwen.jsonl"
    output.write_text("existing\n", encoding="utf-8")
    monkeypatch.setattr(cm57c, "OUTPUT_PATH", output)

    with pytest.raises(RuntimeError, match="non-empty evidence path"):
        asyncio.run(cm57c._run_live(object()))
