"""Produce provider-free SI-V2 representability and responsibility metrics."""

from __future__ import annotations

import json
import statistics
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from scripts.cm59a_system_reevaluation import load_case_definitions
from wellplot.agent.code_mode.planner import SemanticPlan
from wellplot.agent.code_mode.semantic_ir_v2 import SemanticIRV2
from wellplot.agent.code_mode.semantic_ir_v2_compiler import compile_semantic_ir_v2
from wellplot.capabilities import create_builtin_registry

FIXTURE_PATH = Path("tests/fixtures/semantic_ir_v2/cm59a_semantic_intents.json")


def _schema_metrics(model: type[Any]) -> dict[str, int]:
    """Count stable structural properties of one Pydantic schema."""
    schema = model.model_json_schema()
    canonical = json.dumps(schema, sort_keys=True, separators=(",", ":"))

    def walk(value: object, depth: int = 0) -> tuple[int, int, int, int, int]:
        """Return object, array, anyOf, required, and maximum-depth counts."""
        if not isinstance(value, Mapping):
            return 0, 0, 0, 0, depth
        objects = int(value.get("type") == "object")
        arrays = int(value.get("type") == "array")
        any_of = len(value.get("anyOf", ())) if isinstance(value.get("anyOf"), list) else 0
        required = len(value.get("required", ())) if isinstance(value.get("required"), list) else 0
        maximum_depth = depth
        for child in value.values():
            child_counts = walk(child, depth + 1)
            objects += child_counts[0]
            arrays += child_counts[1]
            any_of += child_counts[2]
            required += child_counts[3]
            maximum_depth = max(maximum_depth, child_counts[4])
        return objects, arrays, any_of, required, maximum_depth

    objects, arrays, any_of, required, maximum_depth = walk(schema)
    return {
        "canonical_schema_bytes": len(canonical.encode("utf-8")),
        "defs": len(schema.get("$defs", {})),
        "refs": canonical.count('"$ref"'),
        "any_of": any_of,
        "object_nodes": objects,
        "array_nodes": arrays,
        "required_property_count": required,
        "top_level_model_fields": len(model.model_fields),
        "maximum_nesting_depth": maximum_depth,
    }


def _load_fixture_cases() -> list[dict[str, object]]:
    """Load the authored semantic fixtures."""
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return list(payload["cases"])


def _summarize(values: list[int]) -> dict[str, float | int]:
    """Return the requested distribution statistics."""
    return {
        "minimum": min(values),
        "maximum": max(values),
        "mean": round(statistics.mean(values), 3),
        "median": statistics.median(values),
    }


def _responsibility_metrics(
    fixtures: list[dict[str, object]],
    corpus: dict[str, dict[str, object]],
) -> dict[str, object]:
    """Compare capability-list responsibility with semantic-feature responsibility."""
    current_semantic_choices: list[int] = []
    current_structural_ids: list[int] = []
    current_roots: list[int] = []
    current_closure: list[int] = []
    ir_semantic_choices: list[int] = []
    ir_structural_ids: list[int] = []
    ir_roots: list[int] = []
    ir_closure: list[int] = []
    ir_deterministic_decisions: list[int] = []

    registry = create_builtin_registry()
    for fixture in fixtures:
        case_id = str(fixture["case_id"])
        expected = corpus[case_id]
        current_ids: list[str] = list(expected["expected_report_capabilities"])
        current_ids.extend(
            capability_id for section in expected["expected_sections"] for capability_id in section
        )
        current_semantic_choices.append(len(current_ids))
        current_structural_ids.append(len(current_ids))
        current_roots.append(
            sum(
                capability_id in {"report.standard", "section.log_plot"}
                for capability_id in current_ids
            )
        )
        current_closure.append(
            sum(bool(registry.get(capability_id).allowed_parents) for capability_id in current_ids)
        )

        intent = SemanticIRV2.model_validate(
            {key: value for key, value in fixture.items() if key != "case_id"}
        )
        feature_count = sum(len(section.features) for section in intent.sections)
        semantic_choice_count = feature_count + int(intent.report is not None)
        ir_semantic_choices.append(semantic_choice_count)
        ir_structural_ids.append(0)
        ir_roots.append(0)
        ir_closure.append(0)
        compiled = compile_semantic_ir_v2(intent, registry=registry)
        deterministic_count = len(compiled.section_tasks)
        deterministic_count += (
            len(compiled.report_task.capability_ids) if compiled.report_task else 0
        )
        deterministic_count += sum(
            len(section.capability_ids) for section in compiled.section_tasks
        )
        ir_deterministic_decisions.append(deterministic_count)

    return {
        "current_semantic_choices": _summarize(current_semantic_choices),
        "current_structural_capability_ids": _summarize(current_structural_ids),
        "current_mandatory_roots": _summarize(current_roots),
        "current_parent_closure_decisions": _summarize(current_closure),
        "semantic_ir_v2_choices": _summarize(ir_semantic_choices),
        "semantic_ir_v2_structural_capability_ids": _summarize(ir_structural_ids),
        "semantic_ir_v2_mandatory_roots": _summarize(ir_roots),
        "semantic_ir_v2_parent_closure_decisions": _summarize(ir_closure),
        "semantic_ir_v2_deterministic_lowering_ids": _summarize(ir_deterministic_decisions),
    }


def build_report() -> dict[str, object]:
    """Build the complete provider-free SI-V2 report."""
    fixtures = _load_fixture_cases()
    corpus = {str(case["case_id"]): case for case in load_case_definitions()}
    registry = create_builtin_registry()
    exact_matches = 0
    for fixture in fixtures:
        intent = SemanticIRV2.model_validate(
            {key: value for key, value in fixture.items() if key != "case_id"}
        )
        compiled = compile_semantic_ir_v2(intent, registry=registry)
        expected = corpus[str(fixture["case_id"])]
        actual_report = list(compiled.report_task.capability_ids) if compiled.report_task else []
        actual_sections = [list(task.capability_ids) for task in compiled.section_tasks]
        if actual_report == list(
            expected["expected_report_capabilities"]
        ) and actual_sections == list(expected["expected_sections"]):
            exact_matches += 1
    return {
        "fixture_count": len(fixtures),
        "cm59a_exact_signature_matches": exact_matches,
        "schema_metrics": {
            "SemanticPlan": _schema_metrics(SemanticPlan),
            "SemanticIRV2": _schema_metrics(SemanticIRV2),
            "historical_PlanIntent_v1": {
                "canonical_schema_bytes": 1757,
                "defs": 2,
                "refs": 2,
                "top_level_model_fields": 13,
                "source": "historical supplied evidence",
            },
        },
        "responsibility_metrics": _responsibility_metrics(fixtures, corpus),
    }


if __name__ == "__main__":
    print(json.dumps(build_report(), indent=2, sort_keys=True))
