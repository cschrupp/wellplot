"""OpenRouter API key handling via process env and optional project .env.

Never print, log, commit, or serialize the secret. Presence reports are boolean only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from nlp_gate_modernbert.decomposer_capability_02.dotenv_load import load_experiment_dotenv


class ApiKeyError(RuntimeError):
    """Missing or invalid API key configuration."""


DEFAULT_ENV_VAR = "OPENROUTER_API_KEY"


@dataclass(frozen=True)
class ApiKeyPresence:
    """Safe-to-serialize key presence (boolean only; no length/prefix/secret)."""

    env_var: str
    present: bool

    def to_json(self) -> dict:
        return {
            "OPENROUTER_API_KEY_PRESENT": self.present,
            "env_var": self.env_var,
        }


def ensure_dotenv_loaded(*, override: bool = False) -> dict[str, object]:
    """Load project-local .env without overriding explicit environment variables."""
    return load_experiment_dotenv(override=override)


def inspect_api_key_presence(
    *,
    env_var: str = DEFAULT_ENV_VAR,
    load_dotenv: bool = True,
) -> ApiKeyPresence:
    if load_dotenv:
        ensure_dotenv_loaded(override=False)
    raw = os.environ.get(env_var)
    present = bool(raw is not None and raw.strip() != "")
    return ApiKeyPresence(env_var=env_var, present=present)


def load_api_key(*, env_var: str = DEFAULT_ENV_VAR, load_dotenv: bool = True) -> str:
    """Return the key for an authorized live transport only. Do not log the return value."""
    presence = inspect_api_key_presence(env_var=env_var, load_dotenv=load_dotenv)
    if not presence.present:
        raise ApiKeyError(f"missing_api_key:{env_var}")
    return os.environ[env_var].strip()
