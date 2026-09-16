###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Opt-in MCP edge for Code Mode v2 natural-language authoring."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..agent.execution_trace import AgentRunTrace, bind_agent_trace
from ..agent.session import AgentSession, AgentSourceConfig
from ..api.serialize import report_to_dict
from ..authoring_executor import execute_authoring_plan
from ..authoring_reconciler import reconcile_authoring
from ..authoring_service import AuthoringService
from ..logfile import load_logfile, resolve_section_data_sources_for_logfile
from ..model.authoring import AuthoringDocumentSpec
from . import service


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
    trace_path: str | None = None
    trace_event_count: int = Field(default=0, ge=0)


@dataclass(frozen=True)
class _McpDocumentContext:
    """Host-owned canonical document and explicitly declared source candidates."""

    logfile_path: Path
    document: AuthoringDocumentSpec
    source_candidates: tuple[AgentSourceConfig, ...]


def _request_context(logfile_path: str, *, root: Path) -> _McpDocumentContext:
    """Load one logfile and expose only its declared sources to Code Mode."""
    resolved_logfile = Path(logfile_path).expanduser().resolve()
    spec = load_logfile(resolved_logfile, allowed_root=root)
    document = AuthoringService.from_mapping(report_to_dict(spec)).document
    declared = resolve_section_data_sources_for_logfile(
        spec,
        base_dir=resolved_logfile.parent,
        allowed_root=root,
    )
    unique_sources = sorted(set(declared.values()), key=lambda item: (str(item[0]), item[1]))
    candidates = tuple(
        AgentSourceConfig(
            candidate_id=f"source-{index}",
            root_id="server",
            path=str(path),
            labels=(path.name, path.stem, source_format),
            trusted_format=source_format if source_format in {"las", "dlis"} else None,
        )
        for index, (path, source_format) in enumerate(unique_sources, start=1)
    )
    return _McpDocumentContext(
        logfile_path=resolved_logfile,
        document=document,
        source_candidates=candidates,
    )


def _diagnostic_errors(result: object) -> list[str]:
    """Project bounded public session diagnostics into MCP error text."""
    return [f"{item.code}: {item.message}" for item in getattr(result, "diagnostics", ())]


def _plan_errors(plan: object) -> list[str]:
    """Project deterministic reconciliation issues without exposing internals."""
    return [f"{item.code}: {item.message}" for item in getattr(plan, "issues", ())]


def _execution_errors(execution: object) -> list[str]:
    """Project deterministic executor errors without retaining snapshots."""
    return [str(error) for error in getattr(execution, "errors", ())]


def _apply_session_result(
    *,
    context: _McpDocumentContext,
    session_result: object,
    root: Path,
) -> tuple[bool, bool, bool, list[str], list[str], list[str]]:
    """Apply one successful session intent through a private canonical clone."""
    if not getattr(session_result, "success", False):
        return (
            False,
            False,
            False,
            _diagnostic_errors(session_result),
            ["compile_failed"],
            [section.id for section in context.document.sections],
        )

    intent = getattr(session_result, "intent", None)
    if intent is None:
        return (
            False,
            False,
            False,
            ["Compilation succeeded without an intent."],
            ["compile_failed"],
            [section.id for section in context.document.sections],
        )

    private_service = AuthoringService(context.document)
    plan = reconcile_authoring(intent, existing=private_service.document)
    if not plan.ready:
        return (
            False,
            False,
            False,
            _plan_errors(plan),
            ["reconciliation_blocked"],
            [section.id for section in context.document.sections],
        )

    execution = execute_authoring_plan(private_service, plan)
    if not execution.success:
        return (
            False,
            False,
            True,
            _execution_errors(execution),
            ["execution_failed"],
            [section.id for section in context.document.sections],
        )

    validation = private_service.validate()
    if not validation.valid:
        return (
            False,
            False,
            True,
            list(validation.errors),
            ["validation_failed"],
            [section.id for section in context.document.sections],
        )

    accepted = private_service.document
    changed = context.document.model_dump(mode="json") != accepted.model_dump(mode="json")
    if changed:
        service.persist_authoring_document(
            accepted,
            logfile_path=context.logfile_path,
            root=root,
        )
    return (
        True,
        changed,
        False,
        [],
        ["persisted" if changed else "no_op"],
        [section.id for section in accepted.sections],
    )


