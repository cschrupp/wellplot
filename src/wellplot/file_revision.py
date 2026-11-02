"""Stable filesystem revision tokens for optimistic authoring snapshots."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def file_revision_token(path: Path) -> str:
    """Fingerprint a regular file's resolved identity and filesystem revision."""
    resolved_path = path.resolve(strict=True)
    stat_result = resolved_path.stat()
    if not resolved_path.is_file():
        raise OSError("Inspected source is no longer a regular file.")
    payload = {
        "path": resolved_path.as_posix(),
        "device": stat_result.st_dev,
        "inode": stat_result.st_ino,
        "size": stat_result.st_size,
        "mtime_ns": stat_result.st_mtime_ns,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()
