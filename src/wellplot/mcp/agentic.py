###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Opt-in MCP edge for graph-compiled natural-language authoring."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from ..agent.graph import (
    build_graph_authoring_context,
    execute_document_reconstruction,
    execute_document_revision,
)
from ..authoring_service import AuthoringService
from . import service


class CompiledGraphProtocol(Protocol):
    """Minimal graph interface required by high-level authoring operations."""

    async def ainvoke(self, input: dict[str, object]) -> dict[str, object]:
        """Compile one graph state into typed artifacts and merged intent."""


class GraphAuthoringToolResult(BaseModel):
    """Compact evidence returned by one high-level graph authoring tool."""

    model_config = ConfigDict(extra="forbid")

    logfile_path: str
    mode: Literal["reconstruct", "revise"]
    success: bool
    changed: bool
    rolled_back: bool
    plan_summary: str | None = None
    section_ids: list[str]
    errors: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class GraphAuthoringMcpOperations:
    """High-level graph operations configured at MCP server startup.

    The compiled graph is injected by the hosting application. Tool arguments
    never carry provider credentials, model configuration, or internal source
    context. The adapter rebuilds deterministic context for every request.
    """

    graph: CompiledGraphProtocol
    root: Path

    @classmethod
    def create(
        cls,
        *,
        graph: CompiledGraphProtocol,
        root: str | Path,
    ) -> GraphAuthoringMcpOperations:
        """Create operations bound to one resolved server root."""
        return cls(graph=graph, root=Path(root).expanduser().resolve())

    async def build(
        self,
        *,
        logfile_path: str,
        request: str,
    ) -> GraphAuthoringToolResult:
        """Build a document from one natural-language request."""
        context = build_graph_authoring_context(logfile_path, root=self.root)
        authoring = AuthoringService(context.document)
        before = authoring.document.model_dump(mode="json")
        result = await execute_document_reconstruction(
            self.graph,  # type: ignore[arg-type]
            authoring,
            request=request,
            source_manifest=context.source_manifest,
            available_channels=context.available_channels,
        )
        return self._finalize(
            logfile_path=context.logfile_path,
            authoring=authoring,
            before=before,
            mode="reconstruct",
            success=result.success,
            rolled_back=result.rolled_back,
            plan_summary=result.reconstruction.plan.summary,
            errors=result.errors,
        )

    async def revise(
        self,
        *,
        logfile_path: str,
        request: str,
    ) -> GraphAuthoringToolResult:
        """Revise a document from one natural-language request."""
        context = build_graph_authoring_context(logfile_path, root=self.root)
        authoring = AuthoringService(context.document)
        before = authoring.document.model_dump(mode="json")
        result = await execute_document_revision(
            self.graph,  # type: ignore[arg-type]
            authoring,
            request=request,
            source_manifest=context.source_manifest,
            available_channels=context.available_channels,
        )
        return self._finalize(
            logfile_path=context.logfile_path,
            authoring=authoring,
            before=before,
            mode="revise",
            success=result.success,
            rolled_back=result.rolled_back,
            plan_summary=result.revision.plan.summary,
            errors=result.errors,
        )

    def _finalize(
        self,
        *,
        logfile_path: Path,
        authoring: AuthoringService,
        before: dict[str, object],
        mode: Literal["reconstruct", "revise"],
        success: bool,
        rolled_back: bool,
        plan_summary: str,
        errors: tuple[str, ...],
    ) -> GraphAuthoringToolResult:
        """Persist only a semantically verified canonical document."""
        document = authoring.document
        after = document.model_dump(mode="json")
        changed = before != after
        if success and changed:
            service.persist_authoring_document(
                document,
                logfile_path=logfile_path,
                root=self.root,
            )
        return GraphAuthoringToolResult(
            logfile_path=str(logfile_path),
            mode=mode,
            success=success,
            changed=changed,
            rolled_back=rolled_back,
            plan_summary=plan_summary,
            section_ids=[section.id for section in document.sections],
            errors=list(errors),
        )


def register_agentic_tools(
    mcp: object,
    *,
    operations: GraphAuthoringMcpOperations,
) -> tuple[str, ...]:
    """Register the opt-in high-level graph-authoring MCP operations."""

    async def build_plot_from_request(
        logfile_path: Annotated[str, Field(min_length=1)],
        request: Annotated[str, Field(min_length=1)],
    ) -> GraphAuthoringToolResult:
        """Compile and persist a verified plot reconstruction from a request."""
        return await operations.build(logfile_path=logfile_path, request=request)

    async def revise_plot_from_request(
        logfile_path: Annotated[str, Field(min_length=1)],
        request: Annotated[str, Field(min_length=1)],
    ) -> GraphAuthoringToolResult:
        """Compile and persist a verified plot revision from a request."""
        return await operations.revise(logfile_path=logfile_path, request=request)

    tools = (
        (
            "build_plot_from_request",
            "Compile a full requested plot through the internal graph and persist only "
            "a semantically verified canonical document.",
            build_plot_from_request,
        ),
        (
            "revise_plot_from_request",
            "Compile a scoped requested revision through the internal graph and persist "
            "only a semantically verified canonical document.",
            revise_plot_from_request,
        ),
    )
    for name, description, function in tools:
        mcp.add_tool(
            function,
            name=name,
            description=description,
            structured_output=True,
        )
    return tuple(name for name, _description, _function in tools)


__all__ = [
    "GraphAuthoringMcpOperations",
    "GraphAuthoringToolResult",
    "register_agentic_tools",
]