def _result(
    *,
    context: _McpDocumentContext,
    mode: Literal["reconstruct", "revise"],
    success: bool,
    changed: bool,
    rolled_back: bool,
    errors: list[str],
    section_ids: list[str],
    trace: AgentRunTrace,
) -> GraphAuthoringToolResult:
    """Build the stable MCP result without exposing v2 plan or source state."""
    return GraphAuthoringToolResult(
        logfile_path=str(context.logfile_path),
        mode=mode,
        success=success,
        changed=changed,
        rolled_back=rolled_back,
        plan_summary=None,
        section_ids=section_ids,
        errors=errors,
        trace_path=str(trace.path),
        trace_event_count=trace.event_count,
    )


@dataclass(frozen=True)
class GraphAuthoringMcpOperations:
    """High-level MCP operations configured with the direct v2 session."""

    session: AgentSession
    root: Path

    @classmethod
    def create(
        cls,
        *,
        session: AgentSession,
        root: str | Path,
    ) -> GraphAuthoringMcpOperations:
        """Create operations bound to one resolved server root."""
        return cls(session=session, root=Path(root).expanduser().resolve())

    async def build(
        self,
        *,
        logfile_path: str,
        request: str,
    ) -> GraphAuthoringToolResult:
        """Build a document, privately apply a verified intent, and persist it."""
        return await self._run(logfile_path=logfile_path, request=request, mode="reconstruct")

    async def revise(
        self,
        *,
        logfile_path: str,
        request: str,
    ) -> GraphAuthoringToolResult:
        """Revise a document, privately apply a verified intent, and persist it."""
        return await self._run(logfile_path=logfile_path, request=request, mode="revise")

    async def _run(
        self,
        *,
        logfile_path: str,
        request: str,
        mode: Literal["reconstruct", "revise"],
    ) -> GraphAuthoringToolResult:
        """Execute one bounded compile/apply transaction."""
        context = _request_context(logfile_path, root=self.root)
        trace = AgentRunTrace.create(logfile_path=context.logfile_path, mode=mode)
        with bind_agent_trace(trace):
            trace.record(
                "graph_context_ready",
                status="ready",
                details={"section_ids": [section.id for section in context.document.sections]},
            )
            if mode == "reconstruct":
                result = await self.session.build(
                    request=request,
                    document=context.document,
                    sources=context.source_candidates,
                )
            else:
                result = await self.session.revise(
                    request=request,
                    document=context.document,
                    sources=context.source_candidates,
                )
            trace.record(
                "compile_finished",
                status="succeeded" if result.success else "failed",
                details=result.inspection(),
            )
            (
                success,
                changed,
                rolled_back,
                errors,
                apply_status,
                section_ids,
            ) = _apply_session_result(
                context=context,
                session_result=result,
                root=self.root,
            )
            trace.record(
                "apply_finished",
                status="succeeded" if success else "failed",
                details={
                    "apply_status": apply_status,
                    "changed": changed,
                    "rolled_back": rolled_back,
                },
            )
            final = _result(
                context=context,
                mode=mode,
                success=success,
                changed=changed,
                rolled_back=rolled_back,
                errors=errors,
                section_ids=section_ids,
                trace=trace,
            )
            trace.record(
                "run_finished",
                status="succeeded" if success else "failed",
                details={
                    "success": success,
                    "changed": changed,
                    "rolled_back": rolled_back,
                    "error_codes": [error.split(":", 1)[0] for error in errors],
                },
            )
            return final.model_copy(
                update={
                    "trace_path": str(trace.path),
                    "trace_event_count": trace.event_count,
                }
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
        """Compile and persist a full requested plot through Code Mode v2."""
        return await operations.build(logfile_path=logfile_path, request=request)

    async def revise_plot_from_request(
        logfile_path: Annotated[str, Field(min_length=1)],
        request: Annotated[str, Field(min_length=1)],
    ) -> GraphAuthoringToolResult:
        """Compile and persist a scoped requested revision through Code Mode v2."""
        return await operations.revise(logfile_path=logfile_path, request=request)

    tools = (
        (
            "build_plot_from_request",
            "Compile a full requested plot through Code Mode v2 and persist only "
            "a semantically verified canonical document.",
            build_plot_from_request,
        ),
        (
            "revise_plot_from_request",
            "Compile a scoped requested revision through Code Mode v2 and persist "
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
