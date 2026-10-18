"""DECOMPOSER-PILOT-CONSTRAINT-CFG-ENGINE-BAKEOFF-01 / 01R / 01R2 tests."""

from __future__ import annotations

from pathlib import Path

from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff.fixtures import NEGATIVE
from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff.g2_audit import (
    audit_xgrammar_lowering,
)
from nlp_gate_modernbert.decomposer_pilot.cfg_engine_bakeoff.lower_xgrammar import (
    lower_well_ebnf1_to_xgrammar_ebnf,
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


def _g2_audit_source() -> str:
    return (
        Path(__file__).resolve().parents[1]
        / "src"
        / "nlp_gate_modernbert"
        / "decomposer_pilot"
        / "cfg_engine_bakeoff"
        / "g2_audit.py"
    ).read_text(encoding="utf-8")


_TINY_SOURCE = (
    'START ::= "ok" ;\n'
    'Lit ::= "a" ;\n'
    'Cls ::= ["b"] ;\n'
)

_TINY_LOWERED = (
    'START ::= "ok"\n'
    'Lit ::= "a"\n'
    'Cls ::= ["b"]\n'
)


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


def test_g2_audit_does_not_import_lowerer():
    src = _g2_audit_source()
    assert "lower_xgrammar" not in src
    assert "lower_well_ebnf1_to_xgrammar_ebnf" not in src
    assert "_rewrite_body" not in src


def test_g2_lowering_audit_pass_on_accepted_grammar():
    root = _repo_root()
    data, _ = load_accepted_grammar(root)
    well = data.decode("utf-8")
    lowered_a = lower_well_ebnf1_to_xgrammar_ebnf(well)
    lowered_b = lower_well_ebnf1_to_xgrammar_ebnf(well)
    audit = audit_xgrammar_lowering(
        well, lowered_a, lowered_ebnf_replay=lowered_b
    )
    assert audit["pass"], audit
    assert audit["audit_mode"] == "independent_source_vs_produced_target"
    assert audit["authorized_syntax_rewrites_only"] is True


def test_g2_audit_adversarial_delete_rule_fails():
    lines = _TINY_LOWERED.strip("\n").split("\n")
    deleted = "\n".join(lines[:2]) + "\n"
    audit = audit_xgrammar_lowering(_TINY_SOURCE, deleted)
    assert audit["pass"] is False
    assert audit["same_rule_count"] is False


def test_g2_audit_adversarial_rename_rule_fails():
    renamed = _TINY_LOWERED.replace("Lit ::= ", "Renamed ::= ", 1)
    audit = audit_xgrammar_lowering(_TINY_SOURCE, renamed)
    assert audit["pass"] is False
    assert audit["same_rule_identifiers"] is False


def test_g2_audit_adversarial_mutate_literal_fails():
    mutated = _TINY_LOWERED.replace('"a"', '"x"', 1)
    audit = audit_xgrammar_lowering(_TINY_SOURCE, mutated)
    assert audit["pass"] is False
    assert any("lit_char_mismatch" in u["reason"] for u in audit["unauthorized_rewrites"])


def test_g2_audit_adversarial_mutate_char_class_fails():
    mutated = _TINY_LOWERED.replace('["b"]', '["c"]', 1)
    audit = audit_xgrammar_lowering(_TINY_SOURCE, mutated)
    assert audit["pass"] is False
    assert any("cls_char_mismatch" in u["reason"] for u in audit["unauthorized_rewrites"])


def test_g2_audit_adversarial_unauthorized_escape_fails():
    # Escaping a non-authorized scalar inside a literal is not permitted.
    mutated = _TINY_LOWERED.replace('"a"', '"\\u0061"', 1)
    audit = audit_xgrammar_lowering(_TINY_SOURCE, mutated)
    assert audit["pass"] is False
    assert audit["unauthorized_rewrites"]


def test_g2_audit_adversarial_expression_change_fails():
    mutated = _TINY_LOWERED.replace('Lit ::= "a"', 'Lit ::= "a" | "z"', 1)
    audit = audit_xgrammar_lowering(_TINY_SOURCE, mutated)
    assert audit["pass"] is False


def test_g2_audit_authorized_scalar_escape_passes():
    # Authorized mid-line scalars (TAB / U+2028) may become \uXXXX inside literals.
    src = 'START ::= "x\ty\u2028z" ;\n'
    dst = 'START ::= "x\\u0009y\\u2028z"\n'
    audit = audit_xgrammar_lowering(src, dst)
    assert audit["pass"] is True, audit


def test_bakeoff_01r2_evidence_derived_gates():
    report = run_bakeoff(_repo_root())
    assert report["slice"].endswith("01R2")
    assert report["model_calls"] == 0
    assert report["model_weights_loaded"] is False
    assert report["source_oracle"]["pass"] is True
    assert report["g2_lowering_audit"]["pass"] is True
    assert report["g2_lowering_audit"]["audit_mode"] == (
        "independent_source_vs_produced_target"
    )
    xg = report["backends"]["xgrammar"]
    assert xg["status"] == "PASS"
    assert xg["gates"]["G2"] is True
    assert xg["gates"]["G3"] is True
    assert xg["gates"]["G5"] is True
    assert xg["gates"]["G6"] is True
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
