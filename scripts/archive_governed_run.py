#!/usr/bin/env python3
"""Archive governed evidence without retaining secrets or mutable /tmp state."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path

SECRET_NAMES = {".env", "OPENAI_API_KEY", "OPENROUTER_API_KEY", "LLAMA_CPP_API_KEY.txt"}


def sha256(path: Path) -> str:
    """Hash a regular file in bounded chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory(root: Path) -> list[dict[str, object]]:
    """Return deterministic file identities, rejecting credential-like files."""
    files: list[dict[str, object]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if path.name in SECRET_NAMES or path.name.startswith(".env"):
            raise ValueError(f"credential-like file refused: {path.name}")
        relative = path.relative_to(root).as_posix()
        files.append({"path": relative, "bytes": path.stat().st_size, "sha256": sha256(path)})
    return files


def main() -> int:
    """Archive one evidence root and independently restore-check it."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--authority", required=True)
    parser.add_argument("--checkpoint", required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    if not source.is_dir():
        raise SystemExit(f"source evidence root unavailable: {source}")
    files = inventory(source)
    args.archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(args.archive, "w:gz") as bundle:
        bundle.add(source, arcname="evidence", recursive=True, filter=lambda info: info)
    archive_hash = sha256(args.archive)
    with tempfile.TemporaryDirectory(prefix="wellplot-restore-") as restored:
        with tarfile.open(args.archive, "r:gz") as bundle:
            bundle.extractall(restored, filter="data")
        restored_files = inventory(Path(restored) / "evidence")
    if restored_files != files:
        raise SystemExit("RESTORATION_CHECK_FAIL")
    manifest = {
        "authority": args.authority,
        "scientific_checkpoint": args.checkpoint,
        "source_root": str(source),
        "archive": str(args.archive),
        "archive_sha256": archive_hash,
        "archive_bytes": args.archive.stat().st_size,
        "files": files,
        "created_at": datetime.now(UTC).isoformat(),
        "confidentiality": "private-local-evidence",
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "uv_lock_sha256": sha256(Path("uv.lock")) if Path("uv.lock").exists() else None,
        },
        "restoration": "RESTORATION_CHECK_PASS",
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
