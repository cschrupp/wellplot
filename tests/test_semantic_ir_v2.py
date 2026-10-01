"""Provider-free SI-V2 responsibility, lowering, and regression tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError
from scripts.cm59a_system_reevaluation import load_case_definitions

from wellplot.agent.code_mode.planner import SemanticPlan
from wellplot.agent.code_mode.semantic_ir_v2 import SemanticIRV2
from wellplot.agent.code_mode.semantic_ir_v2_compiler import (
    SemanticIRV2CompilationError,
    SemanticIRV2CompilationErrorCode,
    compile_semantic_ir_v2,
)
from wellplot.agent.code_mode.semantic_ir_v2_registry import (
    SemanticLoweringRule,
    create_builtin_semantic_lowering_registry,
)
from wellplot.capabilities import CapabilitySpec, create_builtin_registry
from wellplot.model.intent import AuthoringDocumentIntent

FIXTURE_PATH = Path("tests/fixtures/semantic_ir_v2/cm59a_semantic_intents.json")


def _fixtures() -> list[dict[str, object]]:
    """Load the manually authored semantic corpus."""
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert payload["version"] == "si-v2.cm59a.semantic-intents.v1"
    return list(payload["cases"])


def _corpus_by_id() -> dict[str, dict[str, object]]:
    """Load the production-free CM-59A gold corpus."""
    return {str(case["case_id"]): case for case in load_case_definitions()}


def _compile_fixture(case: dict[str, object]) -> SemanticPlan:
    """Compile one semantic fixture using only the current registry."""
    intent_payload = {key: value for key, value in case.items() if key != "case_id"}
    return compile_semantic_ir_v2(
        SemanticIRV2.model_validate(intent_payload),
        registry=create_builtin_registry(),
    )


def test_all_cm59a_semantic_fixtures_compile_to_exact_gold_signatures() -> None:
    """Every fresh semantic interpretation preserves the frozen topology."""
    fixtures = _fixtures()
    corpus = _corpus_by_id()

    assert len(fixtures) == 24
    assert {str(item["case_id"]) for item in fixtures} == set(corpus)
    for fixture in fixtures:
        compiled = _compile_fixture(fixture)
        expected = corpus[str(fixture["case_id"])]
        actual_report = list(compiled.report_task.capability_ids) if compiled.report_task else []
        assert actual_report == list(expected["expected_report_capabilities"])
        assert [list(task.capability_ids) for task in compiled.section_tasks] == list(
            expected["expected_sections"]
        )


def test_compiler_output_is_a_valid_existing_semantic_plan() -> None:
    """Successful lowering passes both Pydantic and the current planner validator."""
    for fixture in _fixtures():
        plan = _compile_fixture(fixture)
        assert isinstance(plan, SemanticPlan)
        assert plan.model_dump(mode="python") == SemanticPlan.model_validate(
            plan.model_dump(mode="python")
        ).model_dump(mode="python")


def test_report_and_section_roots_are_host_owned() -> None:
    """Semantic intent does not expose or select mandatory capability roots."""
    fixture = next(item for item in _fixtures() if item["case_id"] == "cm59-mixed-xenon-21")
    serialized = json.dumps(fixture, sort_keys=True)

    assert "report.standard" not in serialized
    assert "section.log_plot" not in serialized
    plan = _compile_fixture(fixture)
    assert plan.report_task is not None
    assert plan.report_task.capability_ids == ("report.standard",)
    assert plan.section_tasks[0].capability_ids[0] == "section.log_plot"


def test_unique_parent_closure_is_generic_and_transitive() -> None:
    """A plugin leaf with one parent is closed without compiler changes."""

    class PluginArtifact(BaseModel):
        value: str = "plugin"

    registry = create_builtin_registry()
    registry.register(
        CapabilitySpec(
            capability_id="plugin.leaf",
            category="track",
            description="Test-only plugin leaf.",
            artifact_model=PluginArtifact,
            compiler=lambda _: AuthoringDocumentIntent(),
            allowed_parents=("track.normal",),
        )
    )
    lowering = create_builtin_semantic_lowering_registry().register(
        SemanticLoweringRule(
            semantic_key="plugin.leaf",
            capability_ids=("plugin.leaf",),
        )
    )
    intent = SemanticIRV2(
        summary="Plugin closure",
        sections=(
            {
                "kind": "log_plot",
                "goal": "Use a plugin leaf.",
                "features": (
                    {
                        "kind": "extension",
                        "semantic_id": "plugin-1",
                        "semantic_key": "plugin.leaf",
                    },
                ),
            },
        ),
    )

    plan = compile_semantic_ir_v2(intent, registry=registry, lowering_registry=lowering)
    assert plan.section_tasks[0].capability_ids == (
        "section.log_plot",
        "track.normal",
        "plugin.leaf",
    )


def test_multi_level_unique_parent_closure_is_deterministic() -> None:
    """Unique parent closure repeats until the existing section root is selected."""

    class PluginArtifact(BaseModel):
        value: str = "plugin"

    registry = create_builtin_registry()
    registry.register(
        CapabilitySpec(
            capability_id="plugin.deep_leaf",
            category="track",
            description="Test-only deep leaf.",
            artifact_model=PluginArtifact,
            compiler=lambda _: AuthoringDocumentIntent(),
            allowed_parents=("plugin.mid",),
        )
    )
    registry.register(
        CapabilitySpec(
            capability_id="plugin.mid",
            category="track",
            description="Test-only intermediate.",
            artifact_model=PluginArtifact,
            compiler=lambda _: AuthoringDocumentIntent(),
            allowed_parents=("section.log_plot",),
        )
    )
    lowering = create_builtin_semantic_lowering_registry().register(
        SemanticLoweringRule(
            semantic_key="plugin.deep_leaf",
            capability_ids=("plugin.deep_leaf",),
        )
    )
    intent = SemanticIRV2(
        summary="Deep plugin closure",
        sections=(
            {
                "kind": "log_plot",
                "goal": "Use a deep plugin leaf.",
                "features": (
                    {
                        "kind": "extension",
                        "semantic_id": "plugin-1",
                        "semantic_key": "plugin.deep_leaf",
                    },
                ),
            },
        ),
    )

    plan = compile_semantic_ir_v2(intent, registry=registry, lowering_registry=lowering)
    assert plan.section_tasks[0].capability_ids == (
        "section.log_plot",
        "plugin.mid",
        "plugin.deep_leaf",
    )


def test_plugin_ambiguous_parent_requires_explicit_resolution() -> None:
    """The compiler never chooses the first of multiple meaningful parents."""

    class PluginArtifact(BaseModel):
        value: str = "plugin"

    registry = create_builtin_registry()
    registry.register(
        CapabilitySpec(
            capability_id="plugin.ambiguous",
            category="binding",
            description="Test-only ambiguous leaf.",
            artifact_model=PluginArtifact,
            compiler=lambda _: AuthoringDocumentIntent(),
            allowed_parents=("track.normal", "track.reference"),
        )
    )
    base = create_builtin_semantic_lowering_registry()
    intent = SemanticIRV2(
        summary="Ambiguous plugin",
        sections=(
            {
                "kind": "log_plot",
                "goal": "Use an ambiguous plugin leaf.",
                "features": (
                    {
                        "kind": "extension",
                        "semantic_id": "plugin-1",
                        "semantic_key": "plugin.ambiguous",
                    },
                ),
            },
        ),
    )

    with pytest.raises(
        SemanticIRV2CompilationError,
        match="multiple meaningful parent choices",
    ) as error:
        compile_semantic_ir_v2(
            intent,
            registry=registry,
            lowering_registry=base.register(
                SemanticLoweringRule(
                    semantic_key="plugin.ambiguous",
                    capability_ids=("plugin.ambiguous",),
                )
            ),
        )
    assert error.value.code is SemanticIRV2CompilationErrorCode.AMBIGUOUS_PARENT

    resolved = base.register(
        SemanticLoweringRule(
            semantic_key="plugin.ambiguous",
            capability_ids=("plugin.ambiguous",),
            explicit_parent_choices=(("plugin.ambiguous", "track.reference"),),
        )
    )
    plan = compile_semantic_ir_v2(intent, registry=registry, lowering_registry=resolved)
    assert plan.section_tasks[0].capability_ids == (
        "section.log_plot",
        "track.reference",
        "plugin.ambiguous",
    )


def test_unknown_semantic_extension_fails_closed() -> None:
    """Unregistered semantic concepts cannot be guessed or silently dropped."""
    intent = SemanticIRV2(
        summary="Unknown extension",
        sections=(
            {
                "kind": "log_plot",
                "goal": "Use an unknown extension.",
                "features": (
                    {
                        "kind": "extension",
                        "semantic_id": "unknown-1",
                        "semantic_key": "plugin.unknown",
                    },
                ),
            },
        ),
    )

    with pytest.raises(SemanticIRV2CompilationError) as error:
        compile_semantic_ir_v2(intent, registry=create_builtin_registry())
    assert error.value.code is SemanticIRV2CompilationErrorCode.UNKNOWN_SEMANTIC


def test_duplicate_semantic_ids_and_invalid_fill_targets_fail_structurally() -> None:
    """The IR rejects identity collapse before any capability lowering."""
    duplicate = {
        "summary": "Duplicate features",
        "sections": (
            {
                "kind": "log_plot",
                "goal": "Duplicate semantic ids.",
                "features": (
                    {"kind": "curve", "semantic_id": "same"},
                    {"kind": "curve", "semantic_id": "same"},
                ),
            },
        ),
    }
    with pytest.raises(ValidationError, match="unique"):
        SemanticIRV2.model_validate(duplicate)

    invalid_fill = {
        "summary": "Invalid fill",
        "sections": (
            {
                "kind": "log_plot",
                "goal": "Use an invalid fill target.",
                "features": (
                    {
                        "kind": "fill",
                        "semantic_id": "fill-1",
                        "target_semantic_id": "missing-curve",
                    },
                ),
            },
        ),
    }
    with pytest.raises(ValidationError, match="target"):
        SemanticIRV2.model_validate(invalid_fill)


def test_wrong_category_lowering_fails_at_existing_plan_validation() -> None:
    """A plugin cannot smuggle a report capability into a section task."""
    lowering = create_builtin_semantic_lowering_registry().register(
        SemanticLoweringRule(
            semantic_key="plugin.bad_category",
            capability_ids=("report.standard",),
        )
    )
    intent = SemanticIRV2(
        summary="Wrong category",
        sections=(
            {
                "kind": "log_plot",
                "goal": "Use a wrong category.",
                "features": (
                    {
                        "kind": "extension",
                        "semantic_id": "bad-1",
                        "semantic_key": "plugin.bad_category",
                    },
                ),
            },
        ),
    )

    with pytest.raises(
        SemanticIRV2CompilationError,
        match="existing SemanticPlan contract",
    ) as error:
        compile_semantic_ir_v2(
            intent,
            registry=create_builtin_registry(),
            lowering_registry=lowering,
        )
    assert error.value.code is SemanticIRV2CompilationErrorCode.PLAN_VALIDATION_FAILED


def test_input_and_registries_are_not_mutated() -> None:
    """Repeated compilation is deterministic and side-effect free."""
    fixture = next(item for item in _fixtures() if item["case_id"] == "cm59-mixed-amber-24")
    original = copy.deepcopy(fixture)
    registry = create_builtin_registry()
    before = tuple(spec.capability_id for spec in registry)

    first = _compile_fixture(fixture)
    second = _compile_fixture(fixture)

    assert fixture == original
    assert tuple(spec.capability_id for spec in registry) == before
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_context_fields_and_multiplicity_survive_ir_round_trip() -> None:
    """Ordered semantic features and downstream context are preserved."""
    intent = SemanticIRV2(
        summary="Preserve context",
        sections=(
            {
                "kind": "log_plot",
                "goal": "Show two scalar instances.",
                "existing_section_hint": "the existing overview",
                "source_hints": ("main pass",),
                "requirements": ("Keep both distinct instances.",),
                "constraints": ("Do not merge them.",),
                "features": (
                    {
                        "kind": "curve",
                        "semantic_id": "first",
                        "requirements": ("First channel.",),
                    },
                    {
                        "kind": "curve",
                        "semantic_id": "second",
                        "requirements": ("Second channel.",),
                    },
                ),
            },
        ),
        unresolved_requirements=("Unsupported annotation detail.",),
    )
    restored = SemanticIRV2.model_validate(intent.model_dump(mode="python"))
    plan = compile_semantic_ir_v2(restored, registry=create_builtin_registry())

    assert restored == intent
    assert plan.section_tasks[0].source_hints == ("main pass",)
    assert plan.section_tasks[0].existing_section_hint == "the existing overview"
    assert plan.section_tasks[0].requirements == (
        "Keep both distinct instances.",
        "First channel.",
        "Second channel.",
    )
    assert plan.unresolved_requirements == ("Unsupported annotation detail.",)
    assert [feature.semantic_id for feature in restored.sections[0].features] == [
        "first",
        "second",
    ]


def test_schema_has_no_provider_or_host_mechanics_and_tags_are_required() -> None:
    """The provider-facing IR stays semantic and path-free."""
    schema_value = SemanticIRV2.model_json_schema()
    schema = json.dumps(schema_value, sort_keys=True)
    forbidden = {
        "provider",
        "endpoint",
        "api_key",
        "retry",
        "repair",
        "canonical_path",
        "source_path",
        "section_id",
        "track_id",
        "binding_id",
        "renderer",
        "matplotlib",
        "layout",
        "width_mm",
        "capability_ids",
        "allowed_parents",
    }
    assert not forbidden.intersection(schema)
    assert '"kind"' in schema
    for definition in schema_value["$defs"].values():
        properties = definition.get("properties", {})
        if "kind" in properties:
            assert "kind" in definition.get("required", [])


def test_fixture_payload_is_path_free_and_capability_topology_free() -> None:
    """Authored provider input contains no host paths or capability topology."""
    serialized = json.dumps(_fixtures(), sort_keys=True)
    forbidden = (
        "/home/",
        "/tmp/",
        "C:\\\\",
        "provider",
        "endpoint",
        "capability_ids",
        "allowed_parents",
        "track.normal",
        "binding.curve",
    )
    assert not any(token in serialized for token in forbidden)


def test_builtin_coverage_includes_every_planner_relevant_capability() -> None:
    """The corpus plus one provider-free fill fixture covers all built-ins."""
    corpus = _corpus_by_id()
    observed: set[str] = set()
    for fixture in _fixtures():
        plan = _compile_fixture(fixture)
        if plan.report_task:
            observed.update(plan.report_task.capability_ids)
        for task in plan.section_tasks:
            observed.update(task.capability_ids)

    fill = SemanticIRV2(
        summary="Fill coverage",
        sections=(
            {
                "kind": "log_plot",
                "goal": "Show a filled scalar response.",
                "features": (
                    {"kind": "curve", "semantic_id": "curve-1"},
                    {
                        "kind": "fill",
                        "semantic_id": "fill-1",
                        "target_semantic_id": "curve-1",
                    },
                ),
            },
        ),
    )
    fill_plan = compile_semantic_ir_v2(fill, registry=create_builtin_registry())
    observed.update(fill_plan.section_tasks[0].capability_ids)

    assert len(corpus) == 24
    assert {
        "report.standard",
        "section.log_plot",
        "track.normal",
        "track.reference",
        "track.array",
        "binding.curve",
        "binding.raster",
        "fill.curve",
        "track.annotation",
        "annotation.typed",
    } <= observed
