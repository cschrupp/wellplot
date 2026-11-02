"""Direct Code Mode v2 adapter for notebook project sessions."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Literal

from ..api.serialize import report_to_dict
from ..authoring_context import AuthoringChannelCandidate
from ..authoring_executor import execute_authoring_plan
from ..authoring_reconciler import reconcile_authoring
from ..authoring_service import AuthoringService
from ..errors import AuthoringPublicationRecoveryError, AuthoringSnapshotConflictError
from ..file_revision import file_revision_token
from ..logfile import load_logfile_text, resolve_section_data_sources_for_logfile
from ..mcp import service as mcp_service
from ..model.authoring import AuthoringDocumentSpec
from .code_mode.enrichment import LoadedSource
from .code_mode.obligations import (
    verify_document_obligations,
    verify_document_preservation,
)
from .code_mode.source_loader import LogfileSourceLoader
from .composition import create_canonical_compile_facade, create_provider_backend
from .results import AuthoringResult, AuthoringRunState, AuthoringUserReport
from .session import (
    AgentSession,
    AgentSessionConfig,
    AgentSessionResult,
    AgentSourceConfig,
)


@dataclass(frozen=True, slots=True)
class _NotebookDocumentContext:
    """Canonical document and declared source candidates for one notebook run."""

    logfile_path: Path
    baseline_text: str
    source_file_sha256: str
    dependency_revisions: tuple[tuple[str, str], ...]
    document: AuthoringDocumentSpec
    source_candidates: tuple[AgentSourceConfig, ...]
    available_channels: Mapping[str, tuple[AuthoringChannelCandidate, ...]]


def _json_value(value: object) -> object:
    """Convert deterministic service dataclasses into JSON-shaped values."""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "model_dump"):
        return _json_value(value.model_dump(mode="json"))
    if hasattr(value, "__dataclass_fields__"):
        return _json_value(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _relative_path(path: Path, *, root: Path) -> str:
    """Render one root-contained path in the notebook's stable form."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _declared_source_inventory(
    spec: object,
    *,
    logfile_path: Path,
    root: Path,
) -> tuple[
    tuple[AgentSourceConfig, ...],
    dict[str, tuple[AuthoringChannelCandidate, ...]],
]:
    """Project declared sources and deterministic channel inventories."""
    declared = resolve_section_data_sources_for_logfile(
        spec,
        base_dir=logfile_path.parent,
        allowed_root=root,
    )
    unique_sources = sorted(set(declared.values()), key=lambda item: (str(item[0]), item[1]))
    loader = LogfileSourceLoader()
    available_channels: dict[str, tuple[AuthoringChannelCandidate, ...]] = {}
    loaded: dict[tuple[Path, str], LoadedSource] = {}
    candidates_list: list[AgentSourceConfig] = []
    candidate_by_source: dict[tuple[Path, str], AgentSourceConfig] = {}
    for index, (path, source_format) in enumerate(unique_sources, start=1):
        cache_key = (path, source_format)
        if path.is_file():
            loaded[cache_key] = loader.load(path, source_format)
            inspection_state = "inspected"
            channels = loaded[cache_key].channels
        else:
            inspection_state = "unavailable"
            channels = ()
        candidate = AgentSourceConfig(
            candidate_id=f"source-{index}",
            root_id="server",
            path=str(path),
            labels=(path.name, path.stem, source_format),
            trusted_format=source_format if source_format in {"las", "dlis"} else None,
            inspection_state=inspection_state,
            channels=channels,
        )
        candidates_list.append(candidate)
        candidate_by_source[cache_key] = candidate
    for section_id, (path, source_format) in declared.items():
        if not path.is_file():
            continue
        cache_key = (path, source_format)
        source = loaded[cache_key]
        candidate = candidate_by_source[(path, source_format)]
        available_channels[section_id] = tuple(
            AuthoringChannelCandidate(
                mnemonic=channel.mnemonic,
                kind=channel.kind,
                unit=channel.unit,
                description=channel.description,
                aliases=list(channel.aliases),
                value_shape=list(channel.shape),
                source_path=candidate.path,
            )
            for channel in source.channels
        )
    return tuple(candidates_list), available_channels


