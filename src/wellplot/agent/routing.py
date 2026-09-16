"""Host-owned selection between the v1 and v2 authoring engines."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import is_dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol, TypeVar

if TYPE_CHECKING:
    from .core import AuthoringResult


AuthoringEngine = Literal["v1", "v2"]
DEFAULT_AUTHORING_ENGINE: AuthoringEngine = "v2"


class AuthoringSessionProtocol(Protocol):
    """Shared notebook-facing surface implemented by both engines."""

    async def run(self, **kwargs: object) -> AuthoringResult:
        """Build one authoring request."""

    async def revise(self, **kwargs: object) -> AuthoringResult:
        """Revise one existing authoring document."""

    async def render_logfile_to_file(self, **kwargs: object) -> dict[str, object]:
        """Render one logfile."""

    async def inspect_heading_slots(self, **kwargs: object) -> dict[str, object]:
        """Inspect heading slots."""

    async def preview_header_mapping(self, **kwargs: object) -> dict[str, object]:
        """Preview deterministic heading assignments."""

    async def apply_header_values(self, **kwargs: object) -> dict[str, object]:
        """Apply deterministic heading assignments."""


def normalize_authoring_engine(engine: str) -> AuthoringEngine:
    """Validate one explicit engine selector without accepting aliases."""
    if engine not in {"v1", "v2"}:
        raise ValueError("engine must be exactly 'v1' or 'v2'.")
    return engine


SessionT = TypeVar("SessionT", bound=AuthoringSessionProtocol)


def tag_authoring_result(result: SessionT, *, engine: str) -> SessionT:
    """Attach the selected engine to the compatibility result envelope."""
    normalized_engine = normalize_authoring_engine(engine)
    if not _is_authoring_result(result):
        return result
    facts = dict(result.report_facts)
    existing_engine = facts.get("engine")
    if existing_engine is not None and existing_engine != normalized_engine:
        raise RuntimeError(
            "Authoring implementation returned an engine different from the host selection."
        )
    facts["engine"] = normalized_engine
    return replace(result, report_facts=facts)


def _is_authoring_result(value: object) -> bool:
    """Identify the legacy compatibility envelope without importing core eagerly."""
    from .core import AuthoringResult

    return isinstance(value, AuthoringResult) and is_dataclass(value)


def create_authoring_session(
    *,
    engine: str,
    provider: str,
    model: str,
    server_root: str | Path | None,
    api_key: str | None,
    base_url: str | None,
    timeout: float | None,
    v2_factory: Callable[..., SessionT] | None = None,
) -> AuthoringSessionProtocol:
    """Construct exactly the explicitly selected authoring implementation."""
    normalized_engine = normalize_authoring_engine(engine)
    if normalized_engine == "v1":
        from .core import AuthoringSession

        return AuthoringSession.from_local_mcp(
            provider=provider,
            model=model,
            server_root=server_root,
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
        )

    if server_root is None:
        resolved_root = Path.cwd().resolve()
    else:
        resolved_root = Path(server_root).expanduser().resolve()
    if v2_factory is None:
        from .direct_notebook import create_direct_notebook_session

        v2_factory = create_direct_notebook_session
    return v2_factory(
        provider=provider,
        model=model,
        server_root=resolved_root,
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
    )


__all__ = [
    "AuthoringEngine",
    "AuthoringSessionProtocol",
    "DEFAULT_AUTHORING_ENGINE",
    "create_authoring_session",
    "normalize_authoring_engine",
    "tag_authoring_result",
]
