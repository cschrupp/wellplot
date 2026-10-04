"""Provider-free tests for the SI-V2R SR7-P0 comparison freeze."""

from __future__ import annotations

import json
import subprocess
from collections import Counter
from pathlib import Path

from scripts.semantic_ir_v2r_sr7_c0_config_probe import canonical_json as c0_canonical_json
from scripts.semantic_ir_v2r_sr7_p0_comparison_contract import (
    BASELINE_SHA,
    CONFIGURATION_A_FINGERPRINT,
    CONFIGURATION_B_FINGERPRINT,
    DIMENSIONS,
    MODEL_ROLES,
    RELATIONS,
    SCHEMA_SHA256,
    SYSTEM_ROLES,
    _configuration_contract,
    _synthetic_mask,
    _synthetic_rows,
    build_artifacts,
    build_execution_schedule,
    canonical_json,
    classify_future_comparison,
    derive_comparison,
    grade_semantics,
    sha256_text,
    structural_relation,
    system_dimension_outcomes,
    validate_evidence_rows,
    validate_runtime_attestation,
)

from wellplot.agent.code_mode.semantic_ir_v2r import SemanticIRV2R

REPO_ROOT = Path(__file__).resolve().parents[1]
P0_DIR = REPO_ROOT / "tests/fixtures/semantic_ir_v2r_sr7_p0"
CORPUS_PATH = REPO_ROOT / "tests/fixtures/typed_worker/cm59a_system_reevaluation_cases.json"
GOLD_PATH = REPO_ROOT / "tests/fixtures/semantic_ir_v2r/cm59a_semantic_intents_v2r.json"


def _fixture(name: str) -> dict[str, object]:
    return json.loads((P0_DIR / name).read_text(encoding="utf-8"))


def test_all_generated_p0_artifacts_are_reproducible() -> None:
    """Committed P0 JSON exactly matches deterministic regeneration."""
    artifacts = build_artifacts(REPO_ROOT)
    for name, expected in artifacts.items():
        assert _fixture(name) == expected


def test_frozen_configuration_and_source_hashes_are_exact() -> None:
    """Configuration and canonical input hashes remain frozen."""
    configs = _fixture("configurations.json")
    records = {record["configuration_id"]: record for record in configs["configurations"]}
    assert records["A"]["fingerprint"] == CONFIGURATION_A_FINGERPRINT
    assert records["B"]["fingerprint"] == CONFIGURATION_B_FINGERPRINT
    assert records["A"]["temperature"] == 0.0
    assert records["B"]["temperature"] == 1.0
    assert records["B"]["top_p"] == 0.95
    assert records["B"]["reasoning_effort"] == "low"
    assert records["A"]["max_tokens"] == records["B"]["max_tokens"] == 16384
    assert records["A"]["timeout_seconds"] == records["B"]["timeout_seconds"] == 900
    assert records["A"]["concurrency"] == records["B"]["concurrency"] == 1
    assert configs["comparison_claim"] == "model-plus-serving configuration comparison"
    assert sha256_text(canonical_json(SemanticIRV2R.model_json_schema())) == SCHEMA_SHA256
    assert c0_canonical_json(configs) == canonical_json(configs)


def test_mask_is_complete_and_has_no_duplicate_case_dimension_rows() -> None:
    """Every frozen case has exactly one entry for every dimension."""
    mask = _fixture("case_dimension_mask.json")
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))["cases"]
    case_ids = {case["case_id"] for case in corpus}
    keys = [(row["case_id"], row["dimension"]) for row in mask["rows"]]
    assert mask["case_count"] == 24
    assert mask["dimension_count"] == len(DIMENSIONS) == 14
    assert len(keys) == 24 * 14
    assert len(set(keys)) == len(keys)
    assert {case_id for case_id, _ in keys} == case_ids
    assert {dimension for _, dimension in keys} == set(DIMENSIONS)
    assert {row["model_role"] for row in mask["rows"]} <= set(MODEL_ROLES)
    assert {row["system_role"] for row in mask["rows"]} <= set(SYSTEM_ROLES)
    assert Counter(row["model_role"] for row in mask["rows"]) == Counter(
        {
            "NOT_APPLICABLE": 203,
            "PRIMARY_MODEL_OBLIGATION": 95,
            "RAW_MODEL_DIAGNOSTIC": 37,
            "MASKED_UNRESOLVED_CONTRACT": 1,
        }
    )


