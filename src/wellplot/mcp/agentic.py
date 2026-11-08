###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Opt-in MCP edge for Code Mode v2 natural-language authoring."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..agent.code_mode.enrichment import (
    bind_semantic_publication_sources,
    intent_requires_channel_context,
    reconciliation_channels,
    validate_enriched_snapshot,
)
from ..agent.code_mode.obligations import (
    DocumentPostconditionError,
    verify_document_postconditions,
)
from ..agent.execution_trace import AgentRunTrace, bind_agent_trace
from ..agent.session import AgentSession, AgentSessionResult, AgentSourceConfig
from ..api.serialize import report_to_dict
from ..authoring_executor import execute_authoring_plan
from ..authoring_reconciler import reconcile_authoring
from ..authoring_service import AuthoringService
from ..errors import AuthoringPublicationRecoveryError, AuthoringSnapshotConflictError
from ..file_revision import file_revision_token
from ..logfile import load_logfile_text, resolve_section_data_sources_for_logfile
from ..model.authoring import AuthoringDocumentSpec
from ..semantic_catalog import (
    EMPTY_SEMANTIC_CHANNEL_CATALOG,
    SemanticCatalogTrustError,
    load_deployed_catalog_release,
)
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
    source_file_sha256: str
    dependency_revisions: tuple[tuple[str, str], ...]
    document: AuthoringDocumentSpec
    source_candidates: tuple[AgentSourceConfig, ...]


