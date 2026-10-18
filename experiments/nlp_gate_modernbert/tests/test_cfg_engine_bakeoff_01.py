"""DECOMPOSER-PILOT-CONSTRAINT-CFG-ENGINE-BAKEOFF-01 tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff.pins import (
    ACCEPTED_GRAMMAR_SHA256,
    PinnedTokenizerUnavailable,
    load_accepted_grammar,
    verify_pinned_tokenizer,
)
from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff.run_bakeoff import run_bakeoff


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_g1_grammar_and_tokenizer_pins():
    data, digest = load_accepted_grammar(_repo_root())
    assert digest == ACCEPTED_GRAMMAR_SHA256
    assert data
    pin = verify_pinned_tokenizer()
    assert pin["artifact_sha256"]


def test_bakeoff_recommends_xgrammar_rejects_llguidance_pathology():
    report = run_bakeoff(_repo_root())
    assert report["model_calls"] == 0
    assert report["model_weights_loaded"] is False
    assert report["backends"]["xgrammar"]["status"] == "PASS"
    assert report["backends"]["xgrammar"]["gates"]["G3"] is True
    assert report["backends"]["xgrammar"]["gates"]["G5"] is True
    assert report["backends"]["llguidance"]["status"] == "REJECTED"
    assert report["backends"]["llguidance"]["reject_gate"] == "G7"
    assert report["recommendation"] == "xgrammar"