def test_mandatory_garnet_verde_amber_and_iris_rules_are_explicit() -> None:
    """Mandatory exception ownership rules are explicit in the mask."""
    rows = _fixture("case_dimension_mask.json")["rows"]
    by_key = {(row["case_id"], row["dimension"]): row for row in rows}
    assert (
        sum(
            row["model_role"] == "MASKED_UNRESOLVED_CONTRACT"
            for row in rows
            if "garnet" in row["case_id"]
        )
        == 1
    )
    assert (
        by_key[("cm59-single-garnet-06", "CONSTRAINT_SCOPE")]["system_role"]
        == "SYSTEM_CREDIT_BLOCKED"
    )
    assert (
        by_key[("cm59-alloc-verde-19", "REFERENCE_PRESENCE")]["model_role"]
        == "RAW_MODEL_DIAGNOSTIC"
    )
    assert (
        by_key[("cm59-alloc-verde-19", "REFERENCE_PRESENCE")]["system_role"]
        == "SYSTEM_CREDIT_BLOCKED"
    )
    assert by_key[("cm59-mixed-amber-24", "ANNOTATION")]["model_role"] == "PRIMARY_MODEL_OBLIGATION"
    assert by_key[("cm59-single-iris-08", "ANNOTATION")]["model_role"] == "PRIMARY_MODEL_OBLIGATION"
    assert (
        by_key[("cm59-single-iris-08", "UNRESOLVED_REQUIREMENT")]["model_role"]
        == "PRIMARY_MODEL_OBLIGATION"
    )
    assert sum(
        row["model_role"] == "MASKED_UNRESOLVED_CONTRACT"
        for row in rows
        if row["case_id"] == "cm59-single-garnet-06"
    ) < len(DIMENSIONS)


def test_execution_schedule_is_balanced_and_complete() -> None:
    """The 96 logical calls are complete and position-balanced."""
    schedule = build_execution_schedule(REPO_ROOT)
    rows = schedule["rows"]
    keys = [(row["configuration_id"], row["case_id"], row["attempt_index"]) for row in rows]
    assert len(rows) == 96
    assert len(set(keys)) == 96
    assert all(
        sum(row["configuration_id"] == config and row["attempt_index"] == attempt for row in rows)
        == 24
        for config in ("A", "B")
        for attempt in (0, 1)
    )
    first_positions = [rows[index]["configuration_id"] for index in range(0, len(rows), 4)]
    assert first_positions.count("A") == first_positions.count("B") == 12
    assert rows[:4] == [
        {
            "case_id": "cm59-report-cascade-01",
            "case_index": 0,
            "configuration_id": "A",
            "attempt_index": 0,
            "execution_order_index": 0,
        },
        {
            "case_id": "cm59-report-cascade-01",
            "case_index": 0,
            "configuration_id": "B",
            "attempt_index": 0,
            "execution_order_index": 1,
        },
        {
            "case_id": "cm59-report-cascade-01",
            "case_index": 0,
            "configuration_id": "B",
            "attempt_index": 1,
            "execution_order_index": 2,
        },
        {
            "case_id": "cm59-report-cascade-01",
            "case_index": 0,
            "configuration_id": "A",
            "attempt_index": 1,
            "execution_order_index": 3,
        },
    ]


