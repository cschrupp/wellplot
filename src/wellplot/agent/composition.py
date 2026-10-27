"""Shared Code Mode composition root for every public authoring adapter."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Literal

from .code_mode.canonical_workers import CanonicalReportWorker
from .code_mode.enrichment import SemanticEnricher
from .code_mode.facade import CodeModeCompileFacade
from .code_mode.planner import SemanticPlanner
from .code_mode.source_loader import LogfileSourceLoader
from .code_mode.typed_section_worker import CanonicalSectionWorker
from .code_mode.workflow import CodeModeGraphDependencies
from .providers._v2_client import is_loopback_url, load_api_key, load_async_openai_client

ProviderName = Literal["openai", "openai_compat"]


def create_provider_backend(
    *,
    provider: ProviderName,
    model: str,
    server_root: Path,
    api_key: str | None,
    base_url: str | None,
    timeout: float | None,
    request_options: Mapping[str, object] | None = None,
) -> object:
    """Construct the one provider-v2 backend used by all Code Mode adapters."""
    if provider == "openai":
        token = load_api_key(
            server_root=server_root,
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

        return OpenAIBackendV2(
            model=model,
            client=load_async_openai_client(api_key=token, timeout=timeout),
        )

    if base_url is None or not base_url.strip():
        raise ValueError("provider='openai_compat' requires a non-empty base_url.")
    normalized_base_url = base_url.strip()
    try:
        token = load_api_key(
            server_root=server_root,
            api_key=api_key,
            env_var_names=("OPENAI_COMPAT_API_KEY", "OPENAI_API_KEY"),
            env_file_keys=("OPENAI_COMPAT_API_KEY", "OPENAI_API_KEY"),
            text_file_names=(
                "LLAMA_CPP_API_KEY.txt",
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

    return OpenAICompatibleBackendV2(
        model=model,
        client=load_async_openai_client(
            api_key=token,
            base_url=normalized_base_url,
            timeout=timeout,
        ),
        structured_output="json_schema",
        request_options=request_options,
    )


def create_canonical_dependencies(
    *,
    backend: object,
    server_root: Path,
    diagnostic_callback: Callable[[Mapping[str, Any]], None] | None = None,
) -> CodeModeGraphDependencies:
    """Build one worker composition shared by notebook, MCP, and experiments."""
    from ..capabilities import create_builtin_registry

    registry = create_builtin_registry()
    return CodeModeGraphDependencies(
        planner=SemanticPlanner(backend=backend, registry=registry),
        enricher=SemanticEnricher(
            loader=LogfileSourceLoader(),
            allowed_roots={"server": server_root},
        ),
        report_compiler=CanonicalReportWorker(backend=backend),
        section_compiler=CanonicalSectionWorker(backend=backend),
        diagnostic_callback=diagnostic_callback,
    )


def create_canonical_compile_facade(
    *,
    backend: object,
    server_root: Path,
    diagnostic_callback: Callable[[Mapping[str, Any]], None] | None = None,
) -> CodeModeCompileFacade:
    """Construct the shared planner, workers, workflow, and facade."""
    return CodeModeCompileFacade(
        create_canonical_dependencies(
            backend=backend,
            server_root=server_root,
            diagnostic_callback=diagnostic_callback,
        )
    )


__all__ = [
    "ProviderName",
    "create_canonical_compile_facade",
    "create_canonical_dependencies",
    "create_provider_backend",
]
