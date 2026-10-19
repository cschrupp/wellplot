"""Immutable bakeoff input pins (G1)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from nlp_gate_modernbert.decomposer_pilot.model_provenance import default_snapshot_path

ACCEPTED_GRAMMAR_REL = Path(
    "experiments/nlp_gate_modernbert/evidence/"
    "decomposer_pilot_constraint_cfg_generator_01.well_ebnf1"
)
ACCEPTED_GRAMMAR_SHA256 = (
    "f8cfd0c2b8a2cb2c708e464147080ebd7400e40e8060fa0426e423d70396d9d3"
)

TOKENIZER_HASHES = {
    "tokenizer.json": "aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4",
    "tokenizer_config.json": "d5d09f07b48c3086c508b30d1c9114bd1189145b74e982a265350c923acd8101",
    "merges.txt": "8831e4f1a044471340f7c0a83d7bd71306a5b867e95fd870f74d0c5308a904d5",
    "vocab.json": "ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910",
}


class PinnedTokenizerUnavailable(RuntimeError):
    """Pinned local tokenizer absent or hash mismatch — do not download."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def load_accepted_grammar(repo_root: Path) -> tuple[bytes, str]:
    path = repo_root / ACCEPTED_GRAMMAR_REL
    data = path.read_bytes()
    digest = sha256_bytes(data)
    if digest != ACCEPTED_GRAMMAR_SHA256:
        raise RuntimeError(
            f"grammar hash mismatch: got {digest} expected {ACCEPTED_GRAMMAR_SHA256}"
        )
    return data, digest


def verify_pinned_tokenizer(snapshot: Path | None = None) -> dict[str, Any]:
    snap = (snapshot or default_snapshot_path()).resolve()
    if not snap.is_dir():
        raise PinnedTokenizerUnavailable(f"snapshot missing: {snap}")
    hashes: dict[str, str] = {}
    for name, expected in TOKENIZER_HASHES.items():
        fp = snap / name
        if not fp.is_file():
            raise PinnedTokenizerUnavailable(f"missing {fp}")
        got = sha256_file(fp)
        if got != expected:
            raise PinnedTokenizerUnavailable(
                f"hash mismatch {name}: got {got} expected {expected}"
            )
        hashes[name] = got
    return {"snapshot_path": str(snap), "artifact_sha256": hashes}
