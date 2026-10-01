"""Pure deterministic lowering from Semantic IR v2 to SemanticPlan."""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum

from ...capabilities import CapabilityRegistry
from .planner import (
    PlannerSemanticError,
    ReportTask,
    SectionTask,
    SemanticPlan,
    validate_semantic_plan,
)
from .semantic_ir_v2 import (
    AnnotationSemanticIntent,
    CurveSemanticIntent,
    ExtensionSemanticIntent,
    FillSemanticIntent,
    RasterSemanticIntent,
    SemanticFeatureV2,
    SemanticIRV2,
)
from .semantic_ir_v2_registry import (
    SemanticLoweringRegistry,
    SemanticLoweringRule,
    create_builtin_semantic_lowering_registry,
)


class SemanticIRV2CompilationErrorCode(StrEnum):
    """Stable provider-free compiler failure categories."""

    UNKNOWN_SEMANTIC = "unknown_semantic"
    UNKNOWN_CAPABILITY = "unknown_capability"
    AMBIGUOUS_PARENT = "ambiguous_parent"
    INVALID_PARENT_CHOICE = "invalid_parent_choice"
    INVALID_FEATURE_REFERENCE = "invalid_feature_reference"
    WRONG_TASK_CATEGORY = "wrong_task_category"
    PLAN_VALIDATION_FAILED = "plan_validation_failed"


class SemanticIRV2CompilationError(ValueError):
    """Bounded failure raised when semantic lowering cannot be faithful."""

    def __init__(self, code: SemanticIRV2CompilationErrorCode, message: str) -> None:
        """Store a stable code without provider or host implementation details."""
        self.code = code
        super().__init__(message)


def compile_semantic_ir_v2(
    intent: SemanticIRV2 | dict[str, object],
    *,
    registry: CapabilityRegistry,
    lowering_registry: SemanticLoweringRegistry | None = None,
) -> SemanticPlan:
    """Lower provider-neutral semantic intent into a validated SemanticPlan."""
    validated = SemanticIRV2.model_validate(intent)
    semantic_registry = (
        lowering_registry
        if lowering_registry is not None
        else create_builtin_semantic_lowering_registry()
    )

    report_task = None
    if validated.report is not None:
        report_rule = _resolve_rule(semantic_registry, "report.standard")
        report_ids = _close_capabilities(
            report_rule.capability_ids,
            report_rule,
            registry,
        )
        report_task = ReportTask(
            goal=validated.report.goal,
            capability_ids=report_ids,
            requirements=validated.report.requirements,
            constraints=validated.report.constraints,
        )

    section_tasks = tuple(
        _compile_section(
            section,
            registry=registry,
            lowering_registry=semantic_registry,
        )
        for section in validated.sections
    )
    plan = SemanticPlan(
        summary=validated.summary,
        report_task=report_task,
        section_tasks=section_tasks,
        unresolved_requirements=validated.unresolved_requirements,
    )
    try:
        return validate_semantic_plan(plan, registry)
    except PlannerSemanticError as error:
        raise SemanticIRV2CompilationError(
            SemanticIRV2CompilationErrorCode.PLAN_VALIDATION_FAILED,
            "Lowered Semantic IR did not satisfy the existing SemanticPlan contract.",
        ) from error


def _compile_section(
    section: object,
    *,
    registry: CapabilityRegistry,
    lowering_registry: SemanticLoweringRegistry,
) -> SectionTask:
    """Compile one ordered semantic section without mutating its input."""
    section_rule = _resolve_rule(lowering_registry, "section.log_plot")
    capability_ids = list(_close_capabilities(section_rule.capability_ids, section_rule, registry))
    for feature in section.features:  # type: ignore[union-attr]
        rule = _resolve_rule(
            lowering_registry,
            _feature_semantic_key(feature),
        )
        if isinstance(feature, FillSemanticIntent) and not _has_curve_target(
            feature.target_semantic_id,
            section.features,  # type: ignore[union-attr]
        ):
            raise SemanticIRV2CompilationError(
                SemanticIRV2CompilationErrorCode.INVALID_FEATURE_REFERENCE,
                "A fill semantic feature must target a curve feature in its section.",
            )
        for capability_id in _close_capabilities(rule.capability_ids, rule, registry):
            if capability_id not in capability_ids:
                capability_ids.append(capability_id)

    feature_requirements = tuple(
        requirement
        for feature in section.features  # type: ignore[union-attr]
        for requirement in feature.requirements
    )
    feature_constraints = tuple(
        constraint
        for feature in section.features  # type: ignore[union-attr]
        for constraint in feature.constraints
    )
    return SectionTask(
        goal=section.goal,  # type: ignore[union-attr]
        capability_ids=tuple(capability_ids),
        existing_section_hint=section.existing_section_hint,  # type: ignore[union-attr]
        source_hints=section.source_hints,  # type: ignore[union-attr]
        requirements=section.requirements + feature_requirements,  # type: ignore[union-attr]
        constraints=section.constraints + feature_constraints,  # type: ignore[union-attr]
    )