def _load_document_context(logfile_path: Path, *, root: Path) -> _NotebookDocumentContext:
    """Load one canonical logfile and its explicitly declared sources."""
    raw_bytes = logfile_path.read_bytes()
    baseline_text = raw_bytes.decode("utf-8")
    template_paths: list[Path] = []
    spec = load_logfile_text(
        baseline_text,
        base_dir=logfile_path.parent,
        allowed_root=root,
        resolved_template_paths=template_paths,
    )
    source_candidates, available_channels = _declared_source_inventory(
        spec,
        logfile_path=logfile_path,
        root=root,
    )
    dependency_paths = {
        candidate.path
        for candidate in source_candidates
        if candidate.inspection_state == "inspected"
    }
    dependency_paths.update(str(path) for path in template_paths)
    dependency_revisions = tuple(
        sorted(
            ((path, file_revision_token(Path(path))) for path in dependency_paths),
            key=lambda item: item[0],
        )
    )
    return _NotebookDocumentContext(
        logfile_path=logfile_path,
        baseline_text=baseline_text,
        source_file_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        dependency_revisions=dependency_revisions,
        document=AuthoringService.from_mapping(report_to_dict(spec)).document,
        source_candidates=source_candidates,
        available_channels=available_channels,
    )


def _provider_backend(
    *,
    provider: str,
    model: str,
    root: Path,
    api_key: str | None,
    base_url: str | None,
    timeout: float | None,
) -> tuple[object, str | None]:
    """Construct one shared provider-v2 backend and bounded credential label."""
    return (
        create_provider_backend(
            provider=provider,  # type: ignore[arg-type]
            model=model,
            server_root=root,
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
        ),
        "configured",
    )


def _build_agent_session(
    *,
    provider: str,
    model: str,
    root: Path,
    api_key: str | None,
    base_url: str | None,
    timeout: float | None,
) -> tuple[AgentSession, str | None]:
    """Compose the direct notebook v2 graph without an MCP edge."""
    session_config = AgentSessionConfig(
        timeout_seconds=120.0 if timeout is None else timeout,
    )
    backend, credential_source = _provider_backend(
        provider=provider,
        model=model,
        root=root,
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
    )
    return (
        AgentSession(
            compiler=create_canonical_compile_facade(backend=backend, server_root=root),
            config=session_config,
        ),
        credential_source,
    )


def _diagnostic_text(result: AgentSessionResult) -> list[str]:
    """Project v2 diagnostics into notebook result text."""
    return [f"{item.code}: {item.message}" for item in result.diagnostics]


