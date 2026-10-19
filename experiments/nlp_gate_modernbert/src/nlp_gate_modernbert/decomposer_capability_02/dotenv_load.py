"""Minimal .env loader — never overrides an already-set environment variable."""

from __future__ import annotations

from pathlib import Path

from nlp_gate_modernbert.paths import EXPERIMENT_ROOT


def _parse_env_line(line: str) -> tuple[str, str] | None:
    raw = line.strip()
    if not raw or raw.startswith("#"):
        return None
    if raw.startswith("export "):
        raw = raw[len("export ") :].strip()
    if "=" not in raw:
        return None
    key, _, value = raw.partition("=")
    key = key.strip()
    if not key:
        return None
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1]
    return key, value


def load_dotenv_file(
    path: Path,
    *,
    environ: dict[str, str],
    override: bool = False,
) -> list[str]:
    """Load KEY=VALUE pairs into ``environ``.

    Returns the list of keys that were newly set (never the values).
    Existing keys are left unchanged unless ``override`` is True.
    """
    if not path.is_file():
        return []
    set_keys: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_env_line(line)
        if parsed is None:
            continue
        key, value = parsed
        if not override and key in environ and environ.get(key, "") != "":
            continue
        environ[key] = value
        set_keys.append(key)
    return set_keys


def experiment_dotenv_path() -> Path:
    return EXPERIMENT_ROOT / ".env"


def load_experiment_dotenv(
    *,
    environ: dict[str, str] | None = None,
    override: bool = False,
) -> dict[str, object]:
    """Load ``experiments/nlp_gate_modernbert/.env`` if present.

    Safe report only — no secret values.
    """
    import os

    env = environ if environ is not None else os.environ
    path = experiment_dotenv_path()
    set_keys = load_dotenv_file(path, environ=env, override=override)
    return {
        "dotenv_path": str(path),
        "dotenv_file_present": path.is_file(),
        "keys_set_from_dotenv": sorted(set_keys),
        "override": override,
    }
