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

from ..agent.composition import create_canonical_dependencies, create_provider_backend
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
    """Construct the shared provider-v2 backend from host configuration."""
    return create_provider_backend(
        provider=provider,
        model=model,
        server_root=server_root,
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
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
        from ..agent.code_mode.facade import CodeModeCompileFacade
        from ..agent.session import AgentSession, AgentSessionConfig
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
    dependencies = create_canonical_dependencies(
        backend=backend,
        server_root=server_root,
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
