"""Provider-free D5-5G historical-claim revalidation tests."""

from __future__ import annotations

from pathlib import Path

from scripts import d5_5g_historical_claim_revalidation as d5g

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_axis_a_uses_one_canonical_model_and_one_schema_requiredness_delta() -> None:
    """A0/A1 differ only at the provider-facing requiredness path."""
    result = d5g.compare_requiredness_arms()
    assert result["schema_difference_paths"] == ["$.$defs.SectionTask.required"]
    assert result["canonical_model"] == "wellplot.agent.code_mode.planner.SemanticPlan"
    assert result["downstream_validation"] == "SHARED"
    assert d5g.canonical_provider_schema(False) != d5g.canonical_provider_schema(True)


def test_axis_b_contract_is_generic_and_field_local() -> None:
    """B1 adds generic capability-local text without qualification answers."""
    result = d5g.compare_capability_contract_arms()
    assert result["changed_surface"] == "capability_local_contract_text"
    assert result["synthetic_examples"] == "GENERIC"
    assert d5g.capability_contract("B0")["mappings"] == []
    assert len(d5g.capability_contract("B1")["mappings"]) == 1


def test_axis_c_observes_only_canonical_correction_and_preserves_projection() -> None:
    """C0 compares protected subtrees without defining an alternative repair."""
    result = d5g.observe_canonical_correction()
    assert result["condition"] == "C0"
    assert result["alternative_correction_paths"] == 0
    assert set(result["protected_subtrees"].values()) == {"PRESERVED"}
    assert result["canonical_model"] == "wellplot.agent.code_mode.planner.SemanticPlan"


def test_model_io_custody_reuses_wire_observer_without_headers_or_credentials(
    tmp_path: Path,
) -> None:
    """The accepted wire observer captures bodies and excludes auth material."""
    result = d5g.capture_wire_custody_probe(REPO_ROOT, tmp_path)
    assert result["request_sha256_present"] is True
    assert result["response_sha256_present"] is True
    assert result["headers_captured"] is False
    assert result["credentials_captured"] is False
    assert result["model_io_sha256"] == result["terminal_model_io_sha256"]


def test_provider_free_d5g_proof_is_zero_call_and_single_engine() -> None:
    """The complete implementation proof remains provider-free."""
    result = d5g.verify_provider_free(REPO_ROOT)
    assert result["single_engine_attestation"] == "PASS"
    assert result["canonical_engine"] == d5g.D5_5G_SINGLE_ENGINE_ENTRYPOINT
    assert result["provider_model_calls"] == 0
    assert result["source_changes"] == 0
    assert result["production_changes"] == 0
