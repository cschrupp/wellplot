"""Tests for strict, deterministic project runtime configuration."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from wellplot.project_config import ProjectConfigError, load_project_config

REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_config(tmp_path: Path, payload: str) -> Path:
    """Write one YAML payload below a temporary repository root."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    path = config_dir / "wellplot.yaml"
    path.write_text(payload, encoding="utf-8")
    return path


def test_repository_config_has_expected_derived_urls_and_values() -> None:
    """The checked-in config contains only the canonical non-secret settings."""
    config = load_project_config(REPO_ROOT)

    assert config.provider.name == "openai_compat"
    assert config.provider.model == "qwen3.6-35b-a3b"
    assert config.server_origin == "http://192.168.2.141:8888"
    assert config.openai_compat_base_url == "http://192.168.2.141:8888/v1"
    assert config.model_catalog_url == "http://192.168.2.141:8888/v1/models"
    assert config.props_url == "http://192.168.2.141:8888/props"
    assert config.provider.timeout_seconds == 900
    assert config.provider.max_retries == 2
    assert config.runtime.concurrency == 1
    assert config.runtime.structured_output == "json_schema"
    assert len(config.fingerprint_sha256) == 64


@pytest.mark.parametrize(
    "payload",
    [
        "schema_version: 1\nprovider: {}\nruntime: {}\n",
        """schema_version: 1
provider:
  name: openai_compat
  model: qwen
  server_origin: ftp://host
  timeout_seconds: 900
  max_retries: 2
runtime:
  concurrency: 1
  structured_output: json_schema
""",
        """schema_version: 1
provider:
  name: openai_compat
  model: qwen
  server_origin: http://host/v1
  timeout_seconds: 900
  max_retries: 2
runtime:
  concurrency: 1
  structured_output: json_schema
""",
    ],
)
def test_invalid_schema_or_server_origin_is_rejected(tmp_path: Path, payload: str) -> None:
    """Malformed or non-origin configuration fails closed."""
    path = _write_config(tmp_path, payload)
    with pytest.raises((ValidationError, ValueError)):
        load_project_config(tmp_path, path)


def test_schema_version_is_frozen(tmp_path: Path) -> None:
    """A future schema version cannot be accepted silently."""
    payload = """schema_version: 2
provider: {}
runtime: {}
"""
    with pytest.raises(ValidationError):
        load_project_config(tmp_path, _write_config(tmp_path, payload))


@pytest.mark.parametrize(
    "origin",
    [
        "192.168.2.141:8888",
        "http://host/?query=x",
        "http://host/#fragment",
    ],
)
def test_server_origin_requires_a_bare_http_origin(tmp_path: Path, origin: str) -> None:
    """Missing schemes and URL components are rejected rather than rewritten."""
    payload = f"""schema_version: 1
provider:
  name: openai_compat
  model: qwen3.6-35b-a3b
  server_origin: "{origin}"
  timeout_seconds: 900
  max_retries: 2
runtime:
  concurrency: 1
  structured_output: json_schema
"""
    with pytest.raises((ValidationError, ValueError)):
        load_project_config(tmp_path, _write_config(tmp_path, payload))


@pytest.mark.parametrize("port", ["abc", "-1", "65536"])
def test_server_origin_rejects_invalid_ports(tmp_path: Path, port: str) -> None:
    """Malformed and out-of-range ports fail closed."""
    payload = f"""schema_version: 1
provider:
  name: openai_compat
  model: qwen3.6-35b-a3b
  server_origin: http://host:{port}
  timeout_seconds: 900
  max_retries: 2
runtime:
  concurrency: 1
  structured_output: json_schema
"""
    with pytest.raises((ValidationError, ValueError)):
        load_project_config(tmp_path, _write_config(tmp_path, payload))


@pytest.mark.parametrize("port", ["1", "8888", "65535"])
def test_server_origin_accepts_valid_ports(tmp_path: Path, port: str) -> None:
    """Valid ports remain accepted at the boundaries and project default."""
    payload = f"""schema_version: 1
provider:
  name: openai_compat
  model: qwen3.6-35b-a3b
  server_origin: http://host:{port}
  timeout_seconds: 900
  max_retries: 2
runtime:
  concurrency: 1
  structured_output: json_schema
"""
    config = load_project_config(tmp_path, _write_config(tmp_path, payload))
    assert config.server_origin == f"http://host:{port}"