def _feature_semantic_key(feature: SemanticFeatureV2) -> str:
    """Map typed semantic meaning to a registry key, not a capability ID."""
    if isinstance(feature, CurveSemanticIntent):
        return "curve.reference" if feature.reference else "curve.ordinary"
    if isinstance(feature, RasterSemanticIntent):
        return "raster.reference" if feature.reference else "raster.ordinary"
    if isinstance(feature, FillSemanticIntent):
        return "fill"
    if isinstance(feature, AnnotationSemanticIntent):
        return "annotation"
    if isinstance(feature, ExtensionSemanticIntent):
        return feature.semantic_key
    raise SemanticIRV2CompilationError(
        SemanticIRV2CompilationErrorCode.UNKNOWN_SEMANTIC,
        "Semantic feature kind has no registered lowering rule.",
    )


def _resolve_rule(
    registry: SemanticLoweringRegistry,
    semantic_key: str,
) -> SemanticLoweringRule:
    """Resolve one semantic rule with a bounded error."""
    try:
        return registry.resolve(semantic_key)
    except KeyError as error:
        raise SemanticIRV2CompilationError(
            SemanticIRV2CompilationErrorCode.UNKNOWN_SEMANTIC,
            f"Unknown semantic lowering key: {semantic_key!r}.",
        ) from error


def _close_capabilities(
    capability_ids: Iterable[str],
    rule: object,
    registry: CapabilityRegistry,
) -> tuple[str, ...]:
    """Apply only unique or explicitly resolved parent closure."""
    ordered = list(capability_ids)
    selected = set(ordered)
    changed = True
    while changed:
        changed = False
        for child_id in tuple(ordered):
            try:
                spec = registry.get(child_id)
            except KeyError as error:
                raise SemanticIRV2CompilationError(
                    SemanticIRV2CompilationErrorCode.UNKNOWN_CAPABILITY,
                    "Semantic lowering referenced an unregistered capability.",
                ) from error
            allowed_parents = tuple(spec.allowed_parents)
            if not allowed_parents or selected.intersection(allowed_parents):
                continue
            explicit_parent = rule.parent_choice(child_id)
            if explicit_parent is not None:
                if explicit_parent not in allowed_parents:
                    raise SemanticIRV2CompilationError(
                        SemanticIRV2CompilationErrorCode.INVALID_PARENT_CHOICE,
                        "Semantic lowering selected a parent outside the registry contract.",
                    )
                parent_id = explicit_parent
            elif len(allowed_parents) == 1:
                parent_id = allowed_parents[0]
            else:
                raise SemanticIRV2CompilationError(
                    SemanticIRV2CompilationErrorCode.AMBIGUOUS_PARENT,
                    "Semantic lowering reached multiple meaningful parent choices.",
                )
            if parent_id not in selected:
                ordered.insert(ordered.index(child_id), parent_id)
                selected.add(parent_id)
                changed = True
                break
    return tuple(ordered)


def _has_curve_target(
    target_semantic_id: str,
    features: tuple[SemanticFeatureV2, ...],
) -> bool:
    """Check a fill target without inventing a binding or object identity."""
    return any(
        isinstance(feature, CurveSemanticIntent) and feature.semantic_id == target_semantic_id
        for feature in features
    )


__all__ = [
    "SemanticIRV2CompilationError",
    "SemanticIRV2CompilationErrorCode",
    "compile_semantic_ir_v2",
]