def test_pure_grader_is_deterministic_and_respects_mask() -> None:
    """Pure grading is repeatable and honors Garnet masking."""
    gold_cases = json.loads(GOLD_PATH.read_text(encoding="utf-8"))["cases"]
    gold = next(case for case in gold_cases if case["case_id"] == "cm59-single-garnet-06")
    case = next(
        case
        for case in json.loads(CORPUS_PATH.read_text(encoding="utf-8"))["cases"]
        if case["case_id"] == gold["case_id"]
    )
    mask = _fixture("case_dimension_mask.json")
    first = grade_semantics(case, gold, gold, mask)
    second = grade_semantics(case, gold, gold, mask)
    assert first == second
    assert first["CONSTRAINT_SCOPE"]["status"] == "MASKED"
    assert first["FEATURE_KIND"]["status"] == "CORRECT"
    assert first["SECTION_STRUCTURE"]["status"] == "CORRECT"


def test_deterministic_repair_does_not_create_model_or_blocked_system_credit() -> None:
    """Safety repair does not create model credit or blocked system credit."""
    mask = _fixture("case_dimension_mask.json")
    verde = [row for row in mask["rows"] if row["case_id"] == "cm59-alloc-verde-19"]
    model_results = {
        "REFERENCE_PRESENCE": {"status": "INCORRECT", "model_role": "RAW_MODEL_DIAGNOSTIC"},
    }
    outcomes = system_dimension_outcomes(
        mask={"rows": verde},
        semantic_dimension_results=model_results,
        credited_interventions={"REFERENCE_PRESENCE"},
    )
    assert model_results["REFERENCE_PRESENCE"]["status"] == "INCORRECT"
    assert outcomes["REFERENCE_PRESENCE"] == "SYSTEM_BLOCKED"

    report = [row for row in mask["rows"] if row["case_id"] == "cm59-report-cascade-01"]
    report_results = {
        "REPORT_PRESENCE": {"status": "INCORRECT", "model_role": "RAW_MODEL_DIAGNOSTIC"}
    }
    report_outcomes = system_dimension_outcomes(
        mask={"rows": report},
        semantic_dimension_results=report_results,
        credited_interventions={"REPORT_PRESENCE"},
    )
    assert report_outcomes["REPORT_PRESENCE"] == "SYSTEM_CORRECT"
    assert report_results["REPORT_PRESENCE"]["status"] == "INCORRECT"


def test_comparison_contains_all_relation_branches_and_tradeoff_reason() -> None:
    """Synthetic paired results cover all case relation branches."""
    rows = _synthetic_rows()
    comparison = derive_comparison(rows, _synthetic_mask())
    expected = {
        "a-better": "A_BETTER",
        "b-better": "B_BETTER",
        "equal": "UNCHANGED",
        "mixed": "UNCHANGED",
        "not-comparable": "NOT_COMPARABLE",
    }
    assert {
        case: value["relation"] for case, value in comparison["case_relations"].items()
    } == expected
    assert comparison["case_relations"]["mixed"]["unchanged_reason"] == "MIXED_TRADEOFF"
    assert comparison["case_relations"]["equal"]["unchanged_reason"] == "EQUAL"
    assert set(RELATIONS) >= {value["relation"] for value in comparison["case_relations"].values()}


def test_structural_relation_is_separate_from_semantic_relation() -> None:
    """Structural reliability is compared independently of semantics."""
    a = [{"initial_canonical_status": "PASS", "final_canonical_status": "PASS"}]
    b = [{"initial_canonical_status": "FAIL", "final_canonical_status": "PASS"}]
    assert structural_relation(a, b) == "A_BETTER"
    b[0]["final_canonical_status"] = "FAIL"
    assert structural_relation(a, b) == "A_BETTER"