@pytest.mark.parametrize("missing", ["schema_version", "provider", "server_origin"])
def test_required_configuration_values_are_rejected(tmp_path: Path, missing: str) -> None:
    """Required top-level and nested values cannot silently default."""
    payload: dict[str, object] = {
        "schema_version": 1,
        "provider": {
            "name": "openai_compat",
            "model": "qwen3.6-35b-a3b",
            "server_origin": "http://192.168.2.141:8888",
            "timeout_seconds": 900,
            "max_retries": 2,
        },
        "runtime": {"concurrency": 1, "structured_output": "json_schema"},
    }
    if missing == "server_origin":
        assert isinstance(payload["provider"], dict)
        payload["provider"].pop("server_origin")
    else:
        payload.pop(missing)
    with pytest.raises(ValidationError):
        load_project_config(tmp_path, _write_config(tmp_path, yaml.safe_dump(payload)))


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("provider", "timeout_seconds", 0),
        ("provider", "max_retries", -1),
        ("runtime", "concurrency", 0),
        ("runtime", "structured_output", "text"),
    ],
)
def test_runtime_constraints_are_rejected(
    tmp_path: Path, section: str, field: str, value: object
) -> None:
    """Runtime values remain constrained by the typed configuration schema."""
    payload: dict[str, object] = {
        "schema_version": 1,
        "provider": {
            "name": "openai_compat",
            "model": "qwen3.6-35b-a3b",
            "server_origin": "http://192.168.2.141:8888",
            "timeout_seconds": 900,
            "max_retries": 2,
        },
        "runtime": {"concurrency": 1, "structured_output": "json_schema"},
    }
    assert isinstance(payload[section], dict)
    payload[section][field] = value
    with pytest.raises(ValidationError):
        load_project_config(tmp_path, _write_config(tmp_path, yaml.safe_dump(payload)))


def test_unknown_keys_and_secret_keys_are_rejected(tmp_path: Path) -> None:
    """The strict schema prevents unreviewed settings and secret material."""
    payload = yaml.safe_dump(
        {
            "schema_version": 1,
            "provider": {
                "name": "openai_compat",
                "model": "qwen3.6-35b-a3b",
                "server_origin": "http://192.168.2.141:8888",
                "timeout_seconds": 900,
                "max_retries": 2,
                "api_key": "must-not-be-in-yaml",
            },
            "runtime": {"concurrency": 1, "structured_output": "json_schema"},
            "unexpected": True,
        }
    )
    with pytest.raises(ValidationError):
        load_project_config(tmp_path, _write_config(tmp_path, payload))


def test_fingerprint_is_stable_for_comments_and_key_order(tmp_path: Path) -> None:
    """Formatting-only YAML changes do not alter the semantic fingerprint."""
    first = """schema_version: 1
provider:
  name: openai_compat
  model: qwen3.6-35b-a3b
  server_origin: http://192.168.2.141:8888/
  timeout_seconds: 900
  max_retries: 2
runtime:
  concurrency: 1
  structured_output: json_schema
"""
    second = """# formatting-only comment
runtime:
  structured_output: json_schema
  concurrency: 1
provider:
  max_retries: 2
  timeout_seconds: 900
  server_origin: http://192.168.2.141:8888
  model: qwen3.6-35b-a3b
  name: openai_compat
schema_version: 1
"""
    first_config = load_project_config(tmp_path, _write_config(tmp_path, first))
    second_path = tmp_path / "config" / "second.yaml"
    second_path.write_text(second, encoding="utf-8")
    second_config = load_project_config(tmp_path, second_path)

    assert first_config.fingerprint_sha256 == second_config.fingerprint_sha256


def test_fingerprint_changes_when_runtime_value_changes(tmp_path: Path) -> None:
    """A semantic runtime change changes the authorization fingerprint."""
    base = """schema_version: 1
provider:
  name: openai_compat
  model: qwen3.6-35b-a3b
  server_origin: http://192.168.2.141:8888
  timeout_seconds: 900
  max_retries: 2
runtime:
  concurrency: 1
  structured_output: json_schema
"""
    changed = base.replace("timeout_seconds: 900", "timeout_seconds: 901")
    first = load_project_config(tmp_path, _write_config(tmp_path, base))
    second_path = tmp_path / "config" / "changed.yaml"
    second_path.write_text(changed, encoding="utf-8")
    second = load_project_config(tmp_path, second_path)

    assert first.fingerprint_sha256 != second.fingerprint_sha256


def test_missing_config_is_a_bounded_configuration_error(tmp_path: Path) -> None:
    """A missing config is reported before any runtime activity."""
    with pytest.raises(ProjectConfigError, match="cannot read"):
        load_project_config(tmp_path)
