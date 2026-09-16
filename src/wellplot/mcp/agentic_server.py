###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Explicit stdio host for provider-v2 Code Mode authoring."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from ..errors import DependencyUnavailableError
from .server import create_mcp_server

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


ProviderName = Literal["openai", "openai_compat"]


def _provider_backend(
    *,
    provider: ProviderName,
    model: str,
    server_root: Path,
    api_key: str | None,
    base_url: str | None,
    timeout: float | None,
) -> object:
    """Construct one async provider-v2 backend from host configuration."""
    from ..agent.providers._v2_client import (
        is_loopback_url,
        load_api_key,
        load_async_openai_client,
    )

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
        from ..agent.providers.openai_v2 import OpenAIBackendV2

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

    from ..agent.providers.openai_compat_v2 import OpenAICompatibleBackendV2

    return OpenAICompatibleBackendV2(
        model=model,
        client=load_async_openai_client(
            api_key=token,
            base_url=normalized_base_url,
            timeout=timeout,
        ),
        structured_output="json_schema",
    )


def create_agentic_mcp_server(
    *,
    provider: ProviderName,
    model: str,
    root: str | Path | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    timeout: float | None = None,
) -> FastMCP:
    """Create the opt-in MCP server backed by the private v2 compile service."""
    normalized_model = model.strip()
    if not normalized_model:
        raise ValueError("Agentic MCP server requires a non-empty model.")
    if timeout is not None and timeout <= 0:
        raise ValueError("Agentic MCP server timeout must be greater than zero seconds.")

    server_root = Path.cwd().resolve() if root is None else Path(root).expanduser().resolve()
    try:
        from ..agent.code_mode.enrichment import SemanticEnricher
        from ..agent.code_mode.facade import CodeModeCompileFacade
        from ..agent.code_mode.planner import SemanticPlanner
        from ..agent.code_mode.program_worker import ProgramSectionCompiler
        from ..agent.code_mode.report_worker import ReportProgramCompiler
        from ..agent.code_mode.source_loader import LogfileSourceLoader
        from ..agent.code_mode.workflow import CodeModeGraphDependencies
        from ..agent.session import AgentSession, AgentSessionConfig
        from ..capabilities import create_builtin_registry
    except ModuleNotFoundError as exc:
        if exc.name in {"langgraph", "openai"}:
            raise DependencyUnavailableError(
                "wellplot-agentic-mcp requires the optional agent and graph dependencies. "
                "Install `wellplot[agent,graph]`."
            ) from exc
        raise

    backend = _provider_backend(
        provider=provider,
        model=normalized_model,
        server_root=server_root,
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
    )
    registry = create_builtin_registry()
    dependencies = CodeModeGraphDependencies(
        planner=SemanticPlanner(backend=backend, registry=registry),
        enricher=SemanticEnricher(
            loader=LogfileSourceLoader(),
            allowed_roots={"server": server_root},
        ),
        report_compiler=ReportProgramCompiler(
            backend=backend,
            registry=registry,
        ),
        section_compiler=ProgramSectionCompiler(
            backend=backend,
            registry=registry,
        ),
    )
    session = AgentSession(
        compiler=CodeModeCompileFacade(dependencies),
        config=AgentSessionConfig(timeout_seconds=timeout or 120.0),
    )
    from .agentic import GraphAuthoringMcpOperations

    operations = GraphAuthoringMcpOperations.create(session=session, root=server_root)
    return create_mcp_server(server_root, agentic_operations=operations)


def _required_environment_value(name: str) -> str:
    """Read one required non-empty agentic-server environment value."""
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Set {name} before starting wellplot-agentic-mcp.")
    return value


def _environment_timeout() -> float | None:
    """Read an optional positive request timeout from the process environment."""
    value = os.getenv("WELLPLOT_AGENTIC_TIMEOUT", "").strip()
    if not value:
        return None
    try:
        timeout = float(value)
    except ValueError as exc:
        raise ValueError("WELLPLOT_AGENTIC_TIMEOUT must be a positive number.") from exc
    if timeout <= 0:
        raise ValueError("WELLPLOT_AGENTIC_TIMEOUT must be a positive number.")
    return timeout


def _server_from_environment() -> FastMCP:
    """Build the explicit provider-backed MCP host from process configuration."""
    provider = _required_environment_value("WELLPLOT_AGENTIC_PROVIDER")
    if provider not in {"openai", "openai_compat"}:
        raise ValueError("WELLPLOT_AGENTIC_PROVIDER must be 'openai' or 'openai_compat'.")
    root = os.getenv("WELLPLOT_AGENTIC_SERVER_ROOT") or Path.cwd()
    return create_agentic_mcp_server(
        provider=provider,
        model=_required_environment_value("WELLPLOT_AGENTIC_MODEL"),
        root=root,
        api_key=os.getenv("WELLPLOT_AGENTIC_API_KEY"),
        base_url=os.getenv("WELLPLOT_AGENTIC_BASE_URL"),
        timeout=_environment_timeout(),
    )


def main() -> int:
    """Run the provider-backed MCP server over stdio."""
    try:
        server = _server_from_environment()
        from .stdio import run_stdio

        run_stdio(server)
    except (DependencyUnavailableError, RuntimeError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
