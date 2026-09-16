"""Direct Code Mode v2 adapter for notebook project sessions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Literal

from ..api.serialize import report_to_dict
from ..authoring_executor import execute_authoring_plan
from ..authoring_reconciler import reconcile_authoring
from ..authoring_service import AuthoringService
from ..logfile import load_logfile, resolve_section_data_sources_for_logfile
from ..mcp import service as mcp_service
from ..model.authoring import AuthoringDocumentSpec
from .code_mode.enrichment import SemanticEnricher
from .code_mode.facade import CodeModeCompileFacade
from .code_mode.planner import SemanticPlanner
from .code_mode.program_worker import ProgramSectionCompiler
from .code_mode.report_worker import ReportProgramCompiler
from .code_mode.source_loader import LogfileSourceLoader
from .code_mode.workflow import CodeModeGraphDependencies
from .core import AuthoringResult, AuthoringRunState, AuthoringUserReport
from .providers._v2_client import is_loopback_url, load_api_key, load_async_openai_client
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
    document: AuthoringDocumentSpec
    source_candidates: tuple[AgentSourceConfig, ...]


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


def _declared_source_candidates(
    spec: object,
    *,
    logfile_path: Path,
    root: Path,
) -> tuple[AgentSourceConfig, ...]:
    """Project only logfile-declared sources into opaque v2 candidates."""
    declared = resolve_section_data_sources_for_logfile(
        spec,
        base_dir=logfile_path.parent,
        allowed_root=root,
    )
    unique_sources = sorted(set(declared.values()), key=lambda item: (str(item[0]), item[1]))
    return tuple(
        AgentSourceConfig(
            candidate_id=f"source-{index}",
            root_id="server",
            path=str(path),
            labels=(path.name, path.stem, source_format),
            trusted_format=source_format if source_format in {"las", "dlis"} else None,
        )
        for index, (path, source_format) in enumerate(unique_sources, start=1)
    )


def _load_document_context(logfile_path: Path, *, root: Path) -> _NotebookDocumentContext:
    """Load one canonical logfile and its explicitly declared sources."""
    spec = load_logfile(logfile_path, allowed_root=root)
    return _NotebookDocumentContext(
        logfile_path=logfile_path,
        document=AuthoringService.from_mapping(report_to_dict(spec)).document,
        source_candidates=_declared_source_candidates(
            spec,
            logfile_path=logfile_path,
            root=root,
        ),
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
    """Construct one provider-v2 backend and a bounded credential label."""
    if provider == "openai":
        token = load_api_key(
            server_root=root,
            api_key=api_key,
            env_var_names=("OPENAI_API_KEY",),
            env_file_keys=("OPENAI_API_KEY",),
            text_file_names=("OPENAI_API_KEY.txt", "openai_api_key.txt"),
            missing_message=(
                "Set OPENAI_API_KEY, pass api_key=..., or create OPENAI_API_KEY.txt "
                "under the configured server root."
            ),
        )
        from .providers.openai_v2 import OpenAIBackendV2

        return (
            OpenAIBackendV2(
                model=model,
                client=load_async_openai_client(api_key=token, timeout=timeout),
            ),
            "configured",
        )

    if base_url is None or not base_url.strip():
        raise ValueError("provider='openai_compat' requires a non-empty base_url.")
    normalized_base_url = base_url.strip()
    try:
        token = load_api_key(
            server_root=root,
            api_key=api_key,
            env_var_names=("OPENAI_COMPAT_API_KEY", "OPENAI_API_KEY"),
            env_file_keys=("OPENAI_COMPAT_API_KEY", "OPENAI_API_KEY"),
            text_file_names=(
                "OPENAI_COMPAT_API_KEY.txt",
                "openai_compat_api_key.txt",
                "OPENAI_API_KEY.txt",
                "openai_api_key.txt",
            ),
            missing_message="OpenAI-compatible API key was not configured.",
        )
    except RuntimeError:
        if not is_loopback_url(normalized_base_url):
            raise RuntimeError(
                "Pass api_key=..., set OPENAI_COMPAT_API_KEY or OPENAI_API_KEY, or "
                "create an OpenAI-compatible key file under the configured server root."
            ) from None
        token = "wellplot-local-openai-compat"

    from .providers.openai_compat_v2 import OpenAICompatibleBackendV2

    return (
        OpenAICompatibleBackendV2(
            model=model,
            client=load_async_openai_client(
                api_key=token,
                base_url=normalized_base_url,
                timeout=timeout,
            ),
            structured_output="json_schema",
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
    from ..capabilities import create_builtin_registry

    registry = create_builtin_registry()
    dependencies = CodeModeGraphDependencies(
        planner=SemanticPlanner(backend=backend, registry=registry),
        enricher=SemanticEnricher(
            loader=LogfileSourceLoader(),
            allowed_roots={"server": root},
        ),
        report_compiler=ReportProgramCompiler(backend=backend, registry=registry),
        section_compiler=ProgramSectionCompiler(backend=backend, registry=registry),
    )
    return (
        AgentSession(
            compiler=CodeModeCompileFacade(dependencies),
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
) -> tuple[bool, bool, bool, list[str], str]:
    """Apply one v2 intent through a private canonical transaction."""
    if not result.success:
        return False, False, False, _diagnostic_text(result), "compile_failed"
    if result.intent is None:
        return False, False, False, ["Compilation succeeded without an intent."], "compile_failed"

    private_service = AuthoringService(context.document)
    plan = reconcile_authoring(result.intent, existing=private_service.document)
    if not plan.ready:
        errors = [f"{issue.code}: {issue.message}" for issue in plan.issues]
        return False, False, False, errors, "reconciliation_blocked"

    execution = execute_authoring_plan(private_service, plan)
    if not execution.success:
        return False, False, True, [str(error) for error in execution.errors], "execution_failed"

    validation = private_service.validate()
    if not validation.valid:
        return False, False, True, list(validation.errors), "validation_failed"

    accepted = private_service.document
    changed = context.document.model_dump(mode="json") != accepted.model_dump(mode="json")
    if changed:
        mcp_service.persist_authoring_document(
            accepted,
            logfile_path=context.logfile_path,
            root=root,
        )
    return True, changed, False, [], "persisted" if changed else "no_op"


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
        baseline_text = logfile_path.read_text(encoding="utf-8")
        context = _load_document_context(logfile_path, root=self.server_root)
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
        success, changed, rolled_back, errors, apply_status = _apply_result(
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
        report_preview = mcp_service.preview_logfile_png(
            str(logfile_path), root=self.server_root, include_report_pages=True, dpi=72
        )
        section_ids = list(getattr(inspect_summary, "section_ids", []))
        section_preview = (
            mcp_service.preview_section_png(
                str(logfile_path), section_id=section_ids[0], root=self.server_root, dpi=72
            )
            if section_ids
            else report_preview
        )
        inspection = result.inspection()
        report_facts = {
            "engine": "v2",
            "compilation": inspection,
            "apply_status": apply_status,
            "success": success,
            "changed": changed,
            "rolled_back": rolled_back,
        }
        if success:
            user_report = AuthoringUserReport(
                done=("Compiled and applied the request through the direct Code Mode v2 path.",),
            )
        else:
            user_report = AuthoringUserReport(
                could_not_do=("Apply the requested v2 authoring change.",),
                why_not=tuple(errors) or ("The v2 authoring request failed.",),
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
                if success
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
