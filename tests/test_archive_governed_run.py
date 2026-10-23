"""Provider-free tests for deterministic governed-evidence archives."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from scripts.archive_governed_run import _write_deterministic_archive, inventory


def test_archive_bytes_are_deterministic(tmp_path: Path) -> None:
    """Repeated archives of unchanged evidence have one stable digest."""
    source = tmp_path / "evidence"
    source.mkdir()
    (source / "result.json").write_text('{"calls": 0}\n')
    (source / "nested").mkdir()
    (source / "nested" / "notes.txt").write_text("bounded\n")
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"

    _write_deterministic_archive(source, first)
    _write_deterministic_archive(source, second)

    assert hashlib.sha256(first.read_bytes()).hexdigest() == hashlib.sha256(
        second.read_bytes()
    ).hexdigest()


def test_archive_inventory_rejects_case_variant_secret_names(tmp_path: Path) -> None:
    """Credential-like files are refused regardless of filename casing."""
    source = tmp_path / "evidence"
    source.mkdir()
    (source / "OPENROUTER_API_KEY.txt").write_text("secret")

    with pytest.raises(ValueError, match="credential-like"):
        inventory(source)
