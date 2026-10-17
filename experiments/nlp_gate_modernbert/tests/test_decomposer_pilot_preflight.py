"""DECOMPOSER-PILOT-PREFLIGHT-01R: R1–R3 pins; fail-closed when Outlines cannot enforce."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from nlp_gate_modernbert.decomposer_pilot import constraint_schema as cs
from nlp_gate_modernbert.decomposer_pilot import outlines_compile
from nlp_gate_modernbert.decomposer_pilot import parity as parity_mod
from nlp_gate_modernbert.decomposer_pilot import preflight
from nlp_gate_modernbert.decomposer_pilot.model_provenance import default_snapshot_path
from nlp_gate_modernbert.decomposer_pilot.workspace_serialize import (
    serialize_projected_workspace,
    serializer_spec,
)


def test_xor_patch_determinism_and_nonempty_pattern() -> None:
    a, a_bytes, raw_a, patched_a = cs.build_constraint_artifact()
    b, b_bytes, raw_b, patched_b = cs.build_constraint_artifact()
    assert a_bytes == b_bytes
    assert raw_a == raw_b
    assert patched_a == patched_b
    q = a["$defs"]["ClosedSemanticQuery"]
    assert "oneOf" in q
    assert len(q["oneOf"]) == 2
    for branch in q["oneOf"]:
        for field in ("text", "local_ref"):
            if field in branch["properties"]:
                assert branch["properties"][field]["type"] == "string"
                assert branch["properties"][field]["pattern"] == ".*\\S.*"


def test_xor_patch_not_widen() -> None:
    raw = cs.raw_pydantic_schema()
    patched = cs.patch_constraint_schema(raw)
    cs.assert_patched_subseteq_raw(raw, patched)


def test_constraint_identity_pins() -> None:
    ident = cs.constraint_identity()
    assert ident["constraint_patch_version"] == cs.CONSTRAINT_PATCH_VERSION
    assert ident["canonical_json_version"] == cs.CANONICAL_JSON_VERSION
    assert ident["canonical_json_spec"] == cs.CANONICAL_JSON_SPEC
    assert ident["constraint_patcher_source_sha256"] == cs.patcher_source_sha256()


def test_serializer_omits_fixture_id_and_orders() -> None:
    ws = {
        "fixture_id": "must_not_appear",
        "curves": [
            {"id": "b", "handle": "B", "aliases": ["z", "a"]},
            {"id": "a", "handle": "A", "aliases": ["m"]},
        ],
        "tracks": [
            {"ref": 2, "title": "T2", "curves": ["b", "a"]},
            {"ref": 1, "title": "T1", "curves": ["a"]},
        ],
        "fills": [
            {"ref": "f2", "curve": "b"},
            {"ref": "f1", "curve": "a"},
        ],
        "focus_curve_handle": None,
        "depth_unit": "m",
        "supported_depth_units": ["m", "ft"],
    }
    text = serialize_projected_workspace(ws)
    assert "fixture_id" not in text
    data = json.loads(text)
    assert [c["id"] for c in data["curves"]] == ["a", "b"]
    assert serializer_spec()["sort_curves_by"] == "(id, handle-or-empty)"


def test_jsonschema_enforces_nonempty_and_xor() -> None:
    patched, _, _, _ = cs.build_constraint_artifact()
    result = parity_mod.run_parity_suite(
        patched_schema=patched,
        outlines_compiled=None,
    )
    assert result["pass"] is True
    assert result["probe_count"] >= 13


def test_outlines_language_fail_closed_on_pattern_gaps() -> None:
    """Frozen rule: if Outlines language diverges from jsonschema expectations → not green."""
    patched, patched_bytes, _, _ = cs.build_constraint_artifact()
    compiled = outlines_compile.compile_json_schema(patched_bytes)
    result = parity_mod.run_parity_suite(
        patched_schema=patched,
        outlines_compiled=compiled,
    )
    # Documented Outlines gaps with pattern .*\S.* (greedy oneOf + JSON \\t escape).
    failed = {p["probe_id"] for p in result["probes"] if not p["pass"]}
    assert "xor_both" in failed or "xor_text_whitespace_tab" in failed
    assert result["pass"] is False


def test_preflight_fail_closed_model_calls_zero(tmp_path: Path) -> None:
    """Parity Outlines gap alone forces FAIL; token-guide DFA covered in dedicated slow test."""
    preflight.MODEL_CALLS = 0
    out = preflight.run_preflight(evidence_dir=tmp_path, skip_token_guide=True)
    assert out["model_calls"] == 0
    assert preflight.MODEL_CALLS == 0
    assert out["result"] == "FAIL"
    assert any("parity_failed" in f for f in out["failures"])
    manifest = json.loads(
        (tmp_path / "decomposer_pilot_preflight_01_run_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["model_calls"] == 0
    assert manifest["pilot_01"] == "NOT_AUTHORIZED"
    assert manifest["slice"] == "DECOMPOSER-PILOT-PREFLIGHT-01R"
    assert manifest["prior_candidate"] == preflight.PRIOR_PREFLIGHT_01_CANDIDATE
    assert manifest["result"] == "FAIL"
    schema = json.loads(
        (tmp_path / "decomposer_pilot_preflight_01_constraint.schema.json").read_text(
            encoding="utf-8"
        )
    )
    text_branch = schema["$defs"]["ClosedSemanticQuery"]["oneOf"][0]
    assert text_branch["properties"]["text"]["pattern"] == ".*\\S.*"

    from transformers.generation import GenerationMixin

    with pytest.raises(preflight.GenerateForbiddenError):
        GenerationMixin.generate(None)  # type: ignore[misc]


def test_token_level_constraint_dfa_fail_closed_slow(tmp_path: Path) -> None:
    """R2: Index construction must succeed; DFA explosion → fail closed (no backend swap)."""
    _, patched_bytes, _, patched_sha = cs.build_constraint_artifact()
    artifact = tmp_path / cs.CONSTRAINT_ARTIFACT_NAME
    artifact.write_bytes(patched_bytes)
    persisted = artifact.read_bytes()
    assert hashlib.sha256(persisted).hexdigest() == patched_sha
    with pytest.raises(ValueError, match="DFA|dfa|states"):
        outlines_compile.construct_token_level_constraint(
            persisted_schema_bytes=persisted,
            expected_schema_sha256=patched_sha,
            snapshot_path=default_snapshot_path(),
        )