def _request_context(logfile_path: str, *, root: Path) -> _McpDocumentContext:
    """Load one logfile and expose only its declared sources to Code Mode."""
    requested_logfile = Path(logfile_path).expanduser()
    resolved_logfile = (
        requested_logfile if requested_logfile.is_absolute() else root / requested_logfile
    ).resolve()
    raw_bytes = resolved_logfile.read_bytes()
    template_paths: list[Path] = []
    spec = load_logfile_text(
        raw_bytes.decode("utf-8"),
        base_dir=resolved_logfile.parent,
        allowed_root=root,
        resolved_template_paths=template_paths,
    )
    document = AuthoringService.from_mapping(report_to_dict(spec)).document
    declared = resolve_section_data_sources_for_logfile(
        spec,
        base_dir=resolved_logfile.parent,
        allowed_root=root,
    )
    unique_sources = sorted(set(declared.values()), key=lambda item: (str(item[0]), item[1]))
    candidates_list: list[AgentSourceConfig] = []
    for index, (path, source_format) in enumerate(unique_sources, start=1):
        revision = file_revision_token(path) if path.is_file() else None
        section_labels = tuple(
            section_id
            for section_id, declared_source in declared.items()
            if declared_source == (path, source_format)
        )
        candidate = AgentSourceConfig(
            candidate_id=f"source-{index}",
            root_id="server",
            path=str(path),
            labels=section_labels or (f"source-{index}",),
            trusted_format=source_format if source_format in {"las", "dlis"} else None,
            inspection_state="not_inspected",
            expected_revision_token=revision,
        )
        candidates_list.append(candidate)
    dependency_paths = {
        candidate.path
        for candidate in candidates_list
        if candidate.expected_revision_token is not None
    }
    dependency_paths.update(str(path) for path in template_paths)
    dependency_revisions = tuple(
        sorted(
            ((path, file_revision_token(Path(path))) for path in dependency_paths),
            key=lambda item: item[0],
        )
    )
    return _McpDocumentContext(
        logfile_path=resolved_logfile,
        source_file_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        dependency_revisions=dependency_revisions,
        document=document,
        source_candidates=tuple(candidates_list),
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
    session_result: AgentSessionResult,
    root: Path,
) -> tuple[bool, bool, bool, list[str], list[str], list[str]]:
    """Apply one successful session intent through a private canonical clone."""
    if not isinstance(session_result, AgentSessionResult):
        return (
            False,
            False,
            False,
            ["session_result_contract_invalid: expected AgentSessionResult"],
            ["compile_failed"],
            [section.id for section in context.document.sections],
        )

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
    inspected = getattr(session_result, "inspection_context", None)
    semantic_catalog = EMPTY_SEMANTIC_CHANNEL_CATALOG
    semantic_contract = session_result.semantic_publication_contract
    if inspected is None:
        if intent_requires_channel_context(intent):
            return (
                False,
                False,
                False,
                ["Source inspection snapshot is missing."],
                ["reconciliation_blocked"],
                [section.id for section in context.document.sections],
            )
        available_channels = {}
    else:
        try:
            validate_enriched_snapshot(inspected, private_service.document)
            available_channels = reconciliation_channels(inspected, intent)
            if semantic_contract is not None and semantic_contract.expected_bindings:
                semantic_contract = bind_semantic_publication_sources(
                    semantic_contract,
                    inspected,
                )
                trusted_release = load_deployed_catalog_release()
                semantic_catalog = trusted_release.catalog
                semantic_contract = semantic_contract.model_copy(
                    update={"trusted_release": trusted_release}
                )
        except SemanticCatalogTrustError as error:
            return (
                False,
                False,
                False,
                [f"{error.code}: trusted semantic catalog unavailable."],
                ["reconciliation_blocked"],
                [section.id for section in context.document.sections],
            )
        except ValueError as error:
            return (
                False,
                False,
                False,
                [f"stale_or_invalid_inspection_snapshot: {error}"],
                ["stale_snapshot_conflict"],
                [section.id for section in context.document.sections],
            )
    try:
        plan = reconcile_authoring(
            intent,
            existing=private_service.document,
            available_channels=available_channels,
            semantic_catalog=semantic_catalog,
            semantic_publication_contract=semantic_contract,
        )
    except SemanticCatalogTrustError as error:
        return (
            False,
            False,
            False,
            [f"{error.code}: trusted semantic catalog unavailable."],
            ["reconciliation_blocked"],
            [section.id for section in context.document.sections],
        )
    if not plan.ready:
        return (
            False,
            False,
            False,
            _plan_errors(plan),
            ["reconciliation_blocked"],
            [section.id for section in context.document.sections],
        )
    if plan.semantic_publication_contract is not None:
        semantic_contract = plan.semantic_publication_contract

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
    try:
        verify_document_postconditions(
            context.document,
            accepted,
            session_result.obligations,
            plan.operations,
            semantic_contract=semantic_contract,
            semantic_evidence=plan.semantic_resolutions,
        )
    except DocumentPostconditionError as error:
        return (
            False,
            False,
            True,
            [str(error)],
            [
                "semantic_postcondition_failed"
                if error.check == "semantic"
                else "post_lowering_obligation_failed"
            ],
            [section.id for section in context.document.sections],
        )

    changed = context.document.model_dump(mode="json") != accepted.model_dump(mode="json")
    if changed:
        try:
            if inspected is not None:
                validate_enriched_snapshot(inspected, context.document)
            service.persist_authoring_document(
                accepted,
                logfile_path=context.logfile_path,
                root=root,
                expected_file_sha256=context.source_file_sha256,
                expected_dependency_revisions=context.dependency_revisions,
            )
        except AuthoringSnapshotConflictError as error:
            return (
                False,
                False,
                True,
                [f"stale_snapshot_conflict: {error}"],
                ["stale_snapshot_conflict"],
                [section.id for section in context.document.sections],
            )
        except AuthoringPublicationRecoveryError as error:
            return (
                False,
                True,
                False,
                [f"publication_recovery_failed: {error}"],
                ["publication_recovery_failed"],
                [section.id for section in accepted.sections],
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
            try:
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
            except Exception as exc:
                trace.record(
                    "run_finished",
                    status="failed",
                    details={"error_type": type(exc).__name__},
                )
                raise
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
                    "failure_owner": _apply_failure_owner(apply_status, result),
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


def _apply_failure_owner(apply_status: list[str], session_result: object) -> str | None:
    """Attribute post-compile failures to the deterministic owning boundary."""
    status = apply_status[0] if apply_status else ""
    owners = {
        "reconciliation_blocked": "reconciliation",
        "execution_failed": "executor",
        "validation_failed": "executor",
        "post_lowering_obligation_failed": "executor",
        "semantic_postcondition_failed": "executor",
        "stale_snapshot_conflict": "persistence",
        "publication_recovery_failed": "persistence",
    }
    if status in owners:
        return owners[status]
    if status == "compile_failed":
        diagnostic_owners = {
            getattr(item, "failure_owner", None)
            for item in getattr(session_result, "diagnostics", ())
        }
        diagnostic_owners.discard(None)
        if len(diagnostic_owners) == 1:
            return next(iter(diagnostic_owners))
    return None


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
