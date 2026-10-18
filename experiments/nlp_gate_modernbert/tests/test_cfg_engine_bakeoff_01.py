"""DECOMPOSER-PILOT-CONSTRAINT-CFG-ENGINE-BAKEOFF-01 / 01R tests."""

from __future__ import annotations

from pathlib import Path

from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff.fixtures import NEGATIVE
from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff.g2_audit import (
    audit_xgrammar_lowering,
)
from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff.pins import (
    ACCEPTED_GRAMMAR_SHA256,
    load_accepted_grammar,
    verify_pinned_tokenizer,
)
from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff.run_bakeoff import run_bakeoff
from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff.source_oracle import (
    source_oracle_parity,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_g1_grammar_and_tokenizer_pins():
    data, digest = load_accepted_grammar(_repo_root())
    assert digest == ACCEPTED_GRAMMAR_SHA256
    assert data
    pin = verify_pinned_tokenizer()
    assert pin["artifact_sha256"]


def test_source_oracle_matches_fixture_labels():
    root = _repo_root()
    data, _ = load_accepted_grammar(root)
    oracle = source_oracle_parity(root, data)
    assert oracle["pass"], oracle.get("failures")


def test_g2_lowering_audit_pass():
    root = _repo_root()
    data, _ = load_accepted_grammar(root)
    audit = audit_xgrammar_lowering(data.decode("utf-8"))
    assert audit["pass"], audit


def test_bakeoff_01r_evidence_derived_gates():
    report = run_bakeoff(_repo_root())
    assert report["model_calls"] == 0
    assert report["model_weights_loaded"] is False
    assert report["source_oracle"]["pass"] is True
    assert report["g2_lowering_audit"]["pass"] is True
    xg = report["backends"]["xgrammar"]
    assert xg["status"] == "PASS"
    assert xg["gates"]["G2"] is True
    assert xg["gates"]["G3"] is True
    assert xg["gates"]["G5"] is True
    assert xg["gates"]["G6"] is True
    # No invalid negative pass path
    neg_labels = {n[0] for n in NEGATIVE}
    for case in xg["token_replay"]["cases"]:
        if case["label"] not in neg_labels:
            continue
        assert "tokens_consumed_but_string_rejected" not in case["detail"]
        assert case["pass"] is True
        assert case["rejection_index"] is not None or (
            case["completed"] is False and case["any_stop_allowed"] is False
        )
    assert report["backends"]["llguidance"]["status"] == "REJECTED"
    assert report["recommendation"] == "xgrammar"
