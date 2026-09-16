"""Provider-v2 client and credential helpers without legacy agent imports."""

from __future__ import annotations

import os
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlparse

from ...errors import DependencyUnavailableError


def load_api_key(
    *,
    server_root: str | Path,
    api_key: str | None,
    env_var_names: tuple[str, ...],
    env_file_keys: tuple[str, ...],
    text_file_names: tuple[str, ...],
    missing_message: str,
) -> str:
    """Load one credential from explicit input or ignored local sources."""
    if api_key is not None and api_key.strip():
        return api_key.strip()
    for env_var_name in env_var_names:
        value = os.getenv(env_var_name, "").strip()
        if value:
            return value

    root = Path(server_root).resolve()
    for env_path in (root / ".env.local", root / ".env"):
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            if key.strip() not in env_file_keys or not value.strip():
                continue
            token = value.strip().strip('"').strip("'")
            if token:
                return token

    for file_name in text_file_names:
        text_path = root / file_name
        if text_path.exists():
            token = text_path.read_text(encoding="utf-8").strip()
            if token:
                return token
    raise RuntimeError(missing_message)


def is_loopback_url(base_url: str) -> bool:
    """Return whether an OpenAI-compatible URL targets the local machine."""
    hostname = urlparse(base_url).hostname
    if hostname is None or hostname == "localhost":
        return hostname == "localhost"
    try:
        return ip_address(hostname).is_loopback
    except ValueError:
        return False


def load_async_openai_client(
    *,
    api_key: str,
    base_url: str | None = None,
    timeout: float | None = None,
) -> object:
    """Construct the async OpenAI client required by provider-v2 adapters."""
    try:
        from openai import AsyncOpenAI
    except ModuleNotFoundError as exc:
        raise DependencyUnavailableError(
            "Install `wellplot[agent]` or add the `openai` package to use an "
            "OpenAI-based authoring session."
        ) from exc

    arguments: dict[str, object] = {"api_key": api_key}
    if base_url is not None and base_url.strip():
        arguments["base_url"] = base_url.strip()
    if timeout is not None:
        if timeout <= 0:
            raise ValueError("OpenAI client timeout must be greater than zero seconds.")
        arguments["timeout"] = timeout
    return AsyncOpenAI(**arguments)


__all__ = ["is_loopback_url", "load_api_key", "load_async_openai_client"]
