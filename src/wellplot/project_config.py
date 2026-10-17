"""Validated, non-secret project runtime configuration."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, field_validator


class ProjectConfigError(ValueError):
    """Raised when the project configuration file cannot be loaded."""


def _normalize_server_origin(value: str) -> str:
    """Validate and normalize an origin without accepting path components."""
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("server_origin must be an HTTP or HTTPS origin")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("server_origin must not contain credentials, query, or fragment")
    if parsed.path not in {"", "/"}:
        raise ValueError("server_origin must not contain a path")
    try:
        _ = parsed.port
    except ValueError as error:
        raise ValueError("server_origin contains an invalid port") from error
    return value.rstrip("/")


class _FrozenModel(BaseModel):
    """Base model for strict, immutable configuration records."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ProviderConfig(_FrozenModel):
    """Non-secret provider and server settings."""

    name: Literal["openai_compat"]
    model: str = Field(min_length=1)
    server_origin: str
    timeout_seconds: Annotated[StrictInt | StrictFloat, Field(gt=0)]
    max_retries: StrictInt = Field(ge=0)

    @field_validator("server_origin")
    @classmethod
    def validate_server_origin(cls, value: str) -> str:
        """Reject non-origin values and normalize one trailing slash."""
        return _normalize_server_origin(value)

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout(cls, value: int | float) -> int | float:
        """Reject booleans and non-finite numeric timeout values."""
        if isinstance(value, bool) or not math.isfinite(float(value)):
            raise ValueError("timeout_seconds must be finite")
        return value

    @property
    def openai_compat_base_url(self) -> str:
        """Return the derived OpenAI-compatible API base URL."""
        return f"{self.server_origin}/v1"

    @property
    def model_catalog_url(self) -> str:
        """Return the derived model-catalog URL."""
        return f"{self.openai_compat_base_url}/models"

    @property
    def props_url(self) -> str:
        """Return the derived llama.cpp properties URL."""
        return f"{self.server_origin}/props"


class RuntimeConfig(_FrozenModel):
    """Canonical runtime controls shared by readiness and live execution."""

    concurrency: StrictInt = Field(ge=1)
    structured_output: Literal["json_schema"]


class ProjectConfig(_FrozenModel):
    """Complete non-secret project runtime configuration."""

    schema_version: Literal[1]
    provider: ProviderConfig
    runtime: RuntimeConfig

    @property
    def server_origin(self) -> str:
        """Return the configured server origin."""
        return self.provider.server_origin

    @property
    def openai_compat_base_url(self) -> str:
        """Return the derived OpenAI-compatible base URL."""
        return self.provider.openai_compat_base_url

    @property
    def model_catalog_url(self) -> str:
        """Return the derived model-catalog URL."""
        return self.provider.model_catalog_url

    @property
    def props_url(self) -> str:
        """Return the derived llama.cpp properties URL."""
        return self.provider.props_url

    @property
    def fingerprint_sha256(self) -> str:
        """Return the stable fingerprint of the normalized config values."""
        payload = self.model_dump(mode="json")
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def load_project_config(repo_root: Path, config_path: Path | None = None) -> ProjectConfig:
    """Load and validate the repository's non-secret YAML configuration."""
    path = config_path or repo_root / "config" / "wellplot.yaml"
    try:
        with path.open(encoding="utf-8") as handle:
            payload = yaml.safe_load(handle)
    except OSError as error:
        raise ProjectConfigError(f"cannot read project configuration: {path}") from error
    except yaml.YAMLError as error:
        raise ProjectConfigError(f"invalid project configuration YAML: {path}") from error
    if not isinstance(payload, dict):
        raise ProjectConfigError("project configuration must be a YAML mapping")
    return ProjectConfig.model_validate(payload)
