"""MB-00 bootstrap invariants."""

from __future__ import annotations

import json
from pathlib import Path

from nlp_gate_modernbert import MB00_AUTHORITY
from nlp_gate_modernbert.paths import ARTIFACTS_DIR, EVIDENCE_DIR, EXPERIMENT_ROOT, SLM03_ADAPTER
from nlp_gate_modernbert.provenance import load_json, sha256_file, verify_pinned_hashes


def test_mb00_authority_preserved_in_provenance() -> None:
    prov = load_json(EVIDENCE_DIR / "mb00_provenance.json")
    assert prov["authority"] == MB00_AUTHORITY
    assert prov["slice"] == "MB-00"


def test_layout_exists() -> None:
    assert EXPERIMENT_ROOT.is_dir()
    assert (EXPERIMENT_ROOT / "README.md").is_file()
    assert (EXPERIMENT_ROOT / "pyproject.toml").is_file()
    assert EVIDENCE_DIR.is_dir()
    assert ARTIFACTS_DIR.is_dir()


def test_artifacts_writable() -> None:
    probe = ARTIFACTS_DIR / "mb00_write_probe.txt"
    probe.write_text("ok\n", encoding="utf-8")
    assert probe.read_text(encoding="utf-8") == "ok\n"
    probe.unlink()


def test_provenance_present_and_valid() -> None:
    path = EVIDENCE_DIR / "mb00_provenance.json"
    assert path.is_file()
    prov = load_json(path)
    assert prov["slice"] == "MB-00"
    assert prov["authority"] == MB00_AUTHORITY
    assert prov["d5_sha"] == "560ec48d2b2809ed2feb55467da15195f527ec44"
    assert prov["well_ir_version"] == "1.2-candidate"
    errors = verify_pinned_hashes(prov)
    assert errors == [], errors


def test_slm03_adapter_untouched_hash() -> None:
    prov = load_json(EVIDENCE_DIR / "mb00_provenance.json")
    expected = prov["pinned_sha256"]["slm03_adapter_model"]
    actual = sha256_file(SLM03_ADAPTER / "adapter_model.safetensors")
    assert actual == expected


def test_no_forbidden_deps_in_pyproject() -> None:
    text = (EXPERIMENT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    # pydantic allowed; forbid ML/orchestration requirement pins
    req_lines = [
        ln.lower()
        for ln in text.splitlines()
        if ln.strip().startswith('"') or ln.strip().startswith("'")
    ]
    banned = ("torch", "transformers", "langgraph", "unsloth", "modernbert", "t5")
    for ln in req_lines:
        for b in banned:
            assert b not in ln, ln
