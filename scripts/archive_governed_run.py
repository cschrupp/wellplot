#!/usr/bin/env python3
"""Archive governed evidence without retaining secrets or mutable /tmp state."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import platform
import subprocess
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path

SECRET_NAMES = {
    ".env",
    "openai_api_key.txt",
    "openrouter_api_key.txt",
    "llama_cpp_api_key.txt",
    "unsloth_api_key.txt",
    "nvidia_api_key.txt",
}


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
        if path.name.casefold() in SECRET_NAMES or path.name.casefold().startswith(".env"):
            raise ValueError(f"credential-like file refused: {path.name}")
        if path.is_symlink():
            raise ValueError(f"credential-like file refused: {path.name}")
        relative = path.relative_to(root).as_posix()
        files.append({"path": relative, "bytes": path.stat().st_size, "sha256": sha256(path)})
    return files


def _write_deterministic_archive(source: Path, archive: Path) -> None:
    """Write a reproducible gzip/tar archive without directory metadata."""
    with (
        archive.open("wb") as stream,
        gzip.GzipFile(
            filename="",
            fileobj=stream,
            mode="wb",
            mtime=0,
            compresslevel=9,
        ) as compressed,
        tarfile.open(fileobj=compressed, mode="w") as bundle,
    ):
        for entry in inventory(source):
            relative = entry["path"]
            if not isinstance(relative, str):
                raise ValueError("archive inventory path is not a string")
            payload = (source / relative).read_bytes()
            info = tarfile.TarInfo(f"evidence/{relative}")
            info.size = len(payload)
            info.mode = 0o600
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            bundle.addfile(info, io.BytesIO(payload))


def _uv_version() -> str | None:
    """Capture the local uv version without invoking dependency resolution."""
    try:
        result = subprocess.run(
            ["uv", "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or result.stderr.strip() or None


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
    _write_deterministic_archive(source, args.archive)
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
            "uv": _uv_version(),
            "uv_lock_sha256": sha256(Path("uv.lock")) if Path("uv.lock").exists() else None,
        },
        "restoration": "RESTORATION_CHECK_PASS",
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