def _apply_result(
    *,
    context: _NotebookDocumentContext,
    result: AgentSessionResult,
    root: Path,
) -> tuple[bool, bool, bool, list[str], str, dict[str, str]]:
    """Apply one v2 intent through a private canonical transaction."""
    stages = {
        "reconciliation": "NOT_REACHED",
        "private_execution": "NOT_REACHED",
        "canonical_validation": "NOT_REACHED",
        "post_lowering_obligation": "NOT_REACHED",
        "preservation": "NOT_REACHED",
        "persistence": "NOT_REACHED",
    }
    if not result.success:
        return False, False, False, _diagnostic_text(result), "compile_failed", stages
    if result.intent is None:
        return (
            False,
            False,
            False,
            ["Compilation succeeded without an intent."],
            "compile_failed",
            stages,
        )

    private_service = AuthoringService(context.document)
    plan = reconcile_authoring(
        result.intent,
        existing=private_service.document,
        available_channels=context.available_channels,
    )
    if not plan.ready:
        errors = [f"{issue.code}: {issue.message}" for issue in plan.issues]
        return False, False, False, errors, "reconciliation_blocked", stages
    stages["reconciliation"] = "PASS"

    execution = execute_authoring_plan(private_service, plan)
    if not execution.success:
        return (
            False,
            False,
            True,
            [str(error) for error in execution.errors],
            "execution_failed",
            stages,
        )
    stages["private_execution"] = "PASS"

    validation = private_service.validate()
    if not validation.valid:
        return False, False, True, list(validation.errors), "validation_failed", stages
    stages["canonical_validation"] = "PASS"

    accepted = private_service.document
    try:
        verify_document_obligations(
            accepted,
            result.obligations,
            grounded_operations=plan.operations,
        )
        stages["post_lowering_obligation"] = "PASS"
        verify_document_preservation(context.document, accepted, plan.operations)
        stages["preservation"] = "PASS"
    except ValueError as error:
        return False, False, True, [str(error)], "post_lowering_obligation_failed", stages
    changed = context.document.model_dump(mode="json") != accepted.model_dump(mode="json")
    if changed:
        try:
            mcp_service.persist_authoring_document(
                accepted,
                logfile_path=context.logfile_path,
                root=root,
                expected_file_sha256=context.source_file_sha256,
                expected_dependency_revisions=context.dependency_revisions,
            )
        except AuthoringSnapshotConflictError as error:
            stages["persistence"] = "FAIL"
            return (
                False,
                False,
                True,
                [str(error)],
                "stale_snapshot_conflict",
                stages,
            )
        except AuthoringPublicationRecoveryError as error:
            stages["persistence"] = "RECOVERY_FAIL"
            return (
                False,
                True,
                False,
                [str(error)],
                "publication_recovery_failed",
                stages,
            )
    stages["persistence"] = "PASS"
    return True, changed, False, [], "persisted" if changed else "no_op", stages


