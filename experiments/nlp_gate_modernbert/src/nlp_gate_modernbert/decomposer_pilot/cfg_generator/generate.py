"""Semantic library entrypoint: pinned schema bytes → canonical WELL-EBNF-1."""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nlp_gate_modernbert.decomposer_pilot.cfg_generator.compile_schema import SchemaCompiler
from nlp_gate_modernbert.decomposer_pilot.cfg_generator.emit_ebnf import emit_grammar_file
from nlp_gate_modernbert.decomposer_pilot.cfg_generator.errors import GeneratorFail
from nlp_gate_modernbert.decomposer_pilot.cfg_generator.json_lex import install_json_lexicals
from nlp_gate_modernbert.decomposer_pilot.constraint_schema import (
    CANONICAL_JSON_SPEC,
    CANONICAL_JSON_VERSION,
    CONSTRAINT_ARTIFACT_NAME,
    CONSTRAINT_PATCH_VERSION,
    build_constraint_artifact,
    canonical_json_bytes,
    sha256_bytes,
)

GENERATOR_VERSION = "decomposer_pilot_cfg_generator.v1"
WELL_EBNF_1_VERSION = "1.0.0"
RULE_ORDER_SPEC = "START first; remaining Identifiers ascending by UTF-8 byte sequence"

PINNED_SCHEMA_RELPATH = (
    "experiments/nlp_gate_modernbert/evidence/" + CONSTRAINT_ARTIFACT_NAME
)


@dataclass(frozen=True, slots=True)
class GenerationResult:
    grammar_bytes: bytes
    grammar_sha256: str
    transform_ledger: list[dict[str, str]]
    coverage: dict[str, Any]
    provenance: dict[str, Any]
    schema_sha256: str


def _generator_source_sha256() -> str:
    root = Path(__file__).resolve().parent
    h = hashlib.sha256()
    for path in sorted(root.glob("*.py")):
        h.update(path.name.encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def expected_pinned_schema_sha256() -> str:
    """SHA-256 of the mechanically rebuilt patched constraint artifact."""
    _, patched_bytes, _, patched_sha = build_constraint_artifact()
    return patched_sha


def load_and_verify_schema_bytes(schema_bytes: bytes) -> tuple[dict[str, Any], str]:
    """Fail closed unless bytes match the pinned rebuilt patched schema."""
    expected = expected_pinned_schema_sha256()
    got = sha256_bytes(schema_bytes)
    if got != expected:
        raise GeneratorFail(
            "patched_schema_hash_mismatch",
            f"got={got} expected={expected}",
        )
    # Also require byte-identity with rebuild (not merely hash collision risk)
    _, rebuilt, _, _ = build_constraint_artifact()
    if schema_bytes != rebuilt:
        raise GeneratorFail(
            "patched_schema_hash_mismatch",
            "schema bytes differ from rebuild despite hash check",
        )
    schema = json.loads(schema_bytes.decode("utf-8"))
    if not isinstance(schema, dict):
        raise GeneratorFail("UNSUPPORTED_SCHEMA_CONSTRUCT", "schema root not object")
    return schema, got


def generate_from_schema_bytes(schema_bytes: bytes) -> GenerationResult:
    """Pure schema → WELL-EBNF-1 generation. Semantic authority for this slice."""
    schema, schema_sha = load_and_verify_schema_bytes(schema_bytes)

    rules: dict[str, Any] = {}
    provenance: dict[str, Any] = {
        "generator_version": GENERATOR_VERSION,
        "generator_source_sha256": _generator_source_sha256(),
        "well_ebnf_1_version": WELL_EBNF_1_VERSION,
        "rule_order_spec": RULE_ORDER_SPEC,
        "constraint_patch_version": CONSTRAINT_PATCH_VERSION,
        "canonical_json_version": CANONICAL_JSON_VERSION,
        "canonical_json_spec": dict(CANONICAL_JSON_SPEC),
        "python_version": sys.version.split()[0],
        "schema_sha256": schema_sha,
        "model_calls": 0,
        "engine_calls": 0,
    }
    install_json_lexicals(rules, provenance)

    compiler = SchemaCompiler(schema)
    compiler.rules.update(rules)
    compiler.compile_root()

    if compiler.coverage["unrecognized_semantic_keywords"]:
        raise GeneratorFail(
            "UNSUPPORTED_SCHEMA_CONSTRUCT",
            f"unrecognized={compiler.coverage['unrecognized_semantic_keywords']!r}",
        )
    if compiler.coverage["silently_ignored_semantic_keywords"]:
        raise GeneratorFail(
            "UNSUPPORTED_SCHEMA_CONSTRUCT",
            "silently_ignored_semantic_keywords_must_be_empty",
        )

    grammar_bytes = emit_grammar_file(compiler.rules)
    grammar_sha = sha256_bytes(grammar_bytes)
    provenance["grammar_sha256"] = grammar_sha
    provenance["transform_ledger_sha256"] = sha256_bytes(
        canonical_json_bytes(compiler.ledger)
    )

    return GenerationResult(
        grammar_bytes=grammar_bytes,
        grammar_sha256=grammar_sha,
        transform_ledger=list(compiler.ledger),
        coverage=dict(compiler.coverage),
        provenance=provenance,
        schema_sha256=schema_sha,
    )


def generate_from_pinned_evidence(
    evidence_dir: Path | None = None,
) -> GenerationResult:
    """Load the pinned evidence schema file, verify, generate."""
    if evidence_dir is None:
        evidence_dir = Path(__file__).resolve().parents[4] / "evidence"
    path = evidence_dir / CONSTRAINT_ARTIFACT_NAME
    return generate_from_schema_bytes(path.read_bytes())


def default_pinned_schema_path() -> Path:
    return Path(__file__).resolve().parents[4] / "evidence" / CONSTRAINT_ARTIFACT_NAME
