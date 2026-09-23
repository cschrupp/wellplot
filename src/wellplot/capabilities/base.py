###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Capability declarations for the extensible Wellplot authoring engine.

The capability layer is intentionally independent from LangGraph and MCP.
It describes what Wellplot can represent and how a compiled capability payload
is converted into the provider-neutral :class:`AuthoringDocumentIntent` IR.

Architectural invariant:
    Adding a new track/section type must not require editing the orchestration
    graph. Register a capability instead.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

from ..model.intent import AuthoringDocumentIntent

CapabilityCategory = Literal[
    "report",
    "section",
    "track",
    "binding",
    "fill",
    "annotation",
]

CapabilityCompiler = Callable[[BaseModel], AuthoringDocumentIntent]
CapabilityHandler = Callable[[BaseModel], object]

_MAX_SEMANTIC_MAPPINGS = 8
_MAX_SEMANTIC_LANGUAGE_PATTERNS = 8
_MAX_SEMANTIC_DISTINCTIONS = 4
_SEMANTIC_TARGET_PATH = r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+"


@dataclass(frozen=True, slots=True)
class CapabilitySemanticMapping:
    """Immutable developer-authored guidance for one semantic concept."""

    concept: str
    language_patterns: tuple[str, ...]
    targets: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        """Validate one capability-owned semantic mapping declaration."""
        _validate_nonempty_text(self.concept, "concept")
        _require_tuple(self.language_patterns, "language_patterns")
        _require_tuple(self.targets, "targets")
        if not self.language_patterns:
            raise ValueError("Capability semantic mappings require a language pattern.")
        if not self.targets:
            raise ValueError("Capability semantic mappings require a target.")
        if len(self.language_patterns) > _MAX_SEMANTIC_LANGUAGE_PATTERNS:
            raise ValueError(
                "Capability semantic mappings support at most "
                f"{_MAX_SEMANTIC_LANGUAGE_PATTERNS} language patterns."
            )

        normalized_patterns: set[str] = set()
        for pattern in self.language_patterns:
            _validate_nonempty_text(pattern, "language pattern")
            normalized_pattern = pattern.strip().casefold()
            if normalized_pattern in normalized_patterns:
                raise ValueError(f"Duplicate capability language pattern: {pattern!r}.")
            normalized_patterns.add(normalized_pattern)

        target_paths: set[str] = set()
        for target in self.targets:
            if not isinstance(target, tuple) or len(target) != 2:
                raise TypeError("Capability semantic targets must be (path, value cue) tuples.")
            target_path, value_cue = target
            _validate_nonempty_text(target_path, "target path")
            _validate_nonempty_text(value_cue, "target value cue")
            if re.fullmatch(_SEMANTIC_TARGET_PATH, target_path) is None:
                raise ValueError(f"Invalid capability semantic target path: {target_path!r}.")
            if target_path in target_paths:
                raise ValueError(f"Duplicate capability semantic target path: {target_path!r}.")
            target_paths.add(target_path)


