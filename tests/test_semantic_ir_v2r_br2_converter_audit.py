"""Provider-free SI-V2R-BR2 converter audit tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.semantic_ir_v2r_br2_converter_audit import (
    BASELINE_SHA,
    HISTORICAL_ENDPOINT_IDENTITY_SHA256,
    PINNED_TOOLCHAIN_UNRESOLVED,
    UPSTREAM_REFERENCE_COMMIT,
    V2R_SCHEMA_SHA256,
    build_audit,
    canonical_json,
    gold_representability,
    historical_provenance,
    validation_matrix,
)

from wellplot.agent.code_mode.semantic_ir_v2 import SemanticIRV2
from wellplot.agent.code_mode.semantic_ir_v2r import SemanticIRV2R

FIXTURE_DIR = Path("tests/fixtures/semantic_ir_v2r_br2")


def test_historical_and_current_provenance_are_separate() -> None:
    """A current build label cannot authenticate the historical converter."""
    historical = historical_provenance()
    assert historical["status"] == "UNRESOLVED"
    assert historical["endpoint_identity_sha256"] == HISTORICAL_ENDPOINT_IDENTITY_SHA256
    audit = build_audit()
    assert audit["current_endpoint_observation"]["classification"] == "CURRENT_ONLY"
    assert audit["historical_lq0_converter_provenance"] == "UNRESOLVED"


def test_same_endpoint_identity_does_not_imply_same_binary() -> None:
    """Endpoint identity is intentionally weaker than converter identity."""
    provenance = historical_provenance()
    assert provenance["same_endpoint_is_not_same_converter"] is True
    assert provenance["facts"][2]["classification"] == "UNAVAILABLE"


def test_frozen_schema_hash_and_v2r_comparison_are_provider_free() -> None:
    """The canonical V2R schema and descriptive SI-V2 comparison are frozen."""
    audit = build_audit()
    assert audit["baseline"] == BASELINE_SHA
    assert audit["schemas"]["si_v2r"]["sha256"] == V2R_SCHEMA_SHA256
    assert audit["schemas"]["si_v2"]["sha256"] != V2R_SCHEMA_SHA256
    assert audit["provider_inference_calls"] == 0
    assert audit["worker_program_calls"] == 0


def test_unpinned_converter_fails_closed() -> None:
    """No executable means no compatibility or adapter conclusion."""
    audit = build_audit()
    assert audit["decision"] == PINNED_TOOLCHAIN_UNRESOLVED
    assert audit["adapter_justified"] == "NONE"
    assert audit["reference_converter_conversion"] == "NOT_EVALUABLE"


def test_converter_audit_records_exact_source_identity() -> None:
    """A reference conversion records source identity without claiming deployment."""
    audit = build_audit()
    assert audit["converter_audit"]["reference_toolchain"]["source_commit"] == (
        UPSTREAM_REFERENCE_COMMIT
    )
    assert (
        audit["converter_audit"]["reference_toolchain"]["source_matches_historical_server"] is False
    )


def test_grammar_metadata_is_not_committed_as_grammar_body() -> None:
    """Artifacts retain hashes and sizes, not potentially large grammar text."""
    for path in FIXTURE_DIR.glob("*.json"):
        assert "grammar_body" not in path.read_text(encoding="utf-8")


def test_committed_result_preserves_conservative_terminal_decision() -> None:
    """The generated result separates conversion evidence from deployment proof."""
    result = json.loads((FIXTURE_DIR / "result.json").read_text(encoding="utf-8"))
    assert result["decision"] == PINNED_TOOLCHAIN_UNRESOLVED
    assert result["reference_converter_conversion"] == "PASS"
    assert result["historical_lq0_converter_provenance"] == "UNRESOLVED"
    assert result["future_target_converter_pinned"] is False


def test_committed_result_preserves_zero_inference_counts() -> None:
    """Provider-free BR2 artifacts cannot claim model or worker execution."""
    result = json.loads((FIXTURE_DIR / "result.json").read_text(encoding="utf-8"))
    assert result["provider_inference_calls"] == 0
    assert result["endpoint_metadata_calls"] == 2
    assert result["worker_program_calls"] == 0


def test_gold_accounting_requires_24_canonical_objects() -> None:
    """All frozen gold intents are checked even when grammar parsing is unavailable."""
    result = gold_representability(SemanticIRV2R.model_json_schema())
    assert result["case_count"] == 24
    assert result["json_schema_accepts"] == "24/24"
    assert result["canonical_model_accepts"] == "24/24"
    assert result["grammar_representability"] == "NOT_EVALUABLE"


def test_malformed_matrix_preserves_canonical_runtime_only_boundary() -> None:
    """JSON Schema acceptance and Pydantic runtime rejection remain distinct."""
    result = validation_matrix(SemanticIRV2R.model_json_schema())
    assert len(result["rows"]) == 11
    assert all(row["canonical_model_accepts"] is False for row in result["rows"])
    assert result["rows"][0]["json_schema_accepts"] is True
    assert all(row["pinned_grammar_gate"] == "NOT_EVALUABLE" for row in result["rows"])


def test_converter_audit_is_reproducible_without_endpoint_or_provider() -> None:
    """The audit projection is deterministic and contains no secrets or paths."""
    first = build_audit()
    second = build_audit()
    assert canonical_json(first) == canonical_json(second)
    text = json.dumps(first, sort_keys=True)
    assert "/home/" not in text
    assert "Authorization" not in text
    assert "api_key" not in text


def test_no_adapter_or_production_imports_are_selected() -> None:
    """BR2 remains a research-only converter audit."""
    source = Path("scripts/semantic_ir_v2r_br2_converter_audit.py").read_text(encoding="utf-8")
    assert "adapter" in source.lower()
    assert "src/wellplot" not in source
    assert "generate_structured" not in source


@pytest.mark.parametrize("model", [SemanticIRV2, SemanticIRV2R])
def test_schema_serialization_is_valid_json(model: type[object]) -> None:
    """Both compared schemas remain ordinary JSON documents."""
    json.loads(json.dumps(model.model_json_schema()))
