"""Environment-based OpenRouter API key handling (never log or persist the secret)."""

from __future__ import annotations

import os
from dataclasses import dataclass


class ApiKeyError(RuntimeError):
    """Missing or invalid API key configuration."""


DEFAULT_ENV_VAR = "OPENROUTER_API_KEY"


@dataclass(frozen=True)
class ApiKeyPresence:
    """Safe-to-serialize key presence report (no secret material)."""

    env_var: str
    present: bool
    length: int
    prefix_redacted: str

    def to_json(self) -> dict:
        return {
            "env_var": self.env_var,
            "present": self.present,
            "length": self.length,
            "prefix_redacted": self.prefix_redacted,
            "secret_exported": False,
        }


def inspect_api_key_presence(*, env_var: str = DEFAULT_ENV_VAR) -> ApiKeyPresence:
    raw = os.environ.get(env_var)
    if raw is None or raw.strip() == "":
        return ApiKeyPresence(
            env_var=env_var, present=False, length=0, prefix_redacted=""
        )
    value = raw.strip()
    prefix = "sk-or-***" if value.startswith("sk-or-") else "***"
    return ApiKeyPresence(
        env_var=env_var,
        present=True,
        length=len(value),
        prefix_redacted=prefix,
    )


def load_api_key(*, env_var: str = DEFAULT_ENV_VAR) -> str:
    """Return the key for live transport only. Do not log the return value."""
    presence = inspect_api_key_presence(env_var=env_var)
    if not presence.present:
        raise ApiKeyError(f"missing_api_key:{env_var}")
    return os.environ[env_var].strip()
