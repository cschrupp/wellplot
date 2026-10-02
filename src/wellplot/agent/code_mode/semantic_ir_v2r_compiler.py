"""Deterministic lowering for the reconciled semantic planner IR."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from ...capabilities import CapabilityRegistry
from .planner import (
    PlannerSemanticError,
    ReportTask,
    SectionTask,
    SemanticPlan,
    validate_semantic_plan,
)
from .semantic_ir_v2_registry import (
    SemanticLoweringRegistry,
    SemanticLoweringRule,
    create_builtin_semantic_lowering_registry,
)
from .semantic_ir_v2r import (
    AnnotationSemanticIntentV2R,
    CurveSemanticIntentV2R,
    ExtensionSemanticIntentV2R,
    FillSemanticIntentV2R,
    RasterSemanticIntentV2R,
    ReferenceSemanticIntentV2R,
    SectionSemanticIntentV2R,
    SemanticFeatureV2R,
    SemanticIRV2R,
)


class SemanticIRV2RCompilationErrorCode(StrEnum):
    """Stable provider-free compiler failure categories."""

    UNKNOWN_SEMANTIC = "unknown_semantic"
    UNKNOWN_CAPABILITY = "unknown_capability"
    AMBIGUOUS_PARENT = "ambiguous_parent"
    INVALID_PARENT_CHOICE = "invalid_parent_choice"
    INVALID_FEATURE_REFERENCE = "invalid_feature_reference"
    PLAN_VALIDATION_FAILED = "plan_validation_failed"


class SemanticIRV2RCompilationError(ValueError):
    """Bounded failure raised when semantic lowering is not faithful."""

    def __init__(self, code: SemanticIRV2RCompilationErrorCode, message: str) -> None:
        """Store a stable error code without host or provider details."""
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class CompiledSemanticPlanV2R:
    """Validated plan plus section-aligned semantics retained for downstream use."""

    semantic_plan: SemanticPlan
    reference_intents: tuple[ReferenceSemanticIntentV2R | None, ...]

    def __post_init__(self) -> None:
        """Require one preserved semantic slot per lowered section."""
        if len(self.reference_intents) != len(self.semantic_plan.section_tasks):
            raise ValueError("V2R reference semantics must align with section tasks.")

    @property
    def report_task(self) -> ReportTask | None:
        """Expose the validated report task for review projections."""
        return self.semantic_plan.report_task

    @property
    def section_tasks(self) -> tuple[SectionTask, ...]:
        """Expose validated section tasks without discarding V2R metadata."""
        return self.semantic_plan.section_tasks

    def to_semantic_plan(self) -> SemanticPlan:
        """Return the validated legacy projection for comparison only."""
        return self.semantic_plan


def compile_semantic_ir_v2r(
    intent: SemanticIRV2R | dict[str, object],
    *,
    registry: CapabilityRegistry,
    lowering_registry: SemanticLoweringRegistry | None = None,
) -> CompiledSemanticPlanV2R:
    """Lower intent into a validated plan without losing reference meaning."""
    validated = SemanticIRV2R.model_validate(intent)
    semantic_registry = (
        lowering_registry
        if lowering_registry is not None
        else create_builtin_semantic_lowering_registry()
    )

    report_task = None
    if validated.report_work is not None:
        report_rule = _resolve_rule(semantic_registry, "report.standard")
        report_ids = _close_capabilities(report_rule.capability_ids, report_rule, registry)
        report_task = ReportTask(
            goal=validated.report_work.goal,
            capability_ids=report_ids,
            requirements=validated.report_work.requirements,
            constraints=validated.report_work.constraints,
        )

    compiled_sections = tuple(
        _compile_section(section, registry=registry, lowering_registry=semantic_registry)
        for section in validated.sections
    )
    section_tasks = tuple(compiled.task for compiled in compiled_sections)
    plan = SemanticPlan(
        summary=validated.summary,
        report_task=report_task,
        section_tasks=section_tasks,
        unresolved_requirements=validated.unresolved_requirements,
    )
    try:
        validated_plan = validate_semantic_plan(SemanticPlan.model_validate(plan), registry)
        return CompiledSemanticPlanV2R(
            semantic_plan=validated_plan,
            reference_intents=tuple(compiled.reference_intent for compiled in compiled_sections),
        )
    except PlannerSemanticError as error:
        raise SemanticIRV2RCompilationError(
            SemanticIRV2RCompilationErrorCode.PLAN_VALIDATION_FAILED,
            "Lowered Semantic IR did not satisfy the existing SemanticPlan contract.",
        ) from error


def _compile_section(
    section: SectionSemanticIntentV2R,
    *,
    registry: CapabilityRegistry,
    lowering_registry: SemanticLoweringRegistry,
) -> _CompiledSection:
    """Compile one section while preserving feature and section order."""
    section_rule = _resolve_rule(lowering_registry, "section.log_plot")
    capability_ids = list(_close_capabilities(section_rule.capability_ids, section_rule, registry))

    if section.reference_intent is not None:
        reference_rule = SemanticLoweringRule(
            semantic_key="reference.intent",
            capability_ids=("track.reference",),
        )
        for capability_id in _close_capabilities(
            reference_rule.capability_ids, reference_rule, registry
        ):
            if capability_id not in capability_ids:
                capability_ids.append(capability_id)

    for feature in section.features:
        key = _feature_semantic_key(feature, section)
        rule = _resolve_rule(lowering_registry, key)
        if isinstance(feature, FillSemanticIntentV2R) and not _has_curve_target(
            feature.target_semantic_id, section.features
        ):
            raise SemanticIRV2RCompilationError(
                SemanticIRV2RCompilationErrorCode.INVALID_FEATURE_REFERENCE,
                "A fill semantic feature must target a curve feature in its section.",
            )
        for capability_id in _close_capabilities(rule.capability_ids, rule, registry):
            if capability_id not in capability_ids:
                capability_ids.append(capability_id)

    feature_requirements = tuple(
        requirement for feature in section.features for requirement in feature.requirements
    )
    feature_constraints = tuple(
        constraint for feature in section.features for constraint in feature.constraints
    )
    return _CompiledSection(
        task=SectionTask(
            goal=section.goal,
            capability_ids=tuple(capability_ids),
            existing_section_hint=section.existing_section_hint,
            source_hints=section.source_hints,
            requirements=section.requirements + feature_requirements,
            constraints=section.constraints + feature_constraints,
        ),
        reference_intent=section.reference_intent,
    )


@dataclass(frozen=True, slots=True)
class _CompiledSection:
    """Internal pair preserving one section task and its semantic ownership."""

    task: SectionTask
    reference_intent: ReferenceSemanticIntentV2R | None


def _feature_semantic_key(
    feature: SemanticFeatureV2R,
    section: SectionSemanticIntentV2R,
) -> str:
    """Resolve feature meaning without putting reference state on features."""
    targeted = (
        section.reference_intent is not None
        and section.reference_intent.kind == "reference_track"
        and section.reference_intent.target_semantic_id == feature.semantic_id
    )
    if isinstance(feature, CurveSemanticIntentV2R):
        return "curve.reference" if targeted else "curve.ordinary"
    if isinstance(feature, RasterSemanticIntentV2R):
        return "raster.reference" if targeted else "raster.ordinary"
    if isinstance(feature, FillSemanticIntentV2R):
        return "fill"
    if isinstance(feature, AnnotationSemanticIntentV2R):
        return "annotation"
    if isinstance(feature, ExtensionSemanticIntentV2R):
        return feature.semantic_key
    raise SemanticIRV2RCompilationError(
        SemanticIRV2RCompilationErrorCode.UNKNOWN_SEMANTIC,
        "Semantic feature kind has no registered lowering rule.",
    )


def _resolve_rule(
    registry: SemanticLoweringRegistry,
    semantic_key: str,
) -> SemanticLoweringRule:
    """Resolve a semantic rule or fail closed."""
    try:
        return registry.resolve(semantic_key)
    except KeyError as error:
        raise SemanticIRV2RCompilationError(
            SemanticIRV2RCompilationErrorCode.UNKNOWN_SEMANTIC,
            f"Unknown semantic lowering key: {semantic_key!r}.",
        ) from error


def _close_capabilities(
    capability_ids: Iterable[str],
    rule: SemanticLoweringRule,
    registry: CapabilityRegistry,
) -> tuple[str, ...]:
    """Apply unique parent closure without guessing among multiple parents."""
    ordered = list(capability_ids)
    selected = set(ordered)
    changed = True
    while changed:
        changed = False
        for child_id in tuple(ordered):
            try:
                spec = registry.get(child_id)
            except KeyError as error:
                raise SemanticIRV2RCompilationError(
                    SemanticIRV2RCompilationErrorCode.UNKNOWN_CAPABILITY,
                    "Semantic lowering referenced an unregistered capability.",
                ) from error
            allowed_parents = tuple(spec.allowed_parents)
            if not allowed_parents or selected.intersection(allowed_parents):
                continue
            explicit_parent = rule.parent_choice(child_id)
            if explicit_parent is not None:
                if explicit_parent not in allowed_parents:
                    raise SemanticIRV2RCompilationError(
                        SemanticIRV2RCompilationErrorCode.INVALID_PARENT_CHOICE,
                        "Semantic lowering selected an invalid parent.",
                    )
                parent_id = explicit_parent
            elif len(allowed_parents) == 1:
                parent_id = allowed_parents[0]
            else:
                raise SemanticIRV2RCompilationError(
                    SemanticIRV2RCompilationErrorCode.AMBIGUOUS_PARENT,
                    "Semantic lowering reached multiple meaningful parent choices.",
                )
            if parent_id not in selected:
                ordered.insert(ordered.index(child_id), parent_id)
                selected.add(parent_id)
                changed = True
                break
    return tuple(ordered)


def _has_curve_target(target_semantic_id: str, features: tuple[SemanticFeatureV2R, ...]) -> bool:
    """Check a fill target without inventing feature identity."""
    return any(
        isinstance(feature, CurveSemanticIntentV2R) and feature.semantic_id == target_semantic_id
        for feature in features
    )


__all__ = [
    "CompiledSemanticPlanV2R",
    "SemanticIRV2RCompilationError",
    "SemanticIRV2RCompilationErrorCode",
    "compile_semantic_ir_v2r",
]
