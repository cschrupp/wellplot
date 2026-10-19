"""C02-03 env config: .env loading, boolean presence, no secret leakage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nlp_gate_modernbert.decomposer_capability_02.api_key import (
    ApiKeyError,
    inspect_api_key_presence,
    load_api_key,
)
from nlp_gate_modernbert.decomposer_capability_02.dotenv_load import (
    load_dotenv_file,
    load_experiment_dotenv,
)
from nlp_gate_modernbert.paths import EXPERIMENT_ROOT, EVIDENCE_DIR


def test_env_example_exists_and_env_is_gitignored() -> None:
    example = EXPERIMENT_ROOT / ".env.example"
    assert example.is_file()
    text = example.read_text(encoding="utf-8")
    assert "OPENROUTER_API_KEY=" in text
    assert "sk-or-" not in text  # placeholder only
    gi = (EXPERIMENT_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gi


def test_dotenv_does_not_override_explicit_env(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("OPENROUTER_API_KEY=from-dotenv\nOTHER=1\n", encoding="utf-8")
    environ = {"OPENROUTER_API_KEY": "from-shell"}
    set_keys = load_dotenv_file(env_file, environ=environ, override=False)
    assert environ["OPENROUTER_API_KEY"] == "from-shell"
    assert "OPENROUTER_API_KEY" not in set_keys
    assert environ["OTHER"] == "1"


def test_dotenv_sets_missing_key(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text('OPENROUTER_API_KEY="sk-or-v1-TESTONLY"\n', encoding="utf-8")
    environ: dict[str, str] = {}
    set_keys = load_dotenv_file(env_file, environ=environ, override=False)
    assert set_keys == ["OPENROUTER_API_KEY"]
    assert environ["OPENROUTER_API_KEY"] == "sk-or-v1-TESTONLY"


def test_presence_report_is_boolean_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    # Point loader at empty temp by monkeypatching path via environ-only inspection
    absent = inspect_api_key_presence(load_dotenv=False)
    payload = absent.to_json()
    assert payload == {
        "OPENROUTER_API_KEY_PRESENT": False,
        "env_var": "OPENROUTER_API_KEY",
    }
    assert "length" not in payload
    assert "prefix" not in json.dumps(payload).lower()

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-DO-NOT-LEAK")
    present = inspect_api_key_presence(load_dotenv=False)
    dumped = json.dumps(present.to_json())
    assert present.present is True
    assert "DO-NOT-LEAK" not in dumped
    assert present.to_json()["OPENROUTER_API_KEY_PRESENT"] is True


def test_evidence_artifacts_must_not_contain_secret_patterns() -> None:
    secretish = ("sk-or-v1-", "OPENROUTER_API_KEY=")
    root = EVIDENCE_DIR / "decomposer_capability_02"
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in {".json", ".md", ".jsonl"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        # Allow documenting the env var name, not an assigned secret value.
        assert "sk-or-v1-" not in text
        for line in text.splitlines():
            if "OPENROUTER_API_KEY=" in line and not line.strip().startswith("#"):
                # .env.example is outside evidence/; evidence must not embed assignments
                assert False, f"secret_assignment_in_evidence:{path}"


def test_load_api_key_refuses_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ApiKeyError):
        load_api_key(load_dotenv=False)
