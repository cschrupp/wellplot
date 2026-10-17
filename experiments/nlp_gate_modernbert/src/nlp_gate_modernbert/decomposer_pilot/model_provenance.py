"""Resolve and hash local Qwen/Qwen3-1.7B ModelScope snapshot (no download, no generate)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from nlp_gate_modernbert.paths import SLM01_ROOT

MODEL_ID = "Qwen/Qwen3-1.7B"
SNAPSHOT_REL = Path("artifacts/modelscope_cache/models/Qwen--Qwen3-1.7B/snapshots/master")

# Files hashed for tokenizer/config provenance.
CONFIG_FILES = (
    "config.json",
    "configuration.json",
    "generation_config.json",
    "tokenizer_config.json",
    "tokenizer.json",
    "vocab.json",
    "merges.txt",
)

WEIGHT_SUFFIXES = (".safetensors", ".bin", ".pt", ".gguf")


def default_snapshot_path() -> Path:
    return (SLM01_ROOT / SNAPSHOT_REL).resolve()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def resolve_snapshot(snapshot_path: Path | None = None) -> Path:
    path = (snapshot_path or default_snapshot_path()).resolve()
    if not path.is_dir():
        raise FileNotFoundError(f"Qwen snapshot absent: {path}")
    required = ("config.json", "tokenizer_config.json")
    missing = [n for n in required if not (path / n).is_file()]
    if missing:
        raise FileNotFoundError(f"Qwen snapshot incomplete at {path}; missing {missing}")
    return path


def _weight_files(snapshot: Path) -> list[Path]:
    weights: list[Path] = []
    for p in sorted(snapshot.iterdir()):
        if not p.is_file():
            continue
        if p.suffix.lower() in WEIGHT_SUFFIXES or p.name.endswith(".safetensors"):
            weights.append(p)
    # Prefer shard files; include index json separately in config hashes if present.
    return weights


def collect_model_provenance(snapshot_path: Path | None = None) -> dict[str, Any]:
    snapshot = resolve_snapshot(snapshot_path)
    config_hashes: dict[str, str | None] = {}
    for name in CONFIG_FILES:
        fp = snapshot / name
        config_hashes[name] = sha256_file(fp) if fp.is_file() else None

    weight_manifest: list[dict[str, Any]] = []
    for wp in _weight_files(snapshot):
        weight_manifest.append(
            {
                "path": str(wp.relative_to(snapshot)),
                "size_bytes": wp.stat().st_size,
                "sha256": sha256_file(wp),
            }
        )

    aggregate_payload = json.dumps(
        weight_manifest,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    aggregate_sha = hashlib.sha256(aggregate_payload.encode("utf-8")).hexdigest()

    index_path = snapshot / "model.safetensors.index.json"
    return {
        "model_id": MODEL_ID,
        "variant": "instruction/non-Base checkpoint",
        "source": "existing local ModelScope snapshot",
        "snapshot_path": str(snapshot),
        "snapshot_revision": "master",
        "adapters": "NONE",
        "auto_download": False,
        "fallback_model": "NONE",
        "config_sha256": config_hashes.get("config.json"),
        "tokenizer_artifact_sha256": {
            k: config_hashes[k]
            for k in (
                "tokenizer_config.json",
                "tokenizer.json",
                "vocab.json",
                "merges.txt",
            )
        },
        "all_config_artifact_sha256": config_hashes,
        "weight_file_manifest": weight_manifest,
        "aggregate_weight_manifest_sha256": aggregate_sha,
        "model_index_sha256": sha256_file(index_path) if index_path.is_file() else None,
    }
