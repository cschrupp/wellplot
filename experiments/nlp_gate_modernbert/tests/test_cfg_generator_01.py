"""DECOMPOSER-PILOT-CONSTRAINT-CFG-GENERATOR-01 acceptance tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from nlp_gate_modernbert.decomposer_pilot.cfg_generator.generate import (
    generate_from_schema_bytes,
    default_pinned_schema_path,
)
from nlp_gate_modernbert.decomposer_pilot.constraint_schema import sha256_bytes
from nlp_gate_modernbert.nl_program_eval.freeze import FrozenCandidate, freeze_candidate
from support.well_ebnf1_recognizer import accepts, parse_well_ebnf1, recognize


def _schema_bytes() -> bytes:
    return default_pinned_schema_path().read_bytes()


@pytest.fixture(scope="module")
def generation():
    return generate_from_schema_bytes(_schema_bytes())


@pytest.fixture(scope="module")
def grammar(generation):
    return parse_well_ebnf1(generation.grammar_bytes)


def test_pinned_schema_hash_matches(generation):
    assert generation.schema_sha256 == sha256_bytes(_schema_bytes())


def test_coverage_no_unrecognized_or_silent(generation):
    assert generation.coverage["unrecognized_semantic_keywords"] == []
    assert generation.coverage["silently_ignored_semantic_keywords"] == []
    assert generation.coverage["schema_constructs_transformed"]
    assert generation.transform_ledger


def test_well_ebnf1_syntax_self_validation(generation):
    g = parse_well_ebnf1(generation.grammar_bytes)
    assert g.start == "START"
    assert "START" in g.by_lhs


def test_deterministic_replay_byte_identity():
    a = generate_from_schema_bytes(_schema_bytes())
    b = generate_from_schema_bytes(_schema_bytes())
    assert a.grammar_bytes == b.grammar_bytes
    assert a.grammar_sha256 == b.grammar_sha256
    assert a.transform_ledger == b.transform_ledger
    assert a.provenance["generator_source_sha256"] == b.provenance["generator_source_sha256"]


def test_hand_edit_detection(generation):
    mutated = bytearray(generation.grammar_bytes)
    # Flip a byte in a non-structural region if possible; else append illegal.
    idx = mutated.find(b"ClosedNormalizedProgram")
    assert idx >= 0
    mutated[idx] ^= 0x01
    assert sha256_bytes(bytes(mutated)) != generation.grammar_sha256


def _task(request_body: str, *, binds: str | None = None) -> str:
    mid = f'"produces_binds":{binds},' if binds is not None else ""
    return '{"tasks":[{' + mid + f'"request":{request_body},"task_id":"t1"' + "}]}"


def _req(*parts: str) -> str:
    return "{" + ",".join(parts) + "}"


POSITIVE = [
    ("empty_tasks", '{"tasks":[]}'),
    ("version_null", '{"tasks":[],"version":null}'),
    ("version_str", '{"tasks":[],"version":"v1"}'),
    (
        "text_only",
        _task(
            _req(
                '"query":{"kind":"curve","text":"GR"}',
                '"requested_operation":"PLACE_CURVE"',
            )
        ),
    ),
    (
        "local_ref_only",
        _task(
            _req(
                '"query":{"kind":"curve","local_ref":"bind1"}',
                '"requested_operation":"PLACE_CURVE"',
            )
        ),
    ),
    (
        "unicode_only_non_ws",
        _task(
            _req(
                '"query":{"kind":"curve","text":"\\u0047\\u0052"}',
                '"requested_operation":"PLACE_CURVE"',
            )
        ),
    ),
    (
        "optionals_absent",
        _task(_req('"requested_operation":"PLACE_CURVE"')),
    ),
    (
        "nullable_alpha_null",
        _task(_req('"alpha":null', '"requested_operation":"PLACE_CURVE"')),
    ),
    ("produces_binds_empty", _task(_req('"requested_operation":"PLACE_CURVE"'), binds="{}")),
    (
        "produces_binds_entry",
        _task(
            _req('"requested_operation":"PLACE_CURVE"'),
            binds='{"petrophysics":"track"}',
        ),
    ),
    ("array_empty_depends", _task(_req('"requested_operation":"PLACE_CURVE"'))),
    (
        "number_forms",
        _task(_req('"alpha":0', '"requested_operation":"PLACE_CURVE"')),
    ),
    (
        "number_frac_exp",
        _task(_req('"alpha":-0.5e+2', '"requested_operation":"PLACE_CURVE"')),
    ),
]

NEGATIVE = [
    ("both_text_and_ref", _task(_req(
        '"query":{"kind":"curve","text":"GR","local_ref":"x"}',
        '"requested_operation":"PLACE_CURVE"',
    ))),
    ("neither_text_nor_ref", _task(_req(
        '"query":{"kind":"curve"}',
        '"requested_operation":"PLACE_CURVE"',
    ))),
    ("empty_text", _task(_req(
        '"query":{"kind":"curve","text":""}',
        '"requested_operation":"PLACE_CURVE"',
    ))),
    ("spaces_text", _task(_req(
        '"query":{"kind":"curve","text":"   "}',
        '"requested_operation":"PLACE_CURVE"',
    ))),
    ("tab_escape", _task(_req(
        '"query":{"kind":"curve","text":"\\t"}',
        '"requested_operation":"PLACE_CURVE"',
    ))),
    ("u0009", _task(_req(
        '"query":{"kind":"curve","text":"\\u0009"}',
        '"requested_operation":"PLACE_CURVE"',
    ))),
    ("reordered_closed_keys", _task(_req(
        '"requested_operation":"PLACE_CURVE"',
        '"query":{"kind":"curve","text":"GR"}',
    ))),
    ("extra_property", '{"tasks":[],"extra":1}'),
    ("wrong_bind_value", _task(
        _req('"requested_operation":"PLACE_CURVE"'),
        binds='{"x":"curve"}',
    )),
    ("nan", _task(_req('"alpha":NaN', '"requested_operation":"PLACE_CURVE"'))),
    ("infinity", _task(_req('"alpha":Infinity', '"requested_operation":"PLACE_CURVE"'))),
    ("neg_infinity", _task(_req('"alpha":-Infinity', '"requested_operation":"PLACE_CURVE"'))),
    ("structural_space", '{"tasks": []}'),
    ("structural_newline", '{"tasks":[\n]}'),
]


@pytest.mark.parametrize("label,text", POSITIVE, ids=[p[0] for p in POSITIVE])
def test_positive_probes(grammar, label, text):
    assert recognize(grammar, text), label


@pytest.mark.parametrize("label,text", NEGATIVE, ids=[n[0] for n in NEGATIVE])
def test_negative_probes(grammar, label, text):
    assert not recognize(grammar, text), label


@pytest.mark.parametrize("label,text", POSITIVE, ids=[p[0] for p in POSITIVE])
def test_grammar_to_freeze_containment(grammar, label, text):
    assert recognize(grammar, text), label
    result = freeze_candidate(text)
    assert isinstance(result, FrozenCandidate), (label, result)


def test_model_and_engine_counters(generation):
    assert generation.provenance["model_calls"] == 0
    assert generation.provenance["engine_calls"] == 0


def test_accepts_helper_matches(generation):
    assert accepts(generation.grammar_bytes, '{"tasks":[]}')
    assert not accepts(generation.grammar_bytes, '{"tasks": []}')