@dataclass(frozen=True, slots=True)
class CapabilitySemanticMetadata:
    """Immutable optional semantic guidance owned by one capability."""

    purpose: str
    mappings: tuple[CapabilitySemanticMapping, ...] = ()
    distinctions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate metadata structure without interpreting semantic targets."""
        _validate_nonempty_text(self.purpose, "purpose")
        _require_tuple(self.mappings, "mappings")
        _require_tuple(self.distinctions, "distinctions")
        if len(self.mappings) > _MAX_SEMANTIC_MAPPINGS:
            raise ValueError(
                f"Capability semantic metadata supports at most {_MAX_SEMANTIC_MAPPINGS} mappings."
            )
        if len(self.distinctions) > _MAX_SEMANTIC_DISTINCTIONS:
            raise ValueError(
                "Capability semantic metadata supports at most "
                f"{_MAX_SEMANTIC_DISTINCTIONS} distinctions."
            )

        concepts: set[str] = set()
        language_patterns: set[str] = set()
        for mapping in self.mappings:
            if not isinstance(mapping, CapabilitySemanticMapping):
                raise TypeError("Capability semantic mappings must use CapabilitySemanticMapping.")
            concept_key = mapping.concept.strip().casefold()
            if concept_key in concepts:
                raise ValueError(f"Duplicate capability semantic concept: {mapping.concept!r}.")
            concepts.add(concept_key)
            for pattern in mapping.language_patterns:
                pattern_key = pattern.strip().casefold()
                if pattern_key in language_patterns:
                    raise ValueError(f"Duplicate capability language pattern: {pattern!r}.")
                language_patterns.add(pattern_key)

        distinctions: set[str] = set()
        for distinction in self.distinctions:
            _validate_nonempty_text(distinction, "distinction")
            distinction_key = distinction.strip().casefold()
            if distinction_key in distinctions:
                raise ValueError(f"Duplicate capability semantic distinction: {distinction!r}.")
            distinctions.add(distinction_key)


@dataclass(frozen=True, slots=True)
class CapabilitySpec:
    """One discoverable Wellplot authoring capability.

    ``artifact_model`` is the typed output contract used by the worker that
    compiles this capability. ``compiler`` is deterministic and converts that
    validated artifact into the existing provider-neutral document intent.

    The planner receives only ``planning_descriptor()``. Section workers receive
    the richer ``worker_descriptor()`` for the capabilities selected by the
    planner. This prevents the context window from growing linearly with every
    Wellplot extension.
    """

    capability_id: str
    category: CapabilityCategory
    description: str
    artifact_model: type[BaseModel]
    compiler: CapabilityCompiler
    aliases: tuple[str, ...] = ()
    allowed_parents: tuple[str, ...] = ()
    source_kinds: tuple[str, ...] = ()
    planning_hints: tuple[str, ...] = ()
    schema_version: str = "1"
    metadata: dict[str, str] = field(default_factory=dict)
    arguments_model: type[BaseModel] | None = None
    handler: CapabilityHandler | None = None
    worker_hints: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()
    semantic_metadata: CapabilitySemanticMetadata | None = None

    def __post_init__(self) -> None:
        """Validate aliases and the optional all-or-nothing v2 contract."""
        _validate_aliases(self.capability_id, self.aliases)
        has_arguments_model = self.arguments_model is not None
        has_handler = self.handler is not None
        if has_arguments_model != has_handler:
            raise ValueError("Capability v2 requires arguments_model and handler together.")
        if self.arguments_model is not None and (
            not isinstance(self.arguments_model, type)
            or not issubclass(self.arguments_model, BaseModel)
        ):
            raise TypeError("Capability arguments_model must be a Pydantic BaseModel type.")
        if self.handler is not None and not callable(self.handler):
            raise TypeError("Capability handler must be callable.")
        _validate_text_sequence(self.worker_hints, "worker_hints")
        _validate_text_sequence(self.examples, "examples")
        if self.semantic_metadata is not None and not isinstance(
            self.semantic_metadata, CapabilitySemanticMetadata
        ):
            raise TypeError("Capability semantic_metadata must use CapabilitySemanticMetadata.")

    @property
    def supports_v2(self) -> bool:
        """Return whether this declaration exposes the complete v2 contract."""
        return self.arguments_model is not None and self.handler is not None

    def planning_descriptor(self) -> dict[str, object]:
        """Return a compact semantic descriptor for the document planner."""
        return {
            "id": self.capability_id,
            "category": self.category,
            "description": self.description,
            "aliases": list(self.aliases),
            "allowed_parents": list(self.allowed_parents),
            "source_kinds": list(self.source_kinds),
            "planning_hints": list(self.planning_hints),
            "schema_version": self.schema_version,
        }

    def worker_descriptor(self) -> dict[str, object]:
        """Return the descriptor and typed schema used by a scoped worker."""
        descriptor = self.planning_descriptor()
        descriptor["artifact_schema"] = self.artifact_model.model_json_schema()
        return descriptor

    def code_mode_worker_descriptor(self) -> dict[str, object]:
        """Return deterministic declarative metadata for a v2 worker.

        The handler is deliberately retained only on the host-side capability
        object. It is never serialized, introspected, or included in worker
        context.
        """
        if not self.supports_v2:
            raise ValueError(f"Capability {self.capability_id!r} does not declare the v2 contract.")
        assert self.arguments_model is not None
        return {
            "id": self.capability_id,
            "category": self.category,
            "description": self.description,
            "aliases": list(self.aliases),
            "allowed_parents": list(self.allowed_parents),
            "source_kinds": list(self.source_kinds),
            "worker_hints": list(self.worker_hints),
            "examples": list(self.examples),
            "arguments_schema": self.arguments_model.model_json_schema(),
        }


def _validate_aliases(capability_id: str, aliases: tuple[str, ...]) -> None:
    """Reject empty, duplicate, or redundant aliases at declaration time."""
    capability_key = capability_id.strip().casefold()
    seen: set[str] = set()
    for alias in aliases:
        if not isinstance(alias, str) or not alias.strip():
            raise ValueError("Capability aliases must be non-empty strings.")
        alias_key = alias.strip().casefold()
        if alias_key == capability_key:
            raise ValueError(
                f"Capability alias {alias!r} redundantly repeats capability id {capability_id!r}."
            )
        if alias_key in seen:
            raise ValueError(f"Capability alias {alias!r} is duplicated.")
        seen.add(alias_key)


def _validate_text_sequence(values: tuple[str, ...], field_name: str) -> None:
    """Require worker hints and examples to remain stable non-empty strings."""
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Capability {field_name} must contain non-empty strings.")


def _require_tuple(value: object, field_name: str) -> None:
    """Reject mutable containers instead of retaining caller-owned references."""
    if not isinstance(value, tuple):
        raise TypeError(f"Capability semantic {field_name} must be a tuple.")


def _validate_nonempty_text(value: object, field_name: str) -> None:
    """Require exact, non-blank declaration text without normalizing it."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Capability semantic {field_name} must be a non-empty string.")
