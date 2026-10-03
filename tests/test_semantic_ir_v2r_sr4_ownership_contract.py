"""Tests for the provider-free SI-V2R SR4 ownership contract."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_SHA = "e14c8814fd3b8f7cb8faae745cba907e537be3b3"
ARTIFACT_DIR = REPO_ROOT / "tests/fixtures/semantic_ir_v2r_sr4"

OWNERS = {
    "MODEL",
    "DETERMINISTIC_BOUNDARY",
    "IR_CONTRACT",
    "SHARED_WITH_EXPLICIT_BOUNDARY",
    "UNRESOLVED",
}
REQUIRED_DIMENSIONS = {
    "report_presence",
    "report_content",
    "reference_admissibility",
    "reference_presence",
    "reference_kind",
    "reference_target",
    "annotation_semantics",
    "constraint_scope",
    "unresolved_requirements",
}
PROTECTED_FILES = {
    "src/wellplot/agent/code_mode/semantic_ir_v2r.py": (
        "88da7f39981b9ff00551767dd0e0d485054d0bec660731cb6132561c3a16adaf"
    ),
    "src/wellplot/agent/code_mode/semantic_ir_v2r_compiler.py": (
        "a6317b6cdf7894ea8e710cb636430279b0c681a9b6a7541cf808133b7fdf7e98"
    ),
    "src/wellplot/agent/code_mode/capability_safety.py": (
        "09eaa16eb3b540c785573233092f7650569158a03ce9747d7b4501302a5e8be7"
    ),
    "src/wellplot/agent/code_mode/report_boundary_safety.py": (
        "86c05471dcbb0f71035ea8eca7eca59cae4f9f9c8665d59d7fe39befe022107f"
    ),
    "src/wellplot/agent/code_mode/section_leaf_safety.py": (
        "8d7890b9c18e4ffcf8a87f474439ce6da0f07338126ea4052201239b8936347d"
    ),
    "scripts/si_v2r_model_qualification.py": (
        "1c9410dc070590f01b547fbb917dd143eddc5c146123edd6351f4b03f8a2d039"
    ),
    "docs/architecture/ADR-CM57-planner-capability-contract.md": (
        "5d879cc8b5b3b62c8c188a747504ecaa3c24b69c5a8ab5ac58967d8f2ff959bb"
    ),
}


def load_json(name: str) -> dict[str, object]:
    """Load one checked-in SR4 machine-readable artifact."""
    return json.loads((ARTIFACT_DIR / name).read_text(encoding="utf-8"))


def test_baseline_and_result_are_frozen_without_scores() -> None:
    """SR4 records policy decisions without recalculating historical results."""
    result = load_json("result.json")
    assert result["baseline"] == BASELINE_SHA
    assert result["upstream_result"] == "SI_V2R_SR3_ROOT_MECHANISMS_RESOLVED"
    assert result["scoring_changed"] is False
    assert result["historical_evidence_reinterpreted"] is False
    assert not any("score" in key or "pass" in key or "rate" in key for key in result)


def test_ownership_matrix_covers_separate_semantic_dimensions() -> None:
    """Reference presence, kind, and target cannot collapse into one owner."""
    rows = load_json("ownership_matrix.json")["rows"]
    assert isinstance(rows, list)
    by_dimension = {row["dimension"]: row for row in rows}
    assert set(by_dimension) == REQUIRED_DIMENSIONS
    assert all(row["owner"] in OWNERS for row in rows)
    assert (
        by_dimension["reference_admissibility"]["dimension"]
        != by_dimension["reference_kind"]["dimension"]
    )
    assert "remove" in by_dimension["reference_admissibility"]["deterministic_action"]
    assert "convert" in by_dimension["reference_kind"]["deterministic_action"]
    assert "invent" in by_dimension["reference_target"]["deterministic_action"]


def test_ambiguity_policy_defines_all_required_outcomes() -> None:
    """Every ownership dimension has explicit ambiguity and conflict behavior."""
    policies = load_json("ambiguity_policy.json")["policies"]
    required = {
        "report_presence",
        "reference_admissibility",
        "reference_kind",
        "reference_target",
        "annotation_semantics",
        "constraint_scope",
        "unresolved_requirements",
    }
    assert {policy["dimension"] for policy in policies} == required
    for policy in policies:
        assert policy["ambiguous"]
        assert policy["conflicting"]
        assert policy["unsupported"]
    reference = next(item for item in policies if item["dimension"] == "reference_admissibility")
    assert "CONTRACT_REQUIRED" in reference["unspecified"]
    assert reference["conflicting"] == "FAIL_CLOSED"


def test_representation_contract_rejects_stale_sidecars() -> None:
    """A repaired capability plan cannot contradict preserved reference intent."""
    matrix = load_json("representation_matrix.json")
    conflict = matrix["conflict_rule"]
    assert conflict["code"] == "REFERENCE_REPRESENTATION_CONFLICT"
    assert conflict["action"] == "FAIL_CLOSED"
    assert conflict["system_semantic_credit"] is False
    assert any("sidecar" in example for example in conflict["examples"])
    assert matrix["selected_model"] == "EXPLICIT_PRE_POST_WRAPPERS"


def test_constraint_equivalence_requires_scope_and_inheritance() -> None:
    """Textual relocation is not sufficient to establish Garnet equivalence."""
    row = next(
        item
        for item in load_json("ownership_matrix.json")["rows"]
        if item["dimension"] == "constraint_scope"
    )
    assert row["owner"] == "SHARED_WITH_EXPLICIT_BOUNDARY"
    assert "scope" in row["representation_invariant"]
    assert row["ambiguous_behavior"] == "FAIL_CLOSED"
    contract_path = (
        REPO_ROOT
        / "docs/evaluations/agent-code-mode/semantic-ir-v2/41-si-v2r-sr4-ownership-contract.md"
    )
    contract = contract_path.read_text(encoding="utf-8")
    for phrase in ("FEATURE_LOCAL", "SECTION_WIDE", "EXPLICITLY_INHERITED", "multi-feature"):
        assert phrase in contract


def test_annotation_and_unresolved_policies_do_not_synthesize_semantics() -> None:
    """Annotation and unresolved semantics remain model-owned."""
    rows = {row["dimension"]: row for row in load_json("ownership_matrix.json")["rows"]}
    assert rows["annotation_semantics"]["owner"] == "MODEL"
    assert "manufacture" in rows["annotation_semantics"]["deterministic_action"]
    assert rows["unresolved_requirements"]["owner"] == "MODEL"
    assert "supported" in rows["unresolved_requirements"]["representation_invariant"]


def test_production_and_scoring_artifacts_match_baseline() -> None:
    """SR4 does not modify protected implementation or evaluation artifacts."""
    for relative_path, expected_hash in PROTECTED_FILES.items():
        current_hash = hashlib.sha256((REPO_ROOT / relative_path).read_bytes()).hexdigest()
        assert current_hash == expected_hash, relative_path
        baseline_bytes = subprocess.check_output(
            ["git", "show", f"{BASELINE_SHA}:{relative_path}"],
            cwd=REPO_ROOT,
        )
        assert hashlib.sha256(baseline_bytes).hexdigest() == expected_hash


def test_sr4_is_provider_free_and_production_inactive() -> None:
    """The terminal artifact records the hard provider and production bounds."""
    result = load_json("result.json")
    assert result["provider_inference_calls"] == 0
    assert result["endpoint_calls"] == 0
    assert result["worker_program_calls"] == 0
    assert result["production_behavior_changed"] is False
    assert result["production_implementation_authorized"] is False
    assert result["decision"] == "SI_V2R_SR4_OWNERSHIP_CONTRACT_RESOLVED"
