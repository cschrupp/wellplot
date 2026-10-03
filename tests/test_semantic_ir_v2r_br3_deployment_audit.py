"""Provider-free SI-V2R-BR3 deployment audit tests."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.semantic_ir_v2r_br3_deployment_audit import (
    BASELINE_SHA,
    DIRECT_SUPPORTED,
    TOOLCHAIN_UNRESOLVED,
    V2R_SCHEMA_SHA256,
    build_audit,
    canonical_json,
    valid_domain_fixtures,
)

from wellplot.agent.code_mode.semantic_ir_v2r import SemanticIRV2R

FIXTURE_DIR = Path("tests/fixtures/semantic_ir_v2r_br3")


def _artifact(name: str) -> dict[str, object]:
    """Load one committed BR3 artifact."""
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_deployment_provenance_fails_closed_without_remote_artifact() -> None:
    """Endpoint metadata cannot authenticate the deployed toolchain."""
    audit = build_audit()
    assert audit["decision"] == TOOLCHAIN_UNRESOLVED
    assert audit["deployment_provenance"]["status"] == "UNRESOLVED"
    assert audit["toolchain_identity"]["deployment_toolchain_pinned"] is False


def test_reference_conversion_is_not_deployment_proof() -> None:
    """Reference tools remain distinct from the serving artifact."""
    result = _artifact("result.json")
    provenance = _artifact("deployment_provenance.json")
    toolchain = _artifact("toolchain_identity.json")
    assert result["decision"] == TOOLCHAIN_UNRESOLVED
    assert provenance["status"] == "UNRESOLVED"
    assert toolchain["deployment_match"] is False


def test_frozen_schema_identity_is_preserved() -> None:
    """BR3 guards the canonical V2R schema before conversion."""
    grammar = _artifact("grammar_validation.json")
    assert grammar["schemas"]["si_v2r"]["sha256"] == V2R_SCHEMA_SHA256
    assert grammar["schemas"]["si_v2"]["sha256"] != V2R_SCHEMA_SHA256
    assert build_audit()["baseline"] == BASELINE_SHA


def test_reference_conversions_have_zero_warnings() -> None:
    """The reference converter result is recorded without overclaiming parsing."""
    conversions = _artifact("grammar_validation.json")["conversions"]
    assert {value["status"] for value in conversions.values()} == {"PASS"}
    assert {value["warning_count"] for value in conversions.values()} == {0}


def test_gold_and_domain_accounting_remain_separate_from_grammar_acceptance() -> None:
    """Schema/model validity does not become a grammar claim."""
    grammar = _artifact("grammar_validation.json")
    gold = grammar["gold"]
    valid = grammar["valid_domain_fixtures"]
    assert gold["case_count"] == 24
    assert gold["json_schema_accepts"] == 24
    assert gold["canonical_model_accepts"] == 24
    assert gold["grammar_accepts"] == "NOT_EVALUABLE"
    assert valid["fixture_count"] == len(valid_domain_fixtures()) == 11
    assert valid["accepted"] == 11
    assert valid["grammar_accepted"] == "NOT_EVALUABLE"


def test_malformed_matrix_and_runtime_only_invariants_are_recorded() -> None:
    """Relational model checks are retained as runtime-owned evidence."""
    grammar = _artifact("grammar_validation.json")
    constraints = _artifact("constraint_matrix.json")
    malformed = grammar["malformed"]
    assert malformed["row_count"] == 11
    assert sum(row["json_schema_accepts"] for row in malformed["rows"]) == 9
    assert sum(row["canonical_model_accepts"] for row in malformed["rows"]) == 0
    assert all(row["grammar_accepts"] == "NOT_EVALUABLE" for row in malformed["rows"])
    assert constraints["canonical_runtime_only_count"] == 6
    assert constraints["relevant_weakened_count"] == 0


def test_no_grammar_body_or_sensitive_path_is_committed() -> None:
    """Machine artifacts retain bounded metadata only."""
    for path in FIXTURE_DIR.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert "grammar_body" not in text
        assert "/home/" not in text
        assert "/tmp/" not in text
        assert "Authorization" not in text
        assert "api_key" not in text


def test_provider_and_worker_counts_are_zero() -> None:
    """BR3 cannot claim model or downstream execution."""
    result = _artifact("result.json")
    assert result["provider_inference_calls"] == 0
    assert result["endpoint_metadata_calls"] == 2
    assert result["worker_program_calls"] == 0


def test_audit_is_deterministic_without_optional_tools() -> None:
    """The unresolved path is stable and provider-free."""
    first = build_audit()
    second = build_audit()
    assert canonical_json(first) == canonical_json(second)


def test_all_valid_domain_fixtures_pass_canonical_model() -> None:
    """The additional domain corpus is valid before grammar evaluation."""
    for payload in valid_domain_fixtures().values():
        SemanticIRV2R.model_validate(payload)


def test_decision_vocabulary_does_not_select_adapter() -> None:
    """A reference conversion never justifies a provider-facing transformation."""
    result = _artifact("result.json")
    assert result["adapter_justified"] == "NONE"
    assert DIRECT_SUPPORTED not in result["decision"]


def test_source_has_no_inference_or_production_route() -> None:
    """BR3 cannot accidentally invoke the model or alter production routing."""
    source = Path("scripts/semantic_ir_v2r_br3_deployment_audit.py").read_text(encoding="utf-8")
    assert "generate_structured" not in source
    assert "src/wellplot" not in source
    assert "chat/completions" not in source
