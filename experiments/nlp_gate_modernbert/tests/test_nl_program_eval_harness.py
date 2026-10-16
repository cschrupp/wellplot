"""NL-PROGRAM-EVAL-HARNESS-01R: freeze immutability, oracle lock, Q3 benign, fixture matrix."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest
from pydantic import ValidationError

from nlp_gate_modernbert.nl_program_eval.closed_schema import ClosedNormalizedProgram
from nlp_gate_modernbert.nl_program_eval.evaluate import evaluate_raw_candidate
from nlp_gate_modernbert.nl_program_eval.freeze import (
    FreezeFailure,
    FrozenCandidate,
    freeze_candidate,
    require_frozen,
)
from nlp_gate_modernbert.nl_program_eval.input import (
    FORBIDDEN_DECOMPOSER_KEYS,
    assert_decomposer_payload_clean,
    build_decomposer_input,
)
from nlp_gate_modernbert.nl_program_eval.oracle import load_oracle_program
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
    assert isinstance(a, FrozenCandidate)
    assert a.sha256 == b.sha256
    assert a.oracle_access_enabled is True


def test_canonicalization_key_order_invariant() -> None:
    a = {"tasks": [{"task_id": "t1", "depends_on": [], "produces_binds": {},
                    "request": {"requested_operation": "CREATE_TRACK", "track_title": "X"}}]}
    b = {"produces_binds": {}, "task_id": "t1", "request": {"track_title": "X",
         "requested_operation": "CREATE_TRACK"}, "depends_on": []}
    # reorder top-level task keys inside tasks array element via alternate construction
    raw_a = {"version": "v", "tasks": [a["tasks"][0]]}
    raw_b = {"tasks": [{
        "produces_binds": {},
        "depends_on": [],
        "request": {"track_title": "X", "requested_operation": "CREATE_TRACK"},
        "task_id": "t1",
    }], "version": "v"}
    fa, fb = freeze_candidate(raw_a), freeze_candidate(raw_b)
    assert isinstance(fa, FrozenCandidate) and isinstance(fb, FrozenCandidate)
    assert fa.sha256 == fb.sha256
    assert fa.canonical_json == fb.canonical_json


def test_canonicalization_whitespace_invariant() -> None:
    compact = json.dumps(_oracle_clean("D5GAP-0101"), separators=(",", ":"))
    pretty = json.dumps(_oracle_clean("D5GAP-0101"), indent=4)
    fa, fb = freeze_candidate(compact), freeze_candidate(pretty)
    assert isinstance(fa, FrozenCandidate) and isinstance(fb, FrozenCandidate)
    assert fa.sha256 == fb.sha256


def test_canonicalization_explicit_null_vs_omitted() -> None:
    base = {
        "tasks": [{
            "task_id": "t1",
            "depends_on": [],
            "produces_binds": {},
            "request": {
                "requested_operation": "CREATE_TRACK",
                "track_title": "Caliper QC",
                "track_width_mm": 24.0,
            },
        }]
    }
    with_null = deepcopy(base)
    with_null["tasks"][0]["request"]["report_title"] = None
    fa, fb = freeze_candidate(base), freeze_candidate(with_null)
    assert isinstance(fa, FrozenCandidate) and isinstance(fb, FrozenCandidate)
    assert fa.sha256 == fb.sha256


def test_canonicalization_semantic_value_changes_digest() -> None:
    raw = _oracle_clean("D5GAP-0101")
    a = freeze_candidate(raw)
    raw2 = deepcopy(raw)
    for t in raw2["tasks"]:
        if t["request"].get("requested_operation") == "CONFIGURE_CURVE_DISPLAY":
            t["request"]["scale_bounds"]["minimum"] = 0.0
    b = freeze_candidate(raw2)
    assert isinstance(a, FrozenCandidate) and isinstance(b, FrozenCandidate)
    assert a.sha256 != b.sha256


def test_frozen_candidate_immutable_and_digest_coupled() -> None:
    frozen = freeze_candidate(_oracle_clean("D5GAP-0101"))
    assert isinstance(frozen, FrozenCandidate)
    digest = frozen.sha256
    # frozen dataclass: attribute reassignment must fail
    with pytest.raises(Exception):
        frozen._sha256 = "0" * 64  # type: ignore[misc]
    with pytest.raises(Exception):
        frozen._canonical_json = "{}"  # type: ignore[misc]
    # mutating a re-parsed program must not change digest or canonical bytes
    prog = frozen.to_runtime_program()
    prog.tasks[0].task_id = "MUTATED"
    assert frozen.sha256 == digest
    assert frozen.verify_digest()
    prog2 = frozen.to_runtime_program()
    assert prog2.tasks[0].task_id != "MUTATED"
    # .program property is also a fresh re-parse
    assert frozen.program.tasks[0].task_id == prog2.tasks[0].task_id


def test_frozen_candidate_public_constructor_bypass_rejected() -> None:
    """R5: cannot forge FrozenCandidate without freeze_candidate / closed-schema path."""
    import hashlib

    raw = _oracle_clean("D5GAP-0101")
    legit = freeze_candidate(raw)
    assert isinstance(legit, FrozenCandidate)

    # Direct construction is hard-blocked
    with pytest.raises(TypeError, match="freeze_candidate"):
        FrozenCandidate(  # type: ignore[call-arg]
            legit.canonical_json,
            legit.sha256,
        )

    # Matching hash of arbitrary non-schema JSON is not acceptable via public API
    bogus = '{"tasks":[],"unexpected_top_level":true}'
    bogus_digest = hashlib.sha256(bogus.encode("utf-8")).hexdigest()
    with pytest.raises(TypeError, match="freeze_candidate"):
        FrozenCandidate(bogus, bogus_digest)  # type: ignore[call-arg]

    # Private factory still enforces closed-schema + canonicalization
    with pytest.raises(RuntimeError, match="frozen_candidate_"):
        FrozenCandidate._create_sealed(bogus, bogus_digest)

    # Non-canonical (valid schema, pretty-printed) rejected by seal factory
    pretty = json.dumps({"tasks": []}, indent=2)
    pretty_digest = hashlib.sha256(pretty.encode("utf-8")).hexdigest()
    with pytest.raises(RuntimeError, match="frozen_candidate_"):
        FrozenCandidate._create_sealed(pretty, pretty_digest)

    # require_frozen / oracle load still deny non-instances
    with pytest.raises(RuntimeError, match="oracle_access_denied_before_FrozenCandidate"):
        require_frozen({"canonical_json": legit.canonical_json, "sha256": legit.sha256})
    with pytest.raises(RuntimeError, match="oracle_access_denied_before_FrozenCandidate"):
        load_oracle_program(  # type: ignore[arg-type]
            {"_canonical_json": legit.canonical_json, "_sha256": legit.sha256},
            "D5GAP-0101",
        )


@pytest.mark.parametrize(
    "nest_path",
    ["top", "task", "request", "query", "scale", "fill"],
)
def test_closed_schema_recursive_forbid(nest_path: str) -> None:
    base: dict = {
        "tasks": [
            {
                "task_id": "t1",
                "depends_on": [],
                "produces_binds": {},
                "request": {
                    "requested_operation": "DEFINE_FILL",
                    "fill": {
                        "mode": "BETWEEN_INSTANCES",
                        "primary_query": "first CBL",
                        "predicate": {
                            "kind": "BETWEEN_CURVES",
                            "secondary_query": "second CBL",
                        },
                    },
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
        base["tasks"][0]["request"]["query"] = {"kind": "curve", "text": "GR", "extra_q": 1}
        base["tasks"][0]["request"]["requested_operation"] = "CONFIGURE_CURVE_DISPLAY"
        base["tasks"][0]["request"]["scale_bounds"] = {
            "kind": "linear", "minimum": 0.0, "maximum": 100.0
        }
        del base["tasks"][0]["request"]["fill"]
    elif nest_path == "scale":
        base["tasks"][0]["request"] = {
            "requested_operation": "CONFIGURE_CURVE_DISPLAY",
            "query": {"kind": "curve", "text": "GR"},
            "scale_bounds": {"kind": "linear", "minimum": 0.0, "maximum": 100.0, "extra_s": 1},
        }
    elif nest_path == "fill":
        base["tasks"][0]["request"]["fill"]["extra_fill"] = 1
    with pytest.raises(ValidationError):
        ClosedNormalizedProgram.model_validate(base)


def test_closed_schema_rejects_nan_infinity() -> None:
    raw = {
        "tasks": [
            {
                "task_id": "t1",
                "depends_on": [],
                "produces_binds": {},
                "request": {
                    "requested_operation": "CONFIGURE_CURVE_DISPLAY",
                    "query": {"kind": "curve", "text": "GR"},
                    "scale_bounds": {
                        "kind": "linear",
                        "minimum": float("nan"),
                        "maximum": 100.0,
                    },
                },
            }
        ]
    }
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


def test_oracle_load_requires_frozen_candidate() -> None:
    """R1: pre-freeze oracle retrieval must hard-fail at the loader boundary."""
    with pytest.raises(RuntimeError, match="oracle_access_denied_before_FrozenCandidate"):
        load_oracle_program("not_frozen", "D5GAP-0101")  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="oracle_access_denied_before_FrozenCandidate"):
        require_frozen(None)
    with pytest.raises(RuntimeError, match="oracle_access_denied_before_FrozenCandidate"):
        require_frozen(_oracle_clean("D5GAP-0101"))


def test_oracle_load_succeeds_only_with_frozen() -> None:
    frozen = freeze_candidate(_oracle_clean("D5GAP-0101"))
    assert isinstance(frozen, FrozenCandidate)
    oracle = load_oracle_program(frozen, "D5GAP-0101")
    assert len(oracle.tasks) == 3


def test_benign_redundant_is_non_identical_state_idempotent() -> None:
    """R3: fixture uses alias reconfigure, not an earlier-identical duplicate."""
    entry = next(e for e in load_manifest()["fixtures"] if e["scenario"] == "benign_redundant")
    raw = json.loads((CANDIDATES_DIR / entry["filename"]).read_text(encoding="utf-8"))
    texts = []
    for t in raw["tasks"]:
        req = t["request"]
        if req["requested_operation"] == "CONFIGURE_CURVE_DISPLAY" and req.get("query"):
            texts.append(req["query"].get("text"))
    # Must include two distinct query spellings for the wide CBL entity
    assert "wide CBL" in texts
    assert "CBL Amplitude wide" in texts
    assert texts.count("wide CBL") == 1
    rec = replay_one(entry)
    assert rec["semantically_equivalent"] is True
    assert "BENIGN_REDUNDANT_TASK" in rec["diagnostics"]
    assert rec["q3_comparison"]["benign_redundant_task_ids"]


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
