"""Provider-free tests for the SI-V2R SR7-P0 comparison freeze."""

from __future__ import annotations

import json
import subprocess
from collections import Counter
from copy import deepcopy
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
    _dimension_equivalent,
    _semantic_model,
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


def _gold_case(case_id: str) -> dict[str, object]:
    cases = json.loads(GOLD_PATH.read_text(encoding="utf-8"))["cases"]
    return next(case for case in cases if case["case_id"] == case_id)


def test_semantic_id_alpha_renaming_preserves_all_applicable_scores() -> None:
    """Local correlation handles do not become semantic grading values."""
    gold = _gold_case("cm59-mixed-amber-24")
    renamed = deepcopy(gold)
    mapping: dict[str, str] = {}
    for section_index, section in enumerate(renamed["sections"]):
        for feature_index, feature in enumerate(section["features"]):
            old_id = feature["semantic_id"]
            mapping[old_id] = f"local-{section_index}-{feature_index}"
            feature["semantic_id"] = mapping[old_id]
    for section in renamed["sections"]:
        for feature in section["features"]:
            if "target_semantic_id" in feature:
                feature["target_semantic_id"] = mapping[feature["target_semantic_id"]]
        reference = section.get("reference_intent")
        if reference and reference.get("target_semantic_id"):
            reference["target_semantic_id"] = mapping[reference["target_semantic_id"]]

    mask = _fixture("case_dimension_mask.json")
    graded = grade_semantics(gold, gold, renamed, mask)
    assert all(
        result["status"] == "CORRECT"
        for result in graded.values()
        if result["status"] not in {"NOT_APPLICABLE", "MASKED"}
    )


def test_normalized_owned_text_does_not_create_false_failures() -> None:
    """Case, punctuation, and spacing variation is normalized in owned context."""
    gold = _gold_case("cm59-mixed-amber-24")
    varied = deepcopy(gold)
    varied["report_work"]["requirements"] = ["READY FOR SIGNOFF!"]
    varied["sections"][0]["features"][1]["requirements"] = [
        "ANNOTATE THE INTERVAL TOP WITH A MARKER"
    ]
    mask = _fixture("case_dimension_mask.json")
    graded = grade_semantics(gold, gold, varied, mask)
    assert graded["REPORT_CONTENT"]["status"] == "CORRECT"
    assert graded["REQUIRED_CONTEXT"]["status"] == "CORRECT"
    assert graded["ANNOTATION"]["status"] == "CORRECT"


def test_normalized_section_source_context_preserves_its_owner() -> None:
    """Source hints are normalized but cannot be silently dropped or relocated."""
    gold = _gold_case("cm59-single-fig-05")
    gold["sections"][0]["source_hints"] = ["Well Alpha"]
    equivalent = deepcopy(gold)
    equivalent["sections"][0]["source_hints"] = ["well alpha"]
    missing = deepcopy(gold)
    missing["sections"][0]["source_hints"] = []
    assert _dimension_equivalent(
        _semantic_model(equivalent), _semantic_model(gold), "REQUIRED_CONTEXT"
    )
    assert not _dimension_equivalent(
        _semantic_model(missing), _semantic_model(gold), "REQUIRED_CONTEXT"
    )


def test_required_context_moved_to_wrong_owner_fails() -> None:
    """Context retained under the wrong owner is not semantic preservation."""
    gold = _gold_case("cm59-mixed-amber-24")
    moved = deepcopy(gold)
    moved["sections"][0]["requirements"] = ["Annotate the interval top with a marker."]
    moved["sections"][0]["features"][1]["requirements"] = []
    mask = _fixture("case_dimension_mask.json")
    graded = grade_semantics(gold, gold, moved, mask)
    assert graded["REQUIRED_CONTEXT"]["status"] == "INCORRECT"


def test_annotation_id_rename_passes_but_annotation_omission_fails() -> None:
    """Annotation identity spelling is irrelevant, but removing the feature is not."""
    gold = _gold_case("cm59-mixed-amber-24")
    renamed = deepcopy(gold)
    renamed["sections"][0]["features"][1]["semantic_id"] = "annotation-local"
    omitted = deepcopy(gold)
    omitted["sections"][0]["features"] = [omitted["sections"][0]["features"][0]]
    mask = _fixture("case_dimension_mask.json")
    renamed_grade = grade_semantics(gold, gold, renamed, mask)
    omitted_grade = grade_semantics(gold, gold, omitted, mask)
    assert renamed_grade["ANNOTATION"]["status"] == "CORRECT"
    assert omitted_grade["ANNOTATION"]["status"] == "INCORRECT"


def test_reordered_semantically_distinguishable_sections_fails_section_order() -> None:
    """Order remains meaningful when section signatures differ semantically."""
    gold = _gold_case("cm59-alloc-verde-19")
    reordered = deepcopy(gold)
    reordered["sections"].reverse()
    assert not _dimension_equivalent(
        _semantic_model(reordered), _semantic_model(gold), "SECTION_ORDER"
    )


def test_reference_target_uses_feature_position_not_target_id_spelling() -> None:
    """Target-ID renaming passes while retargeting to another feature fails."""
    gold = {
        "summary": "Reference one scalar feature.",
        "report_work": None,
        "sections": [
            {
                "kind": "log_plot",
                "goal": "Reference one scalar feature.",
                "source_hints": [],
                "features": [
                    {
                        "kind": "curve",
                        "semantic_id": "left",
                        "requirements": [],
                        "constraints": [],
                    },
                    {
                        "kind": "curve",
                        "semantic_id": "right",
                        "requirements": [],
                        "constraints": [],
                    },
                ],
                "reference_intent": {"kind": "reference_track", "target_semantic_id": "left"},
                "requirements": [],
                "constraints": [],
            }
        ],
        "unresolved_requirements": [],
    }
    renamed = deepcopy(gold)
    renamed["sections"][0]["features"][0]["semantic_id"] = "renamed-left"
    renamed["sections"][0]["features"][1]["semantic_id"] = "renamed-right"
    renamed["sections"][0]["reference_intent"]["target_semantic_id"] = "renamed-left"
    retargeted = deepcopy(renamed)
    retargeted["sections"][0]["reference_intent"]["target_semantic_id"] = "renamed-right"
    assert _dimension_equivalent(
        _semantic_model(renamed), _semantic_model(gold), "REFERENCE_TARGET"
    )
    assert not _dimension_equivalent(
        _semantic_model(retargeted), _semantic_model(gold), "REFERENCE_TARGET"
    )


def test_constraint_scope_is_model_owned_except_for_garnet_mask() -> None:
    """The dimension contract records the SR4 exception at case scope."""
    dimensions = _fixture("semantic_dimension_contract.json")
    owners = {row["dimension"]: row["owner"] for row in dimensions["dimensions"]}
    assert owners["CONSTRAINT_SCOPE"] == "MODEL"
    assert dimensions["case_specific_overrides"] == [
        {
            "case_id": "cm59-single-garnet-06",
            "dimension": "CONSTRAINT_SCOPE",
            "owner": "UNRESOLVED_CONTRACT",
            "reason": "SR4 leaves Garnet depth-column ownership unresolved.",
        }
    ]


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
