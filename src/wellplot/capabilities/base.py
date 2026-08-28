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
