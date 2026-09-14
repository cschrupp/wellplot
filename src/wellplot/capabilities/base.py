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
