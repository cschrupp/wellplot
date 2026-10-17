"""MB-00 provenance pin helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_pinned_hashes(provenance: dict[str, Any]) -> list[str]:
    """Return list of mismatch descriptions (empty => OK)."""
    errors: list[str] = []
    pinned = provenance.get("pinned_sha256") or {}
    for key, expected in pinned.items():
        path = Path((provenance.get("paths") or {}).get(key, ""))
        if not path.is_absolute():
            # paths in provenance are absolute strings
            path = Path(str((provenance.get("paths") or {}).get(key, "")))
        actual = sha256_file(path) if path else None
        if actual != expected:
            errors.append(f"{key}: expected={expected} actual={actual} path={path}")
    return errors
