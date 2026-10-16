"""NL-PROGRAM-EVAL-HARNESS-01: freeze, Q3 compare, fixture matrix, schema negatives."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest
from pydantic import ValidationError

from nlp_gate_modernbert.nl_program_eval.closed_schema import (
    ClosedNormalizedProgram,
    ClosedNormalizedRequest,
    ClosedNormalizedTask,
    ClosedScaleBounds,
    ClosedSemanticQuery,
)
from nlp_gate_modernbert.nl_program_eval.evaluate import evaluate_raw_candidate
from nlp_gate_modernbert.nl_program_eval.freeze import FreezeFailure, freeze_candidate
from nlp_gate_modernbert.nl_program_eval.input import (
    FORBIDDEN_DECOMPOSER_KEYS,
    assert_decomposer_payload_clean,
    build_decomposer_input,
)
from nlp_gate_modernbert.nl_program_eval.replay import (
    CANDIDATES_DIR,
    load_manifest,
    replay_all,
    replay_one,
)
from nlp_gate_modernbert.scope_runtime.replay import load_witnesses


def _oracle_clean(case_id: str) -> dict:
    w = next(x for x in load_witnesses() if x["case_id"] == case_id)
    tasks = []
    for t in w["normalized_program"]["tasks"]:
        tasks.append(
            {
                "task_id": t["task_id"],
                "depends_on": list(t.get("depends_on") or []),
                "produces_binds": dict(t.get("produces_binds") or {}),
                "request": deepcopy(t["request"]),
            }
        )
    return {"version": w["normalized_program"].get("version"), "tasks": tasks}


def test_decomposer_input_allowlist_only() -> None:
    d = build_decomposer_input("D5GAP-0101")
    payload = d.to_payload()
    assert set(payload.keys()) == {"utterance", "projected_workspace"}
    assert_decomposer_payload_clean(payload)
    dirty = {**payload, "case_id": "D5GAP-0101"}
    with pytest.raises(RuntimeError, match="forbidden"):
        assert_decomposer_payload_clean(dirty)
    assert "case_id" in FORBIDDEN_DECOMPOSER_KEYS


def test_freeze_rejects_unknown_field() -> None:
    raw = _oracle_clean("D5GAP-0101")
    raw["unexpected"] = True
    r = freeze_candidate(raw)
    assert isinstance(r, FreezeFailure)
    assert r.failure == "DECOMPOSITION_SCHEMA_INVALID"


def test_freeze_digest_stable() -> None:
    raw = _oracle_clean("D5GAP-0101")
    a = freeze_candidate(raw)
    b = freeze_candidate(raw)
    assert not isinstance(a, FreezeFailure)
    assert a.sha256 == b.sha256
    assert a.oracle_access_enabled is True


@pytest.mark.parametrize(
    "nest_path",
    [
        "top",
        "task",
        "request",
        "query",
        "scale",
    ],
)
def test_closed_schema_recursive_forbid(nest_path: str) -> None:
    base = {
        "tasks": [
            {
                "task_id": "t1",
                "depends_on": [],
                "produces_binds": {},
                "request": {
                    "requested_operation": "CONFIGURE_CURVE_DISPLAY",
                    "query": {"kind": "curve", "text": "GR"},
                    "scale_bounds": {"kind": "linear", "minimum": 0.0, "maximum": 100.0},
                },
            }
        ]
    }
    if nest_path == "top":
        base["extra_top"] = 1
    elif nest_path == "task":
        base["tasks"][0]["extra_task"] = 1
    elif nest_path == "request":
        base["tasks"][0]["request"]["extra_req"] = 1
    elif nest_path == "query":
        base["tasks"][0]["request"]["query"]["extra_q"] = 1
    elif nest_path == "scale":
        base["tasks"][0]["request"]["scale_bounds"]["extra_s"] = 1
    with pytest.raises(ValidationError):
        ClosedNormalizedProgram.model_validate(base)


def test_closed_schema_rejects_nan_infinity() -> None:
    # NaN sneaks in via Python float before JSON; freeze canonicalization must reject
    raw = {
        "tasks": [
            {
                "task_id": "t1",
                "depends_on": [],
                "produces_binds": {},
                "request": {
                    "requested_operation": "CONFIGURE_CURVE_DISPLAY",
                    "query": {"kind": "curve", "text": "GR"},
                    "scale_bounds": {"kind": "linear", "minimum": float("nan"), "maximum": 100.0},
                },
            }
        ]
    }
    # Pydantic may reject NaN on float fields depending on config; either path is schema-invalid
    try:
        r = freeze_candidate(raw)
        assert isinstance(r, FreezeFailure)
    except ValidationError:
        pass

    raw2 = deepcopy(raw)
    raw2["tasks"][0]["request"]["scale_bounds"]["minimum"] = float("inf")
    try:
        r2 = freeze_candidate(raw2)
        assert isinstance(r2, FreezeFailure)
    except ValidationError:
        pass


def test_oracle_equivalent_six() -> None:
    for case_id in [
        "D5GAP-0085",
        "D5GAP-0089",
        "D5GAP-0096",
        "D5GAP-0101",
        "D5GAP-0117",
        "SEED-cm-9643c020e2e02463",
    ]:
        ev = evaluate_raw_candidate(case_id, _oracle_clean(case_id))
        assert ev.schema_valid
        assert ev.runtime_gate["candidate_terminal"]["authority"] == "OK"
        assert ev.semantically_equivalent is True
        assert all(ev.q3_comparison["coverage"].values())


def test_manifest_replay_all_match() -> None:
    out = replay_all(write_evidence=False)
    assert out["summary"]["n_fixtures"] == 18
    assert out["summary"]["all_expected_fixture_outcomes_match"] is True
    assert out["summary"]["oracle_access_before_freeze"] == 0
    assert out["summary"]["candidate_digest_collisions"] == 0
    assert out["summary"]["real_decomposer_calls"] == 0
    assert out["summary"]["oracle_candidate_generation_at_runtime"] == 0


def test_candidate_files_pure_program_payloads() -> None:
    manifest = load_manifest()
    forbidden = {"expected_evaluation", "candidate_fixture_role", "scenario", "case_id"}
    for entry in manifest["fixtures"]:
        raw = json.loads((CANDIDATES_DIR / entry["filename"]).read_text(encoding="utf-8"))
        assert not forbidden.intersection(raw.keys()), entry["filename"]


def test_schema_invalid_no_digest_no_oracle() -> None:
    entry = next(e for e in load_manifest()["fixtures"] if e["scenario"] == "schema_invalid")
    rec = replay_one(entry)
    assert rec["schema_valid"] is False
    assert rec["candidate_digest"] is None
    assert rec["oracle_access_enabled_after_freeze"] is False
    assert "DECOMPOSITION_SCHEMA_INVALID" in rec["failure_labels"]


def test_alias_and_alpha_equivalent() -> None:
    for scenario in ("alias_equivalent", "alpha_renamed_bind", "independent_order_variant"):
        entry = next(e for e in load_manifest()["fixtures"] if e["scenario"] == scenario)
        rec = replay_one(entry)
        assert rec["semantically_equivalent"] is True, scenario