def test_runtime_attestation_and_evidence_drift_fail_closed() -> None:
    """Runtime and evidence integrity mismatches fail closed."""
    configs = _configuration_contract(REPO_ROOT)
    expected = {
        "configuration_id": "B",
        "base_url": configs["configurations"][1]["base_url"],
        "requested_model": configs["configurations"][1]["requested_model"],
        "returned_model": configs["configurations"][1]["requested_model"],
        "temperature": 1.0,
        "top_p": 0.95,
        "reasoning_effort": "low",
        "max_tokens": 16384,
        "timeout_seconds": 900,
        "structured_output_type": "response_format=json_schema",
        "strict": True,
        "schema_sha256": SCHEMA_SHA256,
        "system_prompt_sha256": "5ebdd3da9bc3cdf78442a97ba0a2ef9fc1c0d5e8b1ca641f18a30fe1b0cb50e3",
        "retry_prompt_sha256": "27c6a43c7f611a79401914b6732dbcec946493bba51058c1eb1d1245f47990f0",
        "case_corpus_sha256": "b6a605158e667e5250df99a53cb4ba521473f8146fad2022aed2dff77d5f551b",
        "comparison_concurrency": 1,
    }
    assert validate_runtime_attestation(expected, expected) == "OK"
    altered = dict(expected)
    altered["top_p"] = 0.9
    assert validate_runtime_attestation(altered, expected) == "INCONCLUSIVE_CONFIGURATION_DRIFT"

    schedule = build_execution_schedule(REPO_ROOT)
    errors = validate_evidence_rows(
        [],
        schedule,
        expected_mask_sha256="mask",
        expected_contract_sha256="contract",
    )
    assert "ROW_COUNT" in errors
    assert "SCHEDULE_POPULATION_MISMATCH" in errors


def test_future_decision_precedence_is_frozen() -> None:
    """Infrastructure and drift outcomes dominate directional results."""
    base = {
        "a_case_wins": 1,
        "b_case_wins": 2,
        "a_dimension_accuracy": 0.5,
        "b_dimension_accuracy": 0.7,
        "a_terminal_structural_failures": 1,
        "b_terminal_structural_failures": 1,
    }
    assert classify_future_comparison(base) == "CONFIGURATION_B_DIRECTIONALLY_BETTER"
    assert (
        classify_future_comparison({**base, "infrastructure_failure": True})
        == "INCONCLUSIVE_INFRASTRUCTURE"
    )
    assert (
        classify_future_comparison({**base, "configuration_drift": True})
        == "INCONCLUSIVE_CONFIGURATION_DRIFT"
    )
    assert classify_future_comparison({**base, "evidence_invalid": True}) == "INCONCLUSIVE_EVIDENCE"
    assert (
        classify_future_comparison({**base, "structural_materially_contradicts": True})
        == "NO_CLEAR_DIRECTIONAL_DIFFERENCE"
    )


def test_p0_source_and_artifacts_are_provider_free_and_secret_free() -> None:
    """P0 contains no provider execution path or credential material."""
    source = (
        (REPO_ROOT / "scripts/semantic_ir_v2r_sr7_p0_comparison_contract.py")
        .read_text(encoding="utf-8")
        .lower()
    )
    assert "httpx" not in source
    assert "openai" not in source
    assert "generate_structured" not in source
    assert "--live" not in source
    assert "nvidia.com" not in source
    paths = [
        REPO_ROOT / "scripts/semantic_ir_v2r_sr7_p0_comparison_contract.py",
        *P0_DIR.glob("*.json"),
        *(REPO_ROOT / "docs/evaluations/agent-code-mode/semantic-ir-v2").glob(
            "6[0-5]-si-v2r-sr7-p0-*.md"
        ),
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8").lower()
        assert not any(
            marker in text
            for marker in ("bearer", "nvidia_api_key", "openrouter_api_key", "sk-", "nvapi-")
        )


def test_p0_has_no_production_or_protected_history_delta() -> None:
    """The P0 delta contains no production or protected history changes."""
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", BASELINE_SHA, "HEAD"],
        cwd=REPO_ROOT,
        text=True,
    ).splitlines()
    assert not any(path.startswith("src/wellplot/") for path in changed)
    assert not any(
        path.startswith("docs/evaluations/agent-code-mode/semantic-ir-v2/0") for path in changed
    )
