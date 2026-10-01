"""Immutable, registry-driven semantic lowering declarations."""

from __future__ import annotations

from dataclasses import dataclass


def _nonempty_tuple(values: tuple[str, ...], field_name: str) -> None:
    """Validate immutable declaration sequences."""
    if not isinstance(values, tuple) or any(not value.strip() for value in values):
        raise TypeError(f"{field_name} must be a tuple of non-empty strings.")


@dataclass(frozen=True, slots=True)
class SemanticLoweringRule:
    """Map one semantic concept to existing capability types."""

    semantic_key: str
    capability_ids: tuple[str, ...]
    explicit_parent_choices: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        """Reject mutable or ambiguous declaration data."""
        if not isinstance(self.semantic_key, str) or not self.semantic_key.strip():
            raise ValueError("Semantic lowering keys must be non-empty.")
        _nonempty_tuple(self.capability_ids, "capability_ids")
        if len(self.capability_ids) != len(set(self.capability_ids)):
            raise ValueError("Semantic lowering capability IDs must be unique.")
        keys = {capability_id for capability_id, _ in self.explicit_parent_choices}
        if len(keys) != len(self.explicit_parent_choices):
            raise ValueError("Semantic lowering parent choices must be unique.")
        for capability_id, parent_id in self.explicit_parent_choices:
            if not capability_id.strip() or not parent_id.strip():
                raise ValueError("Semantic lowering parent choices must be non-empty.")

    def parent_choice(self, capability_id: str) -> str | None:
        """Return an explicit parent selected by semantic meaning, if any."""
        for child_id, parent_id in self.explicit_parent_choices:
            if child_id == capability_id:
                return parent_id
        return None


@dataclass(frozen=True, slots=True)
class SemanticLoweringRegistry:
    """Persistent registry that can be extended without compiler changes."""

    rules: tuple[SemanticLoweringRule, ...] = ()

    def register(self, rule: SemanticLoweringRule) -> SemanticLoweringRegistry:
        """Return a new registry containing one plugin or built-in rule."""
        if any(existing.semantic_key == rule.semantic_key for existing in self.rules):
            raise ValueError(f"Semantic lowering key is already registered: {rule.semantic_key!r}.")
        return SemanticLoweringRegistry(self.rules + (rule,))

    def resolve(self, semantic_key: str) -> SemanticLoweringRule:
        """Resolve one semantic concept or fail without fallback semantics."""
        for rule in self.rules:
            if rule.semantic_key == semantic_key:
                return rule
        raise KeyError(f"Unknown semantic lowering key: {semantic_key!r}.")


def create_builtin_semantic_lowering_registry() -> SemanticLoweringRegistry:
    """Create the initial data-driven lowering declarations."""
    registry = SemanticLoweringRegistry()
    for rule in (
        SemanticLoweringRule(
            semantic_key="report.standard",
            capability_ids=("report.standard",),
        ),
        SemanticLoweringRule(
            semantic_key="section.log_plot",
            capability_ids=("section.log_plot",),
        ),
        SemanticLoweringRule(
            semantic_key="curve.ordinary",
            capability_ids=("track.normal", "binding.curve"),
        ),
        SemanticLoweringRule(
            semantic_key="curve.reference",
            capability_ids=("track.reference", "track.normal", "binding.curve"),
        ),
        SemanticLoweringRule(
            semantic_key="raster.ordinary",
            capability_ids=("track.array", "binding.raster"),
        ),
        SemanticLoweringRule(
            semantic_key="raster.reference",
            capability_ids=("track.reference", "track.array", "binding.raster"),
        ),
        SemanticLoweringRule(
            semantic_key="fill",
            capability_ids=("fill.curve",),
        ),
        SemanticLoweringRule(
            semantic_key="annotation",
            capability_ids=("track.annotation", "annotation.typed"),
        ),
    ):
        registry = registry.register(rule)
    return registry


__all__ = [
    "SemanticLoweringRegistry",
    "SemanticLoweringRule",
    "create_builtin_semantic_lowering_registry",
]
