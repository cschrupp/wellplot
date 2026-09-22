"""Deterministic CM-56R5 typed-input forensics tests."""

from __future__ import annotations

import inspect
import json

from scripts.cm56_typed_section_shadow import (
    _document,
    build_fixture_enricher,
    build_source_candidates,
    load_case_definitions,
)
from scripts.cm56r5_typed_input_forensics import (
    REPEATED_CHANNEL_ATTEMPTS,
    REPEATED_CHANNEL_CASE,
    RESPONSE_SCHEMA_SHA256,
    _only_explicit_block_diff,
    audit_explicit_semantics,
    build_explicit_semantics,
    build_pair_input,
)

from wellplot.agent.code_mode.planner import SectionTask, SemanticPlan
from wellplot.agent.code_mode.typed_section_worker import (
    TYPED_SECTION_SYSTEM_PROMPT,
    build_typed_section_input,
    serialize_typed_section_input,
)
from wellplot.capabilities import create_builtin_registry


def _case(case_id: str) -> dict[str, object]:
    return next(case for case in load_case_definitions() if case["case_id"] == case_id)


def _resolved(case: dict[str, object], task: SectionTask) -> object:
    return (
        build_fixture_enricher(case)
        .enrich(
            plan=SemanticPlan(summary=task.goal, section_tasks=(task,)),
            document=_document(),
            source_candidates=build_source_candidates(case),
        )
        .sections[0]
    )


def test_variant_a_exactly_reproduces_current_production_serializer() -> None:
    """A is byte-for-byte the existing typed worker payload."""
    case = _case("scalar_linear")
    task = SectionTask(
        goal=str(case["request"]),
        capability_ids=("section.log_plot", "track.normal", "binding.curve"),
        source_hints=("scalar-source",),
        requirements=("linear scale from 0 to 150",),
    )
    context = _resolved(case, task)
    pair = build_pair_input(task, section_context=context, registry=create_builtin_registry())
    expected_a = serialize_typed_section_input(
        build_typed_section_input(task, section_context=context, registry=create_builtin_registry())
    )
    assert pair.variant_a == expected_a


def test_a_and_b_share_the_same_task_context_and_b_is_only_an_explicit_addition() -> None:
    """B cannot change task/context facts or silently replace A."""
    case = _case("reverse_scale")
    task = SectionTask(
        goal=str(case["request"]),
        capability_ids=("section.log_plot", "track.normal", "binding.curve"),
        source_hints=("scalar-source",),
        requirements=("reverse direction enabled", "200 to 0"),
    )
    context = _resolved(case, task)
    pair = build_pair_input(task, section_context=context, registry=create_builtin_registry())
    assert pair.audit.valid
    assert _only_explicit_block_diff(pair.variant_a, pair.variant_b)
    left = json.loads(pair.variant_a)
    right = json.loads(pair.variant_b)
    right.pop("explicit_semantics")
    assert left == right


def test_explicit_semantics_have_executable_provenance() -> None:
    """Every B field is sourced from task/context or local identity."""
    case = _case("generic_raster")
    task = SectionTask(
        goal=str(case["request"]),
        capability_ids=("section.log_plot", "track.array", "binding.raster"),
        source_hints=("raster-source",),
        requirements=("generic raster", "x scale 0 to 100"),
    )
    context = _resolved(case, task)
    block, records = build_explicit_semantics(task, section_context=context)
    audit = audit_explicit_semantics(block, records, task=task, section_context=context)
    assert audit.valid
    assert audit.records
    assert {record.evidence_class for record in audit.records} <= {
        "task",
        "context",
        "diagnostic_local_identity",
    }


def test_repeated_channel_is_preserved_as_a_separate_planner_fact() -> None:
    """The forensic input keeps repeated channel identity and ordering."""
    case = _case(REPEATED_CHANNEL_CASE)
    task = SectionTask(
        goal=str(case["request"]),
        capability_ids=("section.log_plot", "track.normal", "binding.curve"),
        source_hints=("scalar-source",),
        requirements=("Bind CBL twice as two distinct views", "0 to 100", "0 to 10"),
    )
    context = _resolved(case, task)
    block, records = build_explicit_semantics(task, section_context=context)
    audit = audit_explicit_semantics(block, records, task=task, section_context=context)
    bindings = block.tracks[0].bindings
    assert audit.valid
    assert len(bindings) == 2
    assert [binding.channel for binding in bindings] == ["CBL", "CBL"]
    assert [binding.scale.minimum for binding in bindings] == [0.0, 0.0]
    assert [binding.scale.maximum for binding in bindings] == [100.0, 10.0]
    assert REPEATED_CHANNEL_ATTEMPTS == 10


def test_missing_task_fact_invalidates_b_before_provider_generation() -> None:
    """B never fills a missing scientific fact from an expected answer."""
    case = _case("vdl_sample_axis")
    task = SectionTask(
        goal="Create one new array track titled VDL from the raster source.",
        capability_ids=("section.log_plot", "track.array", "binding.raster"),
        source_hints=("raster-source",),
        requirements=("Bind VDL as a vdl raster",),
    )
    context = _resolved(case, task)
    block, records = build_explicit_semantics(task, section_context=context)
    audit = audit_explicit_semantics(block, records, task=task, section_context=context)
    assert audit.valid
    assert block.tracks[0].bindings[0].sample_axis is None
    assert all("source_origin" not in record.output_path for record in audit.records)


def test_b_input_contains_no_paths_or_expected_artifact_references() -> None:
    """Diagnostic payload construction remains independent of hidden gold."""
    from scripts import cm56r5_typed_input_forensics as harness

    source = "\n".join(
        inspect.getsource(function)
        for function in (harness.build_explicit_semantics, harness.build_pair_input)
    )
    assert "compile_contract" not in source
    assert "merged_intent" not in source
    assert "expected_sections" not in source
    assert "canonical_path" not in source
    assert TYPED_SECTION_SYSTEM_PROMPT
    assert (
        RESPONSE_SCHEMA_SHA256 == "93f1b7d26f1196a1105b733bc13a8de784da19f44eaaa990989d59abaf9fa2d4"
    )


def test_serialized_pair_and_audit_redact_path_shaped_task_text() -> None:
    """Evidence retains locators and hashes, never planner task prose."""
    case = _case("scalar_linear")
    posix_path = "/secret/well/input.dlis"
    windows_path = r"C:\\secret\\well\\input.dlis"
    task = SectionTask(
        goal=(
            "Create one new normal track titled Gamma Ray from the scalar source. "
            f"Do not persist {posix_path} or {windows_path}."
        ),
        capability_ids=("section.log_plot", "track.normal", "binding.curve"),
        source_hints=("scalar-source",),
        requirements=("linear scale from 0 to 150",),
    )
    context = _resolved(case, task)
    pair = build_pair_input(task, section_context=context, registry=create_builtin_registry())
    evidence_row = {
        "variant_a": pair.variant_a,
        "variant_b": pair.variant_b,
        "audit": pair.audit.model_dump(mode="json"),
    }
    serialized = json.dumps(evidence_row, sort_keys=True)
    assert posix_path not in serialized
    assert windows_path not in serialized
    assert all("evidence_text" not in type(record).model_fields for record in pair.audit.records)
    assert {record.evidence_path for record in pair.audit.records} >= {
        "task.goal_requirements_constraints",
        "context.source.candidate_id",
    }
