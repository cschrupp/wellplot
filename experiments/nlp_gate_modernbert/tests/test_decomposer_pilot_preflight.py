"""DECOMPOSER-PILOT-PREFLIGHT-01: XOR patch, serializer, parity, model_calls=0."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nlp_gate_modernbert.decomposer_pilot import constraint_schema as cs
from nlp_gate_modernbert.decomposer_pilot import outlines_compile
from nlp_gate_modernbert.decomposer_pilot import parity as parity_mod
from nlp_gate_modernbert.decomposer_pilot import preflight
from nlp_gate_modernbert.decomposer_pilot.workspace_serialize import (
    serialize_projected_workspace,
)


def test_xor_patch_determinism() -> None:
    a, a_bytes, raw_a, patched_a = cs.build_constraint_artifact()
    b, b_bytes, raw_b, patched_b = cs.build_constraint_artifact()
    assert a_bytes == b_bytes
    assert raw_a == raw_b
    assert patched_a == patched_b
    assert a == b
    q = a["$defs"]["ClosedSemanticQuery"]
    assert "oneOf" in q
    assert len(q["oneOf"]) == 2
    branch_keys = [set(br["properties"]) for br in q["oneOf"]]
    assert {"kind", "text"} in branch_keys
    assert {"kind", "local_ref"} in branch_keys


def test_xor_patch_not_widen() -> None:
    raw = cs.raw_pydantic_schema()
    patched = cs.patch_constraint_schema(raw)
    # Must not raise:
    cs.assert_patched_subseteq_raw(raw, patched)


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
    assert "must_not_appear" not in text
    data = json.loads(text)
    assert [c["id"] for c in data["curves"]] == ["a", "b"]
    assert [t["ref"] for t in data["tracks"]] == [1, 2]
    assert [f["ref"] for f in data["fills"]] == ["f1", "f2"]
    # Nested arrays preserved (not re-sorted as sets).
    assert data["curves"][0]["aliases"] == ["m"]
    assert data["curves"][1]["aliases"] == ["z", "a"]
    assert data["tracks"][0]["curves"] == ["a"]
    assert data["tracks"][1]["curves"] == ["b", "a"]
    assert data["supported_depth_units"] == ["m", "ft"]
    # Canonical dumps flags.
    assert text == json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def test_parity_suite_green() -> None:
    patched, patched_bytes, _, _ = cs.build_constraint_artifact()
    compiled = outlines_compile.compile_json_schema(patched_bytes)
    result = parity_mod.run_parity_suite(
        patched_schema=patched,
        outlines_compiled=compiled,
    )
    assert result["pass"] is True
    assert result["probe_count"] == 9
    for probe in result["probes"]:
        assert probe["pass"] is True, probe


def test_preflight_model_calls_zero_and_no_generate(tmp_path: Path) -> None:
    preflight.MODEL_CALLS = 0
    out = preflight.run_preflight(evidence_dir=tmp_path)
    assert out["model_calls"] == 0
    assert preflight.MODEL_CALLS == 0
    assert (tmp_path / "decomposer_pilot_preflight_01_run_manifest.json").is_file()
    assert (tmp_path / "decomposer_pilot_preflight_01_parity.json").is_file()
    assert (tmp_path / "decomposer_pilot_preflight_01_constraint.schema.json").is_file()
    assert (tmp_path / "decomposer_pilot_preflight_01.md").is_file()
    manifest = json.loads(
        (tmp_path / "decomposer_pilot_preflight_01_run_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["model_calls"] == 0
    assert manifest["pilot_01"] == "NOT_AUTHORIZED"
    assert out["result"] == "PASS", out["failures"]

    # Guard must block generate if invoked.
    from transformers.generation import GenerationMixin

    with pytest.raises(preflight.GenerateForbiddenError):
        GenerationMixin.generate(None)  # type: ignore[misc]
