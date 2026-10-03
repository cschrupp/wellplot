"""Tests for the provider-free SI-V2R SR5 applicability map."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from scripts.semantic_ir_v2r_sr5_contract_applicability import build_artifacts

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = REPO_ROOT / "tests/fixtures/semantic_ir_v2r_sr5"
BASELINE_SHA = "eb9736ddda9feb9e5e601760822da7e0e3933286"
RAW_EVIDENCE = Path("/tmp/si-v2r-live.jsonl")
RAW_EVIDENCE_SHA256 = "9d175c3b80c2cb6a5d5f62195861d4c0070643a37ab4f99dd02559d018011f08"
ALLOWED_STATES = {
    "CONTRACT_APPLICABLE",
    "MODEL_OWNED",
    "BLOCKED_BY_REPRESENTATION_CONFLICT",
    "BLOCKED_BY_UNRESOLVED_CONTRACT",
    "FAIL_CLOSED",
    "NOT_APPLICABLE",
    "NOT_EVALUABLE",
}
APPLICABILITY_DIMENSIONS = {
    "report_presence",
    "report_content",
    "reference_admissibility",
    "reference_kind",
    "reference_target",
    "annotation_semantics",
    "constraint_scope",
    "unresolved_requirements",
}
SR4_FILES = (
    "docs/evaluations/agent-code-mode/semantic-ir-v2/40-si-v2r-sr4-scope.md",
    "docs/evaluations/agent-code-mode/semantic-ir-v2/41-si-v2r-sr4-ownership-contract.md",
    "docs/evaluations/agent-code-mode/semantic-ir-v2/42-si-v2r-sr4-representation-consistency.md",
    "docs/evaluations/agent-code-mode/semantic-ir-v2/43-si-v2r-sr4-result.md",
    "tests/fixtures/semantic_ir_v2r_sr4/ambiguity_policy.json",
    "tests/fixtures/semantic_ir_v2r_sr4/ownership_matrix.json",
    "tests/fixtures/semantic_ir_v2r_sr4/representation_matrix.json",
    "tests/fixtures/semantic_ir_v2r_sr4/result.json",
    "tests/test_semantic_ir_v2r_sr4_ownership_contract.py",
)


def load_json(name: str) -> object:
    """Load one checked-in SR5 machine-readable artifact."""
    return json.loads((ARTIFACT_DIR / name).read_text(encoding="utf-8"))


def test_authenticated_population_and_raw_evidence() -> None:
    """The map is bound to the exact historical evidence population."""
    result = load_json("result.json")
    assert result["raw_evidence_sha256"] == RAW_EVIDENCE_SHA256
    assert result["population"] == {"rows": 48, "cases": 24, "attempts_per_case": 2}
    assert RAW_EVIDENCE.is_file()
    assert hashlib.sha256(RAW_EVIDENCE.read_bytes()).hexdigest() == RAW_EVIDENCE_SHA256
    assert len([line for line in RAW_EVIDENCE.read_text().splitlines() if line]) == 48


def test_committed_artifacts_reproduce_from_authenticated_inputs() -> None:
    """Every committed artifact is derived from the frozen raw inputs."""
    generated = build_artifacts(RAW_EVIDENCE, REPO_ROOT)
    for filename, expected in generated.items():
        assert load_json(filename) == expected


def test_rows_are_complete_and_states_are_bounded() -> None:
    """Every row and dimension has one bounded applicability state."""
    rows = load_json("applicability_rows.json")
    assert len(rows) == 48
    assert len({(row["case_id"], row["attempt"]) for row in rows}) == 48
    assert {row["attempt"] for row in rows} == {0, 1}
    assert len({row["case_id"] for row in rows}) == 24
    for row in rows:
        assert set(row["applicability_dimensions"]) == APPLICABILITY_DIMENSIONS
        assert set(row["applicability_dimensions"].values()) <= ALLOWED_STATES
        assert set(row["system_credit_eligibility_by_dimension"]) == APPLICABILITY_DIMENSIONS


def test_structural_unavailability_is_not_reconstructed() -> None:
    """The six unavailable attempts remain non-evaluable in every dimension."""
    rows = load_json("applicability_rows.json")
    unavailable = [row for row in rows if not row["structurally_evaluable"]]
    assert len(unavailable) == 6
    for row in unavailable:
        assert set(row["applicability_dimensions"].values()) == {"NOT_EVALUABLE"}
        assert row["model_reference_projection"] == []
        assert row["cm58_1_actions"] == []


def test_applicability_is_not_a_score() -> None:
    """Artifacts cannot smuggle in an adjusted pass or regraded score."""
    for artifact in (load_json("result.json"), load_json("applicability_summary.json")):
        assert not any(
            fragment in key
            for key in artifact
            for fragment in ("system_pass", "adjusted_pass", "new_pass", "regraded_pass")
        )
    result = load_json("result.json")
    assert result["historical_scores_recalculated"] is False
    assert result["counterfactual_repairs"] == 0
    assert result["scoring_changed"] is False


def test_reference_intents_keep_forbidden_and_unspecified_distinct() -> None:
    """The empty forbidden population cannot conflate the two intents."""
    policy = load_json("applicability_summary.json")["reference_intent_policy"]
    assert policy["EXPLICITLY_FORBIDDEN"].startswith("CONTRACT_APPLICABLE")
    assert policy["UNSPECIFIED_WITH_MODEL_REFERENCE"] == "BLOCKED_BY_UNRESOLVED_CONTRACT"
    summary = load_json("applicability_summary.json")
    assert summary["reference_explicitly_forbidden_rows"] == 0
    assert summary["reference_unspecified_overreach_rows"] == 4


def test_reference_representation_conflict_blocks_credit() -> None:
    """Stale capability/sidecar state blocks deterministic reference credit."""
    conflicts = [
        row
        for row in load_json("applicability_rows.json")
        if row["reference_representation_status"] == "CONFLICT"
    ]
    assert len(conflicts) == 4
    assert all(
        row["reference_admissibility_applicability"] == "BLOCKED_BY_REPRESENTATION_CONFLICT"
        and not row["system_credit_eligibility_by_dimension"]["reference_admissibility"]
        and "REFERENCE_REPRESENTATION_CONFLICT" in row["applicability_blockers"]
        and "UNSPECIFIED_REFERENCE_POLICY" in row["applicability_blockers"]
        for row in conflicts
    )


def test_named_sr3_cases_retain_sr4_applicability() -> None:
    """Garnet, Verde, Amber, and Iris retain their bounded root explanations."""
    by_case = {}
    for row in load_json("applicability_rows.json"):
        by_case.setdefault(row["case_id"], []).append(row)
    garnet = by_case["cm59-single-garnet-06"]
    assert all(
        row["constraint_scope_applicability"] == "BLOCKED_BY_UNRESOLVED_CONTRACT" for row in garnet
    )
    verde = by_case["cm59-alloc-verde-19"]
    assert all(
        row["reference_admissibility_applicability"] == "BLOCKED_BY_REPRESENTATION_CONFLICT"
        and row["reference_representation_status"] == "CONFLICT"
        for row in verde
    )
    amber = by_case["cm59-mixed-amber-24"]
    assert all(row["annotation_applicability"] == "MODEL_OWNED" for row in amber)
    iris = by_case["cm59-single-iris-08"]
    assert all(
        row["annotation_applicability"] == "MODEL_OWNED"
        and row["unresolved_requirement_applicability"] == "MODEL_OWNED"
        and row["reference_representation_status"] == "CONFLICT"
        and row["reference_admissibility_applicability"] == "BLOCKED_BY_REPRESENTATION_CONFLICT"
        for row in iris
    )


def test_hard_provider_and_production_boundaries() -> None:
    """SR5 remains provider-free and does not modify production artifacts."""
    result = load_json("result.json")
    assert result["provider_inference_calls"] == 0
    assert result["endpoint_calls"] == 0
    assert result["worker_program_calls"] == 0
    assert result["production_behavior_changed"] is False
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", BASELINE_SHA, "--", "src/wellplot"],
        cwd=REPO_ROOT,
        text=True,
    ).splitlines()
    assert changed == []


def test_sr4_evidence_is_untouched() -> None:
    """The applicability slice does not edit SR4 artifacts."""
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", BASELINE_SHA],
        cwd=REPO_ROOT,
        text=True,
    ).splitlines()
    assert not any(path in SR4_FILES for path in changed)


def test_terminal_result_and_readiness_are_separate() -> None:
    """A complete map may remain only partially ready for a later regrade."""
    result = load_json("result.json")
    assert result["decision"] == "SI_V2R_SR5_APPLICABILITY_MAP_COMPLETE"
    assert result["applicability_map"] == "COMPLETE"
    assert result["regrade_readiness"] == "RE_GRADE_PARTIALLY_READY"
    assert result["adr_cm57"] == "UNCHANGED"