@dataclass(frozen=True, slots=True)
class DirectNotebookSession:
    """Notebook-facing v2 adapter with no MCP transport or subprocess."""

    session: AgentSession
    provider: str
    model: str
    credential_source: str | None
    server_root: Path

    def _resolve(self, path: str | Path, *, field_name: str) -> Path:
        """Resolve a server-rooted notebook path."""
        raw_path = Path(path).expanduser()
        resolved = (raw_path if raw_path.is_absolute() else self.server_root / raw_path).resolve()
        try:
            resolved.relative_to(self.server_root)
        except ValueError as exc:
            raise ValueError(
                f"{field_name} must resolve inside the configured server_root."
            ) from exc
        return resolved

    async def run(
        self,
        *,
        goal: str,
        output_logfile: str | Path,
        example_id: str | None = None,
        source_logfile_path: str | Path | None = None,
        max_rounds: int = 12,
    ) -> AuthoringResult:
        """Seed one draft deterministically, then compile and apply through v2."""
        if (example_id is None) == (source_logfile_path is None):
            raise ValueError("Provide exactly one of example_id or source_logfile_path.")
        output_path = self._resolve(output_logfile, field_name="output_logfile")
        mcp_service.create_logfile_draft(
            str(output_path),
            example_id=example_id,
            source_logfile_path=None
            if source_logfile_path is None
            else str(self._resolve(source_logfile_path, field_name="source_logfile_path")),
            overwrite=True,
            root=self.server_root,
        )
        return await self._compile_and_project(
            request=goal,
            logfile_path=output_path,
            mode="reconstruct",
            example_id=example_id,
            source_logfile_path=None if source_logfile_path is None else str(source_logfile_path),
            max_rounds=max_rounds,
        )

    async def revise(
        self,
        *,
        feedback: str,
        logfile_path: str | Path,
        max_rounds: int = 12,
    ) -> AuthoringResult:
        """Compile and privately apply one sparse v2 revision."""
        resolved_logfile = self._resolve(logfile_path, field_name="logfile_path")
        if not resolved_logfile.exists():
            raise FileNotFoundError(f"Draft logfile does not exist: {resolved_logfile}")
        return await self._compile_and_project(
            request=feedback,
            logfile_path=resolved_logfile,
            mode="revise",
            example_id=None,
            source_logfile_path=None,
            max_rounds=max_rounds,
        )

    async def _compile_and_project(
        self,
        *,
        request: str,
        logfile_path: Path,
        mode: Literal["reconstruct", "revise"],
        example_id: str | None,
        source_logfile_path: str | None,
        max_rounds: int,
    ) -> AuthoringResult:
        """Compile, apply, inspect, and project one direct v2 operation."""
        del max_rounds
        context = _load_document_context(logfile_path, root=self.server_root)
        baseline_text = context.baseline_text
        result = (
            await self.session.build(
                request=request,
                document=context.document,
                sources=context.source_candidates,
            )
            if mode == "reconstruct"
            else await self.session.revise(
                request=request,
                document=context.document,
                sources=context.source_candidates,
            )
        )
        success, changed, rolled_back, errors, apply_status, host_stage_evidence = _apply_result(
            context=context,
            result=result,
            root=self.server_root,
        )
        return self._project_result(
            request=request,
            mode=mode,
            logfile_path=logfile_path,
            baseline_text=baseline_text,
            result=result,
            success=success,
            changed=changed,
            rolled_back=rolled_back,
            errors=errors,
            apply_status=apply_status,
            example_id=example_id,
            source_logfile_path=source_logfile_path,
            host_stage_evidence=host_stage_evidence,
        )

    def _project_result(
        self,
        *,
        request: str,
        mode: Literal["reconstruct", "revise"],
        logfile_path: Path,
        baseline_text: str,
        result: AgentSessionResult,
        success: bool,
        changed: bool,
        rolled_back: bool,
        errors: list[str],
        apply_status: str,
        example_id: str | None,
        source_logfile_path: str | None,
        host_stage_evidence: dict[str, str],
    ) -> AuthoringResult:
        """Build the existing notebook result envelope from bounded v2 evidence."""
        validation = mcp_service.validate_logfile(
            str(logfile_path), root=self.server_root, level="render"
        )
        draft_summary = mcp_service.summarize_logfile_draft(
            str(logfile_path), root=self.server_root
        )
        inspect_summary = mcp_service.inspect_logfile(str(logfile_path), root=self.server_root)
        change_summary = mcp_service.summarize_logfile_changes(
            str(logfile_path), previous_text=baseline_text, root=self.server_root
        )
        section_ids = list(getattr(inspect_summary, "section_ids", []))
        report_preview = b""
        section_preview = b""
        render_error: str | None = None
        if success:
            validation_valid = (
                validation.get("valid")
                if isinstance(validation, Mapping)
                else getattr(validation, "valid", None)
            )
            if validation_valid is not True:
                render_error = "Persisted artifact failed render-level validation."
            else:
                try:
                    report_preview = mcp_service.preview_logfile_png(
                        str(logfile_path),
                        root=self.server_root,
                        include_report_pages=True,
                        dpi=72,
                    )
                    section_preview = (
                        mcp_service.preview_section_png(
                            str(logfile_path),
                            section_id=section_ids[0],
                            root=self.server_root,
                            dpi=72,
                        )
                        if section_ids
                        else report_preview
                    )
                    if not report_preview or not section_preview:
                        render_error = "Preview generation returned no image data."
                except Exception as error:
                    render_error = f"Preview generation failed ({type(error).__name__})."
        final_success = success and render_error is None
        final_apply_status = apply_status
        final_errors = list(errors)
        if render_error is not None:
            final_apply_status = "persisted_render_failed" if changed else "render_failed_noop"
            final_errors.append(render_error)

        inspection = result.inspection()
        host_stage_evidence = dict(host_stage_evidence)
        host_stage_evidence["reload"] = "PASS" if success else "NOT_REACHED"
        host_stage_evidence["render"] = (
            "PASS" if success and render_error is None else "FAIL" if success else "NOT_REACHED"
        )
        report_facts = {
            "engine": "v2",
            "compilation": inspection,
            "apply_status": final_apply_status,
            "success": final_success,
            "changed": changed,
            "rolled_back": rolled_back,
            "host_stage_evidence": host_stage_evidence,
        }
        if final_success:
            user_report = AuthoringUserReport(
                done=("Compiled and applied the request through the direct Code Mode v2 path.",),
            )
        else:
            user_report = AuthoringUserReport(
                could_not_do=("Apply the requested v2 authoring change.",),
                why_not=tuple(final_errors) or ("The v2 authoring request failed.",),
                next_help=("Inspect the deterministic validation and compilation evidence.",),
            )
        return AuthoringResult(
            provider=self.provider,
            model=self.model,
            credential_source=self.credential_source,
            request_kind="author" if mode == "reconstruct" else "revise",
            example_id=example_id,
            source_logfile_path=source_logfile_path,
            goal=request,
            draft_logfile=_relative_path(logfile_path, root=self.server_root),
            server_root=self.server_root,
            tool_trace=(),
            final_text=(
                "Direct Code Mode v2 authoring completed."
                if final_success
                else "Direct Code Mode v2 authoring did not produce an accepted change."
            ),
            validation=_json_value(validation),
            draft_summary=_json_value(draft_summary),
            inspect_summary=_json_value(inspect_summary),
            change_summary=_json_value(change_summary),
            draft_text=logfile_path.read_text(encoding="utf-8"),
            report_preview_png=report_preview,
            section_preview_png=section_preview,
            run_state=AuthoringRunState(),
            user_report=user_report,
            submitted_intent=(
                None
                if result.intent is None
                else result.intent.model_dump(
                    mode="json",
                    exclude_none=True,
                    exclude_unset=True,
                )
            ),
            report_facts=report_facts,
        )

    async def render_logfile_to_file(
        self,
        *,
        logfile_path: str | Path,
        output_path: str | Path,
        overwrite: bool = False,
    ) -> dict[str, object]:
        """Render one logfile directly through the deterministic renderer."""
        result = mcp_service.render_logfile_to_file(
            str(self._resolve(logfile_path, field_name="logfile_path")),
            str(self._resolve(output_path, field_name="output_path")),
            overwrite=overwrite,
            root=self.server_root,
        )
        return _json_value(result)  # type: ignore[return-value]

    async def inspect_heading_slots(self, *, logfile_path: str | Path) -> dict[str, object]:
        """Inspect heading slots directly without opening an MCP session."""
        result = mcp_service.inspect_heading_slots(
            logfile_path=str(self._resolve(logfile_path, field_name="logfile_path")),
            root=self.server_root,
        )
        return _json_value(result)  # type: ignore[return-value]

    async def preview_header_mapping(
        self,
        *,
        logfile_path: str | Path,
        values: dict[str, object],
        overwrite_policy: str = "fill_empty",
    ) -> dict[str, object]:
        """Preview deterministic header assignments directly."""
        result = mcp_service.preview_header_mapping(
            str(self._resolve(logfile_path, field_name="logfile_path")),
            values=values,
            overwrite_policy=overwrite_policy,
            root=self.server_root,
        )
        return _json_value(result)  # type: ignore[return-value]

    async def apply_header_values(
        self,
        *,
        logfile_path: str | Path,
        values: dict[str, object],
        overwrite_policy: str = "fill_empty",
    ) -> dict[str, object]:
        """Apply deterministic header assignments directly."""
        result = mcp_service.apply_header_values(
            str(self._resolve(logfile_path, field_name="logfile_path")),
            values=values,
            overwrite_policy=overwrite_policy,
            root=self.server_root,
        )
        return _json_value(result)  # type: ignore[return-value]


def create_direct_notebook_session(
    *,
    provider: str,
    model: str,
    server_root: str | Path,
    api_key: str | None,
    base_url: str | None,
    timeout: float | None,
) -> DirectNotebookSession:
    """Create the direct v2 adapter used by ``ProjectSession``."""
    root = Path(server_root).expanduser().resolve()
    session, credential_source = _build_agent_session(
        provider=provider,
        model=model,
        root=root,
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
    )
    return DirectNotebookSession(
        session=session,
        provider=provider,
        model=model,
        credential_source=credential_source,
        server_root=root,
    )


__all__ = ["DirectNotebookSession", "create_direct_notebook_session"]
